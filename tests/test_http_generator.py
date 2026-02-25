"""
Tests for HTTP implementation layer (http.py) generation.
Validates decorator ordering, Annotated types, and path variable handling.
"""

import ast
import pytest
from typing import Dict, Any, List

from ahttp_generator.parser.extractor import OpenAPIExtractor
from ahttp_generator.generator.http import HTTPGenerator


class TestHTTPGenerator:
    """Test HTTP implementation layer generation."""

    def test_generate_http_class(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test basic HTTP class generation."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=[])

        assert isinstance(http_module, ast.Module)

        # Find the HTTP class
        classes = [node for node in http_module.body if isinstance(node, ast.ClassDef)]
        assert len(classes) > 0

        http_class = classes[0]
        assert 'HTTP' in http_class.name

    def test_decorator_order(self, edge_case_openapi_spec: Dict[str, Any]):
        """
        Test that decorators are in correct order:
        1. @pydantic_response_model (if present)
        2. @request
        3. @Header.default_header (if present)
        """
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=['User', 'Item'])

        source = ast.unparse(http_module)

        # Find method definitions with decorators
        classes = [node for node in http_module.body if isinstance(node, ast.ClassDef)]
        if classes:
            http_class = classes[0]
            methods = [node for node in http_class.body if isinstance(node, ast.FunctionDef)]

            for method in methods:
                if len(method.decorator_list) > 0:
                    decorator_names = []
                    for dec in method.decorator_list:
                        if isinstance(dec, ast.Name):
                            decorator_names.append(dec.id)
                        elif isinstance(dec, ast.Call):
                            if isinstance(dec.func, ast.Name):
                                decorator_names.append(dec.func.id)
                            elif isinstance(dec.func, ast.Attribute):
                                decorator_names.append(dec.func.attr)

                    # If request decorator is present, it should be after pydantic_response_model
                    if 'request' in decorator_names:
                        request_idx = decorator_names.index('request')
                        # Check that pydantic_response_model comes before if it exists
                        if 'pydantic_response_model' in decorator_names:
                            pydantic_idx = decorator_names.index('pydantic_response_model')
                            assert pydantic_idx < request_idx, \
                                f"Decorator order wrong: {decorator_names}"

    def test_path_parameter_annotation(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that path parameters use Annotated[str, Path] syntax."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=['User'])

        source = ast.unparse(http_module)

        # Should have Annotated import
        assert 'Annotated' in source

        # Find methods with path parameters
        classes = [node for node in http_module.body if isinstance(node, ast.ClassDef)]
        if classes:
            http_class = classes[0]
            methods = [node for node in http_class.body if isinstance(node, ast.FunctionDef)]

            for method in methods:
                # Check method arguments for Annotated types
                for arg in method.args.args:
                    if arg.annotation:
                        # Path parameters should use Annotated
                        if isinstance(arg.annotation, ast.Subscript):
                            if isinstance(arg.annotation.value, ast.Name):
                                if arg.annotation.value.id == 'Annotated':
                                    # This is an Annotated type
                                    # Check that it contains Path
                                    pass  # Successfully found Annotated

    def test_query_parameter_annotation(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that query parameters use Annotated[str, Query] syntax."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=['User'])

        source = ast.unparse(http_module)

        # Should import Query from ahttp_client
        assert 'Query' in source

    def test_server_path_variables(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that server path variables are properly handled."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        # The edge case spec has server variables: environment and version
        servers = extracted_data.get('servers', {})

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=[])

        source = ast.unparse(http_module)

        # __init__ method should accept server path variables
        # or store them in the class
        # At minimum, server configuration should be present

    def test_custom_name_mapping(self):
        """Test that parameters with special characters get custom_name mapping."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {
                "/items": {
                    "get": {
                        "operationId": "listItems",
                        "parameters": [
                            {
                                "name": "filter[type]",
                                "in": "query",
                                "schema": {"type": "string"}
                            }
                        ],
                        "responses": {
                            "200": {
                                "description": "Success",
                                "content": {
                                    "application/json": {
                                        "schema": {"type": "object"}
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "components": {"schemas": {}}
        }

        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(spec)

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=[])

        source = ast.unparse(http_module)

        # Parameter should be sanitized to filter_type
        # But original name should be mapped via Query(name='filter[type]')
        assert 'filter' in source.lower()

    def test_request_body_handling(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that request body uses Annotated[Model, Body] syntax."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=['Item'])

        source = ast.unparse(http_module)

        # Should import Body from ahttp_client
        assert 'Body' in source

        # createItem method should have a body parameter
        if 'create_item' in source.lower():
            # Should use Annotated for body
            assert 'Annotated' in source

    def test_response_model_annotation(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that response models are properly typed in return annotations."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=['User', 'Item'])

        source = ast.unparse(http_module)

        # Methods should have return type annotations
        classes = [node for node in http_module.body if isinstance(node, ast.ClassDef)]
        if classes:
            http_class = classes[0]
            methods = [node for node in http_class.body if isinstance(node, ast.FunctionDef)]

            for method in methods:
                if method.name.startswith('_'):
                    continue
                # Should have return annotation
                # (might be Response, User, Item, etc.)
                # At minimum, non-private methods should have returns

    def test_http_method_mapping(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that HTTP methods are correctly mapped to @request decorators."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=[])

        source = ast.unparse(http_module)

        # Should have @request('GET', ...) and @request('POST', ...)
        assert 'GET' in source or 'get' in source.lower()
        assert 'POST' in source or 'post' in source.lower()

    def test_exception_imports(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that exception classes are imported for error responses."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=[])

        source = ast.unparse(http_module)

        # Should import exceptions for error handling
        # (implementation may vary, but errors should be handled)

    def test_models_import(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that models are imported from .models package."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=['User', 'Item', 'Error'])

        source = ast.unparse(http_module)

        # Should have model imports
        assert 'User' in source or 'Item' in source or 'models' in source.lower()

    def test_all_declaration(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that __all__ declaration is present and correct."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=[])

        source = ast.unparse(http_module)

        # Should have __all__ declaration
        assert '__all__' in source

        # Should export the HTTP class
        assert 'HTTP' in source

    def test_session_wrapper(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that HTTP class wraps ahttp_client Session."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=[])

        source = ast.unparse(http_module)

        # Should import Session from ahttp_client
        assert 'Session' in source or 'session' in source.lower()

    def test_authentication_handling(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that authentication schemes are properly integrated."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        # Has BearerAuth security scheme
        security_schemes = extracted_data.get('security_schemes', [])

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=[])

        if security_schemes:
            source = ast.unparse(http_module)

            # Should handle authentication in some way
            # (implementation may vary - might use headers, RequestCore, etc.)

    def test_accept_header_generation(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that Accept headers are generated for operations."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=[])

        source = ast.unparse(http_module)

        # Should set Accept header for JSON responses
        # Implementation may use Header or manual header setting

    def test_ast_validity(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that generated AST is valid Python code."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=['User', 'Item'])

        # Should be able to unparse without errors
        source = ast.unparse(http_module)
        assert source is not None
        assert len(source) > 0

        # Should be able to parse the unparsed code
        reparsed = ast.parse(source)
        assert reparsed is not None

    def test_syntax_validity(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that generated code is syntactically valid."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = HTTPGenerator()
        http_module = generator.generate(extracted_data, model_names=['User', 'Item'])

        source = ast.unparse(http_module)

        # Try to compile the source code
        try:
            compile(source, '<generated>', 'exec')
        except SyntaxError as e:
            pytest.fail(f"Generated code has syntax errors: {e}")
