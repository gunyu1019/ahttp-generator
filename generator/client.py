"""
ahttp_client service generator module.
Generates service.py with ahttp_client declarative class.
"""

import ast
from typing import Dict, Any, List, Set

from core.ast_helper import ASTHelper
from core.type_mapper import TypeMapper


class ClientGenerator:
    """Generates ahttp_client service class."""

    def __init__(self):
        self.ast_helper = ASTHelper()
        self.type_mapper = TypeMapper()

    def generate(self, extracted_data: Dict[str, Any], model_names: List[str]) -> ast.Module:
        """
        Generate AST module for service.py.

        Args:
            extracted_data: Extracted OpenAPI data
            model_names: List of generated model names

        Returns:
            AST module for service.py
        """
        # Create module body
        body = []

        # Track types used for imports
        types_used = {'Session', 'request', 'Annotated'}

        # Pre-analyze operations to determine all needed types
        paths = extracted_data.get('paths', [])
        schemas = extracted_data.get('schemas', {})

        # Check if we need pydantic_response_model decorator
        needs_pydantic_decorator = False

        for operation in paths:
            # Check parameters
            for param in operation.get('parameters', []):
                _, annotation_source = self.type_mapper.map_parameter_type(param)
                types_used.add(annotation_source)
                # Add Optional if parameter is not required
                if not param.get('required', False):
                    types_used.add('Optional')

            # Check request body
            request_body = operation.get('request_body')
            if request_body:
                types_used.add('Body')

            # Check return types and see if they are Pydantic models
            response = operation.get('responses', {})
            return_type = self._get_return_type(response, schemas, types_used)
            if return_type and self._is_pydantic_model(return_type, model_names):
                needs_pydantic_decorator = True

        # Add pydantic_response_model to types_used if needed
        if needs_pydantic_decorator:
            types_used.add('pydantic_response_model')

        # Add imports
        body.extend(self._create_imports(model_names, types_used))

        # Generate service class
        service_class = self._create_service_class(extracted_data, types_used)
        body.append(service_class)

        # Create module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)

        return module

    def _create_imports(self, model_names: List[str], types_used: Set[str]) -> List[ast.stmt]:
        """Create import statements."""
        imports = []
        
        # Import typing components
        typing_imports = []
        if 'Annotated' in types_used:
            typing_imports.append('Annotated')
        if 'List' in types_used:
            typing_imports.append('List')
        if 'Dict' in types_used:
            typing_imports.append('Dict')
        if 'Any' in types_used:
            typing_imports.append('Any')
        if 'Optional' in types_used:
            typing_imports.append('Optional')
        
        if typing_imports:
            imports.append(self.ast_helper.create_import('typing', typing_imports))
        
        # Import ahttp_client components
        ahttp_imports = ['Session', 'request']
        
        # Check if we need parameter annotations
        if 'Path' in types_used:
            ahttp_imports.append('Path')
        if 'Query' in types_used:
            ahttp_imports.append('Query')
        if 'Body' in types_used:
            ahttp_imports.append('Body')
        if 'Header' in types_used:
            ahttp_imports.append('Header')
        if 'pydantic_response_model' in types_used:
            ahttp_imports.append('pydantic_response_model')

        imports.append(self.ast_helper.create_import('ahttp_client', ahttp_imports))
        
        # Import models from relative path
        if model_names:
            imports.append(self.ast_helper.create_relative_import('models', model_names))
        
        return imports

    def _create_service_class(self, extracted_data: Dict[str, Any], types_used: Set[str]) -> ast.ClassDef:
        """Create the service class."""
        service_name = extracted_data.get('service_name', 'ApiService')
        servers = extracted_data.get('servers', ['https://api.example.com'])
        base_url = servers[0]  # Use first server

        # Create class body
        body = []

        # Add __init__ method
        init_method = self._create_init_method(base_url)
        body.append(init_method)

        # Add operation methods
        paths = extracted_data.get('paths', [])
        schemas = extracted_data.get('schemas', {})

        for operation in paths:
            method_def = self._create_operation_method(operation, schemas, types_used)
            body.append(method_def)

        # Create class
        return self.ast_helper.create_class_def(
            name=service_name,
            bases=['Session'],
            body=body
        )

    def _create_init_method(self, base_url: str) -> ast.FunctionDef:
        """Create __init__ method."""
        # Create method body
        body = [
            ast.Expr(
                value=ast.Call(
                    func=self.ast_helper.create_attribute('super()', '__init__'),
                    args=[self.ast_helper.create_string_constant(base_url)],
                    keywords=[]
                )
            )
        ]

        # Create self argument
        self_arg = self.ast_helper.create_arg('self')

        return self.ast_helper.create_function_def(
            name='__init__',
            args=[self_arg],
            body=body
        )

    def _create_operation_method(self, operation: Dict[str, Any], schemas: Dict[str, Any], types_used: Set[str]) -> ast.FunctionDef:
        """Create a method for an API operation."""
        operation_id = operation.get('operation_id', 'operation')
        method = operation.get('method', 'GET')
        path = operation.get('path', '/')
        parameters = operation.get('parameters', [])
        request_body = operation.get('request_body')
        response = operation.get('responses', {})

        # Create method arguments
        args = [self.ast_helper.create_arg('self')]

        # Add path parameters
        for param in parameters:
            if param['in'] == 'path':
                param_type, annotation_source = self.type_mapper.map_parameter_type(param)
                types_used.add(param_type)
                types_used.add(annotation_source)

                annotated_arg = self.ast_helper.create_annotated_arg(
                    param['name'],
                    param_type,
                    annotation_source
                )
                args.append(annotated_arg)

        # Add query parameters
        for param in parameters:
            if param['in'] == 'query':
                param_type, annotation_source = self.type_mapper.map_parameter_type(param)
                types_used.add(param_type)
                types_used.add(annotation_source)

                # Handle optional parameters
                if not param.get('required', False):
                    param_type = f'Optional[{param_type}]'
                    types_used.add('Optional')

                annotated_arg = self.ast_helper.create_annotated_arg(
                    param['name'],
                    param_type,
                    annotation_source
                )
                args.append(annotated_arg)

        # Add request body parameter
        if request_body:
            body_schema = request_body.get('schema', {})
            body_type, _ = self.type_mapper.map_schema_to_type(body_schema, schemas)
            types_used.add(body_type)
            types_used.add('Body')

            body_arg = self.ast_helper.create_annotated_arg('data', body_type, 'Body')
            args.append(body_arg)

        # Determine return type
        return_type = self._get_return_type(response, schemas, types_used)
        return_annotation = self._parse_return_type(return_type) if return_type else None

        # Create decorators list
        decorators = []

        # Add pydantic_response_model decorator if return type is a Pydantic model
        if return_type and self._is_pydantic_model(return_type, list(schemas.keys())):
            # Extract model name from return type (handle List[Model] case)
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

        # Create method body
        body = [ast.Return(value=None)]

        return self.ast_helper.create_function_def(
            name=operation_id,
            args=args,
            body=body,
            decorators=decorators,
            returns=return_annotation
        )

    def _get_return_type(self, response: Dict[str, Any], schemas: Dict[str, Any], types_used: Set[str]) -> str:
        """Determine return type from response schema."""
        response_schema = response.get('schema', {})

        if not response_schema:
            return None

        return_type, _ = self.type_mapper.map_schema_to_type(response_schema, schemas)

        # Add to types used
        if 'List[' in return_type:
            types_used.add('List')
        if 'Dict[' in return_type:
            types_used.add('Dict')
        if 'Any' in return_type:
            types_used.add('Any')

        return return_type

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

    def _is_pydantic_model(self, type_str: str, model_names: List[str]) -> bool:
        """Check if the type string represents a Pydantic model."""
        # Extract the base model name from type string
        model_name = self._extract_model_name(type_str)
        return model_name in model_names if model_name else False

    def _extract_model_name(self, type_str: str) -> str:
        """Extract model name from type string (handles List[Model] -> Model)."""
        if not type_str:
            return None

        # Handle List[ModelName] -> ModelName
        if type_str.startswith('List[') and type_str.endswith(']'):
            return type_str[5:-1]  # Remove 'List[' and ']'

        # Handle simple model name
        if type_str and type_str[0].isupper():  # Assuming model names start with uppercase
            return type_str

        return None


