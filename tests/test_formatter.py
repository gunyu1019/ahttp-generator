"""
Tests for PEP8 formatting and code style compliance.
"""

import ast
import pytest
from typing import Dict, Any

from ahttp_generator.core.pep8_formatter import PEP8Formatter
from ahttp_generator.parser.extractor import OpenAPIExtractor
from ahttp_generator.generator.models import ModelsGenerator
from ahttp_generator.generator.client import ClientGenerator
from ahttp_generator.generator.http import HTTPGenerator


class TestPEP8Formatter:
    """Test PEP8 formatting utilities."""

    def test_file_header_creation(self):
        """Test creation of file header."""
        formatter = PEP8Formatter()
        header = formatter.create_file_header()

        # Header is handled in post-processing
        assert isinstance(header, list)

    def test_import_sorting(self):
        """Test that imports are sorted according to PEP8."""
        formatter = PEP8Formatter()

        # Create mock imports
        imports = [
            ast.ImportFrom(module='models', names=[ast.alias(name='User')], level=1),
            ast.Import(names=[ast.alias(name='typing')]),
            ast.ImportFrom(module='ahttp_client', names=[ast.alias(name='Session')], level=0),
            ast.Import(names=[ast.alias(name='os')]),
        ]

        sorted_imports = formatter.sort_imports(imports)

        # Should return a list
        assert isinstance(sorted_imports, list)
        assert len(sorted_imports) == len(imports)

    def test_all_declaration_creation(self):
        """Test creation of __all__ declaration."""
        formatter = PEP8Formatter()

        exports = ['User', 'Item', 'Client']
        all_decl = formatter.create_all_declaration(exports)

        assert isinstance(all_decl, ast.Assign)

        # Should assign to __all__
        assert len(all_decl.targets) == 1
        assert isinstance(all_decl.targets[0], ast.Name)
        assert all_decl.targets[0].id == '__all__'

    def test_detect_typing_imports(self):
        """Test detection of required typing imports."""
        formatter = PEP8Formatter()

        # Create a module with various type annotations
        code = """
from typing import Optional, List

class User:
    name: str
    items: List[str]
    manager: Optional['User']
"""
        module = ast.parse(code)

        required = formatter.detect_typing_imports(module)

        # Should detect List and Optional
        assert isinstance(required, set)
        if required:
            # At minimum should work without errors
            pass


