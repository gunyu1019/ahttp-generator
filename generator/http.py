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
        import_statements = self._create_imports(status_code_mapping, model_names)
        body.extend(import_statements)

        # Create HTTP implementation class
        http_impl_class = self._create_http_impl_class(service_name, status_code_mapping, extracted_data)
        body.append(http_impl_class)

        # Create module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)

        return module

    def _create_imports(self, status_code_mapping: Dict[int, str], model_names: List[str] = None) -> List[ast.stmt]:
        """Create import statements including exception imports."""
        imports = []

        # Import typing components
        typing_imports = ['Annotated']

        # Add additional typing imports based on usage
        typing_imports.extend(['Any', 'Dict'])  # Common types for return values

        # Add Optional if needed
        typing_imports.append('Optional')

        imports.append(self.ast_helper.create_import('typing', typing_imports))

        # Import ahttp_client Session and decorators
        ahttp_imports = ['Session', 'request', 'Body', 'Path', 'Query']

        # Add pydantic_response_model if needed
        if status_code_mapping or (model_names and len(model_names) > 0):
            ahttp_imports.append('pydantic_response_model')

        imports.append(self.ast_helper.create_import('ahttp_client', ahttp_imports))

        # Import models if any exist
        if model_names and len(model_names) > 0:
            imports.append(self.ast_helper.create_relative_import('models', model_names))

        # Import exceptions if any exist
        if status_code_mapping:
            # Get unique exception names
            exception_names = list(set(status_code_mapping.values()))
            imports.append(self.ast_helper.create_relative_import('exceptions', exception_names))

        return imports

    def _create_http_impl_class(self, service_name: str, status_code_mapping: Dict[int, str], extracted_data: Dict[str, Any]) -> ast.ClassDef:
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

        # Add __init__ method
        init_method = self._create_init_method()
        class_body.append(init_method)

        # Add after_request hook method if there are error responses
        if status_code_mapping:
            after_request_method = self._create_after_request_method(status_code_mapping)
            class_body.append(after_request_method)

        # Add API operation methods
        paths = extracted_data.get('paths', [])
        schemas = extracted_data.get('schemas', {})

        for operation in paths:
            method_def = self._create_http_operation_method(operation, schemas)
            class_body.append(method_def)

        # Create class
        return self.ast_helper.create_class_def(
            name=http_class_name,
            bases=['Session'],
            body=class_body
        )

    def _create_http_operation_method(self, operation: Dict[str, Any], schemas: Dict[str, Any]) -> ast.FunctionDef:
        """Create HTTP operation method with full ahttp_client decorators and annotations."""
        operation_id = operation.get('operation_id', 'operation')
        method = operation.get('method', 'GET')
        path = operation.get('path', '/')
        parameters = operation.get('parameters', [])
        request_body = operation.get('request_body')
        response = operation.get('responses', {})

        # Create method arguments
        args = [self.ast_helper.create_arg('self')]

        # Add path parameters with Annotated types
        for param in parameters:
            if param['in'] == 'path':
                param_type, annotation_source = self._map_parameter_type(param)
                original_name = param['name']
                sanitized_name = IdentifierSanitizer.to_snake_case(original_name)

                # Check if we need custom_name
                if IdentifierSanitizer.needs_custom_name(original_name, sanitized_name):
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

        # Add query parameters with Annotated types
        for param in parameters:
            if param['in'] == 'query':
                param_type, annotation_source = self._map_parameter_type(param)
                original_name = param['name']
                sanitized_name = IdentifierSanitizer.to_snake_case(original_name)

                # Handle optional parameters
                if not param.get('required', False):
                    param_type = f'Optional[{param_type}]'

                # Check if we need custom_name
                if IdentifierSanitizer.needs_custom_name(original_name, sanitized_name):
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

        # Add request body parameter with Annotated type
        if request_body:
            body_schema = request_body.get('schema', {})
            body_type = self._get_body_type(body_schema, operation_id, schemas)

            body_arg = self.ast_helper.create_annotated_arg('body', body_type, 'Body')
            args.append(body_arg)

        # Determine return type
        return_type = self._get_return_type(response, schemas)
        return_annotation = self._parse_return_type(return_type) if return_type else None

        # Create decorators list
        decorators = []

        # Add pydantic_response_model decorator if return type is a Pydantic model
        if return_type and self._is_pydantic_model(return_type):
            model_name = self._extract_model_name(return_type)
            if model_name:
                pydantic_decorator = self.ast_helper.create_decorator(
                    'pydantic_response_model',
                    [ast.Name(id=model_name, ctx=ast.Load())]
                )
                decorators.append(pydantic_decorator)

        # Add request decorator
        request_decorator = self.ast_helper.create_decorator(
            'request',
            [
                self.ast_helper.create_string_constant(method),
                self.ast_helper.create_string_constant(path)
            ]
        )
        decorators.append(request_decorator)

        # Create method body (empty return)
        body = [ast.Return(value=None)]

        return self.ast_helper.create_function_def(
            name=operation_id,
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

    def _create_init_method(self) -> ast.FunctionDef:
        """Create __init__ method for HTTPClient."""
        # Create arguments
        args = [
            self.ast_helper.create_arg('self'),
            self.ast_helper.create_arg('base_url', ast.Name(id='str', ctx=ast.Load()))
        ]

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

        return self.ast_helper.create_function_def(
            name='__init__',
            args=args,
            body=body
        )

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

