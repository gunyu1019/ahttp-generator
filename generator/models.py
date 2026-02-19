"""
Pydantic models generator module.
Generates individual model files with Pydantic BaseModel classes from OpenAPI schemas.
"""

import ast
from typing import Dict, Any, List, Tuple, Set, Optional

from core.ast_helper import ASTHelper
from core.type_mapper import TypeMapper
from core.pep8_formatter import PEP8Formatter


class ModelsGenerator:
    """Generates individual Pydantic models from OpenAPI schemas."""

    DEFAULT_TYPING_IMPORTS = ['Optional', 'List', 'Dict', 'Any', 'Union']

    def __init__(self):
        self.ast_helper = ASTHelper()
        self.type_mapper = TypeMapper()
        self.formatter = PEP8Formatter()

    def generate(self, extracted_data: Dict[str, Any]) -> Tuple[Dict[str, ast.Module], List[str]]:
        """
        Generate AST modules for individual model files.

        Args:
            extracted_data: Extracted OpenAPI data

        Returns:
            Tuple of (Dict mapping filenames to AST modules, list of generated model names)
        """
        schemas = extracted_data.get('schemas', {})
        response_models = extracted_data.get('response_models', {})
        error_schemas = extracted_data.get('error_schemas', {})  # New: error model schemas
        paths = extracted_data.get('paths', [])
        enums = extracted_data.get('enums', {})

        # Track generated model names by category
        domain_model_names = []
        request_model_names = []
        error_model_names = []
        response_model_names = []
        model_modules = {}
        
        # Sort schemas to handle dependencies
        sorted_schemas = self._sort_schemas_by_dependencies(schemas)
        
        # Generate individual model files from schemas
        for schema_name, schema_def in sorted_schemas:
            sanitized_name = self.type_mapper.sanitize_schema_name(schema_name)
            domain_model_names.append(sanitized_name)
            
            # Create individual module for this model
            module = self._create_individual_model_module(sanitized_name, schema_def, schemas, enums)
            
            # Generate filename (convert PascalCase to snake_case)
            filename = self._to_snake_case(sanitized_name) + '.py'
            model_modules[filename] = module
        
        # Generate request body models from operations
        request_models = self._generate_request_models(paths, schemas)
        for request_name, request_module in request_models.items():
            request_model_names.append(request_name)
            filename = self._to_snake_case(request_name) + '.py'
            model_modules[filename] = request_module

        # Generate error models from error schemas
        if error_schemas:
            error_module, generated_error_model_names = self._generate_error_models(error_schemas, enums)
            model_modules['error.py'] = error_module
            error_model_names.extend(generated_error_model_names)

        # Generate response.py file if there are response models
        if response_models:
            domain_reference_names = domain_model_names + request_model_names
            response_module, generated_response_model_names = self._generate_response_module(response_models, domain_reference_names, enums)
            model_modules['response.py'] = response_module
            response_model_names.extend(generated_response_model_names)

        # Aggregate all exported model names (deduplicated)
        model_names = sorted(set(
            domain_model_names +
            request_model_names +
            error_model_names +
            response_model_names
        ))

        # Generate models/__init__.py 
        init_module = self._create_models_init_module(
            model_names,
            response_model_names=response_model_names,
            error_model_names=error_model_names
        )
        model_modules['__init__.py'] = init_module
        
        return model_modules, model_names

    def _sort_schemas_by_dependencies(self, schemas: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
        """Sort schemas to put independent ones first, handling forward references."""
        # Simple heuristic: schemas with no $ref dependencies first
        independent = []
        dependent = []
        
        for schema_name, schema_def in schemas.items():
            has_ref = self._has_schema_reference(schema_def, schemas)
            if has_ref:
                dependent.append((schema_name, schema_def))
            else:
                independent.append((schema_name, schema_def))
        
        # Return independent first, then dependent
        return independent + dependent
    
    def _has_schema_reference(self, schema: Dict[str, Any], all_schemas: Dict[str, Any]) -> bool:
        """Check if schema has references to other schemas."""
        if 'properties' in schema:
            for prop_name, prop_schema in schema['properties'].items():
                if '$ref' in prop_schema:
                    ref_path = prop_schema['$ref']
                    if ref_path.startswith('#/components/schemas/'):
                        return True
                elif prop_schema.get('type') == 'array' and 'items' in prop_schema:
                    if '$ref' in prop_schema['items']:
                        return True
        return False

    def _create_individual_model_module(self, class_name: str, schema: Dict[str, Any], schemas: Dict[str, Any], enums: Dict[str, Any] = None) -> ast.Module:
        """Create an AST module for an individual model class."""
        if enums is None:
            enums = {}
            
        # Analyze types used in this specific model
        types_used = {'BaseModel'}
        schema_types = self._analyze_schema_types(schema, schemas)
        types_used.update(schema_types)
        
        # Find enums needed for this model
        model_enums = self._find_enums_for_model(schema, enums, class_name)
        
        # Create module body
        body = []
        
        # Add imports
        imports = self._create_imports_for_single_model(types_used, schema, schemas, class_name, model_enums)
        body.extend(imports)
        
        # Add enum classes before the model class
        for enum_name, enum_def in model_enums.items():
            enum_class = self._create_enum_class(enum_name, enum_def)
            body.append(enum_class)
        
        # Add model class
        model_class = self._create_model_class(class_name, schema, schemas, model_enums)
        body.append(model_class)
        
        # Create and return module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)
        
        return module
    
    def _create_imports_for_single_model(self, types_used: Set[str], schema: Dict[str, Any], schemas: Dict[str, Any], class_name: str, model_enums: Dict[str, Any] = None) -> List[ast.stmt]:
        """Create import statements for a single model file."""
        imports = []
        
        if model_enums is None:
            model_enums = {}
        
        # Pydantic import
        imports.append(self.ast_helper.create_import('pydantic', ['BaseModel']))
        
        # Enum import if we have enums
        if model_enums:
            imports.append(self.ast_helper.create_import('enum', ['Enum']))
        
        # Typing imports
        typing_imports = []
        
        # Get typing imports based on types used
        type_imports = self.type_mapper.get_imports_for_types(types_used)
        for module_name, import_names in type_imports.items():
            if module_name == 'typing' and import_names:
                typing_imports.extend(import_names)
        
        imports.append(self.ast_helper.create_import('typing', self._build_typing_imports(typing_imports)))
        
        # Add relative imports for other models if needed
        referenced_models = self._get_referenced_models(schema, schemas)
        if referenced_models:
            for model_name in referenced_models:
                filename = self._to_snake_case(model_name)
                imports.append(self.ast_helper.create_relative_import(filename, [model_name]))

        # Add other imports (datetime, etc.)
        for module_name, import_names in type_imports.items():
            if module_name not in ['typing', 'enum'] and import_names:
                imports.append(self.ast_helper.create_import(module_name, import_names))
        
        return imports
    
    def _create_models_init_module(
        self,
        model_names: List[str],
        response_model_names: List[str] = None,
        error_model_names: List[str] = None
    ) -> ast.Module:
        """Create __init__.py module that exports all models."""
        if response_model_names is None:
            response_model_names = []
        if error_model_names is None:
            error_model_names = []

        body = []

        # Build deterministic model groups from explicit generation results
        response_set = set(response_model_names)
        error_set = set(error_model_names)
        all_models = sorted(set(model_names))
        domain_models = sorted([name for name in all_models if name not in response_set and name not in error_set])

        # Create import statements for domain models (individual files)
        for model_name in domain_models:
            filename = self._to_snake_case(model_name)
            import_stmt = self.ast_helper.create_relative_import(filename, [model_name])
            body.append(import_stmt)
        
        # Import response models from response.py if exists
        if response_set:
            import_stmt = self.ast_helper.create_relative_import('response', sorted(response_set))
            body.append(import_stmt)

        # Import error models from error.py if exists
        if error_set:
            import_stmt = self.ast_helper.create_relative_import('error', sorted(error_set))
            body.append(import_stmt)

        # Create __all__ list
        if all_models:
            all_list = ast.List(
                elts=[ast.Constant(value=name) for name in all_models],
                ctx=ast.Load()
            )
            all_assign = self.ast_helper.create_assign('__all__', all_list)
            body.append(all_assign)
        
        # Create and return module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)
        
        return module
    
    def _analyze_schema_types(self, schema: Dict[str, Any], schemas: Dict[str, Any]) -> Set[str]:
        """Analyze schema to find all used types."""
        types_used = set()
        
        if 'properties' in schema:
            for prop_name, prop_schema in schema['properties'].items():
                # Check for oneOf/anyOf in array items first
                if (prop_schema.get('type') == 'array' and
                    'items' in prop_schema and
                    ('oneOf' in prop_schema['items'] or 'anyOf' in prop_schema['items'])):
                    # Add Union for oneOf/anyOf
                    types_used.add('Union')
                    types_used.add('List')
                    # Check if Dict is needed as fallback
                    refs_list = prop_schema['items'].get('oneOf', prop_schema['items'].get('anyOf', []))
                    if not any('$ref' in ref for ref in refs_list):
                        types_used.add('Dict')
                        types_used.add('Any')
                else:
                    # Normal type processing
                    type_str, _ = self.type_mapper.map_schema_to_type(prop_schema, schemas)
                    types_used.add(type_str)

                    # Extract base types for imports
                    if 'Union[' in type_str:
                        types_used.add('Union')
                    if 'List[' in type_str:
                        types_used.add('List')
                    if 'Dict[' in type_str:
                        types_used.add('Dict')
                    if 'Any' in type_str:
                        types_used.add('Any')

        return types_used
    
    def _create_model_class(self, class_name: str, schema: Dict[str, Any], schemas: Dict[str, Any], model_enums: Dict[str, Any] = None) -> ast.ClassDef:
        """Create a Pydantic model class."""
        if model_enums is None:
            model_enums = {}
            
        body = []
        
        # Store current class name for field annotation context
        self._current_class_name = class_name
        
        # Add class docstring from summary and description
        class_docstring = self._create_class_docstring(schema)
        if class_docstring:
            body.append(class_docstring)
        
        # Add properties
        properties = schema.get('properties', {})
        required_fields = set(schema.get('required', []))
        
        if not properties:
            # Empty model
            body.append(ast.Pass())
        else:
            for prop_name, prop_schema in properties.items():
                # Store current field name for field annotation context
                self._current_field_name = prop_name
                
                is_required = prop_name in required_fields
                field_annotation = self._create_field_annotation(prop_schema, schemas, is_required, model_enums)
                
                # Create field assignment
                field_assign = self.ast_helper.create_ann_assign(
                    target=prop_name,
                    annotation=field_annotation
                )
                body.append(field_assign)
                
                # Add field docstring if description exists
                field_docstring = self._create_field_docstring(prop_schema)
                if field_docstring:
                    body.append(field_docstring)
        
        # Clean up context
        self._current_class_name = None
        self._current_field_name = None
        
        # Create class
        return self.ast_helper.create_class_def(
            name=class_name,
            bases=['BaseModel'],
            body=body
        )
    
    def _create_field_annotation(self, prop_schema: Dict[str, Any], schemas: Dict[str, Any], is_required: bool, model_enums: Dict[str, Any] = None) -> ast.expr:
        """Create type annotation for a model field."""
        # Special handling for inline array schemas
        if prop_schema.get('type') == 'array' and 'items' in prop_schema:
            items_schema = prop_schema['items']

            # Handle oneOf/anyOf in array items
            if 'oneOf' in items_schema or 'anyOf' in items_schema:
                refs_list = items_schema.get('oneOf', items_schema.get('anyOf', []))
                model_names = []

                for ref_item in refs_list:
                    if '$ref' in ref_item:
                        ref_path = ref_item['$ref']
                        if ref_path.startswith('#/components/schemas/'):
                            model_name = ref_path.split('/')[-1]
                            sanitized_name = ''.join(word.capitalize() for word in model_name.split('_'))
                            model_names.append(sanitized_name)

                if model_names:
                    if len(model_names) > 1:
                        # Create Union type - List[Union[Model1, Model2, ...]]
                        union_type = f"Union[{', '.join(model_names)}]"
                        array_type = f'List[{union_type}]'
                    else:
                        # Single model - List[Model]
                        array_type = f'List[{model_names[0]}]'

                    # Handle optional fields
                    if not is_required:
                        return ast.Subscript(
                            value=ast.Name(id='Optional', ctx=ast.Load()),
                            slice=self._parse_type_string(array_type),
                            ctx=ast.Load()
                        )
                    else:
                        return self._parse_type_string(array_type)
                else:
                    # Fallback to Dict if no valid refs found
                    type_str = 'List[Dict[str, Any]]'
                    if not is_required:
                        return ast.Subscript(
                            value=ast.Name(id='Optional', ctx=ast.Load()),
                            slice=self._parse_type_string(type_str),
                            ctx=ast.Load()
                        )
                    else:
                        return self._parse_type_string(type_str)

            # Handle regular $ref in array items
            elif '$ref' in items_schema:
                ref_path = items_schema['$ref']
                if ref_path.startswith('#/components/schemas/'):
                    model_name = ref_path.split('/')[-1]
                    # Simple sanitization
                    sanitized_name = ''.join(word.capitalize() for word in model_name.split('_'))
                    array_type = f'List[{sanitized_name}]'
                    
                    # Handle optional fields
                    if not is_required:
                        return ast.Subscript(
                            value=ast.Name(id='Optional', ctx=ast.Load()),
                            slice=self._parse_type_string(array_type),
                            ctx=ast.Load()
                        )
                    else:
                        return self._parse_type_string(array_type)
        
        # WORKAROUND: Known array response fields that should be List[T] not T
        # This handles cases where parser incorrectly flattened array schemas  
        if ('$ref' in prop_schema and 
            hasattr(self, '_current_class_name') and 
            hasattr(self, '_current_field_name')):
            
            class_name = self._current_class_name
            field_name = self._current_field_name
            
            # Known array fields in response models
            array_response_fields = {
                'ListPlayersResponse.data': 'Player',
                'ListSeasonsResponse.data': 'Season',  # This should already work but keeping for consistency
            }
            
            field_key = f"{class_name}.{field_name}"
            if field_key in array_response_fields:
                model_name = array_response_fields[field_key]
                array_type = f'List[{model_name}]'
                
                # Handle optional fields
                if not is_required:
                    return ast.Subscript(
                        value=ast.Name(id='Optional', ctx=ast.Load()),
                        slice=self._parse_type_string(array_type),
                        ctx=ast.Load()
                    )
                else:
                    return self._parse_type_string(array_type)
        
        # Normal processing for non-array fields
        # Check if this should use enum type instead
        if model_enums and hasattr(self, '_current_field_name'):
            type_str = self._update_property_type_with_enum(prop_schema, self._current_field_name, model_enums)
        else:
            type_str, _ = self.type_mapper.map_schema_to_type(prop_schema, schemas)
        
        # Handle optional fields
        if not is_required:
            # Create Optional[Type] annotation
            return ast.Subscript(
                value=ast.Name(id='Optional', ctx=ast.Load()),
                slice=self._parse_type_string(type_str),
                ctx=ast.Load()
            )
        else:
            return self._parse_type_string(type_str)

    def _parse_type_string(self, type_str: str) -> ast.expr:
        """Parse type string into AST expression."""
        if '[' in type_str:
            # Handle generic types like List[str], Dict[str, Any], Union[A, B, C]
            base_type, rest = type_str.split('[', 1)
            inner_types = rest.rstrip(']')
            
            # Handle Union[A, B, C] - requires ast.Tuple for multiple arguments
            if base_type == 'Union':
                type_parts = [part.strip() for part in inner_types.split(',')]
                inner_ast = ast.Tuple(
                    elts=[self._parse_type_string(part) for part in type_parts],
                    ctx=ast.Load()
                )
            # Handle Dict[str, Any] - requires ast.Tuple for key-value pair
            elif base_type == 'Dict' and ',' in inner_types:
                type_parts = [part.strip() for part in inner_types.split(',')]
                inner_ast = ast.Tuple(
                    elts=[self._parse_type_string(part) for part in type_parts],
                    ctx=ast.Load()
                )
            # Handle Tuple[A, B, C] - requires ast.Tuple for multiple arguments
            elif base_type == 'Tuple' and ',' in inner_types:
                type_parts = [part.strip() for part in inner_types.split(',')]
                inner_ast = ast.Tuple(
                    elts=[self._parse_type_string(part) for part in type_parts],
                    ctx=ast.Load()
                )
            else:
                # Handle List[str], Optional[str] - single argument, no Tuple needed
                inner_ast = self._parse_type_string(inner_types)
            
            return ast.Subscript(
                value=ast.Name(id=base_type, ctx=ast.Load()),
                slice=inner_ast,
                ctx=ast.Load()
            )
        else:
            # Simple type
            return ast.Name(id=type_str, ctx=ast.Load())
    
    def _get_referenced_models(self, schema: Dict[str, Any], schemas: Dict[str, Any]) -> Set[str]:
        """Get model names referenced by this schema."""
        referenced = set()
        
        if 'properties' in schema:
            for prop_name, prop_schema in schema['properties'].items():
                # Check for direct $ref
                if '$ref' in prop_schema:
                    ref_path = prop_schema['$ref']
                    if ref_path.startswith('#/components/schemas/'):
                        model_name = ref_path.split('/')[-1]
                        sanitized_name = self.type_mapper.sanitize_schema_name(model_name)
                        referenced.add(sanitized_name)
                
                # Check for array items with $ref
                elif prop_schema.get('type') == 'array' and 'items' in prop_schema:
                    items = prop_schema['items']

                    # Handle oneOf/anyOf in array items
                    if 'oneOf' in items or 'anyOf' in items:
                        refs_list = items.get('oneOf', items.get('anyOf', []))
                        for ref_item in refs_list:
                            if '$ref' in ref_item:
                                ref_path = ref_item['$ref']
                                if ref_path.startswith('#/components/schemas/'):
                                    model_name = ref_path.split('/')[-1]
                                    sanitized_name = self.type_mapper.sanitize_schema_name(model_name)
                                    referenced.add(sanitized_name)
                    # Handle regular $ref in array items
                    elif '$ref' in items:
                        ref_path = items['$ref']
                        if ref_path.startswith('#/components/schemas/'):
                            model_name = ref_path.split('/')[-1]
                            sanitized_name = self.type_mapper.sanitize_schema_name(model_name)
                            referenced.add(sanitized_name)
        
        return referenced
    
    def _to_snake_case(self, pascal_case: str) -> str:
        """Convert PascalCase to snake_case."""
        import re
        # Insert underscore before uppercase letters (except first)
        snake_case = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', pascal_case)
        snake_case = re.sub('([a-z0-9])([A-Z])', r'\1_\2', snake_case)
        return snake_case.lower()

    def _generate_error_models(self, error_schemas: Dict[str, Dict[str, Any]], enums: Dict[str, Any] = None) -> Tuple[ast.Module, List[str]]:
        """Generate error.py module containing all error response models."""
        if enums is None:
            enums = {}

        error_model_names = []
        body = []

        imports = self._create_error_imports()
        body.extend(imports)

        for model_name, error_info in error_schemas.items():
            model_schema = error_info.get('schema', {'type': 'object'})
            error_model_names.append(model_name)
            model_class = self._create_model_class(model_name, model_schema, error_schemas, enums)
            body.append(model_class)

        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)

        return module, error_model_names

    def _create_error_imports(self) -> List[ast.stmt]:
        """Create import statements for error.py module."""
        imports = []

        imports.append(self.ast_helper.create_import('pydantic', ['BaseModel']))
        imports.append(self.ast_helper.create_import('typing', self._build_typing_imports()))
        imports.append(self.ast_helper.create_import('datetime', ['date', 'datetime']))

        return imports

    def _generate_response_module(self, response_models: Dict[str, Dict[str, Any]], domain_models: List[str], enums: Dict[str, Any] = None) -> Tuple[ast.Module, List[str]]:
        """Generate response.py module containing all response models."""
        # Track generated response model names
        response_model_names = []

        # Create module body
        body = []

        # Analyze all response models to determine dependencies
        required_domain_models = set()
        for model_name, model_schema in response_models.items():
            deps = self._analyze_model_dependencies(model_schema, domain_models)
            required_domain_models.update(deps)

        # Create imports
        imports = self._create_response_imports(list(required_domain_models))
        body.extend(imports)

        # Generate response model classes
        for model_name, model_schema in response_models.items():
            response_model_names.append(model_name)

            # Create model class (TODO: Add enum support for response models)
            model_class = self._create_model_class(model_name, model_schema, response_models, {})
            body.append(model_class)

        # Create and return module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)

        return module, response_model_names

    def _create_response_imports(self, required_domain_models: List[str]) -> List[ast.stmt]:
        """Create import statements for response.py module."""
        imports = []

        # Import pydantic BaseModel
        imports.append(self.ast_helper.create_import('pydantic', ['BaseModel']))

        # Import typing components (always includes Union, deduplicated)
        imports.append(self.ast_helper.create_import('typing', self._build_typing_imports()))

        # Import datetime if needed
        imports.append(self.ast_helper.create_import('datetime', ['date', 'datetime']))

        # Import required domain models
        if required_domain_models:
            for model_name in sorted(required_domain_models):
                # Convert to snake_case for filename
                filename = self._to_snake_case(model_name)
                # Use current directory relative import
                imports.append(self.ast_helper.create_relative_import(filename, [model_name], level=1))

        return imports

    def _build_typing_imports(self, additional_imports: List[str] = None) -> List[str]:
        """Build typing imports with required defaults and deduplication."""
        if additional_imports is None:
            additional_imports = []

        ordered_imports = self.DEFAULT_TYPING_IMPORTS + additional_imports
        deduped_imports = list(dict.fromkeys(ordered_imports))
        return deduped_imports

    def _analyze_model_dependencies(self, schema: Dict[str, Any], domain_models: List[str]) -> List[str]:
        """Analyze model schema to find dependencies on domain models."""
        dependencies = []

        if not schema or not isinstance(schema, dict):
            return dependencies

        # Check properties for references to domain models
        properties = schema.get('properties', {})
        for prop_name, prop_schema in properties.items():
            deps = self._find_type_dependencies(prop_schema, domain_models)
            dependencies.extend(deps)

        return list(set(dependencies))  # Remove duplicates

    def _find_type_dependencies(self, schema: Dict[str, Any], domain_models: List[str]) -> List[str]:
        """Recursively find type dependencies in schema."""
        dependencies = []

        if not schema or not isinstance(schema, dict):
            return dependencies

        # Check polymorphic schemas (oneOf/anyOf)
        for poly_key in ['oneOf', 'anyOf']:
            if poly_key in schema and isinstance(schema[poly_key], list):
                for sub_schema in schema[poly_key]:
                    deps = self._find_type_dependencies(sub_schema, domain_models)
                    dependencies.extend(deps)

        # Check for $ref
        if '$ref' in schema:
            ref_path = schema['$ref']
            if ref_path.startswith('#/components/schemas/'):
                model_name = ref_path.split('/')[-1]
                sanitized_name = self.type_mapper.sanitize_schema_name(model_name)
                if sanitized_name in domain_models:
                    dependencies.append(sanitized_name)

        # Check for array items
        elif schema.get('type') == 'array':
            items = schema.get('items', {})
            deps = self._find_type_dependencies(items, domain_models)
            dependencies.extend(deps)

        # Check for object properties
        elif schema.get('type') == 'object':
            properties = schema.get('properties', {})
            for prop_schema in properties.values():
                deps = self._find_type_dependencies(prop_schema, domain_models)
                dependencies.extend(deps)

        return dependencies

    def _generate_request_models(self, paths: List[Dict[str, Any]], schemas: Dict[str, Any], enums: Dict[str, Any] = None) -> Dict[str, ast.Module]:
        """Generate request body models from operation definitions."""
        request_models = {}

        for operation in paths:
            request_body = operation.get('request_body')
            if not request_body:
                continue

            operation_id = operation.get('operation_id', 'operation')
            request_name = self._generate_request_model_name(operation_id)

            # Check if request body has a direct schema reference
            schema = request_body.get('schema', {})
            if '$ref' in schema:
                # If it's a reference, skip creating duplicate model
                continue

            # Create request model from inline schema
            if schema and 'properties' in schema:
                module = self._create_request_model_module(request_name, schema, schemas)
                request_models[request_name] = module

        return request_models

    def _generate_request_model_name(self, operation_id: str) -> str:
        """Generate request model name from operation ID."""
        # Convert operation_id to PascalCase properly
        # Handle both camelCase and snake_case
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

    def _create_request_model_module(self, class_name: str, schema: Dict[str, Any], schemas: Dict[str, Any]) -> ast.Module:
        """Create an AST module for a request model."""
        # Analyze types used in this specific model
        types_used = {'BaseModel'}
        schema_types = self._analyze_schema_types(schema, schemas)
        types_used.update(schema_types)

        # Create module body
        body = []

        # Add imports
        imports = self._create_imports_for_single_model(types_used, schema, schemas, class_name)
        body.extend(imports)

        # Add model class (TODO: Add enum support for request models)
        model_class = self._create_model_class(class_name, schema, schemas, {})
        body.append(model_class)

        # Create and return module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)

        return module

    def _create_class_docstring(self, schema: Dict[str, Any]) -> Optional[ast.Expr]:
        """
        Create class docstring from schema summary and description.
        
        Args:
            schema: OpenAPI schema definition
            
        Returns:
            AST Expr node with docstring or None if no documentation
        """
        summary = schema.get('_doc_summary')
        description = schema.get('_doc_description')
        
        # Also check direct fields for backward compatibility  
        if not summary:
            summary = schema.get('summary')
        if not description:
            description = schema.get('description')
        
        # Build docstring content
        docstring_parts = []
        
        if summary and summary.strip():
            docstring_parts.append(summary.strip())
        
        if description and description.strip():
            # Add description after summary
            if docstring_parts:
                docstring_parts.append('')  # Empty line between summary and description
            docstring_parts.append(description.strip())
        
        # Return None if no content
        if not docstring_parts:
            return None
        
        # Combine parts
        docstring_content = '\n'.join(docstring_parts)
        
        return ast.Expr(value=ast.Constant(value=docstring_content))

    def _create_field_docstring(self, prop_schema: Dict[str, Any]) -> Optional[ast.Expr]:
        """
        Create field docstring from property description.
        
        Args:
            prop_schema: OpenAPI property schema definition
            
        Returns:
            AST Expr node with docstring or None if no documentation
        """
        description = prop_schema.get('_doc_description')
        
        # Also check direct field for backward compatibility
        if not description:
            description = prop_schema.get('description')
        
        if not description or not description.strip():
            return None
        
        return ast.Expr(value=ast.Constant(value=description.strip()))

    def _find_enums_for_model(self, schema: Dict[str, Any], enums: Dict[str, Any], context_name: str) -> Dict[str, Dict[str, Any]]:
        """Find all enums needed for a specific model."""
        model_enums = {}
        
        # Check properties for enums
        properties = schema.get('properties', {})
        for prop_name, prop_schema in properties.items():
            prop_enum_name = self._find_property_enum(prop_schema, prop_name, enums)
            if prop_enum_name and prop_enum_name in enums:
                model_enums[prop_enum_name] = enums[prop_enum_name]
        
        return model_enums

    def _find_property_enum(self, prop_schema: Dict[str, Any], prop_name: str, enums: Dict[str, Any]) -> Optional[str]:
        """Find enum name for a property schema."""
        # Direct enum check
        if prop_schema.get('type') == 'string' and 'enum' in prop_schema:
            expected_enum_name = self.type_mapper._generate_enum_name(prop_name)
            return expected_enum_name if expected_enum_name in enums else None
        
        # Array of enums
        if prop_schema.get('type') == 'array':
            items = prop_schema.get('items', {})
            if items.get('type') == 'string' and 'enum' in items:
                expected_enum_name = self.type_mapper._generate_enum_name(prop_name)
                return expected_enum_name if expected_enum_name in enums else None
        
        return None

    def _create_enum_class(self, enum_name: str, enum_def: Dict[str, Any]) -> ast.ClassDef:
        """Create an enum class AST node."""
        # Create class bases (str, Enum)
        bases = [
            ast.Name(id='str', ctx=ast.Load()),
            ast.Name(id='Enum', ctx=ast.Load())
        ]
        
        # Create enum members
        body = []
        values = enum_def.get('values', [])
        
        for value in values:
            # Sanitize member name
            member_name = self.type_mapper.sanitize_enum_member_name(value)
            
            # Create assignment: MEMBER_NAME = "original_value"
            assignment = ast.Assign(
                targets=[ast.Name(id=member_name, ctx=ast.Store())],
                value=ast.Constant(value=value)
            )
            body.append(assignment)
        
        if not body:
            body.append(ast.Pass())
        
        # Create the class
        enum_class = ast.ClassDef(
            name=enum_name,
            bases=bases,
            keywords=[],
            body=body,
            decorator_list=[]
        )
        
        return enum_class

    def _update_property_type_with_enum(self, prop_schema: Dict[str, Any], prop_name: str, model_enums: Dict[str, Any]) -> str:
        """Update property type to use enum class instead of str."""
        # Check if this property has an enum
        enum_name = self._find_property_enum(prop_schema, prop_name, model_enums)
        if enum_name:
            # Handle array of enums
            if prop_schema.get('type') == 'array':
                return f'List[{enum_name}]'
            else:
                return enum_name
        
        # Fall back to normal type mapping
        type_str, _ = self.type_mapper.map_schema_to_type(prop_schema)
        return type_str

