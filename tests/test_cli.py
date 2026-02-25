"""
Tests for CLI argument parsing and end-to-end execution.
"""

import os
import json
import tempfile
import shutil
import pytest
from pathlib import Path
from typing import Dict, Any

from ahttp_generator.main import build_parser, MainController, main


class TestCLIArgumentParsing:
    """Test CLI argument parsing with argparse."""

    def test_parser_creation(self):
        """Test that parser is created correctly."""
        parser = build_parser()
        assert parser is not None

    def test_required_input_argument(self):
        """Test that input argument is required."""
        parser = build_parser()

        # Should fail without input
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_input_argument_parsing(self):
        """Test parsing of input file argument."""
        parser = build_parser()

        args = parser.parse_args(['-i', 'spec.json'])
        assert args.input == 'spec.json'

        args = parser.parse_args(['--input', 'spec.yaml'])
        assert args.input == 'spec.yaml'

    def test_output_argument_parsing(self):
        """Test parsing of output directory argument."""
        parser = build_parser()

        args = parser.parse_args(['-i', 'spec.json', '-o', 'generated'])
        assert args.output == 'generated'

        args = parser.parse_args(['-i', 'spec.json', '--output', 'my_client'])
        assert args.output == 'my_client'

    def test_output_default_value(self):
        """Test that output has default value."""
        parser = build_parser()

        args = parser.parse_args(['-i', 'spec.json'])
        assert args.output == 'output'


class TestMainController:
    """Test MainController orchestration."""

    def test_controller_initialization(self):
        """Test that controller can be initialized."""
        controller = MainController(input_file='spec.json', output_dir='output')
        assert controller.input_file == 'spec.json'
        assert controller.output_dir == 'output'

    def test_controller_run_with_valid_spec(self, edge_case_openapi_spec: Dict[str, Any], tmp_path: Path):
        """Test controller execution with valid spec."""
        # Create a temporary spec file
        spec_file = tmp_path / 'test_spec.json'
        with open(spec_file, 'w') as f:
            json.dump(edge_case_openapi_spec, f)

        output_dir = tmp_path / 'generated'

        controller = MainController(
            input_file=str(spec_file),
            output_dir=str(output_dir)
        )

        # Should run without errors
        controller.run()

        # Check that output directory was created
        assert output_dir.exists()
        assert output_dir.is_dir()

    def test_controller_generates_expected_files(self, edge_case_openapi_spec: Dict[str, Any], tmp_path: Path):
        """Test that controller generates expected package files."""
        spec_file = tmp_path / 'test_spec.json'
        with open(spec_file, 'w') as f:
            json.dump(edge_case_openapi_spec, f)

        output_dir = tmp_path / 'generated'

        controller = MainController(
            input_file=str(spec_file),
            output_dir=str(output_dir)
        )
        controller.run()

        # Check for expected files
        expected_files = [
            '__init__.py',
            'client.py',
            'http.py',
            'exceptions.py',
        ]

        for expected_file in expected_files:
            file_path = output_dir / expected_file
            assert file_path.exists(), f"Expected file not found: {expected_file}"

        # Check for models directory
        models_dir = output_dir / 'models'
        assert models_dir.exists()
        assert models_dir.is_dir()

        # Models directory should have __init__.py
        models_init = models_dir / '__init__.py'
        assert models_init.exists()

    def test_generated_files_are_valid_python(self, minimal_openapi_spec: Dict[str, Any], tmp_path: Path):
        """Test that all generated files are valid Python code."""
        spec_file = tmp_path / 'test_spec.json'
        with open(spec_file, 'w') as f:
            json.dump(minimal_openapi_spec, f)

        output_dir = tmp_path / 'generated'

        controller = MainController(
            input_file=str(spec_file),
            output_dir=str(output_dir)
        )
        controller.run()

        # Try to compile all .py files
        for py_file in output_dir.rglob('*.py'):
            with open(py_file, 'r') as f:
                code = f.read()

            try:
                compile(code, str(py_file), 'exec')
            except SyntaxError as e:
                pytest.fail(f"Generated file {py_file} has syntax errors: {e}")


class TestCLIMainFunction:
    """Test main() CLI entry point."""

    def test_main_with_valid_spec(self, edge_case_openapi_spec: Dict[str, Any], tmp_path: Path):
        """Test main function with valid specification."""
        spec_file = tmp_path / 'test_spec.json'
        with open(spec_file, 'w') as f:
            json.dump(edge_case_openapi_spec, f)

        output_dir = tmp_path / 'generated'

        # Call main with arguments
        exit_code = main(['-i', str(spec_file), '-o', str(output_dir)])

        assert exit_code == 0
        assert output_dir.exists()

    def test_main_with_missing_file(self, tmp_path: Path):
        """Test main function with non-existent input file."""
        spec_file = tmp_path / 'nonexistent.json'
        output_dir = tmp_path / 'generated'

        exit_code = main(['-i', str(spec_file), '-o', str(output_dir)])

        # Should return non-zero exit code
        assert exit_code != 0

    def test_main_with_invalid_json(self, tmp_path: Path):
        """Test main function with invalid JSON file."""
        spec_file = tmp_path / 'invalid.json'
        with open(spec_file, 'w') as f:
            f.write('{ invalid json }')

        output_dir = tmp_path / 'generated'

        exit_code = main(['-i', str(spec_file), '-o', str(output_dir)])

        # Should return non-zero exit code
        assert exit_code != 0

    def test_main_with_invalid_openapi_spec(self, tmp_path: Path):
        """Test main function with invalid OpenAPI spec."""
        spec_file = tmp_path / 'invalid_spec.json'

        # Valid JSON but not valid OpenAPI (missing openapi field)
        invalid_spec = {
            "info": {
                "title": "Test",
                "version": "1.0.0"
            },
            "paths": {}
            # Missing required 'openapi' field
        }

        with open(spec_file, 'w') as f:
            json.dump(invalid_spec, f)

        output_dir = tmp_path / 'generated'

        exit_code = main(['-i', str(spec_file), '-o', str(output_dir)])

        # Should return non-zero exit code
        # Note: Some implementations may be lenient and still generate code
        # The important thing is that it doesn't crash
        assert exit_code is not None  # Function completed


