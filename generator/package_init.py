"""
Package __init__.py generator module.
Generates __init__.py for the generated package with proper exports.
"""

import ast
from typing import Dict, Any, List

from core.ast_helper import ASTHelper


class PackageInitGenerator:
    """Generates __init__.py for the generated package."""

    def __init__(self):
        self.ast_helper = ASTHelper()

    def generate(self, extracted_data: Dict[str, Any], model_names: List[str]) -> ast.Module:
        """
        Generate AST module for __init__.py.

        Args:
            extracted_data: Extracted OpenAPI data
            model_names: List of generated model names

        Returns:
            AST module for __init__.py
        """
        service_name = extracted_data.get('service_name', 'ApiService')

        # Create module body
        body = []

        # Import and export service class
        service_import = self.ast_helper.create_relative_import('service', [service_name])
        body.append(service_import)

        # Import and export all models
        if model_names:
            models_import = self.ast_helper.create_import_all('models')
            body.append(models_import)

        # Create __all__ list for explicit exports
        all_exports = [service_name] + model_names
        all_list = ast.List(
            elts=[ast.Constant(value=name) for name in all_exports],
            ctx=ast.Load()
        )
        all_assign = self.ast_helper.create_assign('__all__', all_list)
        body.append(all_assign)

        # Create module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)

        return module

