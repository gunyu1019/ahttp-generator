"""
HTTP implementation generator module.
Generates HTTP implementation class from OpenAPI specification (Implementation Layer).
"""

import ast
from typing import Dict, Any, List

from core.ast_helper import ASTHelper
from core.sanitizer import IdentifierSanitizer
from core.pep8_formatter import PEP8Formatter
from generator.docstring import DocstringGenerator


class HTTPGenerator:
    """Generates HTTP implementation class (Low-Level ahttp_client Session wrapper)."""

    def __init__(self):
        self.ast_helper = ASTHelper()
        self.formatter = PEP8Formatter()
        self.docstring_generator = DocstringGenerator()

    def generate(self, extracted_data: Dict[str, Any], model_names: List[str] = None) -> ast.Module:
        """
        Generate AST module for http.py (Implementation Layer) with PEP 8 compliance.

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
        service_name = extracted_data.get('service_name', 'Api')

        # Create module body
        body = []

        # Add PEP 8 compliant file header
        header = self.formatter.create_file_header()
        body.extend(header)

        # Create HTTP implementation class (temporarily, to analyze typing needs)
        temp_http_class = self._create_http_impl_class(service_name, status_code_mapping, extracted_data, model_names)

        # Create temporary module to analyze typing requirements
        temp_module = ast.Module(body=[temp_http_class], type_ignores=[])
        required_typing = self.formatter.detect_typing_imports(temp_module)

        # Add import statements with detected typing imports
        import_statements = self._create_imports(status_code_mapping, model_names, extracted_data, required_typing)
        sorted_imports = self.formatter.sort_imports(import_statements)
        body.extend(sorted_imports)

        # Add __all__ declaration
        http_class_name = service_name.replace('Service', 'HTTP')
        all_declaration = self.formatter.create_all_declaration([http_class_name])
        body.append(all_declaration)

        # Create HTTP implementation class
        body.append(temp_http_class)

        # Create module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)

        return module

    def _create_imports(self, status_code_mapping: Dict[int, str], model_names: List[str] = None, extracted_data: Dict[str, Any] = None, required_typing: set = None) -> List[ast.stmt]:
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
        ahttp_imports = ['Session', 'request', 'Body', 'Path', 'Query', 'Header']

        # Add RequestCore import if there are injectable authentication schemes
        if injectable_schemes:
            ahttp_imports.append('RequestCore')

        imports.append(self.ast_helper.create_import('ahttp_client', ahttp_imports))

        # Import pydantic_response_model from extension if needed
        if status_code_mapping or (model_names and len(model_names) > 0):
            imports.append(self.ast_helper.create_import('ahttp_client.extension', ['pydantic_response_model']))

        # Import models if any exist
        if model_names and len(model_names) > 0:
            # Separate domain models, success response models, and error response models
            domain_models = []
            response_models = []
            error_models = []

            for model_name in model_names:
                if model_name.endswith('ErrorResponse'):
                    error_models.append(model_name)
                elif model_name.endswith('Response'):
                    response_models.append(model_name)
                else:
                    domain_models.append(model_name)

            # Import domain models from individual files
            if domain_models:
                imports.append(self.ast_helper.create_relative_import('models', domain_models))

            # Import response models from response.py
            if response_models:
                imports.append(self.ast_helper.create_relative_import('models.response', response_models))

            # Import error models from error.py
            if error_models:
                imports.append(self.ast_helper.create_relative_import('models.error', error_models))

        # Import aiohttp response type and endpoint-specific exception classes
        if status_code_mapping:
            imports.append(self.ast_helper.create_import('aiohttp', ['ClientResponse']))
            exception_names = sorted(set(status_code_mapping.values()))
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

        # Add close method for resource cleanup
        close_method = self._create_close_method()
        class_body.append(close_method)

        # Add API operation methods
        paths = extracted_data.get('paths', [])
        schemas = extracted_data.get('schemas', {})

        for operation in paths:
            method_def = self._create_http_operation_method(operation, schemas, model_names, extracted_data)
            class_body.append(method_def)

            operation_error_mapping = self._create_operation_error_mapping(operation, status_code_mapping)
            if operation_error_mapping:
                hook_def = self._create_operation_error_hook(method_def.name, operation_error_mapping)
                class_body.append(hook_def)

        # Create class
        return self.ast_helper.create_class_def(
            name=http_class_name,
            bases=['Session'],
            body=class_body
        )

    def _create_http_operation_method(self, operation: Dict[str, Any], schemas: Dict[str, Any], model_names: List[str] = None, extracted_data: Dict[str, Any] = None) -> ast.FunctionDef:
        """Create HTTP operation method with full ahttp_client decorators and annotations."""
        operation_id = operation.get('operation_id', 'operation')
        method = operation.get('method', 'GET')
        path = operation.get('path', '/')
        parameters = operation.get('parameters', [])
        request_body = operation.get('request_body')
        response = operation.get('responses', {})

        # Get path variables from server configuration
        servers_info = extracted_data.get('servers', {}) if extracted_data else {}
        path_vars = servers_info.get('path_vars', {})

        # Use parser-determined function name (deduplication already applied)
        func_name = operation.get('func_name')
        if not func_name:
            # Fallback if func_name not set (should not happen)
            func_name = IdentifierSanitizer.to_snake_case(operation_id)

        # Create method arguments
        args = [self.ast_helper.create_arg('self')]
        defaults = []  # Track default values for optional parameters
        # Track parameter name mappings for URL template replacement
        param_name_mappings = {}
        used_names = set()  # Track used parameter names to avoid collisions

        # First, add path variables from server configuration (these go first)
        for var_name, var_def in path_vars.items():
            default_value = var_def.get('default', '')
            sanitized_name = IdentifierSanitizer.to_snake_case(var_name)
            
            # Handle name collisions
            if sanitized_name in used_names:
                counter = 1
                original_sanitized = sanitized_name
                while sanitized_name in used_names:
                    sanitized_name = f"{original_sanitized}_{counter}"
                    counter += 1
            used_names.add(sanitized_name)
            
            # Store mapping for URL template replacement
            if var_name != sanitized_name:
                param_name_mappings[var_name] = sanitized_name
            
            # Create argument with default value using Annotated[str, Path]
            args.append(self.ast_helper.create_annotated_arg(sanitized_name, 'str', 'Path'))
            defaults.append(ast.Constant(value=default_value))

        # Add path parameters with Annotated types
        param_index = 0
        for param in parameters:
            if param['in'] == 'path':
                param_type, annotation_source = self._map_parameter_type(param)
                original_name = param.get('name', f'arg_{param_index}')
                sanitized_name = IdentifierSanitizer.to_snake_case(original_name) if original_name != f'arg_{param_index}' else original_name

                # Handle name collisions
                if sanitized_name in used_names:
                    counter = 1
                    original_sanitized = sanitized_name
                    while sanitized_name in used_names:
                        sanitized_name = f"{original_sanitized}_{counter}"
                        counter += 1
                used_names.add(sanitized_name)

                # Store mapping for URL template replacement
                if original_name != sanitized_name:
                    param_name_mappings[original_name] = sanitized_name

                # Always use regular annotation (no custom_name)
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
                is_required = param.get('required', False)
                if not is_required:
                    param_type = f'Optional[{param_type}]'

                # Handle name collisions
                if sanitized_name in used_names:
                    sanitized_name = f"{sanitized_name}_{param_index}"
                used_names.add(sanitized_name)

                # Use custom_name for Query parameters when names differ
                if original_name != sanitized_name:
                    annotated_arg = self.ast_helper.create_annotated_arg_with_custom_name(
                        sanitized_name,
                        param_type,
                        annotation_source,
                        original_name
                    )
                else:
                    annotated_arg = self.ast_helper.create_annotated_arg(
                        sanitized_name,
                        param_type,
                        annotation_source
                    )
                args.append(annotated_arg)

                # Add default value for optional parameters
                if not is_required:
                    defaults.append(ast.Constant(value=None))

                param_index += 1

        # Add header parameters with Annotated types
        for param in parameters:
            if param['in'] == 'header':
                param_type, annotation_source = self._map_parameter_type(param)
                original_name = param.get('name', f'arg_{param_index}')
                sanitized_name = IdentifierSanitizer.to_snake_case(original_name) if original_name != f'arg_{param_index}' else original_name

                # Handle optional parameters
                is_required = param.get('required', False)
                if not is_required:
                    param_type = f'Optional[{param_type}]'

                # Handle name collisions
                if sanitized_name in used_names:
                    sanitized_name = f"{sanitized_name}_{param_index}"
                used_names.add(sanitized_name)

                # Use custom_name for Header parameters when names differ
                if original_name != sanitized_name:
                    annotated_arg = self.ast_helper.create_annotated_arg_with_custom_name(
                        sanitized_name,
                        param_type,
                        annotation_source,
                        original_name
                    )
                else:
                    annotated_arg = self.ast_helper.create_annotated_arg(
                        sanitized_name,
                        param_type,
                        annotation_source
                    )
                args.append(annotated_arg)

                # Add default value for optional parameters
                if not is_required:
                    defaults.append(ast.Constant(value=None))

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

        # Apply URL template parameter name replacements
        updated_path = path
        for original_name, sanitized_name in param_name_mappings.items():
            # Replace {originalName} with {sanitized_name} in URL template
            updated_path = updated_path.replace(f"{{{original_name}}}", f"{{{sanitized_name}}}")

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

        # Add request decorator with updated path (must come before Header.default_header)
        request_decorator = ast.Call(
            func=ast.Name(id='request', ctx=ast.Load()),
            args=[
                self.ast_helper.create_string_constant(method),
                self.ast_helper.create_string_constant(updated_path)  # Use updated path with sanitized parameter names
            ],
            keywords=[
                ast.keyword(arg='directly_response', value=ast.Constant(value=True))
            ]
        )
        decorators.append(request_decorator)

        # Add Accept header decorator if accept_content_type is specified (must come AFTER request decorator)
        accept_content_type = operation.get('accept_content_type')
        if accept_content_type:
            accept_header_decorator = ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id='Header', ctx=ast.Load()),
                    attr='default_header',
                    ctx=ast.Load()
                ),
                args=[
                    ast.Constant(value='Accept'),
                    ast.Constant(value=accept_content_type)
                ],
                keywords=[]
            )
            decorators.append(accept_header_decorator)

        # Create method body with docstring as first element
        body = []

        # Generate docstring from operation information
        docstring_text = self._generate_operation_docstring(operation, parameters, return_type, return_type_info)
        if docstring_text:
            # Use normalized docstring for proper formatting
            normalized_docstring = self.docstring_generator.normalize_docstring(docstring_text)
            docstring_node = ast.Expr(value=ast.Constant(value=normalized_docstring))
            body.append(docstring_node)

        # Add pass statement for decorator-implemented methods
        body.append(ast.Pass())

        return self._create_async_function_def(
            name=func_name,  # Use parser-confirmed unique function name
            args=args,
            body=body,
            decorators=decorators,
            returns=return_annotation,
            defaults=defaults  # Pass defaults for optional parameters
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

        # Create class
        return self.ast_helper.create_class_def(
            name='HTTPClient',
            bases=['Session'],
            body=class_body
        )

    def _create_init_method(self, extracted_data: Dict[str, Any] = None) -> ast.FunctionDef:
        """Create __init__ method for HTTPClient with domain variables and security schemes support."""
        security_schemes = extracted_data.get('security_schemes', []) if extracted_data else []
        servers_info = extracted_data.get('servers', {}) if extracted_data else {}
        domain_vars = servers_info.get('domain_vars', {})
        domain_url_template = servers_info.get('domain_url', 'https://api.example.com')

        # Create arguments - base_url is first, then domain variables, then security schemes
        args = [
            self.ast_helper.create_arg('self'),
            self.ast_helper.create_arg('base_url', 
                ast.Subscript(
                    value=ast.Name(id='Optional', ctx=ast.Load()),
                    slice=ast.Name(id='str', ctx=ast.Load()),
                    ctx=ast.Load()
                )
            )
        ]

        # Add domain variable arguments
        defaults = [ast.Constant(value=None)]  # Default for base_url
        for var_name, var_def in domain_vars.items():
            default_value = var_def.get('default', '')
            args.append(self.ast_helper.create_arg(
                var_name,
                ast.Name(id='str', ctx=ast.Load())
            ))
            defaults.append(ast.Constant(value=default_value))

        # Add security scheme arguments
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
        body = []
        
        # Handle base_url with domain variable formatting
        if domain_vars:
            # if base_url is None:
            #     base_url = domain_url_template.format(**domain_vars)
            format_kwargs = []
            for var_name in domain_vars.keys():
                format_kwargs.append(
                    ast.keyword(
                        arg=var_name,
                        value=ast.Name(id=var_name, ctx=ast.Load())
                    )
                )
            
            if_condition = ast.Compare(
                left=ast.Name(id='base_url', ctx=ast.Load()),
                ops=[ast.Is()],
                comparators=[ast.Constant(value=None)]
            )
            
            format_call = ast.Call(
                func=ast.Attribute(
                    value=ast.Constant(value=domain_url_template),
                    attr='format',
                    ctx=ast.Load()
                ),
                args=[],
                keywords=format_kwargs
            )
            
            base_url_assignment = ast.Assign(
                targets=[ast.Name(id='base_url', ctx=ast.Store())],
                value=format_call
            )
            
            if_stmt = ast.If(
                test=if_condition,
                body=[base_url_assignment],
                orelse=[]
            )
            body.append(if_stmt)
        
        # super().__init__(base_url)
        super_call = ast.Expr(
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
        body.append(super_call)

        # Store authentication parameters as instance variables (PRIVATE for security)
        for scheme in security_schemes:
            arg_name = scheme['arg_name']
            # Create assignment: self.__{arg_name} = {arg_name} (Name Mangling for security)
            assignment = ast.Assign(
                targets=[
                    ast.Attribute(
                        value=ast.Name(id='self', ctx=ast.Load()),
                        attr=f'__{arg_name}',  # Apply name mangling with double underscore
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
                defaults=defaults  # Default values for optional arguments
            ),
            body=body,
            decorator_list=[],
            returns=None
        )

        return ast.fix_missing_locations(func_def)

    def _create_operation_error_mapping(
        self,
        operation: Dict[str, Any],
        status_code_mapping: Dict[int, str]
    ) -> Dict[int, str]:
        """Create endpoint-specific status code to exception mapping."""
        operation_error_responses = operation.get('error_responses', {})
        operation_mapping = {}

        for status_code in operation_error_responses.keys():
            if not status_code.isdigit():
                continue

            status_code_int = int(status_code)
            exception_name = status_code_mapping.get(status_code_int, f'HttpError{status_code}')
            operation_mapping[status_code_int] = exception_name

        return operation_mapping

    def _create_operation_error_hook(
        self,
        method_name: str,
        operation_error_mapping: Dict[int, str]
    ) -> ast.AsyncFunctionDef:
        """Create endpoint-specific after_hook method for error handling."""
        args = [
            self.ast_helper.create_arg('self'),
            self.ast_helper.create_arg('response', ast.Name(id='ClientResponse', ctx=ast.Load()))
        ]

        sorted_codes = sorted(operation_error_mapping.keys())
        if_chain_root = None
        current_if = None

        for status_code in sorted_codes:
            exception_name = operation_error_mapping[status_code]

            condition = ast.Compare(
                left=ast.Attribute(
                    value=ast.Name(id='response', ctx=ast.Load()),
                    attr='status',
                    ctx=ast.Load()
                ),
                ops=[ast.Eq()],
                comparators=[ast.Constant(value=status_code)]
            )

            try_body = [
                ast.Assign(
                    targets=[ast.Name(id='error_data', ctx=ast.Store())],
                    value=ast.Await(
                        value=ast.Call(
                            func=ast.Attribute(
                                value=ast.Name(id='response', ctx=ast.Load()),
                                attr='json',
                                ctx=ast.Load()
                            ),
                            args=[],
                            keywords=[]
                        )
                    )
                ),
                ast.Assign(
                    targets=[ast.Name(id='error_model', ctx=ast.Store())],
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Attribute(
                                value=ast.Attribute(
                                    value=ast.Name(id=exception_name, ctx=ast.Load()),
                                    attr='__init__',
                                    ctx=ast.Load()
                                ),
                                attr='__annotations__',
                                ctx=ast.Load()
                            ),
                            attr='get',
                            ctx=ast.Load()
                        ),
                        args=[ast.Constant(value='response_model')],
                        keywords=[]
                    )
                ),
                ast.Assign(
                    targets=[ast.Name(id='parsed_model', ctx=ast.Store())],
                    value=ast.IfExp(
                        test=ast.Name(id='error_model', ctx=ast.Load()),
                        body=ast.Call(
                            func=ast.Name(id='error_model', ctx=ast.Load()),
                            args=[],
                            keywords=[ast.keyword(arg=None, value=ast.Name(id='error_data', ctx=ast.Load()))]
                        ),
                        orelse=ast.Constant(value=None)
                    )
                )
            ]

            except_body = [
                ast.Assign(
                    targets=[ast.Name(id='parsed_model', ctx=ast.Store())],
                    value=ast.Constant(value=None)
                )
            ]

            parse_try_except = ast.Try(
                body=try_body,
                handlers=[
                    ast.ExceptHandler(
                        type=ast.Name(id='Exception', ctx=ast.Load()),
                        name=None,
                        body=except_body
                    )
                ],
                orelse=[],
                finalbody=[]
            )

            raise_stmt = ast.Raise(
                exc=ast.Call(
                    func=ast.Name(id=exception_name, ctx=ast.Load()),
                    args=[],
                    keywords=[ast.keyword(arg='response_model', value=ast.Name(id='parsed_model', ctx=ast.Load()))]
                ),
                cause=None
            )

            if_node = ast.If(
                test=condition,
                body=[parse_try_except, raise_stmt],
                orelse=[]
            )

            if if_chain_root is None:
                if_chain_root = if_node
                current_if = if_node
            else:
                current_if.orelse = [if_node]
                current_if = if_node

        body = [if_chain_root] if if_chain_root else [ast.Pass()]

        func_def = ast.AsyncFunctionDef(
            name=f'_{method_name}_error_hook',
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
            decorator_list=[
                ast.Attribute(
                    value=ast.Name(id=method_name, ctx=ast.Load()),
                    attr='after_hook',
                    ctx=ast.Load()
                )
            ],
            returns=ast.Constant(value=None)
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

            # Create condition: if self.__{arg_name}: (Private attribute access)
            condition = ast.Attribute(
                value=ast.Name(id='self', ctx=ast.Load()),
                attr=f'__{arg_name}',  # Access private attribute with name mangling
                ctx=ast.Load()
            )

            # Create assignment based on target type
            if target == 'header':
                # request.headers['{key}'] = format_str.format(self.__{arg_name})
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
                                attr=f'__{arg_name}',  # Private attribute access
                                ctx=ast.Load()
                            )
                        ],
                        keywords=[]
                    )
                else:
                    # Direct value
                    value_expr = ast.Attribute(
                        value=ast.Name(id='self', ctx=ast.Load()),
                        attr=f'__{arg_name}',  # Private attribute access
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
                # request.cookies['{key}'] = self.__{arg_name}
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
                        attr=f'__{arg_name}',  # Private attribute access
                        ctx=ast.Load()
                    )
                )

            elif target == 'query':
                # request.params['{key}'] = self.__{arg_name}
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
                        attr=f'__{arg_name}',  # Private attribute access
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

        # Create body: raise ExceptionName()
        body = [
            # raise ExceptionName()
            ast.Raise(
                exc=ast.Call(
                    func=ast.Name(id=exception_name, ctx=ast.Load()),
                    args=[],
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

    def _generate_operation_docstring(self, operation: Dict[str, Any], parameters: List[Dict[str, Any]], return_type: str, return_type_info: Dict[str, Any]) -> str:
        """Generate NumPy style docstring for HTTP operation method."""
        # Extract operation information
        summary = operation.get('summary', '').strip()
        description = operation.get('description', '').strip()
        response_info = operation.get('responses', {})
        response_description = response_info.get('description', 'The response from the API operation.')

        # Prepare parameters for docstring - only include path, query, and body parameters
        docstring_parameters = []

        for param in parameters:
            param_in = param.get('in', 'query')
            if param_in in ['path', 'query', 'header']:
                # Create parameter info for docstring
                param_name = param.get('name', 'unknown')
                param_desc = param.get('description', '').strip()

                # Sanitize parameter name for Python
                from core.sanitizer import IdentifierSanitizer
                sanitized_name = IdentifierSanitizer.to_snake_case(param_name)

                docstring_param = {
                    'name': sanitized_name,
                    'schema': param.get('schema', param),  # Some specs put schema info directly
                    'description': param_desc,
                    'required': param.get('required', True)
                }
                docstring_parameters.append(docstring_param)

        # Add body parameter if exists
        request_body = operation.get('request_body')
        if request_body:
            docstring_parameters.append({
                'name': 'body',
                'schema': {'type': 'object'},
                'description': 'Request body data.',
                'required': request_body.get('required', False)
            })

        # Generate docstring using DocstringGenerator
        return self.docstring_generator.generate_numpy_docstring(
            summary=summary,
            description=description,
            parameters=docstring_parameters,
            return_type=return_type,
            return_description=response_description
        )

    def _create_async_function_def(
        self,
        name: str,
        args: List[ast.arg],
        body: List[ast.stmt],
        decorators: List[ast.expr] = None,
        returns: ast.expr = None,
        defaults: List[ast.expr] = None
    ) -> ast.AsyncFunctionDef:
        """Create an async function definition."""
        if decorators is None:
            decorators = []
        if defaults is None:
            defaults = []

        func_def = ast.AsyncFunctionDef(
            name=name,
            args=ast.arguments(
                posonlyargs=[],
                args=args,
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=defaults  # Use provided defaults instead of empty list
            ),
            body=body,
            decorator_list=decorators,
            returns=returns
        )

        return ast.fix_missing_locations(func_def)

    def _create_close_method(self) -> ast.AsyncFunctionDef:
        """Create async close method for HTTP class."""
        # Create method body: await super().close()
        body = [
            ast.Expr(
                value=ast.Await(
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Call(
                                func=ast.Name(id='super', ctx=ast.Load()),
                                args=[],
                                keywords=[]
                            ),
                            attr='close',
                            ctx=ast.Load()
                        ),
                        args=[],
                        keywords=[]
                    )
                )
            )
        ]

        # Create self argument
        args = [self.ast_helper.create_arg('self')]

        # Create return annotation for None
        returns = ast.Constant(value=None)

        return self._create_async_function_def(
            name='close',
            args=args,
            body=body,
            returns=returns
        )
