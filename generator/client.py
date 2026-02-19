"""
Client facade generator module.
Generates client facade class from OpenAPI specification (Facade Layer).
"""

import ast
from typing import Dict, Any, List, Set

from core.ast_helper import ASTHelper
from core.sanitizer import IdentifierSanitizer
from core.pep8_formatter import PEP8Formatter
from generator.docstring import DocstringGenerator


class ClientGenerator:
    """Generates client facade class (High-Level user interface)."""

    def __init__(self):
        self.ast_helper = ASTHelper()
        self.formatter = PEP8Formatter()
        self.docstring_generator = DocstringGenerator()

    def generate(self, extracted_data: Dict[str, Any], model_names: List[str]) -> ast.Module:
        """
        Generate AST module for client.py (Facade Layer) with PEP 8 compliance.
        """
        service_name = extracted_data.get('service_name', 'ApiService')
        servers_info = extracted_data.get('servers', {'base_url': 'https://api.example.com', 'base_path': ''})
        base_url = servers_info.get('base_url', 'https://api.example.com')

        # Create module body
        body = []

        # Add PEP 8 compliant file header
        header = self.formatter.create_file_header()
        body.extend(header)

        # Create client facade class (temporarily, to analyze typing needs)
        temp_client_class = self._create_client_class(service_name, base_url, extracted_data)

        # Create temporary module to analyze typing requirements
        temp_module = ast.Module(body=[temp_client_class], type_ignores=[])
        required_typing = self.formatter.detect_typing_imports(temp_module)

        # Add import statements with detected typing imports
        import_statements = self._create_imports(service_name, model_names, extracted_data, required_typing)
        sorted_imports = self.formatter.sort_imports(import_statements)
        body.extend(sorted_imports)

        # Add __all__ declaration
        client_class_name = service_name.replace('Service', 'Client')
        all_declaration = self.formatter.create_all_declaration([client_class_name])
        body.append(all_declaration)

        # Add the actual client class
        body.append(temp_client_class)

        # Create module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)

        return module

    def _create_imports(self, service_name: str, model_names: List[str], extracted_data: Dict[str, Any], required_typing: Set[str] = None) -> List[ast.stmt]:
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

        # Add any required typing imports (e.g., List, Dict)
        if required_typing:
            imports.extend(self.ast_helper.create_imports_from_typing(required_typing))

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

        # Add __init__ method with security schemes support
        init_method = self._create_facade_init_method(http_class_name, base_url, extracted_data)
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

    def _create_facade_init_method(self, http_class_name: str, base_url: str, extracted_data: Dict[str, Any] = None) -> ast.FunctionDef:
        """Create __init__ method for facade class with composition and security schemes support."""
        security_schemes = extracted_data.get('security_schemes', []) if extracted_data else []

        # Create arguments: self, then security scheme arguments, then base_url with default value
        args = [self.ast_helper.create_arg('self')]

        # Add security scheme arguments first
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

        # Add base_url argument with default value
        args.append(self.ast_helper.create_arg('base_url', ast.Name(id='str', ctx=ast.Load())))
        defaults.append(self.ast_helper.create_string_constant(base_url))

        # Create method body: self.http = HTTPClass(base_url, **auth_args)
        http_call_keywords = [
            ast.keyword(arg='base_url', value=ast.Name(id='base_url', ctx=ast.Load()))
        ]

        # Add security scheme arguments to HTTP class call
        for scheme in security_schemes:
            arg_name = scheme['arg_name']
            http_call_keywords.append(
                ast.keyword(
                    arg=arg_name,
                    value=ast.Name(id=arg_name, ctx=ast.Load())
                )
            )

        body = [
            ast.Assign(
                targets=[ast.Attribute(
                    value=ast.Name(id='self', ctx=ast.Load()),
                    attr='http',
                    ctx=ast.Store()
                )],
                value=ast.Call(
                    func=ast.Name(id=http_class_name, ctx=ast.Load()),
                    args=[],
                    keywords=http_call_keywords
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

        # Create method body with docstring as first element
        body = []

        # Generate docstring from operation information - reuse parameters but filter for user-friendly names
        docstring_text = self._generate_client_operation_docstring(operation, parameters, return_type_info)
        if docstring_text:
            # Use normalized docstring for proper formatting
            normalized_docstring = self.docstring_generator.normalize_docstring(docstring_text)
            docstring_node = ast.Expr(value=ast.Constant(value=normalized_docstring))
            body.append(docstring_node)

        # Add delegation call
        body.append(ast.Return(value=delegation_call))

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
                defaults=defaults
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

    def _generate_client_operation_docstring(self, operation: Dict[str, Any], parameters: List[Dict[str, Any]], return_type_info: Dict[str, Any]) -> str:
        """Generate NumPy style docstring for client facade operation method."""
        # Extract operation information
        summary = operation.get('summary', '').strip()
        description = operation.get('description', '').strip()
        response_info = operation.get('responses', {})
        response_description = response_info.get('description', 'The response from the API operation.')

        # Prepare parameters for docstring - use friendly names for client interface
        docstring_parameters = []

        for param in parameters:
            param_in = param.get('in', 'query')
            if param_in in ['path', 'query', 'header']:
                # Create parameter info for docstring
                param_name = param.get('name', 'unknown')
                param_desc = param.get('description', '').strip()

                # For client layer, use more friendly names
                from core.sanitizer import IdentifierSanitizer
                if param_name == 'target_id':
                    friendly_name = 'target_channel_id'
                else:
                    friendly_name = IdentifierSanitizer.to_snake_case(param_name)

                docstring_param = {
                    'name': friendly_name,
                    'schema': param.get('schema', param),
                    'description': param_desc,
                    'required': param.get('required', True)
                }
                docstring_parameters.append(docstring_param)

        # Add request body parameter if exists
        request_body = operation.get('request_body')
        if request_body:
            docstring_parameters.append({
                'name': 'request_body',
                'schema': {'type': 'object'},
                'description': 'Request body data as dictionary.',
                'required': request_body.get('required', False)
            })

        # Get return type from annotation
        return_type = 'dict'  # Default
        if return_type_info and return_type_info.get('annotation'):
            ann = return_type_info['annotation']
            if hasattr(ann, 'id'):
                return_type = ann.id
            elif hasattr(ann, 'value') and hasattr(ann.value, 'id'):
                # Handle subscript types like List[Model]
                if hasattr(ann, 'slice') and hasattr(ann.slice, 'id'):
                    return_type = f"{ann.value.id}[{ann.slice.id}]"
                else:
                    return_type = ann.value.id

        # Generate docstring using DocstringGenerator
        return self.docstring_generator.generate_numpy_docstring(
            summary=summary,
            description=description,
            parameters=docstring_parameters,
            return_type=return_type,
            return_description=response_description
        )