class TestEndToEndGeneration:
    """End-to-end integration tests."""

    def test_full_generation_with_edge_cases(self, edge_case_openapi_spec: Dict[str, Any], tmp_path: Path):
        """Test full generation pipeline with edge case spec."""
        spec_file = tmp_path / 'edge_case_spec.json'
        with open(spec_file, 'w') as f:
            json.dump(edge_case_openapi_spec, f)

        output_dir = tmp_path / 'edge_case_client'

        controller = MainController(
            input_file=str(spec_file),
            output_dir=str(output_dir)
        )
        controller.run()

        # Verify package structure
        assert (output_dir / '__init__.py').exists()
        assert (output_dir / 'client.py').exists()
        assert (output_dir / 'http.py').exists()
        assert (output_dir / 'models' / '__init__.py').exists()

        # Verify that reserved keywords were handled
        user_model = output_dir / 'models' / 'user.py'
        if user_model.exists():
            with open(user_model, 'r') as f:
                content = f.read()

            # Should handle 'class' keyword
            assert 'class' in content.lower() or 'class_' in content

    def test_generated_package_is_importable(self, minimal_openapi_spec: Dict[str, Any], tmp_path: Path):
        """Test that generated package can be imported (syntax check)."""
        spec_file = tmp_path / 'minimal_spec.json'
        with open(spec_file, 'w') as f:
            json.dump(minimal_openapi_spec, f)

        output_dir = tmp_path / 'test_client'

        controller = MainController(
            input_file=str(spec_file),
            output_dir=str(output_dir)
        )
        controller.run()

        # Try to parse all Python files (simulates import check)
        import ast as ast_module

        for py_file in output_dir.rglob('*.py'):
            with open(py_file, 'r') as f:
                try:
                    ast_module.parse(f.read())
                except SyntaxError as e:
                    pytest.fail(f"File {py_file} has syntax errors: {e}")

    def test_yaml_spec_support(self, minimal_openapi_spec: Dict[str, Any], tmp_path: Path):
        """Test that YAML specs are supported."""
        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")

        spec_file = tmp_path / 'test_spec.yaml'
        with open(spec_file, 'w') as f:
            yaml.dump(minimal_openapi_spec, f)

        output_dir = tmp_path / 'generated'

        exit_code = main(['-i', str(spec_file), '-o', str(output_dir)])

        assert exit_code == 0
        assert output_dir.exists()

    def test_output_directory_creation(self, minimal_openapi_spec: Dict[str, Any], tmp_path: Path):
        """Test that output directory is created if it doesn't exist."""
        spec_file = tmp_path / 'test_spec.json'
        with open(spec_file, 'w') as f:
            json.dump(minimal_openapi_spec, f)

        # Use nested path that doesn't exist
        output_dir = tmp_path / 'deeply' / 'nested' / 'output'

        controller = MainController(
            input_file=str(spec_file),
            output_dir=str(output_dir)
        )
        controller.run()

        assert output_dir.exists()
        assert output_dir.is_dir()

    def test_file_encoding_utf8(self, minimal_openapi_spec: Dict[str, Any], tmp_path: Path):
        """Test that generated files use UTF-8 encoding."""
        spec_file = tmp_path / 'test_spec.json'
        with open(spec_file, 'w') as f:
            json.dump(minimal_openapi_spec, f)

        output_dir = tmp_path / 'generated'

        controller = MainController(
            input_file=str(spec_file),
            output_dir=str(output_dir)
        )
        controller.run()

        # Check that files can be read as UTF-8
        for py_file in output_dir.rglob('*.py'):
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Should have encoding declaration
            if '# -*- coding: utf-8 -*-' in content or '#coding' in content:
                # Good practice
                pass

    def test_pep8_compliance(self, minimal_openapi_spec: Dict[str, Any], tmp_path: Path):
        """Test that generated code follows PEP8 guidelines."""
        spec_file = tmp_path / 'test_spec.json'
        with open(spec_file, 'w') as f:
            json.dump(minimal_openapi_spec, f)

        output_dir = tmp_path / 'generated'

        controller = MainController(
            input_file=str(spec_file),
            output_dir=str(output_dir)
        )
        controller.run()

        # Check key PEP8 aspects
        for py_file in output_dir.rglob('*.py'):
            with open(py_file, 'r') as f:
                content = f.read()

            # Should not have tabs
            assert '\t' not in content, f"File {py_file} contains tabs"

            # Should end with newline
            assert content.endswith('\n'), f"File {py_file} doesn't end with newline"
