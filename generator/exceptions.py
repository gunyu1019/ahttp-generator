"""
Exception classes generator module.
Generates exception classes from OpenAPI error responses.
"""

import ast
from typing import Dict, Any, List, Set

from core.ast_helper import ASTHelper
from core.type_mapper import TypeMapper


class ExceptionsGenerator:
    """Generates exception classes from OpenAPI error responses."""

    def __init__(self):
        self.ast_helper = ASTHelper()
        self.type_mapper = TypeMapper()

    # HTTP status code to exception name mapping
    STATUS_CODE_NAMES = {
        '400': 'BadRequestError',
        '401': 'UnauthorizedError',
        '403': 'ForbiddenError',
        '404': 'NotFoundError',
        '405': 'MethodNotAllowedError',
        '409': 'ConflictError',
        '422': 'UnprocessableEntityError',
        '429': 'TooManyRequestsError',
        '500': 'InternalServerError',
        '502': 'BadGatewayError',
        '503': 'ServiceUnavailableError',
        '504': 'GatewayTimeoutError'
    }

    def generate(self, extracted_data: Dict[str, Any]) -> Dict[str, ast.Module]:
        """
        Generate AST modules for exception files.

        Args:
            extracted_data: Extracted OpenAPI data

        Returns:
            Dict mapping filenames to AST modules
        """
        error_responses = extracted_data.get('error_responses', {})
        exception_modules = {}

        # Generate base exception class
        base_module = self._create_base_exception_module()
        exception_modules['base.py'] = base_module

        # Generate specific exception classes for each error status
        exception_names = []
        for status_code, error_info in error_responses.items():
            exception_name = self._get_exception_name(status_code)
            exception_names.append(exception_name)

            module = self._create_exception_module(
                status_code,
                exception_name,
                error_info['description']
            )

            filename = self._to_snake_case(exception_name) + '.py'
            exception_modules[filename] = module

        # Generate exceptions/__init__.py
        init_module = self._create_exceptions_init_module(['BaseClientException'] + exception_names)
        exception_modules['__init__.py'] = init_module

        return exception_modules

    def _create_base_exception_module(self) -> ast.Module:
        """Create base exception module."""
        body = []

        # Create base exception class
        class_body = []

        # Add docstring
        docstring = ast.Expr(
            value=ast.Constant(value="Base exception class for all API client errors.")
        )
        class_body.append(docstring)

        # Add __init__ method
        init_method = self._create_base_exception_init()
        class_body.append(init_method)

        # Add __str__ method
        str_method = self._create_base_exception_str()
        class_body.append(str_method)

        # Create class
        base_class = self.ast_helper.create_class_def(
            name='BaseClientException',
            bases=['Exception'],
            body=class_body
        )
        body.append(base_class)

        # Create module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)

        return module

    def _create_base_exception_init(self) -> ast.FunctionDef:
        """Create __init__ method for base exception."""
        # Create arguments
        args = [
            self.ast_helper.create_arg('self'),
            self.ast_helper.create_arg('message', ast.Name(id='str', ctx=ast.Load())),
            self.ast_helper.create_arg('status_code', ast.Name(id='int', ctx=ast.Load())),
            self.ast_helper.create_arg('response', ast.Name(id='dict', ctx=ast.Load()))
        ]

        # Set default values for optional parameters
        defaults = [
            ast.Constant(value=None),  # response default
        ]

        # Create method body
        body = [
            # super().__init__(message)
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
                    args=[ast.Name(id='message', ctx=ast.Load())],
                    keywords=[]
                )
            ),
            # self.status_code = status_code
            self.ast_helper.create_assign(
                'self.status_code',
                ast.Name(id='status_code', ctx=ast.Load())
            ),
            # self.response = response
            self.ast_helper.create_assign(
                'self.response',
                ast.Name(id='response', ctx=ast.Load())
            )
        ]

        # Update function def creation to support defaults
        func_def = ast.FunctionDef(
            name='__init__',
            args=ast.arguments(
                posonlyargs=[],
                args=args,
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=defaults
            ),
            body=body,
            decorator_list=[],
            returns=None
        )

        return ast.fix_missing_locations(func_def)

    def _create_base_exception_str(self) -> ast.FunctionDef:
        """Create __str__ method for base exception."""
        args = [self.ast_helper.create_arg('self')]

        # Create body: return f"HTTP {self.status_code}: {super().__str__()}"
        body = [
            ast.Return(
                value=ast.JoinedStr(
                    values=[
                        ast.Constant(value='HTTP '),
                        ast.FormattedValue(
                            value=ast.Attribute(
                                value=ast.Name(id='self', ctx=ast.Load()),
                                attr='status_code',
                                ctx=ast.Load()
                            ),
                            conversion=-1,
                            format_spec=None
                        ),
                        ast.Constant(value=': '),
                        ast.FormattedValue(
                            value=ast.Call(
                                func=ast.Attribute(
                                    value=ast.Call(
                                        func=ast.Name(id='super', ctx=ast.Load()),
                                        args=[],
                                        keywords=[]
                                    ),
                                    attr='__str__',
                                    ctx=ast.Load()
                                ),
                                args=[],
                                keywords=[]
                            ),
                            conversion=-1,
                            format_spec=None
                        )
                    ]
                )
            )
        ]

        return self.ast_helper.create_function_def(
            name='__str__',
            args=args,
            body=body,
            returns=ast.Name(id='str', ctx=ast.Load())
        )

    def _create_exception_module(self, status_code: str, exception_name: str, description: str) -> ast.Module:
        """Create specific exception module."""
        body = []

        # Add import for base exception
        import_stmt = self.ast_helper.create_relative_import('base', ['BaseClientException'])
        body.append(import_stmt)

        # Create exception class
        class_body = []

        # Add docstring with description
        docstring_text = f"{description}\n\nHTTP Status Code: {status_code}"
        docstring = ast.Expr(
            value=ast.Constant(value=docstring_text)
        )
        class_body.append(docstring)

        # Add __init__ method
        init_method = self._create_specific_exception_init(status_code)
        class_body.append(init_method)

        # Create class
        exception_class = self.ast_helper.create_class_def(
            name=exception_name,
            bases=['BaseClientException'],
            body=class_body
        )
        body.append(exception_class)

        # Create module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)

        return module

    def _create_specific_exception_init(self, status_code: str) -> ast.FunctionDef:
        """Create __init__ method for specific exception."""
        args = [
            self.ast_helper.create_arg('self'),
            self.ast_helper.create_arg('message', ast.Name(id='str', ctx=ast.Load())),
            self.ast_helper.create_arg('response', ast.Name(id='dict', ctx=ast.Load()))
        ]

        defaults = [
            ast.Constant(value=None),  # response default
        ]

        # Create method body
        body = [
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
                    args=[
                        ast.Name(id='message', ctx=ast.Load()),
                        ast.Constant(value=int(status_code)),
                        ast.Name(id='response', ctx=ast.Load())
                    ],
                    keywords=[]
                )
            )
        ]

        # Create function def with defaults
        func_def = ast.FunctionDef(
            name='__init__',
            args=ast.arguments(
                posonlyargs=[],
                args=args,
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=defaults
            ),
            body=body,
            decorator_list=[],
            returns=None
        )

        return ast.fix_missing_locations(func_def)

    def _create_exceptions_init_module(self, exception_names: List[str]) -> ast.Module:
        """Create __init__.py module that exports all exceptions."""
        body = []

        # Import base exception
        base_import = self.ast_helper.create_relative_import('base', ['BaseClientException'])
        body.append(base_import)

        # Import specific exceptions
        for exception_name in exception_names[1:]:  # Skip base exception
            filename = self._to_snake_case(exception_name)
            import_stmt = self.ast_helper.create_relative_import(filename, [exception_name])
            body.append(import_stmt)

        # Create __all__ list
        if exception_names:
            all_list = ast.List(
                elts=[ast.Constant(value=name) for name in exception_names],
                ctx=ast.Load()
            )
            all_assign = self.ast_helper.create_assign('__all__', all_list)
            body.append(all_assign)

        # Create module
        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)

        return module

    def _get_exception_name(self, status_code: str) -> str:
        """Get exception class name for status code."""
        return self.STATUS_CODE_NAMES.get(status_code, f'HttpError{status_code}')

    def _to_snake_case(self, pascal_case: str) -> str:
        """Convert PascalCase to snake_case."""
        import re
        # Insert underscore before uppercase letters (except first)
        snake_case = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', pascal_case)
        snake_case = re.sub('([a-z0-9])([A-Z])', r'\1_\2', snake_case)
        return snake_case.lower()
