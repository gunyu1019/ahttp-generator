"""
HTTP implementation generator module.
Generates HTTP implementation class from OpenAPI specification (Implementation Layer).
"""

import ast
from typing import Dict, Any, List

from core.ast_helper import ASTHelper
from core.sanitizer import IdentifierSanitizer


class HTTPGenerator:
    """Generates HTTP implementation class (Low-Level ahttp_client Session wrapper)."""

    def __init__(self):
        self.ast_helper = ASTHelper()

    def generate(self, extracted_data: Dict[str, Any], model_names: List[str] = None) -> ast.Module:
        """
        Generate AST module for http.py (Implementation Layer).

        Args:
            extracted_data: Extracted OpenAPI data
            model_names: List of generated model names

        Returns:
            AST module for http.py
        """
        if model_names is None:
            model_names = []
        # Get status code mapping for exception handling
        status_code_mapping = extracted_data.get('status_code_mapping', {})
        error_responses = extracted_data.get('error_responses', {})
        service_name = extracted_data.get('service_name', 'Api')

        # Create module body
        body = []

        # Add import statements
        import_statements = self._create_imports(status_code_mapping, model_names, extracted_data)
        body.extend(import_statements)

        # Create HTTP implementation class
        http_impl_class = self._create_http_impl_class(service_name, status_code_mapping, extracted_data, model_names)
        body.append(http_impl_class)

        # Create module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)

        return module

    def _create_imports(self, status_code_mapping: Dict[int, str], model_names: List[str] = None, extracted_data: Dict[str, Any] = None) -> List[ast.stmt]:
        """Create import statements including exception imports."""
        imports = []

        # Import typing components
        typing_imports = ['Annotated']

        # Add additional typing imports based on usage
        typing_imports.extend(['Any', 'Dict'])  # Common types for return values

        # Add Optional if needed
        typing_imports.append('Optional')

        # Add Tuple and check if we need RequestCore for authentication schemes
        security_schemes = extracted_data.get('security_schemes', []) if extracted_data else []
        injectable_schemes = [s for s in security_schemes if s.get('target') in ['header', 'cookie', 'query']]
        if injectable_schemes:
            typing_imports.append('Tuple')

        imports.append(self.ast_helper.create_import('typing', typing_imports))

        # Import ahttp_client Session and decorators
        ahttp_imports = ['Session', 'request', 'Body', 'Path', 'Query']

        # Add RequestCore import if there are injectable authentication schemes
        if injectable_schemes:
            ahttp_imports.append('RequestCore')

        imports.append(self.ast_helper.create_import('ahttp_client', ahttp_imports))

        # Import pydantic_response_model from extension if needed
        if status_code_mapping or (model_names and len(model_names) > 0):
            imports.append(self.ast_helper.create_import('ahttp_client.extension', ['pydantic_response_model']))

        # Import models if any exist
        if model_names and len(model_names) > 0:
            # Separate domain models and response models
            domain_models = []
            response_models = []

            for model_name in model_names:
                if model_name.endswith('Response'):
                    response_models.append(model_name)
                else:
                    domain_models.append(model_name)

            # Import domain models from individual files
            if domain_models:
                imports.append(self.ast_helper.create_relative_import('models', domain_models))

            # Import response models from response.py
            if response_models:
                imports.append(self.ast_helper.create_relative_import('models.response', response_models))

        # Import exceptions if any exist
        if status_code_mapping:
            # Get unique exception names
            exception_names = list(set(status_code_mapping.values()))
            imports.append(self.ast_helper.create_relative_import('exceptions', exception_names))

        return imports

    def _create_http_impl_class(self, service_name: str, status_code_mapping: Dict[int, str], extracted_data: Dict[str, Any], model_names: List[str] = None) -> ast.ClassDef:
        """Create HTTP implementation class definition (Session wrapper)."""
        # Generate HTTP class name: ApiService -> ApiHTTP
        http_class_name = service_name.replace('Service', 'HTTP')

        # Create class body
        class_body = []

        # Add docstring
        docstring = ast.Expr(
            value=ast.Constant(value=f"HTTP implementation class for {service_name} (Low-Level ahttp_client wrapper).")
        )
        class_body.append(docstring)

        # Add __init__ method with security schemes support
        init_method = self._create_init_method(extracted_data)
        class_body.append(init_method)

        # Add before_request hook method if there are any authentication schemes
        security_schemes = extracted_data.get('security_schemes', [])
        # Filter out oauth2_creds as they are stored but not directly injected in before_request
        injectable_schemes = [s for s in security_schemes if s.get('target') in ['header', 'cookie', 'query']]
        if injectable_schemes:
            before_request_method = self._create_before_request_method(injectable_schemes)
            class_body.append(before_request_method)

        # Add after_request hook method if there are error responses
        if status_code_mapping:
            after_request_method = self._create_after_request_method(status_code_mapping)
            class_body.append(after_request_method)

        # Add API operation methods
        paths = extracted_data.get('paths', [])
        schemas = extracted_data.get('schemas', {})

        for operation in paths:
            method_def = self._create_http_operation_method(operation, schemas, model_names)
            class_body.append(method_def)

        # Create class
        return self.ast_helper.create_class_def(
            name=http_class_name,
            bases=['Session'],
            body=class_body
        )

    def _create_http_operation_method(self, operation: Dict[str, Any], schemas: Dict[str, Any], model_names: List[str] = None) -> ast.FunctionDef:
        """Create HTTP operation method with full ahttp_client decorators and annotations."""
        operation_id = operation.get('operation_id', 'operation')
        method = operation.get('method', 'GET')
        path = operation.get('path', '/')
        parameters = operation.get('parameters', [])
        request_body = operation.get('request_body')
        response = operation.get('responses', {})

        # Use parser-determined function name (deduplication already applied)
        func_name = operation.get('func_name')
        if not func_name:
            # Fallback if func_name not set (should not happen)
            func_name = IdentifierSanitizer.to_snake_case(operation_id)

        # Create method arguments
        args = [self.ast_helper.create_arg('self')]
        used_names = set()  # Track used parameter names to avoid collisions

        # Add path parameters with Annotated types
        param_index = 0
        for param in parameters:
            if param['in'] == 'path':
                param_type, annotation_source = self._map_parameter_type(param)
                original_name = param.get('name', f'arg_{param_index}')
                sanitized_name = IdentifierSanitizer.to_snake_case(original_name) if original_name != f'arg_{param_index}' else original_name

                # Handle name collisions
                if sanitized_name in used_names:
                    sanitized_name = f"{sanitized_name}_{param_index}"
                used_names.add(sanitized_name)

                # Check if we need custom_name
                if original_name != f'arg_{param_index}' and IdentifierSanitizer.needs_custom_name(original_name, sanitized_name):
                    # Use custom_name annotation
                    annotated_arg = self.ast_helper.create_annotated_arg_with_custom_name(
                        sanitized_name,
                        param_type,
                        annotation_source,
                        original_name
                    )
                else:
                    # Use regular annotation
                    annotated_arg = self.ast_helper.create_annotated_arg(
                        sanitized_name,
                        param_type,
                        annotation_source
                    )
                args.append(annotated_arg)
                param_index += 1

        # Add query parameters with Annotated types
        for param in parameters:
            if param['in'] == 'query':
                param_type, annotation_source = self._map_parameter_type(param)
                original_name = param.get('name', f'arg_{param_index}')
                sanitized_name = IdentifierSanitizer.to_snake_case(original_name) if original_name != f'arg_{param_index}' else original_name

                # Handle optional parameters
                if not param.get('required', False):
                    param_type = f'Optional[{param_type}]'

                # Handle name collisions
                if sanitized_name in used_names:
                    sanitized_name = f"{sanitized_name}_{param_index}"
                used_names.add(sanitized_name)

                # Check if we need custom_name
                if original_name != f'arg_{param_index}' and IdentifierSanitizer.needs_custom_name(original_name, sanitized_name):
                    # Use custom_name annotation
                    annotated_arg = self.ast_helper.create_annotated_arg_with_custom_name(
                        sanitized_name,
                        param_type,
                        annotation_source,
                        original_name
                    )
                else:
                    # Use regular annotation
                    annotated_arg = self.ast_helper.create_annotated_arg(
                        sanitized_name,
                        param_type,
                        annotation_source
                    )
                args.append(annotated_arg)
                param_index += 1

        # Add request body parameter with Annotated type
        if request_body:
            body_schema = request_body.get('schema', {})
            body_type = self._get_body_type(body_schema, operation_id, schemas)

            body_arg = self.ast_helper.create_annotated_arg('body', body_type, 'Body')
            args.append(body_arg)

        # Determine return type based on response content type
        return_type_info = self._analyze_return_type(response, schemas, model_names)
        return_type = return_type_info.get('type', 'Dict[str, Any]')
        is_pydantic_model = return_type_info.get('is_pydantic_model', False)

        return_annotation = self._parse_return_type(return_type) if return_type else None

        # Create decorators list
        decorators = []

        # Add pydantic_response_model decorator ONLY for Pydantic models
        if is_pydantic_model and return_type_info.get('model_name'):
            model_name = return_type_info['model_name']
            pydantic_decorator = self.ast_helper.create_decorator(
                'pydantic_response_model',
                [ast.Name(id=model_name, ctx=ast.Load())]
            )
            decorators.append(pydantic_decorator)

        # Add request decorator
        request_decorator = ast.Call(
            func=ast.Name(id='request', ctx=ast.Load()),
            args=[
                self.ast_helper.create_string_constant(method),
                self.ast_helper.create_string_constant(path)
            ],
            keywords=[
                ast.keyword(arg='directly_response', value=ast.Constant(value=True))
            ]
        )
        decorators.append(request_decorator)

        # Create method body (pass statement for decorator-implemented methods)
        body = [ast.Pass()]

        return self._create_async_function_def(
            name=func_name,  # Use parser-confirmed unique function name
            args=args,
            body=body,
            decorators=decorators,
            returns=return_annotation
        )

    def _create_http_client_class(self, status_code_mapping: Dict[int, str]) -> ast.ClassDef:
        """Create HTTPClient class definition."""
        # Create class body
        class_body = []

        # Add docstring
        docstring = ast.Expr(
            value=ast.Constant(value="Base HTTP client class for API communication.")
        )
        class_body.append(docstring)

        # Add __init__ method
        init_method = self._create_init_method()
        class_body.append(init_method)

        # Add after_request hook method if there are error responses
        if status_code_mapping:
            after_request_method = self._create_after_request_method(status_code_mapping)
            class_body.append(after_request_method)

        # Create class
        return self.ast_helper.create_class_def(
            name='HTTPClient',
            bases=['Session'],
            body=class_body
        )

    def _create_init_method(self, extracted_data: Dict[str, Any] = None) -> ast.FunctionDef:
        """Create __init__ method for HTTPClient with optional security schemes support."""
        security_schemes = extracted_data.get('security_schemes', []) if extracted_data else []

        # Create arguments - base_url is always first, then security scheme arguments
        args = [
            self.ast_helper.create_arg('self'),
            self.ast_helper.create_arg('base_url', ast.Name(id='str', ctx=ast.Load()))
        ]

        # Add security scheme arguments
        defaults = []
        for scheme in security_schemes:
            arg_name = scheme['arg_name']
            args.append(self.ast_helper.create_arg(
                arg_name,
                ast.Subscript(
                    value=ast.Name(id='Optional', ctx=ast.Load()),
                    slice=ast.Name(id='str', ctx=ast.Load()),
                    ctx=ast.Load()
                )
            ))
            defaults.append(ast.Constant(value=None))

        # Create method body
        body = [
            # super().__init__(base_url)
            ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Call(
                            func=ast.Name(id='super', ctx=ast.Load()),
                            args=[],
                            keywords=[]
                        ),
                        attr='__init__',
                        ctx=ast.Load()
                    ),
                    args=[ast.Name(id='base_url', ctx=ast.Load())],
                    keywords=[]
                )
            )
        ]

        # Store authentication parameters as instance variables (not directly in headers/cookies)
        for scheme in security_schemes:
            arg_name = scheme['arg_name']
            # Create assignment: self.{arg_name} = {arg_name}
            assignment = ast.Assign(
                targets=[
                    ast.Attribute(
                        value=ast.Name(id='self', ctx=ast.Load()),
                        attr=arg_name,
                        ctx=ast.Store()
                    )
                ],
                value=ast.Name(id=arg_name, ctx=ast.Load())
            )
            body.append(assignment)

        # Create function definition with defaults support
        func_def = ast.FunctionDef(
            name='__init__',
            args=ast.arguments(
                posonlyargs=[],
                args=args,
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=defaults  # Default values for optional security arguments
            ),
            body=body,
            decorator_list=[],
            returns=None
        )

        return ast.fix_missing_locations(func_def)

    def _create_after_request_method(self, status_code_mapping: Dict[int, str]) -> ast.AsyncFunctionDef:
        """Create after_request hook method for automatic exception handling."""
        # Create arguments: self, response, context
        args = [
            self.ast_helper.create_arg('self'),
            self.ast_helper.create_arg('response'),
            self.ast_helper.create_arg('context')
        ]

        # Create method body
        body = []

        # Sort status codes for consistent ordering
        sorted_status_codes = sorted(status_code_mapping.keys())

        # Create if/elif chain for status code checking
        if sorted_status_codes:
            first_status = sorted_status_codes[0]
            remaining_status_codes = sorted_status_codes[1:]

            # Create the first if statement
            if_stmt = self._create_status_check_if(first_status, status_code_mapping[first_status], remaining_status_codes, status_code_mapping)
            body.append(if_stmt)

        # Add return response statement
        return_stmt = ast.Return(value=ast.Name(id='response', ctx=ast.Load()))
        body.append(return_stmt)

        # Create async function definition
        func_def = ast.AsyncFunctionDef(
            name='after_request',
            args=ast.arguments(
                posonlyargs=[],
                args=args,
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[]
            ),
            body=body,
            decorator_list=[],
            returns=None
        )

        return ast.fix_missing_locations(func_def)

    def _create_before_request_method(self, security_schemes: List[Dict[str, Any]]) -> ast.AsyncFunctionDef:
        """Create before_request hook method for all authentication types (header, cookie, query)."""
        # Create arguments: self, request: RequestCore, path: str
        args = [
            self.ast_helper.create_arg('self'),
            self.ast_helper.create_arg('request', ast.Name(id='RequestCore', ctx=ast.Load())),
            self.ast_helper.create_arg('path', ast.Name(id='str', ctx=ast.Load()))
        ]

        # Create method body
        body = []

        # Process each security scheme and add appropriate logic
        for scheme in security_schemes:
            arg_name = scheme['arg_name']
            target = scheme['target']
            key = scheme['key']
            format_str = scheme.get('format', '{}')

            # Create condition: if self.{arg_name}:
            condition = ast.Attribute(
                value=ast.Name(id='self', ctx=ast.Load()),
                attr=arg_name,
                ctx=ast.Load()
            )

            # Create assignment based on target type
            if target == 'header':
                # request.headers['{key}'] = format_str.format(self.{arg_name})
                if '{}' in format_str and format_str != '{}':
                    # Format string like "Bearer {}"
                    value_expr = ast.Call(
                        func=ast.Attribute(
                            value=ast.Constant(value=format_str),
                            attr='format',
                            ctx=ast.Load()
                        ),
                        args=[
                            ast.Attribute(
                                value=ast.Name(id='self', ctx=ast.Load()),
                                attr=arg_name,
                                ctx=ast.Load()
                            )
                        ],
                        keywords=[]
                    )
                else:
                    # Direct value
                    value_expr = ast.Attribute(
                        value=ast.Name(id='self', ctx=ast.Load()),
                        attr=arg_name,
                        ctx=ast.Load()
                    )

                assignment = ast.Assign(
                    targets=[
                        ast.Subscript(
                            value=ast.Attribute(
                                value=ast.Name(id='request', ctx=ast.Load()),
                                attr='headers',
                                ctx=ast.Load()
                            ),
                            slice=ast.Constant(value=key),
                            ctx=ast.Store()
                        )
                    ],
                    value=value_expr
                )

            elif target == 'cookie':
                # request.cookies['{key}'] = self.{arg_name}
                assignment = ast.Assign(
                    targets=[
                        ast.Subscript(
                            value=ast.Attribute(
                                value=ast.Name(id='request', ctx=ast.Load()),
                                attr='cookies',
                                ctx=ast.Load()
                            ),
                            slice=ast.Constant(value=key),
                            ctx=ast.Store()
                        )
                    ],
                    value=ast.Attribute(
                        value=ast.Name(id='self', ctx=ast.Load()),
                        attr=arg_name,
                        ctx=ast.Load()
                    )
                )

            elif target == 'query':
                # request.params['{key}'] = self.{arg_name}
                assignment = ast.Assign(
                    targets=[
                        ast.Subscript(
                            value=ast.Attribute(
                                value=ast.Name(id='request', ctx=ast.Load()),
                                attr='params',
                                ctx=ast.Load()
                            ),
                            slice=ast.Constant(value=key),
                            ctx=ast.Store()
                        )
                    ],
                    value=ast.Attribute(
                        value=ast.Name(id='self', ctx=ast.Load()),
                        attr=arg_name,
                        ctx=ast.Load()
                    )
                )

            else:
                # Skip unsupported targets (oauth2 credentials are stored but not injected here)
                continue

            # Add if statement to body
            if_stmt = ast.If(
                test=condition,
                body=[assignment],
                orelse=[]
            )
            body.append(if_stmt)

        # Add return statement: return request, path
        return_stmt = ast.Return(
            value=ast.Tuple(
                elts=[
                    ast.Name(id='request', ctx=ast.Load()),
                    ast.Name(id='path', ctx=ast.Load())
                ],
                ctx=ast.Load()
            )
        )
        body.append(return_stmt)

        # Create async function definition with return type annotation
        func_def = ast.AsyncFunctionDef(
            name='before_request',
            args=ast.arguments(
                posonlyargs=[],
                args=args,
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[]
            ),
            body=body,
            decorator_list=[],
            returns=ast.Subscript(
                value=ast.Name(id='Tuple', ctx=ast.Load()),
                slice=ast.Tuple(
                    elts=[
                        ast.Name(id='RequestCore', ctx=ast.Load()),
                        ast.Name(id='str', ctx=ast.Load())
                    ],
                    ctx=ast.Load()
                ),
                ctx=ast.Load()
            )
        )

        return ast.fix_missing_locations(func_def)

    def _create_status_check_if(self, status_code: int, exception_name: str, remaining_codes: List[int], mapping: Dict[int, str]) -> ast.If:
        """Create if/elif chain for status code checking."""
        # Create condition: response.status == status_code
        test = ast.Compare(
            left=ast.Attribute(
                value=ast.Name(id='response', ctx=ast.Load()),
                attr='status',
                ctx=ast.Load()
            ),
            ops=[ast.Eq()],
            comparators=[ast.Constant(value=status_code)]
        )

        # Create body: text = await response.text(); raise ExceptionName(text)
        body = [
            # text = await response.text()
            ast.Assign(
                targets=[ast.Name(id='text', ctx=ast.Store())],
                value=ast.Await(
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id='response', ctx=ast.Load()),
                            attr='text',
                            ctx=ast.Load()
                        ),
                        args=[],
                        keywords=[]
                    )
                )
            ),
            # raise ExceptionName(text)
            ast.Raise(
                exc=ast.Call(
                    func=ast.Name(id=exception_name, ctx=ast.Load()),
                    args=[ast.Name(id='text', ctx=ast.Load())],
                    keywords=[]
                ),
                cause=None
            )
        ]

        # Create orelse (elif chain) for remaining status codes
        orelse = []
        if remaining_codes:
            next_status = remaining_codes[0]
            next_remaining = remaining_codes[1:]
            orelse = [self._create_status_check_if(next_status, mapping[next_status], next_remaining, mapping)]

        if_stmt = ast.If(test=test, body=body, orelse=orelse)
        return ast.fix_missing_locations(if_stmt)

    def _map_parameter_type(self, param: Dict[str, Any]) -> tuple:
        """Map parameter to Python type and annotation source."""
        # Inline type mapping to avoid circular imports
        schema = param.get('schema', param)
        param_type = schema.get('type', 'string')
        param_in = param.get('in', 'query')

        # Map the basic type
        type_mapping = {
            'string': 'str',
            'integer': 'int',
            'number': 'float',
            'boolean': 'bool'
        }
        python_type = type_mapping.get(param_type, 'str')

        # Map the annotation source
        annotation_mapping = {
            'path': 'Path',
            'query': 'Query',
            'header': 'Header',
            'cookie': 'Cookie'
        }
        annotation_source = annotation_mapping.get(param_in, 'Query')

        return python_type, annotation_source

    def _get_body_type(self, body_schema: Dict[str, Any], operation_id: str, schemas: Dict[str, Any]) -> str:
        """Get body type for request body parameter."""
        # Check if it's a schema reference
        if '$ref' in body_schema:
            # Use the referenced model directly
            ref_path = body_schema['$ref']
            if ref_path.startswith('#/components/schemas/'):
                model_name = ref_path.split('/')[-1]
                # Simple sanitization
                sanitized = ''.join(word.capitalize() for word in model_name.split('_'))
                return sanitized
        elif 'properties' in body_schema:
            # Use generated request model
            return self._generate_request_model_name(operation_id)

        return 'Dict[str, Any]'

    def _get_return_type(self, response: Dict[str, Any], schemas: Dict[str, Any]) -> str:
        """Determine return type from response schema."""
        response_schema = response.get('schema', {})
        if not response_schema:
            return 'Dict[str, Any]'

        # Simple type mapping without external dependencies
        if '$ref' in response_schema:
            ref_path = response_schema['$ref']
            if ref_path.startswith('#/components/schemas/'):
                model_name = ref_path.split('/')[-1]
                # Simple sanitization
                return ''.join(word.capitalize() for word in model_name.split('_'))
        elif response_schema.get('type') == 'array':
            items = response_schema.get('items', {})
            if '$ref' in items:
                ref_path = items['$ref']
                if ref_path.startswith('#/components/schemas/'):
                    model_name = ref_path.split('/')[-1]
                    sanitized = ''.join(word.capitalize() for word in model_name.split('_'))
                    return f'List[{sanitized}]'
            return 'List[Dict[str, Any]]'

        return 'Dict[str, Any]'

    def _is_pydantic_model(self, type_str: str) -> bool:
        """Check if the type string represents a Pydantic model."""
        if not type_str:
            return False

        # Extract base model name
        model_name = self._extract_model_name(type_str)
        if not model_name:
            return False

        # Simple heuristic: if it starts with uppercase, it's likely a model
        return model_name[0].isupper() and not model_name in ['Dict', 'List', 'Any', 'Optional']

    def _is_pydantic_model_in_list(self, type_str: str, model_names: List[str]) -> bool:
        """Check if the type string represents a Pydantic model in our generated models list."""
        if not type_str or not model_names:
            return False

        # Extract base model name
        model_name = self._extract_model_name(type_str)
        if not model_name:
            return False

        # Check if the model name is in our generated models list
        return model_name in model_names

    def _analyze_return_type(self, response: Dict[str, Any], schemas: Dict[str, Any], model_names: List[str] = None) -> Dict[str, Any]:
        """Analyze response to determine return type based on content type."""
        if not response:
            return {'type': 'Dict[str, Any]', 'is_pydantic_model': False}

        # Get response type info from parser
        response_type = response.get('response_type', 'json')
        python_type = response.get('python_type', 'Dict[str, Any]')
        model_name = response.get('model_name')

        # Case 1: Text response
        if response_type == 'text':
            return {
                'type': 'str',
                'is_pydantic_model': False
            }

        # Case 2: Binary response
        elif response_type == 'binary':
            return {
                'type': 'bytes',
                'is_pydantic_model': False
            }

        # Case 3: JSON response
        elif response_type == 'json':
            # Check if it's a Pydantic model
            if model_name and model_names and model_name in model_names:
                return {
                    'type': python_type,
                    'is_pydantic_model': True,
                    'model_name': model_name
                }
            else:
                # Check if it's a List of models
                if python_type.startswith('List[') and python_type.endswith(']'):
                    inner_type = python_type[5:-1]  # Extract inner type from List[X]
                    if model_names and inner_type in model_names:
                        return {
                            'type': python_type,
                            'is_pydantic_model': True,
                            'model_name': inner_type
                        }

                # Fallback to Dict for JSON
                return {
                    'type': 'Dict[str, Any]',
                    'is_pydantic_model': False
                }

        # Fallback
        return {
            'type': 'Dict[str, Any]',
            'is_pydantic_model': False
        }

    def _extract_model_name(self, type_str: str) -> str:
        """Extract model name from type string (handles List[Model] -> Model)."""
        if not type_str:
            return None

        # Handle List[ModelName] -> ModelName
        if type_str.startswith('List[') and type_str.endswith(']'):
            return type_str[5:-1]  # Remove 'List[' and ']'

        # Handle simple model name
        if type_str and type_str[0].isupper():
            return type_str

        return None

    def _parse_return_type(self, type_str: str) -> ast.expr:
        """Parse return type string into AST expression."""
        if '[' in type_str:
            # Handle generic types
            base_type, rest = type_str.split('[', 1)
            inner_types = rest.rstrip(']')

            if ',' in inner_types:
                # Handle Dict[str, Any]
                type_parts = [part.strip() for part in inner_types.split(',')]
                inner_ast = ast.Tuple(
                    elts=[self._parse_return_type(part) for part in type_parts],
                    ctx=ast.Load()
                )
            else:
                # Handle List[str]
                inner_ast = self._parse_return_type(inner_types)

            return ast.Subscript(
                value=ast.Name(id=base_type, ctx=ast.Load()),
                slice=inner_ast,
                ctx=ast.Load()
            )
        else:
            # Simple type
            return ast.Name(id=type_str, ctx=ast.Load())

    def _generate_request_model_name(self, operation_id: str) -> str:
        """Generate request model name from operation ID."""
        import re

        # Split by underscores or camelCase boundaries
        words = re.findall(r'[A-Z]*[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)|[A-Z]+$|[0-9]+', operation_id)
        if not words:
            words = operation_id.split('_')

        # Capitalize each word
        pascal_case = ''.join(word.capitalize() for word in words if word)

        # Add Request suffix if not present
        if not pascal_case.endswith('Request'):
            pascal_case += 'Request'

        return pascal_case

    def _create_async_function_def(
        self,
        name: str,
        args: List[ast.arg],
        body: List[ast.stmt],
        decorators: List[ast.expr] = None,
        returns: ast.expr = None
    ) -> ast.AsyncFunctionDef:
        """Create an async function definition."""
        if decorators is None:
            decorators = []

        func_def = ast.AsyncFunctionDef(
            name=name,
            args=ast.arguments(
                posonlyargs=[],
                args=args,
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[]
            ),
            body=body,
            decorator_list=decorators,
            returns=returns
        )

        return ast.fix_missing_locations(func_def)

