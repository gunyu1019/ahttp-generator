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

        Uses the same naming as ClientGenerator: client class name is derived from
        service_name (e.g. ApiService -> ApiClient, Pubg -> PubgClient via info.title).

        Args:
            extracted_data: Extracted OpenAPI data
            model_names: List of generated model names

        Returns:
            AST module for __init__.py
        """
        service_name = extracted_data.get('service_name', 'ApiService')
        # Same naming rule as client.py: ApiService -> ApiClient, Pubg -> PubgClient
        client_class_name = service_name.replace('Service', 'Client')

        body = []

        # Export main client facade from .client (replaces legacy .service / ApiService)
        client_import = self.ast_helper.create_relative_import('client', [client_class_name])
        body.append(client_import)

        # Domain models for type hints
        if model_names:
            body.append(self.ast_helper.create_import_all('models'))

        # Response models for type hints (only when models/response.py exists)
        if extracted_data.get('response_models'):
            body.append(self.ast_helper.create_import_all('models.response', level=1))

        # __all__: primary export is the client class (PEP 8 blank line before __all__)
        all_list = ast.List(
            elts=[ast.Constant(value=client_class_name)],
            ctx=ast.Load()
        )
        body.append(self.ast_helper.create_assign('__all__', all_list))

        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)
        return module

