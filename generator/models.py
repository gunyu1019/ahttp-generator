"""
Pydantic models generator module.
Generates individual model files with Pydantic BaseModel classes from OpenAPI schemas.
"""

import ast
from typing import Dict, Any, List, Tuple, Set

from core.ast_helper import ASTHelper
from core.type_mapper import TypeMapper


class ModelsGenerator:
    """Generates individual Pydantic models from OpenAPI schemas."""

    def __init__(self):
        self.ast_helper = ASTHelper()
        self.type_mapper = TypeMapper()

    def generate(self, extracted_data: Dict[str, Any]) -> Tuple[Dict[str, ast.Module], List[str]]:
        """
        Generate AST modules for individual model files.

        Args:
            extracted_data: Extracted OpenAPI data

        Returns:
            Tuple of (Dict mapping filenames to AST modules, list of generated model names)
        """
        schemas = extracted_data.get('schemas', {})
        
        # Track generated model names
        model_names = []
        model_modules = {}
        
        # Sort schemas to handle dependencies
        sorted_schemas = self._sort_schemas_by_dependencies(schemas)
        
        # Generate individual model files
        for schema_name, schema_def in sorted_schemas:
            sanitized_name = self.type_mapper.sanitize_schema_name(schema_name)
            model_names.append(sanitized_name)
            
            # Create individual module for this model
            module = self._create_individual_model_module(sanitized_name, schema_def, schemas)
            
            # Generate filename (convert PascalCase to snake_case)
            filename = self._to_snake_case(sanitized_name) + '.py'
            model_modules[filename] = module
        
        # Generate models/__init__.py
        init_module = self._create_models_init_module(model_names)
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

    def _create_individual_model_module(self, class_name: str, schema: Dict[str, Any], schemas: Dict[str, Any]) -> ast.Module:
        """Create an AST module for an individual model class."""
        # Analyze types used in this specific model
        types_used = {'BaseModel'}
        schema_types = self._analyze_schema_types(schema, schemas)
        types_used.update(schema_types)
        
        # Create module body
        body = []
        
        # Add imports
        imports = self._create_imports_for_single_model(types_used, schema, schemas)
        body.extend(imports)
        
        # Add model class
        model_class = self._create_model_class(class_name, schema, schemas)
        body.append(model_class)
        
        # Create and return module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)
        
        return module
    
    def _create_imports_for_single_model(self, types_used: Set[str], schema: Dict[str, Any], schemas: Dict[str, Any]) -> List[ast.stmt]:
        """Create import statements for a single model file."""
        imports = []
        
        # Pydantic import
        imports.append(self.ast_helper.create_import('pydantic', ['BaseModel']))
        
        # Typing imports
        typing_imports = ['Optional']  # Always include Optional
        
        # Get typing imports based on types used
        type_imports = self.type_mapper.get_imports_for_types(types_used)
        for module_name, import_names in type_imports.items():
            if module_name == 'typing' and import_names:
                typing_imports.extend(import_names)
        
        # Remove duplicates
        typing_imports = list(set(typing_imports))
        imports.append(self.ast_helper.create_import('typing', typing_imports))
        
        # Add relative imports for other models if needed
        referenced_models = self._get_referenced_models(schema, schemas)
        if referenced_models:
            for model_name in referenced_models:
                filename = self._to_snake_case(model_name)
                imports.append(self.ast_helper.create_relative_import(filename, [model_name]))
        
        # Add other imports (datetime, etc.)
        for module_name, import_names in type_imports.items():
            if module_name not in ['typing'] and import_names:
                imports.append(self.ast_helper.create_import(module_name, import_names))
        
        return imports
    
    def _create_models_init_module(self, model_names: List[str]) -> ast.Module:
        """Create __init__.py module that exports all models."""
        body = []
        
        # Create import statements for each model
        for model_name in model_names:
            filename = self._to_snake_case(model_name)
            import_stmt = self.ast_helper.create_relative_import(filename, [model_name])
            body.append(import_stmt)
        
        # Create __all__ list
        if model_names:
            all_list = ast.List(
                elts=[ast.Constant(value=name) for name in model_names],
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
                type_str, _ = self.type_mapper.map_schema_to_type(prop_schema, schemas)
                types_used.add(type_str)
                
                # Extract base types for imports
                if 'List[' in type_str:
                    types_used.add('List')
                if 'Dict[' in type_str:
                    types_used.add('Dict')
                if 'Any' in type_str:
                    types_used.add('Any')
        
        return types_used
    
    def _create_model_class(self, class_name: str, schema: Dict[str, Any], schemas: Dict[str, Any]) -> ast.ClassDef:
        """Create a Pydantic model class."""
        body = []
        
        # Add docstring if description exists
        description = schema.get('description')
        if description:
            docstring = ast.Expr(value=ast.Constant(value=description))
            body.append(docstring)
        
        # Add properties
        properties = schema.get('properties', {})
        required_fields = set(schema.get('required', []))
        
        if not properties:
            # Empty model
            body.append(ast.Pass())
        else:
            for prop_name, prop_schema in properties.items():
                is_required = prop_name in required_fields
                field_annotation = self._create_field_annotation(prop_schema, schemas, is_required)
                
                # Create field assignment
                field_assign = self.ast_helper.create_ann_assign(
                    target=prop_name,
                    annotation=field_annotation
                )
                body.append(field_assign)
        
        # Create class
        return self.ast_helper.create_class_def(
            name=class_name,
            bases=['BaseModel'],
            body=body
        )
    
    def _create_field_annotation(self, prop_schema: Dict[str, Any], schemas: Dict[str, Any], is_required: bool) -> ast.expr:
        """Create type annotation for a model field."""
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
            # Handle generic types like List[str], Dict[str, Any]
            base_type, rest = type_str.split('[', 1)
            inner_types = rest.rstrip(']')
            
            if ',' in inner_types:
                # Handle Dict[str, Any]
                type_parts = [part.strip() for part in inner_types.split(',')]
                inner_ast = ast.Tuple(
                    elts=[self._parse_type_string(part) for part in type_parts],
                    ctx=ast.Load()
                )
            else:
                # Handle List[str]
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
                    if '$ref' in items:
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
