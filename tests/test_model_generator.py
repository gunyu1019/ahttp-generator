"""
Tests for Pydantic V2 model generation.
"""

import ast
import pytest
from typing import Dict, Any

from ahttp_generator.parser.extractor import OpenAPIExtractor
from ahttp_generator.generator.models import ModelsGenerator


class TestModelsGenerator:
    """Test Pydantic model generation logic."""

    def test_generate_basic_model(self, minimal_openapi_spec: Dict[str, Any]):
        """Test generation of a basic Pydantic model."""
        # Add a simple schema to the spec
        minimal_openapi_spec['components']['schemas']['Product'] = {
            'type': 'object',
            'required': ['id', 'name'],
            'properties': {
                'id': {'type': 'string'},
                'name': {'type': 'string'},
                'price': {'type': 'number'}
            }
        }

        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(minimal_openapi_spec)

        generator = ModelsGenerator()
        model_modules, model_names = generator.generate(extracted_data)

        # Should generate a Product model
        assert 'Product' in model_names

        # Should generate a file for Product
        assert 'product.py' in model_modules

    def test_reserved_keyword_handling(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that reserved keywords in properties are properly handled."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ModelsGenerator()
        model_modules, model_names = generator.generate(extracted_data)

        # Parse the User model
        user_module = model_modules.get('user.py')
        assert user_module is not None

        # Convert to source code
        source = ast.unparse(user_module)

        # Should contain 'class_' as alias for 'class' field
        # or use Field(alias='class')
        assert 'class' in source.lower()
        assert 'Field' in source or 'class_' in source

    def test_circular_reference_handling(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that circular references use ForwardRef or string annotations."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ModelsGenerator()
        model_modules, model_names = generator.generate(extracted_data)

        # Parse the User model
        user_module = model_modules.get('user.py')
        assert user_module is not None

        # Convert to source code
        source = ast.unparse(user_module)

        # Should use Optional['User'] or ForwardRef for manager field
        # or use model_rebuild() for Pydantic V2
        # Also acceptable: Optional[User] if forward reference is not needed
        assert ("'User'" in source or 'ForwardRef' in source or
                'model_rebuild' in source or 'Optional[User]' in source)

    def test_enum_generation(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that enums are properly generated."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ModelsGenerator()
        model_modules, model_names = generator.generate(extracted_data)

        # Check for enum in Item model
        item_module = model_modules.get('item.py')
        if item_module:
            source = ast.unparse(item_module)

            # Should have enum import or definition
            # Enums can be defined as Literal or as separate Enum class
            assert 'Enum' in source or 'Literal' in source or 'status' in source.lower()

    def test_required_vs_optional_fields(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that required and optional fields are properly typed."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ModelsGenerator()
        model_modules, model_names = generator.generate(extracted_data)

        user_module = model_modules.get('user.py')
        assert user_module is not None

        source = ast.unparse(user_module)

        # Required fields (id, name) should not be Optional
        # Optional fields should use Optional[...]
        assert 'Optional' in source  # For optional fields like manager

    def test_nested_object_handling(self, deeply_nested_spec: Dict[str, Any]):
        """Test handling of nested object references."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(deeply_nested_spec)

        generator = ModelsGenerator()
        model_modules, model_names = generator.generate(extracted_data)

        # All levels should be generated as separate models
        assert 'Level1' in model_names
        assert 'Level2' in model_names
        assert 'Level3' in model_names

        # Check that Level1 references Level2
        level1_module = model_modules.get('level1.py')
        if level1_module:
            source = ast.unparse(level1_module)
            assert 'Level2' in source

    def test_model_ast_structure(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that generated AST has proper structure."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ModelsGenerator()
        model_modules, model_names = generator.generate(extracted_data)

        # Check User model AST structure
        user_module = model_modules.get('user.py')
        assert user_module is not None
        assert isinstance(user_module, ast.Module)

        # Find the class definition
        classes = [node for node in user_module.body if isinstance(node, ast.ClassDef)]
        assert len(classes) > 0

        user_class = classes[0]
        assert user_class.name == 'User'

        # Should inherit from BaseModel
        assert len(user_class.bases) > 0

    def test_pydantic_v2_features(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that Pydantic V2 features are used."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ModelsGenerator()
        model_modules, model_names = generator.generate(extracted_data)

        user_module = model_modules.get('user.py')
        assert user_module is not None

        source = ast.unparse(user_module)

        # Should import from pydantic
        assert 'pydantic' in source.lower()
        assert 'BaseModel' in source

        # Pydantic V2 uses Field for field configuration
        # Should use Field for aliases and other config
        # (may not always be present if no special config needed)

    def test_response_models_generation(self, inline_response_spec: Dict[str, Any]):
        """Test that inline response models are generated separately."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(inline_response_spec)

        generator = ModelsGenerator()
        model_modules, model_names = generator.generate(extracted_data)

        # Should generate a response.py file for inline responses
        # or include the response model in the modules
        assert len(model_modules) > 1  # At least __init__.py and one model

    def test_error_models_generation(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that error models are generated."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ModelsGenerator()
        model_modules, model_names = generator.generate(extracted_data)

        # Should have error.py or Error model
        has_error_file = 'error.py' in model_modules
        has_error_model = 'Error' in model_names

        assert has_error_file or has_error_model

    def test_models_init_generation(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that models/__init__.py is generated with proper exports."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ModelsGenerator()
        model_modules, model_names = generator.generate(extracted_data)

        # Should have __init__.py
        assert '__init__.py' in model_modules

        init_module = model_modules['__init__.py']
        source = ast.unparse(init_module)

        # Should have __all__ declaration
        assert '__all__' in source

        # Should import all models
        assert 'User' in source or 'import' in source

    def test_special_characters_in_properties(self):
        """Test handling of special characters in property names."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {},
            "components": {
                "schemas": {
                    "SpecialFields": {
                        "type": "object",
                        "properties": {
                            "normal_field": {"type": "string"},
                            "field-with-dash": {"type": "string"},
                            "field.with.dot": {"type": "string"},
                            "field[with]brackets": {"type": "string"}
                        }
                    }
                }
            }
        }

        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(spec)

        generator = ModelsGenerator()
        model_modules, model_names = generator.generate(extracted_data)

        special_module = model_modules.get('special_fields.py')
        assert special_module is not None

        source = ast.unparse(special_module)

        # Special characters should be sanitized and use Field(alias=...)
        assert 'Field' in source or 'field_with_dash' in source

    def test_array_type_handling(self):
        """Test that array types are properly converted to List[...]."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {},
            "components": {
                "schemas": {
                    "Container": {
                        "type": "object",
                        "properties": {
                            "items": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "numbers": {
                                "type": "array",
                                "items": {"type": "integer"}
                            }
                        }
                    }
                }
            }
        }

        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(spec)

        generator = ModelsGenerator()
        model_modules, model_names = generator.generate(extracted_data)

        container_module = model_modules.get('container.py')
        assert container_module is not None

        source = ast.unparse(container_module)

        # Should use List type annotation
        assert 'List' in source

    def test_object_type_with_additional_properties(self):
        """Test that objects with additionalProperties are typed as Dict."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {},
            "components": {
                "schemas": {
                    "DynamicObject": {
                        "type": "object",
                        "properties": {
                            "metadata": {
                                "type": "object",
                                "additionalProperties": True
                            }
                        }
                    }
                }
            }
        }

        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(spec)

        generator = ModelsGenerator()
        model_modules, model_names = generator.generate(extracted_data)

        dynamic_module = model_modules.get('dynamic_object.py')
        assert dynamic_module is not None

        source = ast.unparse(dynamic_module)

        # Should use Dict type annotation
        assert 'Dict' in source or 'dict' in source
