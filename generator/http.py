"""
HTTP client generator module.
Generates base HTTP client class from OpenAPI specification.
"""

import ast
from typing import Dict, Any, List

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
        # Get status code mapping for exception handling
        status_code_mapping = extracted_data.get('status_code_mapping', {})
        error_responses = extracted_data.get('error_responses', {})

        # Create module body
        body = []

        # Add import statements
        import_statements = self._create_imports(status_code_mapping)
        body.extend(import_statements)

        # Create HTTPClient class
        http_client_class = self._create_http_client_class(status_code_mapping)
        body.append(http_client_class)

        # Create module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)

        return module

    def _create_imports(self, status_code_mapping: Dict[int, str]) -> List[ast.stmt]:
        """Create import statements including exception imports."""
        imports = []

        # Import ahttp_client Session
        imports.append(self.ast_helper.create_import('ahttp_client', ['Session']))

        # Import exceptions if any exist
        if status_code_mapping:
            # Get unique exception names
            exception_names = list(set(status_code_mapping.values()))
            imports.append(self.ast_helper.create_relative_import('exceptions', exception_names))

        return imports

    def _create_http_client_class(self, status_code_mapping: Dict[int, str]) -> ast.ClassDef:
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

        # Add after_request hook method if there are error responses
        if status_code_mapping:
            after_request_method = self._create_after_request_method(status_code_mapping)
            class_body.append(after_request_method)

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

    def _create_after_request_method(self, status_code_mapping: Dict[int, str]) -> ast.AsyncFunctionDef:
        """Create after_request hook method for automatic exception handling."""
        # Create arguments: self, response, context
        args = [
            self.ast_helper.create_arg('self'),
            self.ast_helper.create_arg('response'),
            self.ast_helper.create_arg('context')
        ]

        # Create method body
        body = []

        # Sort status codes for consistent ordering
        sorted_status_codes = sorted(status_code_mapping.keys())

        # Create if/elif chain for status code checking
        if sorted_status_codes:
            first_status = sorted_status_codes[0]
            remaining_status_codes = sorted_status_codes[1:]

            # Create the first if statement
            if_stmt = self._create_status_check_if(first_status, status_code_mapping[first_status], remaining_status_codes, status_code_mapping)
            body.append(if_stmt)

        # Add return response statement
        return_stmt = ast.Return(value=ast.Name(id='response', ctx=ast.Load()))
        body.append(return_stmt)

        # Create async function definition
        func_def = ast.AsyncFunctionDef(
            name='after_request',
            args=ast.arguments(
                posonlyargs=[],
                args=args,
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[]
            ),
            body=body,
            decorator_list=[],
            returns=None
        )

        return ast.fix_missing_locations(func_def)

    def _create_status_check_if(self, status_code: int, exception_name: str, remaining_codes: List[int], mapping: Dict[int, str]) -> ast.If:
        """Create if/elif chain for status code checking."""
        # Create condition: response.status == status_code
        test = ast.Compare(
            left=ast.Attribute(
                value=ast.Name(id='response', ctx=ast.Load()),
                attr='status',
                ctx=ast.Load()
            ),
            ops=[ast.Eq()],
            comparators=[ast.Constant(value=status_code)]
        )

        # Create body: text = await response.text(); raise ExceptionName(text)
        body = [
            # text = await response.text()
            ast.Assign(
                targets=[ast.Name(id='text', ctx=ast.Store())],
                value=ast.Await(
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id='response', ctx=ast.Load()),
                            attr='text',
                            ctx=ast.Load()
                        ),
                        args=[],
                        keywords=[]
                    )
                )
            ),
            # raise ExceptionName(text)
            ast.Raise(
                exc=ast.Call(
                    func=ast.Name(id=exception_name, ctx=ast.Load()),
                    args=[ast.Name(id='text', ctx=ast.Load())],
                    keywords=[]
                ),
                cause=None
            )
        ]

        # Create orelse (elif chain) for remaining status codes
        orelse = []
        if remaining_codes:
            next_status = remaining_codes[0]
            next_remaining = remaining_codes[1:]
            orelse = [self._create_status_check_if(next_status, mapping[next_status], next_remaining, mapping)]

        if_stmt = ast.If(test=test, body=body, orelse=orelse)
        return ast.fix_missing_locations(if_stmt)

