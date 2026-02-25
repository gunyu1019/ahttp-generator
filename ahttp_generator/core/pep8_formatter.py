# Copyright (c) 2026 gunyu1019
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""
PEP 8 formatting utilities for code generation.
"""
import ast
from typing import List


class PEP8Formatter:
    """Utility class for PEP 8 compliant code generation."""

    @staticmethod
    def create_file_header() -> List[ast.stmt]:
        """
        Create PEP 8 compliant file header with encoding and auto-generation warning.

        Returns:
            List of AST statements for file header (empty - handled in formatting)
        """
        # Don't add docstring here - will be handled in post-processing
        return []

    @staticmethod
    def sort_imports(imports: List[ast.stmt]) -> List[ast.stmt]:
        """
        Sort imports according to PEP 8 guidelines:
        1. Standard library imports
        2. Third-party library imports
        3. Local/relative imports

        Args:
            imports: List of import statements

        Returns:
            Sorted import statements
        """
        standard_lib = []
        third_party = []
        local_imports = []

        for imp in imports:
            if isinstance(imp, ast.Import):
                # Standard library check (simplified)
                module_name = imp.names[0].name
                if module_name in ['typing', 'os', 'sys', 'json', 're', 'datetime', 'collections']:
                    standard_lib.append(imp)
                else:
                    third_party.append(imp)
            elif isinstance(imp, ast.ImportFrom):
                if imp.module and imp.module.startswith('.'):
                    # Relative import
                    local_imports.append(imp)
                elif imp.module in ['typing', 'os', 'sys', 'json', 're', 'datetime', 'collections']:
                    standard_lib.append(imp)
                elif imp.module and imp.module.startswith(('ahttp_client', 'pydantic')):
                    third_party.append(imp)
                else:
                    local_imports.append(imp)
            else:
                # Default to third party
                third_party.append(imp)

        # Combine groups - don't add blank lines here, they'll be handled by unparse formatting
        result = []
        result.extend(standard_lib)
        result.extend(third_party)
        result.extend(local_imports)

        return result

    @staticmethod
    def create_all_declaration(class_names: List[str]) -> ast.Assign:
        """
        Create __all__ declaration for module exports.

        Args:
            class_names: List of class names to export

        Returns:
            AST assignment for __all__ declaration
        """
        return ast.Assign(
            targets=[ast.Name(id='__all__', ctx=ast.Store())],
            value=ast.List(
                elts=[ast.Constant(value=name) for name in class_names],
                ctx=ast.Load()
            )
        )

    @staticmethod
    def detect_typing_imports(module: ast.Module) -> set:
        """
        Analyze AST module to detect required typing imports.

        Args:
            module: AST module to analyze

        Returns:
            Set of typing imports needed
        """
        typing_imports = set()

        class TypingVisitor(ast.NodeVisitor):
            def visit_Name(self, node):
                if node.id in ['Optional', 'List', 'Dict', 'Any', 'Tuple', 'Union']:
                    typing_imports.add(node.id)
                self.generic_visit(node)

            def visit_Subscript(self, node):
                if isinstance(node.value, ast.Name) and node.value.id in ['Optional', 'List', 'Dict', 'Tuple', 'Union']:
                    typing_imports.add(node.value.id)
                self.generic_visit(node)

        visitor = TypingVisitor()
        visitor.visit(module)

        return typing_imports

    @staticmethod
    def add_proper_spacing(module: ast.Module) -> ast.Module:
        """
        Add proper spacing between classes and functions according to PEP 8.
        This is a post-processing step after AST generation.

        Args:
            module: AST module to format

        Returns:
            Module with proper spacing
        """
        # Note: Actual spacing is handled during code writing/unparsing
        # This method can be used for any special spacing logic
        return module



