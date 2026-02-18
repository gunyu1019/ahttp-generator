"""
AST helper utilities for code generation.
Provides utility functions for creating common AST nodes.
"""

import ast
from typing import List, Optional, Union, Any


class ASTHelper:
    """Helper class for creating AST nodes."""

    def __init__(self):
        self._lineno = 1

    def _fix_node(self, node):
        """Add required lineno and col_offset to AST node."""
        if hasattr(node, 'lineno'):
            node.lineno = self._lineno
            node.col_offset = 0
            self._lineno += 1
        return node

    @staticmethod
    def create_import(module: str, names: List[str]) -> ast.ImportFrom:
        """Create an 'from module import names' statement."""
        aliases = [ast.alias(name=name, asname=None) for name in names]
        node = ast.ImportFrom(
            module=module,
            names=aliases,
            level=0
        )
        return ast.fix_missing_locations(node)

    @staticmethod
    def create_relative_import(module: str, names: List[str], level: int = 1) -> ast.ImportFrom:
        """Create a relative import statement like 'from .module import names'."""
        aliases = [ast.alias(name=name, asname=None) for name in names]
        node = ast.ImportFrom(
            module=module,
            names=aliases,
            level=level
        )
        return ast.fix_missing_locations(node)

    @staticmethod
    def create_import_all(module: str, level: int = 1) -> ast.ImportFrom:
        """Create 'from .module import *' statement."""
        node = ast.ImportFrom(
            module=module,
            names=[ast.alias(name='*', asname=None)],
            level=level
        )
        return ast.fix_missing_locations(node)

    @staticmethod
    def create_class_def(
        name: str,
        bases: List[str] = None,
        body: List[ast.stmt] = None,
        decorators: List[ast.expr] = None
    ) -> ast.ClassDef:
        """Create a class definition."""
        if bases is None:
            bases = []
        if body is None:
            body = [ast.Pass()]
        if decorators is None:
            decorators = []

        base_nodes = [ast.Name(id=base, ctx=ast.Load()) for base in bases]

        node = ast.ClassDef(
            name=name,
            bases=base_nodes,
            keywords=[],
            decorator_list=decorators,
            body=body
        )
        return ast.fix_missing_locations(node)

    @staticmethod
    def create_function_def(
        name: str,
        args: List[ast.arg] = None,
        body: List[ast.stmt] = None,
        decorators: List[ast.expr] = None,
        returns: Optional[ast.expr] = None
    ) -> ast.FunctionDef:
        """Create a function definition."""
        if args is None:
            args = []
        if body is None:
            body = [ast.Return(value=None)]
        if decorators is None:
            decorators = []

        node = ast.FunctionDef(
            name=name,
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
            decorator_list=decorators,
            returns=returns
        )
        return ast.fix_missing_locations(node)

    @staticmethod
    def create_arg(name: str, annotation: Optional[ast.expr] = None) -> ast.arg:
        """Create a function argument."""
        return ast.arg(arg=name, annotation=annotation)

    @staticmethod
    def create_annotation(type_name: str, subscript: Optional[str] = None) -> ast.expr:
        """Create a type annotation like 'List[str]' or 'str'."""
        if subscript is None:
            return ast.Name(id=type_name, ctx=ast.Load())
        else:
            return ast.Subscript(
                value=ast.Name(id=type_name, ctx=ast.Load()),
                slice=ast.Name(id=subscript, ctx=ast.Load()),
                ctx=ast.Load()
            )

    @staticmethod
    def create_annotated_arg(name: str, annotation_name: str, annotation_source: str) -> ast.arg:
        """Create an annotated argument like 'user: Annotated[str, Path]'."""
        annotation = ast.Subscript(
            value=ast.Name(id='Annotated', ctx=ast.Load()),
            slice=ast.Tuple(
                elts=[
                    ast.Name(id=annotation_name, ctx=ast.Load()),
                    ast.Name(id=annotation_source, ctx=ast.Load())
                ],
                ctx=ast.Load()
            ),
            ctx=ast.Load()
        )
        return ast.arg(arg=name, annotation=annotation)

    @staticmethod
    def create_string_constant(value: str) -> ast.Constant:
        """Create a string constant."""
        return ast.Constant(value=value)

    @staticmethod
    def create_assign(target: str, value: ast.expr) -> ast.Assign:
        """Create an assignment statement."""
        node = ast.Assign(
            targets=[ast.Name(id=target, ctx=ast.Store())],
            value=value
        )
        return ast.fix_missing_locations(node)

    @staticmethod
    def create_ann_assign(target: str, annotation: ast.expr, value: Optional[ast.expr] = None) -> ast.AnnAssign:
        """Create an annotated assignment statement."""
        node = ast.AnnAssign(
            target=ast.Name(id=target, ctx=ast.Store()),
            annotation=annotation,
            value=value,
            simple=1
        )
        return ast.fix_missing_locations(node)

    @staticmethod
    def create_call(func_name: str, args: List[ast.expr] = None) -> ast.Call:
        """Create a function call."""
        if args is None:
            args = []

        return ast.Call(
            func=ast.Name(id=func_name, ctx=ast.Load()),
            args=args,
            keywords=[]
        )

    @staticmethod
    def create_attribute(obj: str, attr: str) -> ast.Attribute:
        """Create an attribute access like 'obj.attr'."""
        return ast.Attribute(
            value=ast.Name(id=obj, ctx=ast.Load()),
            attr=attr,
            ctx=ast.Load()
        )

    @staticmethod
    def create_super_call() -> ast.Call:
        """Create a super() call."""
        return ast.Call(
            func=ast.Name(id='super', ctx=ast.Load()),
            args=[],
            keywords=[]
        )

    @staticmethod
    def create_decorator(name: str, args: List[ast.expr] = None) -> ast.expr:
        """Create a decorator."""
        if args is None:
            return ast.Name(id=name, ctx=ast.Load())
        else:
            return ast.Call(
                func=ast.Name(id=name, ctx=ast.Load()),
                args=args,
                keywords=[]
            )

    @staticmethod
    def create_custom_name_annotation(component_type: str, original_name: str) -> ast.expr:
        """
        Create AST for Component.custom_name("original") annotation.

        Args:
            component_type: Component type (Query, Path, Body, etc.)
            original_name: Original parameter name

        Returns:
            AST expression for Component.custom_name("original")
        """
        return ast.Call(
            func=ast.Attribute(
                value=ast.Name(id=component_type, ctx=ast.Load()),
                attr='custom_name',
                ctx=ast.Load()
            ),
            args=[ast.Constant(value=original_name)],
            keywords=[]
        )

    @staticmethod
    def create_annotated_arg_with_custom_name(
        arg_name: str,
        type_annotation: str,
        component_type: str,
        original_name: str
    ) -> ast.arg:
        """
        Create annotated argument with custom_name.

        Args:
            arg_name: Sanitized argument name
            type_annotation: Type annotation string
            component_type: Component type (Query, Path, etc.)
            original_name: Original parameter name

        Returns:
            AST argument with Annotated[Type, Component.custom_name("original")]
        """
        # Create Annotated[Type, Component.custom_name("original")]
        annotation = ast.Subscript(
            value=ast.Name(id='Annotated', ctx=ast.Load()),
            slice=ast.Tuple(
                elts=[
                    ast.Name(id=type_annotation, ctx=ast.Load()),
                    ASTHelper.create_custom_name_annotation(component_type, original_name)
                ],
                ctx=ast.Load()
            ),
            ctx=ast.Load()
        )

        arg = ast.arg(arg=arg_name, annotation=annotation)
        return ast.fix_missing_locations(arg)



