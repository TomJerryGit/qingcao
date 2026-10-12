# -*- coding: utf-8 -*-
"""代码异味检测"""
import ast
import re
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class Smell:
    """代码异味"""
    kind: str          # 类型
    severity: str      # info/warning/error
    message: str
    line: int          # 行号（0 开始）
    col: int = 0
    length: int = 0


class SmellDetector:
    """代码异味检测器"""

    MAX_FUNCTION_LINES = 50
    MAX_NESTING_DEPTH = 4
    MAX_LINE_LENGTH = 100
    MIN_DUPLICATE_LINES = 5

    def __init__(self, text, language="python"):
        self.text = text
        self.language = language
        self.lines = text.splitlines()
        self.smells: List[Smell] = []

    def detect_all(self) -> List[Smell]:
        """检测所有异味"""
        self.smells = []

        self._check_long_lines()
        self._check_todos()

        if self.language == "python":
            self._check_python_ast()

        self._check_duplicates()

        return self.smells

    def _check_long_lines(self):
        """长行检测"""
        for i, line in enumerate(self.lines):
            if len(line) > self.MAX_LINE_LENGTH:
                self.smells.append(Smell(
                    kind="long_line",
                    severity="info",
                    message="行过长 (%d 字符，建议 <%d)" % (
                        len(line), self.MAX_LINE_LENGTH
                    ),
                    line=i,
                    col=self.MAX_LINE_LENGTH,
                    length=len(line) - self.MAX_LINE_LENGTH,
                ))

    def _check_todos(self):
        """TODO/FIXME 检测"""
        pattern = re.compile(
            r'#\s*(TODO|FIXME|XXX|HACK)[:\s]*(.*)',
            re.IGNORECASE
        )
        for i, line in enumerate(self.lines):
            m = pattern.search(line)
            if m:
                kind = m.group(1).upper()
                msg = m.group(2).strip()
                self.smells.append(Smell(
                    kind="todo",
                    severity="warning" if kind in ('FIXME', 'XXX') else "info",
                    message="[%s] %s" % (kind, msg or "(无描述)"),
                    line=i,
                    col=line.find('#'),
                ))

    def _check_python_ast(self):
        """Python AST 分析"""
        try:
            tree = ast.parse(self.text)
        except SyntaxError as e:
            self.smells.append(Smell(
                kind="syntax_error",
                severity="error",
                message="语法错误: %s" % e.msg,
                line=(e.lineno or 1) - 1,
                col=(e.offset or 1) - 1,
            ))
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                self._check_function(node)
            elif isinstance(node, (ast.If, ast.For, ast.While,
                                   ast.With, ast.Try)):
                self._check_nesting(node)

    def _check_function(self, node):
        """检查函数长度"""
        end = getattr(node, 'end_lineno', node.lineno)
        length = end - node.lineno + 1

        if length > self.MAX_FUNCTION_LINES:
            self.smells.append(Smell(
                kind="long_function",
                severity="warning",
                message="函数 '%s' 过长 (%d 行，建议 <%d)" % (
                    node.name, length, self.MAX_FUNCTION_LINES
                ),
                line=node.lineno - 1,
                length=length,
            ))

        # 参数过多
        if len(node.args.args) > 7:
            self.smells.append(Smell(
                kind="too_many_args",
                severity="info",
                message="函数 '%s' 参数过多 (%d 个)" % (
                    node.name, len(node.args.args)
                ),
                line=node.lineno - 1,
            ))

    def _check_nesting(self, node):
        """检查嵌套深度"""
        depth = 0
        parent = node
        while parent:
            if isinstance(parent, (ast.If, ast.For, ast.While,
                                   ast.With, ast.Try)):
                depth += 1
            parent = getattr(parent, 'parent', None)

        # 简化：只检查节点本身的行号
        if depth >= self.MAX_NESTING_DEPTH:
            self.smells.append(Smell(
                kind="deep_nesting",
                severity="warning",
                message="嵌套过深 (深度 %d)" % depth,
                line=node.lineno - 1,
            ))

    def _check_duplicates(self):
        """检测重复代码块"""
        # 简化：查找 5 行相同的块
        seen: Dict[str, int] = {}

        for i in range(len(self.lines) - self.MIN_DUPLICATE_LINES):
            # 取 5 行
            block = '\n'.join(
                self.lines[i:i + self.MIN_DUPLICATE_LINES]
            ).strip()

            # 忽略空块
            if len(block) < 30:
                continue

            if block in seen:
                self.smells.append(Smell(
                    kind="duplicate",
                    severity="info",
                    message="重复代码块（与第 %d 行相同）" % (
                        seen[block] + 1
                    ),
                    line=i,
                    length=self.MIN_DUPLICATE_LINES,
                ))
            else:
                seen[block] = i


def get_smells(text, language="python") -> List[Smell]:
    """便捷函数"""
    detector = SmellDetector(text, language)
    return detector.detect_all()