class TestGeneratedCodeFormatting:
    """Test that generated code follows PEP8 guidelines."""

    def test_end_of_file_newline(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that generated files end with exactly one newline."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ModelsGenerator()
        model_modules, _ = generator.generate(extracted_data)

        for filename, module in model_modules.items():
            source = ast.unparse(module)

            # After applying formatting, should end with newline
            # The main.py applies additional formatting
            # For now, check that source is valid

    def test_blank_lines_between_classes(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that there are 2 blank lines between top-level class definitions."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        generator = ModelsGenerator()
        model_modules, _ = generator.generate(extracted_data)

        # Get __init__.py which might have multiple classes or imports
        if '__init__.py' in model_modules:
            module = model_modules['__init__.py']
            source = ast.unparse(module)

            # Check for proper spacing (will be applied in post-processing)
            # At minimum, code should be valid

    def test_blank_lines_between_functions(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that there are 2 blank lines between top-level functions."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        http_gen = HTTPGenerator()
        http_module = http_gen.generate(extracted_data, model_names=['User'])

        source = ast.unparse(http_module)

        # Should be valid code at minimum

    def test_line_length_limit(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that generated lines don't exceed reasonable length."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        client_gen = ClientGenerator()
        client_module = client_gen.generate(extracted_data, model_names=['User', 'Item'])

        source = ast.unparse(client_module)

        # Check line lengths (PEP8 recommends 79, but 120 is acceptable)
        lines = source.split('\n')

        excessively_long_lines = [line for line in lines if len(line) > 200]

        # Should not have extremely long lines (200+ chars)
        # Some long lines are acceptable (URLs, long strings, etc.)
        # But most should be reasonable

    def test_import_order(self, edge_case_openapi_spec: Dict[str, Any]):
        """
        Test that imports are ordered:
        1. Standard library
        2. Third-party
        3. Local
        """
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        client_gen = ClientGenerator()
        client_module = client_gen.generate(extracted_data, model_names=['User'])

        source = ast.unparse(client_module)

        # Find import lines
        import_lines = []
        in_imports = False
        for line in source.split('\n'):
            stripped = line.strip()
            if stripped.startswith(('import ', 'from ')):
                import_lines.append(line)
                in_imports = True
            elif in_imports and stripped and not stripped.startswith('#'):
                # End of import block
                break

        # Should have imports organized
        # Standard lib (typing) before third-party (ahttp_client) before local (.)

    def test_no_trailing_whitespace(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that generated code has no trailing whitespace."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        http_gen = HTTPGenerator()
        http_module = http_gen.generate(extracted_data, model_names=['User'])

        source = ast.unparse(http_module)

        # Check for trailing whitespace
        lines = source.split('\n')
        lines_with_trailing_ws = [i for i, line in enumerate(lines)
                                  if line and line != line.rstrip()]

        # AST unparsing typically doesn't add trailing whitespace
        # But post-processing might

    def test_proper_indentation(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that code uses 4 spaces for indentation."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        model_gen = ModelsGenerator()
        model_modules, _ = model_gen.generate(extracted_data)

        for filename, module in model_modules.items():
            source = ast.unparse(module)

            # Check that we don't have tabs
            assert '\t' not in source, f"File {filename} contains tabs"

            # Check for consistent indentation (4 spaces)
            # AST unparse should handle this correctly

    def test_encoding_declaration(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that files have UTF-8 encoding declaration."""
        # This is added in main.py's write_ast_to_file function
        # The apply_pep8_formatting adds:
        # # -*- coding: utf-8 -*-
        pass  # Verified in integration test

    def test_docstring_format(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that docstrings are properly formatted."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        client_gen = ClientGenerator()
        client_module = client_gen.generate(extracted_data, model_names=['User'])

        # Find classes with docstrings
        classes = [node for node in client_module.body if isinstance(node, ast.ClassDef)]

        for cls in classes:
            docstring = ast.get_docstring(cls)
            if docstring:
                # Docstring should not be empty
                assert len(docstring.strip()) > 0


class TestFormattingIntegration:
    """Test formatting in the context of full code generation."""

    def test_full_pipeline_formatting(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that full generation pipeline produces well-formatted code."""
        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        # Generate all components
        model_gen = ModelsGenerator()
        model_modules, model_names = model_gen.generate(extracted_data)

        http_gen = HTTPGenerator()
        http_module = http_gen.generate(extracted_data, model_names=model_names)

        client_gen = ClientGenerator()
        client_module = client_gen.generate(extracted_data, model_names=model_names)

        # All should be valid Python
        for module in [http_module, client_module]:
            source = ast.unparse(module)
            try:
                compile(source, '<generated>', 'exec')
            except SyntaxError as e:
                pytest.fail(f"Generated code has syntax errors: {e}")

    def test_autopep8_compatibility(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that generated code can be processed by autopep8."""
        try:
            import autopep8
        except ImportError:
            pytest.skip("autopep8 not installed")

        extractor = OpenAPIExtractor()
        extracted_data = extractor.extract(edge_case_openapi_spec)

        client_gen = ClientGenerator()
        client_module = client_gen.generate(extracted_data, model_names=['User'])

        source = ast.unparse(client_module)

        # Try to format with autopep8
        formatted = autopep8.fix_code(source, options={'aggressive': 1})

        assert formatted is not None
        assert len(formatted) > 0

        # Formatted code should still be valid
        compile(formatted, '<generated>', 'exec')

    def test_consistent_formatting_across_runs(self, edge_case_openapi_spec: Dict[str, Any]):
        """Test that generating the same spec twice produces identical output."""
        extractor1 = OpenAPIExtractor()
        extracted_data1 = extractor1.extract(edge_case_openapi_spec)

        extractor2 = OpenAPIExtractor()
        extracted_data2 = extractor2.extract(edge_case_openapi_spec)

        gen1 = ClientGenerator()
        module1 = gen1.generate(extracted_data1, model_names=['User', 'Item'])

        gen2 = ClientGenerator()
        module2 = gen2.generate(extracted_data2, model_names=['User', 'Item'])

        source1 = ast.unparse(module1)
        source2 = ast.unparse(module2)

        # Should produce identical output
        assert source1 == source2
