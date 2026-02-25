# Copyright (c) 2026 gunyu1019
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""
Exception classes generator module.
Generates a unified exceptions.py from OpenAPI error responses.
"""

import ast
from typing import Dict, Any

from ..core.ast_helper import ASTHelper


class ExceptionsGenerator:
    """Generates exception classes from OpenAPI error responses."""

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

    STATUS_CODE_MESSAGES = {
        '400': 'Bad Request',
        '401': 'Unauthorized',
        '403': 'Forbidden',
        '404': 'Not Found',
        '405': 'Method Not Allowed',
        '409': 'Conflict',
        '422': 'Unprocessable Entity',
        '429': 'Too Many Requests',
        '500': 'Internal Server Error',
        '502': 'Bad Gateway',
        '503': 'Service Unavailable',
        '504': 'Gateway Timeout'
    }

    def __init__(self):
        self.ast_helper = ASTHelper()

    def generate(self, extracted_data: Dict[str, Any]) -> Dict[str, ast.Module]:
        """
        Generate AST module for unified exceptions.py.

        Args:
            extracted_data: Extracted OpenAPI data

        Returns:
            Dict mapping filename to AST module
        """
        error_responses = extracted_data.get('error_responses', {})
        error_schemas = extracted_data.get('error_schemas', {})

        if not error_responses:
            return {}

        module = self._create_exceptions_module(error_responses, error_schemas)
        return {'exceptions.py': module}

    def _create_exceptions_module(
        self,
        error_responses: Dict[str, Dict[str, Any]],
        error_schemas: Dict[str, Dict[str, Any]]
    ) -> ast.Module:
        """Create unified exceptions.py module."""
        body = []

        status_to_error_model = {
            info.get('status_code'): model_name
            for model_name, info in error_schemas.items()
            if info.get('status_code')
        }

        # Imports
        body.append(self.ast_helper.create_import('typing', ['Optional']))

        error_model_names = sorted(status_to_error_model.values())
        if error_model_names:
            body.append(self.ast_helper.create_relative_import('models.error', error_model_names))

        # Base exception class
        body.append(self._create_base_exception_class())

        # Detailed exception classes
        mapping_keys = []
        mapping_values = []
        exported_names = ['PubgAPIError']

        sorted_codes = sorted(error_responses.keys(), key=lambda code: int(code) if code.isdigit() else 9999)
        for status_code in sorted_codes:
            if not status_code.isdigit():
                continue

            exception_name = self._get_exception_name(status_code)
            error_model_name = status_to_error_model.get(status_code)

            exception_class = self._create_detailed_exception_class(
                status_code=status_code,
                exception_name=exception_name,
                error_model_name=error_model_name
            )
            body.append(exception_class)

            mapping_keys.append(ast.Constant(value=int(status_code)))
            mapping_values.append(ast.Name(id=exception_name, ctx=ast.Load()))
            exported_names.append(exception_name)

        # Error mapping table for runtime hook usage
        error_mapping_assign = ast.Assign(
            targets=[ast.Name(id='ERROR_MAPPING', ctx=ast.Store())],
            value=ast.Dict(keys=mapping_keys, values=mapping_values)
        )
        body.append(ast.fix_missing_locations(error_mapping_assign))
        exported_names.append('ERROR_MAPPING')

        # __all__
        all_assign = ast.Assign(
            targets=[ast.Name(id='__all__', ctx=ast.Store())],
            value=ast.List(
                elts=[ast.Constant(value=name) for name in exported_names],
                ctx=ast.Load()
            )
        )
        body.append(ast.fix_missing_locations(all_assign))

        module = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module)
        return module

    def _create_base_exception_class(self) -> ast.ClassDef:
        """Create PubgAPIError base class."""
        args = [
            self.ast_helper.create_arg('self'),
            self.ast_helper.create_arg('status_code', ast.Name(id='int', ctx=ast.Load())),
            self.ast_helper.create_arg('message', ast.Name(id='str', ctx=ast.Load()))
        ]

        init_body = [
            ast.Assign(
                targets=[
                    ast.Attribute(
                        value=ast.Name(id='self', ctx=ast.Load()),
                        attr='status_code',
                        ctx=ast.Store()
                    )
                ],
                value=ast.Name(id='status_code', ctx=ast.Load())
            ),
            ast.Assign(
                targets=[
                    ast.Attribute(
                        value=ast.Name(id='self', ctx=ast.Load()),
                        attr='message',
                        ctx=ast.Store()
                    )
                ],
                value=ast.Name(id='message', ctx=ast.Load())
            ),
            ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Call(func=ast.Name(id='super', ctx=ast.Load()), args=[], keywords=[]),
                        attr='__init__',
                        ctx=ast.Load()
                    ),
                    args=[
                        ast.Attribute(
                            value=ast.Name(id='self', ctx=ast.Load()),
                            attr='message',
                            ctx=ast.Load()
                        )
                    ],
                    keywords=[]
                )
            )
        ]

        init_method = ast.FunctionDef(
            name='__init__',
            args=ast.arguments(
                posonlyargs=[],
                args=args,
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[]
            ),
            body=init_body,
            decorator_list=[],
            returns=None
        )

        class_body = [
            ast.fix_missing_locations(init_method)
        ]

        return self.ast_helper.create_class_def(
            name='PubgAPIError',
            bases=['Exception'],
            body=class_body
        )

    def _create_detailed_exception_class(
        self,
        status_code: str,
        exception_name: str,
        error_model_name: str
    ) -> ast.ClassDef:
        """Create detailed exception class for a specific status code."""
        model_annotation = ast.Subscript(
            value=ast.Name(id='Optional', ctx=ast.Load()),
            slice=(
                ast.Name(id=error_model_name, ctx=ast.Load())
                if error_model_name
                else ast.Name(id='dict', ctx=ast.Load())
            ),
            ctx=ast.Load()
        )

        args = [
            self.ast_helper.create_arg('self'),
            self.ast_helper.create_arg('response_model', model_annotation)
        ]

        defaults = [ast.Constant(value=None)]

        message = self.STATUS_CODE_MESSAGES.get(status_code, f'HTTP {status_code} Error')

        init_body = [
            ast.Assign(
                targets=[
                    ast.Attribute(
                        value=ast.Name(id='self', ctx=ast.Load()),
                        attr='response_model',
                        ctx=ast.Store()
                    )
                ],
                value=ast.Name(id='response_model', ctx=ast.Load())
            ),
            ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Call(func=ast.Name(id='super', ctx=ast.Load()), args=[], keywords=[]),
                        attr='__init__',
                        ctx=ast.Load()
                    ),
                    args=[],
                    keywords=[
                        ast.keyword(arg='status_code', value=ast.Constant(value=int(status_code))),
                        ast.keyword(arg='message', value=ast.Constant(value=message))
                    ]
                )
            )
        ]

        init_method = ast.FunctionDef(
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
            body=init_body,
            decorator_list=[],
            returns=None
        )

        class_body = [ast.fix_missing_locations(init_method)]

        return self.ast_helper.create_class_def(
            name=exception_name,
            bases=['PubgAPIError'],
            body=class_body
        )

    def _get_exception_name(self, status_code: str) -> str:
        """Get exception class name for status code."""
        return self.STATUS_CODE_NAMES.get(status_code, f'HttpError{status_code}')
