"""
Type mapping utilities for converting OpenAPI types to Python types.
"""

from typing import Dict, Any, Optional, Tuple, List


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

        # Handle enum types
        # if cls._is_enum_schema(schema):
        #     enum_name = cls._generate_enum_name_from_context(schema, schemas)
        #     return enum_name, False

        # Handle type
        schema_type = schema.get('type', 'object')
        schema_format = schema.get('format')


        # Check format first
        if schema_format and schema_format in cls.FORMAT_MAPPING:
            return cls.FORMAT_MAPPING[schema_format], False

        # Handle array
        if schema_type == 'array':
            items_schema = schema.get('items', {'type': 'object'})

            # Handle oneOf/anyOf in array items
            if 'oneOf' in items_schema or 'anyOf' in items_schema:
                refs_list = items_schema.get('oneOf', items_schema.get('anyOf', []))
                model_names = []

                for ref_item in refs_list:
                    if '$ref' in ref_item:
                        ref_path = ref_item['$ref']
                        if ref_path.startswith('#/components/schemas/'):
                            model_name = ref_path.split('/')[-1]
                            model_names.append(model_name)

                if model_names:
                    if len(model_names) > 1:
                        union_type = f"Union[{', '.join(model_names)}]"
                        return f'List[{union_type}]', False
                    else:
                        return f'List[{model_names[0]}]', False
                else:
                    # Fallback if no valid refs found
                    return 'List[Dict[str, Any]]', False
            else:
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
        param_name = param_schema.get('name', '')

        # Check if this is an enum parameter
        if cls._is_enum_schema(schema):
            enum_name = cls._generate_enum_name(param_name)
            python_type = enum_name
        else:
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
        if any('Union[' in str(t) for t in types_used) or 'Union' in types_used:
            typing_imports.append('Union')
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

        # Check for enum imports (if any type ends with 'Enum')
        enum_types = [t for t in types_used if str(t).endswith('Enum')]
        if enum_types:
            imports['enum'] = ['Enum']

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

    @classmethod
    def _is_enum_schema(cls, schema: Dict[str, Any]) -> bool:
        """
        Check if a schema definition represents an enum.

        Args:
            schema: Schema definition

        Returns:
            True if the schema is an enum
        """
        return (
            schema.get('type') == 'string' and 
            'enum' in schema and 
            isinstance(schema['enum'], list) and 
            len(schema['enum']) > 0
        )

    @classmethod
    def _generate_enum_name_from_context(cls, schema: Dict[str, Any], schemas: Dict[str, Any]) -> str:
        """
        Generate enum name from schema context. 
        This is a fallback - ideally enum names should come from the parser.

        Args:
            schema: Schema definition
            schemas: All available schemas

        Returns:
            Generated enum class name
        """
        # Try to find the enum in schemas to get the proper name
        for schema_name, schema_def in schemas.items():
            if schema_def == schema:
                return cls._generate_enum_name(schema_name)
        
        # Fallback: generate based on enum values
        values = schema.get('enum', [])
        if values:
            first_value = str(values[0]).replace('-', '_').replace(' ', '_')
            return f"{first_value.capitalize()}Enum"
        
        return "StringEnum"

    @classmethod
    def _generate_enum_name(cls, field_name: str) -> str:
        """
        Generate PascalCase enum name from field/parameter name.

        Args:
            field_name: The field or parameter name

        Returns:
            PascalCase enum name with 'Enum' suffix
        """
        # Convert to PascalCase
        words = []
        
        # Split by common separators
        for separator in ['_', '-', ' ']:
            field_name = field_name.replace(separator, '|')
        
        parts = field_name.split('|')
        for part in parts:
            if part:
                # Handle camelCase by splitting on uppercase letters
                import re
                subparts = re.findall(r'[A-Z]*[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)', part)
                if not subparts:  # If no match, use the whole part
                    subparts = [part]
                words.extend(subparts)
        
        # Capitalize each word and join
        pascal_case = ''.join(word.capitalize() for word in words if word)
        
        # Add Enum suffix if not present
        if not pascal_case.endswith('Enum'):
            pascal_case += 'Enum'
        
        return pascal_case

    @classmethod
    def map_enum_type(cls, enum_name: str, enum_values: List[str]) -> str:
        """
        Map enum definition to Python type string.

        Args:
            enum_name: Name of the enum class
            enum_values: List of enum values

        Returns:
            Enum class name as type string
        """
        return enum_name

    @classmethod 
    def sanitize_enum_member_name(cls, value: str) -> str:
        """
        Convert enum value to valid Python identifier.

        Args:
            value: The enum value from OpenAPI

        Returns:
            Valid Python identifier in UPPER_SNAKE_CASE
        """
        # Convert to uppercase
        result = value.upper()
        
        # Replace non-alphanumeric characters with underscore
        import re
        result = re.sub(r'[^A-Z0-9_]', '_', result)
        
        # Remove consecutive underscores
        result = re.sub(r'_+', '_', result)
        
        # Remove leading/trailing underscores
        result = result.strip('_')
        
        # If starts with digit, prepend with VALUE_
        if result and result[0].isdigit():
            result = f'VALUE_{result}'
        
        # If empty after processing, use generic name
        if not result:
            result = 'UNKNOWN'
        
        return result

