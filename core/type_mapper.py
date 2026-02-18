"""
Type mapping utilities for converting OpenAPI types to Python types.
"""

from typing import Dict, Any, Optional, Tuple


class TypeMapper:
    """Maps OpenAPI types to Python types."""

    # OpenAPI type to Python type mapping
    TYPE_MAPPING = {
        'string': 'str',
        'integer': 'int',
        'number': 'float',
        'boolean': 'bool',
        'array': 'List',
        'object': 'Dict[str, Any]'
    }

    # OpenAPI format to Python type mapping
    FORMAT_MAPPING = {
        'date': 'datetime.date',
        'date-time': 'datetime.datetime',
        'email': 'str',
        'uri': 'str',
        'uuid': 'str',
        'int32': 'int',
        'int64': 'int',
        'float': 'float',
        'double': 'float'
    }

    @classmethod
    def map_schema_to_type(cls, schema: Dict[str, Any], schemas: Dict[str, Any] = None) -> Tuple[str, bool]:
        """
        Map OpenAPI schema to Python type string.

        Args:
            schema: OpenAPI schema definition
            schemas: Available schemas for $ref resolution

        Returns:
            Tuple of (type_string, is_optional)
        """
        if schemas is None:
            schemas = {}

        # Handle $ref
        if '$ref' in schema:
            ref_path = schema['$ref']
            if ref_path.startswith('#/components/schemas/'):
                schema_name = ref_path.split('/')[-1]
                return schema_name, False
            return 'Any', False

        # Handle type
        schema_type = schema.get('type', 'object')
        schema_format = schema.get('format')

        # Check format first
        if schema_format and schema_format in cls.FORMAT_MAPPING:
            return cls.FORMAT_MAPPING[schema_format], False

        # Handle array
        if schema_type == 'array':
            items_schema = schema.get('items', {'type': 'object'})
            item_type, _ = cls.map_schema_to_type(items_schema, schemas)
            return f'List[{item_type}]', False

        # Handle object with properties (inline object)
        if schema_type == 'object' and 'properties' in schema:
            return 'Dict[str, Any]', False

        # Handle basic types
        if schema_type in cls.TYPE_MAPPING:
            return cls.TYPE_MAPPING[schema_type], False

        # Fallback
        return 'Any', False

    @classmethod
    def map_parameter_type(cls, param_schema: Dict[str, Any]) -> Tuple[str, str]:
        """
        Map parameter schema to Python type and annotation source.

        Args:
            param_schema: Parameter schema definition

        Returns:
            Tuple of (python_type, annotation_source)
        """
        # Get the actual schema (might be nested under 'schema' key)
        schema = param_schema.get('schema', param_schema)
        param_type = schema.get('type', 'string')
        param_in = param_schema.get('in', 'query')

        # Map the basic type
        python_type = cls.TYPE_MAPPING.get(param_type, 'str')

        # Map the annotation source based on parameter location
        annotation_mapping = {
            'path': 'Path',
            'query': 'Query',
            'header': 'Header',
            'cookie': 'Cookie'
        }

        annotation_source = annotation_mapping.get(param_in, 'Query')

        return python_type, annotation_source

    @classmethod
    def get_imports_for_types(cls, types_used: set) -> Dict[str, list]:
        """
        Get required imports for the given types.

        Args:
            types_used: Set of type strings used in the code

        Returns:
            Dictionary mapping module names to import lists
        """
        imports = {}

        # Check for typing imports
        typing_imports = []
        if any('List[' in str(t) for t in types_used) or 'List' in types_used:
            typing_imports.append('List')
        if any('Dict[' in str(t) for t in types_used) or 'Dict' in types_used:
            typing_imports.append('Dict')
        if 'Any' in types_used:
            typing_imports.append('Any')
        if 'Annotated' in types_used:
            typing_imports.append('Annotated')
        if 'Optional' in types_used:
            typing_imports.append('Optional')

        if typing_imports:
            imports['typing'] = typing_imports

        # Check for datetime imports
        datetime_imports = []
        if any('datetime.date' in str(t) for t in types_used):
            datetime_imports.append('date')
        if any('datetime.datetime' in str(t) for t in types_used):
            datetime_imports.append('datetime')

        if datetime_imports:
            imports['datetime'] = datetime_imports

        return imports

    @classmethod
    def sanitize_schema_name(cls, name: str) -> str:
        """
        Sanitize schema name to be a valid Python class name.

        Args:
            name: Raw schema name

        Returns:
            Sanitized class name
        """
        import re

        # Remove non-alphanumeric characters and convert to PascalCase
        name = re.sub(r'[^a-zA-Z0-9]', '', name)
        if not name:
            return 'Model'

        # Ensure it starts with a capital letter
        return name[0].upper() + name[1:] if len(name) > 1 else name.upper()

