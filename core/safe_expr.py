# -*- coding: utf-8 -*-
"""受限数学表达式求值（替代 eval）。"""

import ast


class SafeExprError(ValueError):
    pass


def evaluate(expr: str, max_len: int = 200):
    expr = str(expr or "").strip().replace("^", "**")
    if not expr or len(expr) > max_len:
        raise SafeExprError("表达式为空或过长")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise SafeExprError(str(e)) from e

    def num(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if isinstance(node.value, bool):
                raise SafeExprError("不支持布尔值")
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            v = num(node.operand)
            return v if isinstance(node.op, ast.UAdd) else -v
        if isinstance(node, ast.BinOp):
            left, right = num(node.left), num(node.right)
            op = node.op
            if isinstance(op, ast.Add):
                return left + right
            if isinstance(op, ast.Sub):
                return left - right
            if isinstance(op, ast.Mult):
                return left * right
            if isinstance(op, ast.Div):
                return left / right
            if isinstance(op, ast.FloorDiv):
                return left // right
            if isinstance(op, ast.Mod):
                return left % right
            if isinstance(op, ast.Pow):
                if abs(right) > 100:
                    raise SafeExprError("指数过大")
                return left**right
        raise SafeExprError("不支持的表达式")

    return num(tree.body)
