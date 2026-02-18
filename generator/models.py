"""
Pydantic models generator module.
Generates models.py with Pydantic BaseModel classes from OpenAPI schemas.
"""

import ast
from typing import Dict, Any, List, Tuple, Set

from core.ast_helper import ASTHelper
from core.type_mapper import TypeMapper


class ModelsGenerator:
    """Generates Pydantic models from OpenAPI schemas."""

    def __init__(self):
        self.ast_helper = ASTHelper()
        self.type_mapper = TypeMapper()

    def generate(self, extracted_data: Dict[str, Any]) -> Tuple[ast.Module, List[str]]:
        """
        Generate AST module for models.py.

        Args:
            extracted_data: Extracted OpenAPI data

        Returns:
            Tuple of (AST module, list of generated model names)
        """
        schemas = extracted_data.get('schemas', {})

        # Track generated model names and required imports
        model_names = []
        types_used = {'BaseModel'}

        # Create module body
        body = []

        # Add required imports (will be updated later)
        body.extend(self._create_imports(types_used))

        # Sort schemas to handle dependencies (simple heuristic: independent schemas first)
        sorted_schemas = self._sort_schemas_by_dependencies(schemas)

        # Generate model classes
        for schema_name, schema_def in sorted_schemas:
            sanitized_name = self.type_mapper.sanitize_schema_name(schema_name)
            model_names.append(sanitized_name)

            # Analyze schema for types
            schema_types = self._analyze_schema_types(schema_def, schemas)
            types_used.update(schema_types)

            # Create model class
            model_class = self._create_model_class(sanitized_name, schema_def, schemas)
            body.append(model_class)

        # Update imports with all used types
        import_statements = self._create_imports(types_used)

        # Rebuild body with correct imports
        body = import_statements + body[len(import_statements):]

        # Create module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)

        return module, model_names

    def _create_imports(self, types_used: Set[str]) -> List[ast.stmt]:
        """Create import statements based on types used."""
        imports = []

        # Pydantic import
        imports.append(self.ast_helper.create_import('pydantic', ['BaseModel']))

        # Always add Optional for typing imports since we use it for non-required fields
        typing_imports = ['Optional']

        # Get typing imports
        type_imports = self.type_mapper.get_imports_for_types(types_used)
        for module_name, import_names in type_imports.items():
            if module_name == 'typing' and import_names:
                typing_imports.extend(import_names)

        # Remove duplicates and add typing import
        typing_imports = list(set(typing_imports))
        imports.append(self.ast_helper.create_import('typing', typing_imports))

        # Add other imports
        for module_name, import_names in type_imports.items():
            if module_name != 'typing' and import_names:
                imports.append(self.ast_helper.create_import(module_name, import_names))

        return imports

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



