"""
Client facade generator module.
Generates client facade class from OpenAPI specification (Facade Layer).
"""

import ast
from typing import Dict, Any, List

from core.ast_helper import ASTHelper
from core.sanitizer import IdentifierSanitizer


class ClientGenerator:
    """Generates client facade class (High-Level user interface)."""

    def __init__(self):
        self.ast_helper = ASTHelper()

    def generate(self, extracted_data: Dict[str, Any], model_names: List[str]) -> ast.Module:
        """
        Generate AST module for client.py (Facade Layer).
        """
        service_name = extracted_data.get('service_name', 'ApiService')
        servers = extracted_data.get('servers', ['https://api.example.com'])
        base_url = servers[0]

        # Create module body
        body = []

        # Add import statements
        import_statements = self._create_imports(service_name, model_names, extracted_data)
        body.extend(import_statements)

        # Create client facade class
        client_class = self._create_client_class(service_name, base_url, extracted_data)
        body.append(client_class)

        # Create module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)

        return module

    def _create_imports(self, service_name: str, model_names: List[str], extracted_data: Dict[str, Any]) -> List[ast.stmt]:
        """Create import statements for facade layer with response model separation."""
        imports = []

        # Import HTTP implementation class
        http_class_name = service_name.replace('Service', 'HTTP')
        imports.append(self.ast_helper.create_relative_import('http', [http_class_name]))

        # Collect all return types from operations to determine needed imports
        paths = extracted_data.get('paths', [])
        used_domain_models = set()
        used_response_models = set()

        for operation in paths:
            response_info = operation.get('responses', {})
            return_type_info = self._analyze_client_return_type(response_info)
            model_name = return_type_info.get('model_name')

            if model_name:
                if model_name.endswith('Response'):
                    used_response_models.add(model_name)
                else:
                    used_domain_models.add(model_name)

        # Import domain models that are used
        if used_domain_models:
            imports.append(self.ast_helper.create_relative_import('models', sorted(used_domain_models)))

        # Import response models that are used
        if used_response_models:
            imports.append(self.ast_helper.create_relative_import('models.response', sorted(used_response_models)))

        return imports

    def _create_client_class(self, service_name: str, base_url: str, extracted_data: Dict[str, Any]) -> ast.ClassDef:
        """Create client facade class definition."""
        # Generate client class name: ApiService -> ApiClient
        client_class_name = service_name.replace('Service', 'Client')
        http_class_name = service_name.replace('Service', 'HTTP')

        # Create class body
        class_body = []

        # Add docstring
        docstring = ast.Expr(
            value=ast.Constant(value=f"High-level client facade for {service_name} (User Interface Layer).")
        )
        class_body.append(docstring)

        # Add __init__ method
        init_method = self._create_facade_init_method(http_class_name, base_url)
        class_body.append(init_method)

        # Add API operation methods (facade methods)
        paths = extracted_data.get('paths', [])

        for operation in paths:
            method_def = self._create_facade_operation_method(operation)
            class_body.append(method_def)

        # Create class (no inheritance - standalone class)
        return self.ast_helper.create_class_def(
            name=client_class_name,
            bases=[],  # No inheritance
            body=class_body
        )

    def _create_facade_init_method(self, http_class_name: str, base_url: str) -> ast.FunctionDef:
        """Create __init__ method for facade class with composition."""
        # Create arguments: self, base_url with default value
        args = [
            self.ast_helper.create_arg('self'),
            self.ast_helper.create_arg('base_url', ast.Name(id='str', ctx=ast.Load()))
        ]

        # Set default value for base_url
        defaults = [self.ast_helper.create_string_constant(base_url)]

        # Create method body: self.http = HTTPClass(base_url)
        body = [
            ast.Assign(
                targets=[ast.Attribute(
                    value=ast.Name(id='self', ctx=ast.Load()),
                    attr='http',
                    ctx=ast.Store()
                )],
                value=ast.Call(
                    func=ast.Name(id=http_class_name, ctx=ast.Load()),
                    args=[ast.Name(id='base_url', ctx=ast.Load())],
                    keywords=[]
                )
            )
        ]

        # Create function definition with default values
        func_def = ast.FunctionDef(
            name='__init__',
            args=ast.arguments(
                posonlyargs=[],
                args=args,
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=defaults
            ),
            body=body,
            decorator_list=[],
            returns=None
        )

        return ast.fix_missing_locations(func_def)

    def _create_facade_operation_method(self, operation: Dict[str, Any]) -> ast.FunctionDef:
        """Create facade operation method that delegates to HTTP implementation with correct return types."""
        operation_id = operation.get('operation_id', 'operation')
        parameters = operation.get('parameters', [])
        request_body = operation.get('request_body')
        response_info = operation.get('responses', {})

        # Use parser-determined function name (deduplication already applied)
        func_name = operation.get('func_name')
        if not func_name:
            # Fallback if func_name not set (should not happen)
            func_name = IdentifierSanitizer.to_snake_case(operation_id)

        # Create method arguments (clean interface without Annotated)
        args = [self.ast_helper.create_arg('self')]
        call_keywords = []  # For delegation call

        # Add path parameters with friendly names
        param_index = 0
        for param in parameters:
            if param['in'] == 'path':
                original_name = param.get('name', f'arg_{param_index}')
                sanitized_name = IdentifierSanitizer.to_snake_case(original_name) if original_name != f'arg_{param_index}' else original_name

                # Use more friendly names for common cases
                if original_name == 'target_id':
                    friendly_name = 'target_channel_id'
                else:
                    friendly_name = sanitized_name

                arg = self.ast_helper.create_arg(friendly_name, ast.Name(id='str', ctx=ast.Load()))
                args.append(arg)
                
                # Map back to sanitized parameter name for HTTP layer
                call_keywords.append(ast.keyword(
                    arg=sanitized_name,  # HTTP layer uses sanitized name for parameters
                    value=ast.Name(id=friendly_name, ctx=ast.Load())
                ))
                param_index += 1

        # Add query parameters
        for param in parameters:
            if param['in'] == 'query':
                original_name = param.get('name', f'arg_{param_index}')
                sanitized_name = IdentifierSanitizer.to_snake_case(original_name) if original_name != f'arg_{param_index}' else original_name

                arg = self.ast_helper.create_arg(sanitized_name, ast.Name(id='str', ctx=ast.Load()))
                args.append(arg)
                
                # Add to delegation call using sanitized name
                call_keywords.append(ast.keyword(
                    arg=sanitized_name,  # HTTP layer uses sanitized name for parameters
                    value=ast.Name(id=sanitized_name, ctx=ast.Load())
                ))
                param_index += 1

        # Add request body parameter
        if request_body:
            # Use friendly name for body parameter
            body_arg = self.ast_helper.create_arg('request_body', ast.Name(id='dict', ctx=ast.Load()))
            args.append(body_arg)
            
            # Add to delegation call (HTTP layer expects 'body')
            call_keywords.append(ast.keyword(
                arg='body',  # HTTP layer expects 'body'
                value=ast.Name(id='request_body', ctx=ast.Load())
            ))

        # Analyze return type to match HTTP layer exactly
        return_type_info = self._analyze_client_return_type(response_info)
        return_annotation = return_type_info.get('annotation')

        # Create delegation call with await: return await self.http.sanitized_method_name(**kwargs)
        delegation_call = ast.Await(
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Attribute(
                        value=ast.Name(id='self', ctx=ast.Load()),
                        attr='http',
                        ctx=ast.Load()
                    ),
                    attr=func_name,  # Use parser-confirmed unique function name
                    ctx=ast.Load()
                ),
                args=[],  # No positional args, all are keywords
                keywords=call_keywords
            )
        )

        # Create method body
        body = [ast.Return(value=delegation_call)]

        return self._create_async_function_def(
            name=func_name,  # Use parser-confirmed unique function name
            args=args,
            body=body,
            decorators=[],  # No decorators in facade layer
            returns=return_annotation
        )

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

    def _analyze_client_return_type(self, response_info: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze response info to determine correct return type for client methods."""
        if not response_info:
            return {
                'annotation': ast.Name(id='dict', ctx=ast.Load()),
                'model_name': None
            }

        response_type = response_info.get('response_type', 'json')
        python_type = response_info.get('python_type', 'dict')
        model_name = response_info.get('model_name')

        # Case 1: Text response
        if response_type == 'text':
            return {
                'annotation': ast.Name(id='str', ctx=ast.Load()),
                'model_name': None
            }

        # Case 2: Binary response
        elif response_type == 'binary':
            return {
                'annotation': ast.Name(id='bytes', ctx=ast.Load()),
                'model_name': None
            }

        # Case 3: JSON response with Pydantic model
        elif response_type == 'json' and model_name:
            # Parse the return type to create appropriate AST annotation
            return_annotation = self._create_type_annotation(python_type)
            return {
                'annotation': return_annotation,
                'model_name': model_name
            }

        # Fallback to dict
        return {
            'annotation': ast.Name(id='dict', ctx=ast.Load()),
            'model_name': None
        }

    def _create_type_annotation(self, type_str: str) -> ast.expr:
        """Create AST type annotation from type string."""
        if not type_str:
            return ast.Name(id='dict', ctx=ast.Load())

        # Handle List[Model] types
        if type_str.startswith('List[') and type_str.endswith(']'):
            inner_type = type_str[5:-1]  # Extract Model from List[Model]
            return ast.Subscript(
                value=ast.Name(id='List', ctx=ast.Load()),
                slice=ast.Name(id=inner_type, ctx=ast.Load()),
                ctx=ast.Load()
            )

        # Handle simple model names
        elif type_str and type_str[0].isupper():  # Looks like a model name
            return ast.Name(id=type_str, ctx=ast.Load())

        # Handle basic types
        elif type_str in ['str', 'int', 'float', 'bool', 'dict', 'bytes']:
            return ast.Name(id=type_str, ctx=ast.Load())

        # Fallback
        return ast.Name(id='dict', ctx=ast.Load())
