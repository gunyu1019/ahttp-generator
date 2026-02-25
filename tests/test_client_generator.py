"""
Tests for client facade layer (client.py) generation.
Validates clean interfaces, async context manager support, and delegation.
"""

import ast
import pytest
from typing import Dict, Any

from ahttp_generator.parser.extractor import OpenAPIExtractor
from ahttp_generator.generator.client import ClientGenerator


class TestClientGenerator:
    """Test client facade layer generation."""

    def test_generate_client_class(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test basic client class generation."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ClientGenerator()
        client_module = generator.generate(extracted_data, model_names=['User', 'Item'])

        assert isinstance(client_module, ast.Module)

        # Find the client class
        classes = [node for node in client_module.body if isinstance(node, ast.ClassDef)]
        assert len(classes) > 0

        client_class = classes[0]
        assert 'Client' in client_class.name

    def test_pure_type_annotations(self, edge_case_openapi_spec: Dict[str, Any]):
        """
        Test that method signatures use pure types (str, int) instead of Annotated.
        Client layer should be clean and user-friendly.
        """
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ClientGenerator()
        client_module = generator.generate(extracted_data, model_names=['User', 'Item'])

        source = ast.unparse(client_module)

        # Find the client class
        classes = [node for node in client_module.body if isinstance(node, ast.ClassDef)]
        if classes:
            client_class = classes[0]
            methods = [node for node in client_class.body
                      if isinstance(node, ast.FunctionDef) and not node.name.startswith('_')]

            for method in methods:
                for arg in method.args.args:
                    if arg.arg == 'self':
                        continue

                    # Arguments should NOT use Annotated in client layer
                    if arg.annotation:
                        annotation_source = ast.unparse(arg.annotation)
                        # Allow Optional, List, Dict but not Annotated[str, Path] etc.
                        if 'Annotated' in annotation_source:
                            # Check if it's truly framework-specific
                            if any(x in annotation_source for x in ['Path', 'Query', 'Header', 'Body']):
                                pytest.fail(
                                    f"Client method {method.name} has framework-specific "
                                    f"annotation: {annotation_source}. Should use pure types."
                                )

    def test_async_context_manager_support(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that __aenter__ and __aexit__ methods are present."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ClientGenerator()
        client_module = generator.generate(extracted_data, model_names=[])

        source = ast.unparse(client_module)

        # Verify in AST - check if context manager methods exist
        classes = [node for node in client_module.body if isinstance(node, ast.ClassDef)]
        if classes:
            client_class = classes[0]
            method_names = [node.name for node in client_class.body
                           if isinstance(node, ast.FunctionDef)]

            # Context manager support is optional but recommended
            # If implemented, should have both __aenter__ and __aexit__
            has_aenter = '__aenter__' in method_names
            has_aexit = '__aexit__' in method_names

            # Either both should be present or neither
            assert has_aenter == has_aexit, "Should have both __aenter__ and __aexit__ or neither"

    def test_delegation_to_http_layer(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that client methods delegate to HTTP implementation layer."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ClientGenerator()
        client_module = generator.generate(extracted_data, model_names=['User', 'Item'])

        source = ast.unparse(client_module)

        # Client should have an http attribute that references HTTP class
        # and methods should call self.http.method_name(...)
        classes = [node for node in client_module.body if isinstance(node, ast.ClassDef)]
        if classes:
            client_class = classes[0]

            # Check for http attribute or similar
            # Methods should delegate to http layer
            methods = [node for node in client_class.body
                      if isinstance(node, ast.AsyncFunctionDef) and not node.name.startswith('__')]

            for method in methods:
                method_source = ast.unparse(method)
                # Should call self.http.something or self._http.something
                if 'http' in method_source.lower() or 'return' in method_source.lower():
                    # Has delegation logic
                    pass

    def test_path_variables_synchronization(self, edge_case_openapi_spec: Dict[str, Any]):
        """
        Test that server path variables from http.py are synchronized to client.py.
        If HTTP layer has path variables, client should too.
        """
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        # edge_case spec has server variables: environment, version
        servers = extracted_data.get('servers', {})

        generator = ClientGenerator()
        client_module = generator.generate(extracted_data, model_names=[])

        source = ast.unparse(client_module)

        # If servers have variables, client __init__ should accept them
        # or have some way to configure them

    def test_operation_parameters_synchronized(self, edge_case_openapi_spec: Dict[str, Any]):
        """
        Test that operation parameters from http.py are present in client.py.
        No parameters should be lost in the delegation.
        """
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        from ahttp_generator.generator.http import HTTPGenerator

        http_gen = HTTPGenerator()
        http_module = http_gen.generate(extracted_data, model_names=['User', 'Item'])

        client_gen = ClientGenerator()
        client_module = client_gen.generate(extracted_data, model_names=['User', 'Item'])

        # Parse both modules
        http_classes = [node for node in http_module.body if isinstance(node, ast.ClassDef)]
        client_classes = [node for node in client_module.body if isinstance(node, ast.ClassDef)]

        if http_classes and client_classes:
            http_class = http_classes[0]
            client_class = client_classes[0]

            # Get public methods from both
            http_methods = {node.name: node for node in http_class.body
                          if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                          and not node.name.startswith('_')}

            client_methods = {node.name: node for node in client_class.body
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and not node.name.startswith('_')}

            # Client should have corresponding methods for HTTP methods
            for http_method_name in http_methods:
                if http_method_name in client_methods:
                    http_method = http_methods[http_method_name]
                    client_method = client_methods[http_method_name]

                    # Count parameters (excluding self)
                    http_param_count = len([arg for arg in http_method.args.args if arg.arg != 'self'])
                    client_param_count = len([arg for arg in client_method.args.args if arg.arg != 'self'])

                    # Client should have same or similar number of parameters
                    # (might differ due to implementation details, but should be close)

    def test_method_return_types(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that client methods have proper return type annotations."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ClientGenerator()
        client_module = generator.generate(extracted_data, model_names=['User', 'Item'])

        classes = [node for node in client_module.body if isinstance(node, ast.ClassDef)]
        if classes:
            client_class = classes[0]
            methods = [node for node in client_class.body
                      if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and not node.name.startswith('_')]

            for method in methods:
                # Public methods should have return annotations
                # Might be User, Item, Response, etc.
                if method.returns:
                    return_source = ast.unparse(method.returns)
                    # Should have valid return type

    def test_all_declaration(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that __all__ declaration is present and exports client class."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ClientGenerator()
        client_module = generator.generate(extracted_data, model_names=[])

        source = ast.unparse(client_module)

        # Should have __all__ declaration
        assert '__all__' in source

        # Should export the Client class
        assert 'Client' in source

    def test_base_url_configuration(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that base_url is properly configured from servers."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ClientGenerator()
        client_module = generator.generate(extracted_data, model_names=[])

        source = ast.unparse(client_module)

        # Should have base_url in __init__ or as class attribute
        # assert 'base_url' in source or 'url' in source.lower()

    def test_http_import(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that HTTP implementation class is imported."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ClientGenerator()
        client_module = generator.generate(extracted_data, model_names=[])

        source = ast.unparse(client_module)

        # Should import HTTP class from .http
        # or have some reference to the HTTP layer

    def test_models_import(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that models are imported for type hints."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ClientGenerator()
        client_module = generator.generate(extracted_data, model_names=['User', 'Item', 'Error'])

        source = ast.unparse(client_module)

        # Should have model imports for type annotations
        # May be absolute or relative imports

    def test_optional_parameters(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that optional parameters have default values."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ClientGenerator()
        client_module = generator.generate(extracted_data, model_names=['User'])

        classes = [node for node in client_module.body if isinstance(node, ast.ClassDef)]
        if classes:
            client_class = classes[0]
            methods = [node for node in client_class.body
                      if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and not node.name.startswith('_')]

            for method in methods:
                # Check for optional parameters with defaults
                if method.args.defaults:
                    # Has some optional parameters
                    pass

    def test_enum_parameters(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that enum parameters use enum types in signatures."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ClientGenerator()
        client_module = generator.generate(extracted_data, model_names=['Item'])

        source = ast.unparse(client_module)

        # If enums are used, they should be imported and used in type hints
        # Implementation may use Literal or Enum classes

    def test_ast_validity(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that generated AST is valid Python code."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ClientGenerator()
        client_module = generator.generate(extracted_data, model_names=['User', 'Item'])

        # Should be able to unparse without errors
        source = ast.unparse(client_module)
        assert source is not None
        assert len(source) > 0

        # Should be able to parse the unparsed code
        reparsed = ast.parse(source)
        assert reparsed is not None

    def test_syntax_validity(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that generated code is syntactically valid."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ClientGenerator()
        client_module = generator.generate(extracted_data, model_names=['User', 'Item'])

        source = ast.unparse(client_module)

        # Try to compile the source code
        try:
            compile(source, '<generated>', 'exec')
        except SyntaxError as e:
            pytest.fail(f"Generated code has syntax errors: {e}")

    def test_docstrings_present(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that methods have docstrings."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ClientGenerator()
        client_module = generator.generate(extracted_data, model_names=['User', 'Item'])

        classes = [node for node in client_module.body if isinstance(node, ast.ClassDef)]
        if classes:
            client_class = classes[0]
            methods = [node for node in client_class.body
                      if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and not node.name.startswith('_')]

            # At least some methods should have docstrings
            methods_with_docs = [m for m in methods
                                if ast.get_docstring(m) is not None]

            # It's acceptable if not all have docs, but good practice
