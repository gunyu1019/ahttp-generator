"""
HTTP client generator module.
Generates base HTTP client class from OpenAPI specification.
"""

import ast
from typing import Dict, Any

from core.ast_helper import ASTHelper


class HTTPGenerator:
    """Generates base HTTP client class."""

    def __init__(self):
        self.ast_helper = ASTHelper()

    def generate(self, extracted_data: Dict[str, Any]) -> ast.Module:
        """
        Generate AST module for http.py.

        Args:
            extracted_data: Extracted OpenAPI data

        Returns:
            AST module for http.py
        """
        # Create module body
        body = []

        # Add import statement
        import_stmt = self.ast_helper.create_import('ahttp_client', ['Session'])
        body.append(import_stmt)

        # Create HTTPClient class
        http_client_class = self._create_http_client_class()
        body.append(http_client_class)

        # Create module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)

        return module

    def _create_http_client_class(self) -> ast.ClassDef:
        """Create HTTPClient class definition."""
        # Create class body
        class_body = []

        # Add docstring
        docstring = ast.Expr(
            value=ast.Constant(value="Base HTTP client class for API communication.")
        )
        class_body.append(docstring)

        # Add __init__ method
        init_method = self._create_init_method()
        class_body.append(init_method)

        # Create class
        return self.ast_helper.create_class_def(
            name='HTTPClient',
            bases=['Session'],
            body=class_body
        )

    def _create_init_method(self) -> ast.FunctionDef:
        """Create __init__ method for HTTPClient."""
        # Create arguments
        args = [
            self.ast_helper.create_arg('self'),
            self.ast_helper.create_arg('base_url', ast.Name(id='str', ctx=ast.Load()))
        ]

        # Create method body
        body = [
            # super().__init__(base_url)
            ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Call(
                            func=ast.Name(id='super', ctx=ast.Load()),
                            args=[],
                            keywords=[]
                        ),
                        attr='__init__',
                        ctx=ast.Load()
                    ),
                    args=[ast.Name(id='base_url', ctx=ast.Load())],
                    keywords=[]
                )
            )
        ]

        return self.ast_helper.create_function_def(
            name='__init__',
            args=args,
            body=body
        )
