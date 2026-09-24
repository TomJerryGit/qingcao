#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为符号大纲面板模块，包含：
- OutlinePanel：符号大纲面板（QDockWidget，基础/增强两种模式）
- OutlineTree：符号树控件（QTreeWidget）
- SymbolParser：符号解析器（正则 + 简单语法分析）
- SymbolNode：符号节点数据类
- SymbolType：符号类型枚举
- 多语言符号解析（Python/JS/TS/C++/Java/Go/Rust 等）
- 层级结构展示
- 符号类型图标
- 搜索过滤
- 类型筛选（增强模式）
- 排序切换（增强模式）
- 面包屑导航（增强模式）
- 跟随光标高亮（增强模式）
- 双击跳转
- 右键菜单
- 自动更新
- 折叠/展开
- 符号统计

合并说明（P3-8）:
    原文件 ui/outline_panel.py 与 ui/outline_panel_enhanced.py 已合并到
    本文件。通过 OutlinePanel(enhanced=True) 启用增强功能（面包屑、
    筛选、排序、跟随光标）。原 OutlinePanelEnhanced 类已删除。
    调用方（如 ui/main_window.py）请使用 OutlinePanel(..., enhanced=True)。
"""

import os
import re
import time
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto

from PyQt5.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget,
    QTreeWidgetItem, QLineEdit, QMenu, QLabel, QToolButton,
    QPushButton, QApplication, QAbstractItemView, QHeaderView,
    QComboBox, QStyle
)
from PyQt5.QtGui import (
    QIcon,
    QColor,
    QFont,
    QBrush,
    QPainter,
    QPixmap,
    QPen,
    QKeySequence,
)
from PyQt5.QtWidgets import QAction
from PyQt5.QtCore import (
    Qt, pyqtSignal, QTimer, QSize, QSettings, QPoint
)

from app.event_bus import (
    bus, CursorEvent, EditorChangedEvent, FileOpenedEvent,
    StatusMessageEvent
)


# ============================================================
# 常量
# ============================================================
# 自动更新延迟（毫秒）
UPDATE_DELAY_MS = 500

# 最大解析行数（防止超大文件卡顿）
MAX_PARSE_LINES = 50000

# 符号类型
SYMBOL_TYPES = {
    'class': '类',
    'function': '函数',
    'method': '方法',
    'variable': '变量',
    'constant': '常量',
    'module': '模块',
    'import': '导入',
    'interface': '接口',
    'struct': '结构体',
    'enum': '枚举',
    'namespace': '命名空间',
    'property': '属性',
    'field': '字段',
    'constructor': '构造函数',
    'decorator': '装饰器',
    'macro': '宏',
    'type': '类型',
}

# 符号类型颜色（用于标识）
SYMBOL_TYPE_COLORS = {
    'class': QColor("#4EC9B0"),
    'function': QColor("#DCDCAA"),
    'method': QColor("#DCDCAA"),
    'variable': QColor("#9CDCFE"),
    'constant': QColor("#4FC1FF"),
    'module': QColor("#C586C0"),
    'import': QColor("#808080"),
    'interface': QColor("#4EC9B0"),
    'struct': QColor("#4EC9B0"),
    'enum': QColor("#4EC9B0"),
    'namespace': QColor("#C586C0"),
    'property': QColor("#9CDCFE"),
    'field': QColor("#9CDCFE"),
    'constructor': QColor("#DCDCAA"),
    'decorator': QColor("#C586C0"),
    'macro': QColor("#C586C0"),
    'type': QColor("#4EC9B0"),
}

# 符号类型图标（Unicode 符号）
SYMBOL_TYPE_ICONS = {
    'class': '🔷',
    'function': '🔧',
    'method': '⚙',
    'variable': '📦',
    'constant': '🔒',
    'module': '📁',
    'import': '📥',
    'interface': '🔶',
    'struct': '🔸',
    'enum': '🔹',
    'namespace': '📂',
    'property': '🏷',
    'field': '📌',
    'constructor': '🏗',
    'decorator': '✨',
    'macro': '⚡',
    'type': '🔺',
}

# 树列索引
COL_SYMBOL = 0
COL_LINE = 1
COL_TYPE = 2

# 增强模式：筛选类别（合并自 outline_panel_enhanced.py）
FILTER_CATEGORIES = {
    'all':       '全部',
    'class':     '类/接口',
    'function':  '函数',
    'method':    '方法',
    'variable':  '变量',
    'constant':  '常量',
}

# 增强模式：排序选项（合并自 outline_panel_enhanced.py）
SORT_OPTIONS = {
    'line':      '按行号',
    'name':      '按名称',
    'type':      '按类型',
}


# ============================================================
# 符号类型枚举
# ============================================================
class SymbolType(Enum):
    """符号类型枚举"""
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    MODULE = "module"
    IMPORT = "import"
    INTERFACE = "interface"
    STRUCT = "struct"
    ENUM = "enum"
    NAMESPACE = "namespace"
    PROPERTY = "property"
    FIELD = "field"
    CONSTRUCTOR = "constructor"
    DECORATOR = "decorator"
    MACRO = "macro"
    TYPE = "type"
    UNKNOWN = "unknown"


# ============================================================
# 符号节点数据类
# ============================================================
@dataclass
class SymbolNode:
    """
    符号节点。

    表示一个函数、类、变量等符号。
    """

    name: str = ""                          # 符号名称
    type: str = "unknown"                   # 符号类型（class/function/...）
    line: int = 0                           # 起始行号（0 开始）
    col: int = 0                            # 起始列（0 开始）
    end_line: int = 0                       # 结束行号（0 开始）
    indent: int = 0                         # 缩进层级
    parent_name: Optional[str] = None       # 父符号名称
    signature: str = ""                     # 签名（如参数列表）
    doc: str = ""                           # 文档字符串
    children: List['SymbolNode'] = field(default_factory=list)

    def add_child(self, child: 'SymbolNode'):
        """添加子节点"""
        child.parent_name = self.name
        self.children.append(child)

    @property
    def display_name(self) -> str:
        """显示名称"""
        icon = SYMBOL_TYPE_ICONS.get(self.type, '•')
        if self.signature:
            return f"{icon} {self.name}{self.signature}"
        return f"{icon} {self.name}"

    @property
    def line_display(self) -> str:
        """行号显示（1 开始）"""
        return str(self.line + 1)

    def has_children(self) -> bool:
        """是否有子节点"""
        return len(self.children) > 0

    def get_depth(self) -> int:
        """获取深度"""
        return self.indent

    def __repr__(self) -> str:
        return (f"<SymbolNode {self.type} {self.name} "
                f"line={self.line} children={len(self.children)}>")


# ============================================================
# 符号解析器
# ============================================================
class SymbolParser:
    """
    符号解析器。

    使用正则表达式 + 简单语法分析解析各类语言的符号。

    支持语言:
    - Python
    - JavaScript / TypeScript
    - C / C++
    - Java
    - Go
    - Rust
    - Ruby
    - PHP
    - 通用（fallback）
    """

    def __init__(self):
        # 语言 -> 解析函数映射
        self._parsers = {
            'Python': self._parse_python,
            'JavaScript': self._parse_javascript,
            'TypeScript': self._parse_typescript,
            'JavaScript React': self._parse_javascript,
            'TypeScript React': self._parse_typescript,
            'C': self._parse_c_cpp,
            'C++': self._parse_c_cpp,
            'Java': self._parse_java,
            'Go': self._parse_go,
            'Rust': self._parse_rust,
            'Ruby': self._parse_ruby,
            'PHP': self._parse_php,
        }

    # --------------------------------------------------------
    # 主入口
    # --------------------------------------------------------
    def parse(self, text: str, language: str,
              filepath: Optional[str] = None) -> List[SymbolNode]:
        """
        解析文本中的符号。

        参数:
            text: 文件内容
            language: 语言名称
            filepath: 文件路径（用于更精细的判断）

        返回:
            符号节点列表（顶层）
        """
        if not text or not language:
            return []

        # 限制解析行数
        lines = text.splitlines()
        if len(lines) > MAX_PARSE_LINES:
            lines = lines[:MAX_PARSE_LINES]
            text = '\n'.join(lines)

        # 获取对应语言的解析器
        parser = self._parsers.get(language, self._parse_generic)
        if parser is None:
            parser = self._parse_generic

        try:
            symbols = parser(text, lines)
            # 构建层级
            symbols = self._build_hierarchy(symbols)
            return symbols
        except Exception as e:
            print(f"[SymbolParser] 解析失败: {e}")
            return []

    # --------------------------------------------------------
    # Python 解析
    # --------------------------------------------------------
    def _parse_python(self, text: str, lines: List[str]) -> List[SymbolNode]:
        """解析 Python 符号"""
        symbols = []

        # 类定义
        class_pattern = re.compile(
            r'^(\s*)class\s+(\w+)(?:\s*\(([^)]*)\))?\s*:'
        )

        # 函数/方法定义
        def_pattern = re.compile(
            r'^(\s*)(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)'
        )

        # 装饰器
        decorator_pattern = re.compile(r'^(\s*)@(\w+)')

        # 模块级常量（大写字母）
        constant_pattern = re.compile(
            r'^([A-Z][A-Z0-9_]*)\s*=\s*'
        )

        # 模块级变量
        variable_pattern = re.compile(
            r'^(\w+)\s*=\s*'
        )

        pending_decorators = []

        for i, line in enumerate(lines):
            # 装饰器
            dec_match = decorator_pattern.match(line)
            if dec_match:
                pending_decorators.append(dec_match.group(2))
                continue

            # 类
            class_match = class_pattern.match(line)
            if class_match:
                indent = len(class_match.group(1))
                name = class_match.group(2)
                bases = class_match.group(3) or ""

                signature = f"({bases})" if bases else ""

                node = SymbolNode(
                    name=name,
                    type='class',
                    line=i,
                    col=indent,
                    indent=indent,
                    signature=signature,
                )
                if pending_decorators:
                    node.doc = f"@{', @'.join(pending_decorators)}"
                symbols.append(node)
                pending_decorators = []
                continue

            # 函数/方法
            def_match = def_pattern.match(line)
            if def_match:
                indent = len(def_match.group(1))
                name = def_match.group(2)
                params = def_match.group(3) or ""

                # 简化参数
                if len(params) > 40:
                    params = params[:37] + "..."

                signature = f"({params})"

                # 判断是方法还是函数（根据缩进判断是否在类中）
                symbol_type = 'method' if indent > 0 else 'function'

                node = SymbolNode(
                    name=name,
                    type=symbol_type,
                    line=i,
                    col=indent,
                    indent=indent,
                    signature=signature,
                )
                if pending_decorators:
                    node.doc = f"@{', @'.join(pending_decorators)}"
                symbols.append(node)
                pending_decorators = []
                continue

            # 常量
            const_match = constant_pattern.match(line)
            if const_match and not line.strip().startswith('#'):
                name = const_match.group(1)
                if not any(s.name == name and s.line == i for s in symbols):
                    node = SymbolNode(
                        name=name,
                        type='constant',
                        line=i,
                        col=0,
                        indent=0,
                    )
                    symbols.append(node)
                continue

            # 重置装饰器
            if line.strip() and not line.strip().startswith('@'):
                pending_decorators = []

        return symbols

    # --------------------------------------------------------
    # JavaScript 解析
    # --------------------------------------------------------
    def _parse_javascript(self, text: str,
                          lines: List[str]) -> List[SymbolNode]:
        """解析 JavaScript 符号"""
        return self._parse_js_like(text, lines, is_ts=False)

    def _parse_typescript(self, text: str,
                          lines: List[str]) -> List[SymbolNode]:
        """解析 TypeScript 符号"""
        return self._parse_js_like(text, lines, is_ts=True)

    def _parse_js_like(self, text: str, lines: List[str],
                       is_ts: bool) -> List[SymbolNode]:
        """解析类 JavaScript 语言"""
        symbols = []

        patterns = [
            # class Foo {  /  class Foo extends Bar {
            (re.compile(r'^(\s*)class\s+(\w+)(?:\s+extends\s+(\w+))?'),
             'class'),
            # function foo() {  /  async function foo() {
            (re.compile(r'^(\s*)(?:async\s+)?function\s+(\w+)\s*\('),
             'function'),
            # const foo = () => {  /  const foo = function() {
            (re.compile(r'^(\s*)(?:const|let|var)\s+(\w+)\s*=\s*'
                        r'(?:async\s+)?(?:function|\()'),
             'function'),
            # foo() {  (class method)
            (re.compile(r'^(\s{2,})(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{'),
             'method'),
            # interface Foo {
            (re.compile(r'^(\s*)interface\s+(\w+)'), 'interface'),
            # type Foo =
            (re.compile(r'^(\s*)type\s+(\w+)'), 'type'),
            # enum Foo {
            (re.compile(r'^(\s*)enum\s+(\w+)'), 'enum'),
        ]

        for i, line in enumerate(lines):
            for pattern, symbol_type in patterns:
                match = pattern.match(line)
                if match:
                    indent = len(match.group(1))
                    name = match.group(2)

                    node = SymbolNode(
                        name=name,
                        type=symbol_type,
                        line=i,
                        col=indent,
                        indent=indent,
                    )
                    symbols.append(node)
                    break

        return symbols

    # --------------------------------------------------------
    # C/C++ 解析
    # --------------------------------------------------------
    def _parse_c_cpp(self, text: str, lines: List[str]) -> List[SymbolNode]:
        """解析 C/C++ 符号"""
        symbols = []

        # 类/结构体
        class_pattern = re.compile(
            r'^\s*(class|struct|union)\s+(\w+)'
        )

        # 函数（简单匹配）
        func_pattern = re.compile(
            r'^(\w[\w\s\*&:<>]*?)\s+(\w+)\s*\([^)]*\)\s*(?:const)?\s*\{?'
        )

        # 命名空间
        namespace_pattern = re.compile(r'^\s*namespace\s+(\w+)')

        # #define 宏
        macro_pattern = re.compile(r'^\s*#define\s+(\w+)')

        # 枚举
        enum_pattern = re.compile(r'^\s*enum\s+(?:class\s+)?(\w+)')

        for i, line in enumerate(lines):
            # 跳过注释
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*'):
                continue

            # 宏
            macro_match = macro_pattern.match(line)
            if macro_match:
                node = SymbolNode(
                    name=macro_match.group(1),
                    type='macro',
                    line=i,
                    col=0,
                    indent=0,
                )
                symbols.append(node)
                continue

            # 类
            class_match = class_pattern.match(line)
            if class_match:
                node = SymbolNode(
                    name=class_match.group(2),
                    type=class_match.group(1),
                    line=i,
                    col=0,
                    indent=0,
                )
                symbols.append(node)
                continue

            # 命名空间
            ns_match = namespace_pattern.match(line)
            if ns_match:
                node = SymbolNode(
                    name=ns_match.group(1),
                    type='namespace',
                    line=i,
                    col=0,
                    indent=0,
                )
                symbols.append(node)
                continue

            # 枚举
            enum_match = enum_pattern.match(line)
            if enum_match:
                node = SymbolNode(
                    name=enum_match.group(1),
                    type='enum',
                    line=i,
                    col=0,
                    indent=0,
                )
                symbols.append(node)
                continue

            # 函数（简单匹配，避免误判）
            func_match = func_pattern.match(line)
            if func_match:
                name = func_match.group(2)
                # 排除关键字
                if name not in ('if', 'else', 'for', 'while', 'switch',
                                'return', 'case', 'break', 'continue'):
                    node = SymbolNode(
                        name=name,
                        type='function',
                        line=i,
                        col=0,
                        indent=0,
                    )
                    symbols.append(node)

        return symbols

    # --------------------------------------------------------
    # Java 解析
    # --------------------------------------------------------
    def _parse_java(self, text: str, lines: List[str]) -> List[SymbolNode]:
        """解析 Java 符号"""
        symbols = []

        class_pattern = re.compile(
            r'^\s*(?:public|private|protected)?\s*'
            r'(?:abstract|final|static)?\s*'
            r'(class|interface|enum)\s+(\w+)'
        )

        method_pattern = re.compile(
            r'^\s*(?:public|private|protected|static|final|abstract|'
            r'synchronized|native|\s)+\s*'
            r'(\w+(?:<[^>]+>)?)\s+(\w+)\s*\([^)]*\)'
        )

        field_pattern = re.compile(
            r'^\s*(?:public|private|protected|static|final|'
            r'transient|volatile|\s)+\s*'
            r'(\w+(?:<[^>]+>)?)\s+(\w+)\s*(?:=|;)'
        )

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('*'):
                continue

            class_match = class_pattern.match(line)
            if class_match:
                node = SymbolNode(
                    name=class_match.group(2),
                    type=class_match.group(1),
                    line=i,
                    col=0,
                    indent=0,
                )
                symbols.append(node)
                continue

            method_match = method_pattern.match(line)
            if method_match:
                name = method_match.group(2)
                if name not in ('if', 'else', 'for', 'while', 'switch'):
                    node = SymbolNode(
                        name=name,
                        type='method',
                        line=i,
                        col=0,
                        indent=0,
                    )
                    symbols.append(node)
                continue

            field_match = field_pattern.match(line)
            if field_match:
                node = SymbolNode(
                    name=field_match.group(2),
                    type='field',
                    line=i,
                    col=0,
                    indent=0,
                )
                symbols.append(node)

        return symbols

    # --------------------------------------------------------
    # Go 解析
    # --------------------------------------------------------
    def _parse_go(self, text: str, lines: List[str]) -> List[SymbolNode]:
        """解析 Go 符号"""
        symbols = []

        func_pattern = re.compile(
            r'^\s*func\s+(?:\([^)]+\)\s+)?(\w+)\s*\([^)]*\)'
        )

        type_pattern = re.compile(r'^\s*type\s+(\w+)\s+(struct|interface)')

        var_pattern = re.compile(r'^\s*(?:var|const)\s+(\w+)')

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//'):
                continue

            func_match = func_pattern.match(line)
            if func_match:
                name = func_match.group(1)
                # 判断是否为方法（带接收者）
                is_method = ')' in line.split('func')[1].split('(')[0] if 'func' in line else False
                node = SymbolNode(
                    name=name,
                    type='method' if is_method else 'function',
                    line=i,
                    col=0,
                    indent=0,
                )
                symbols.append(node)
                continue

            type_match = type_pattern.match(line)
            if type_match:
                node = SymbolNode(
                    name=type_match.group(1),
                    type=type_match.group(2),
                    line=i,
                    col=0,
                    indent=0,
                )
                symbols.append(node)
                continue

            var_match = var_pattern.match(line)
            if var_match:
                node = SymbolNode(
                    name=var_match.group(1),
                    type='variable',
                    line=i,
                    col=0,
                    indent=0,
                )
                symbols.append(node)

        return symbols

    # --------------------------------------------------------
    # Rust 解析
    # --------------------------------------------------------
    def _parse_rust(self, text: str, lines: List[str]) -> List[SymbolNode]:
        """解析 Rust 符号"""
        symbols = []

        patterns = [
            (re.compile(r'^\s*(?:pub\s+)?fn\s+(\w+)'), 'function'),
            (re.compile(r'^\s*(?:pub\s+)?struct\s+(\w+)'), 'struct'),
            (re.compile(r'^\s*(?:pub\s+)?enum\s+(\w+)'), 'enum'),
            (re.compile(r'^\s*(?:pub\s+)?trait\s+(\w+)'), 'interface'),
            (re.compile(r'^\s*(?:pub\s+)?mod\s+(\w+)'), 'namespace'),
            (re.compile(r'^\s*(?:pub\s+)?type\s+(\w+)'), 'type'),
            (re.compile(r'^\s*(?:pub\s+)?const\s+(\w+)'), 'constant'),
            (re.compile(r'^\s*(?:pub\s+)?static\s+(\w+)'), 'variable'),
            (re.compile(r'^\s*impl\s+(?:<[^>]*>\s+)?(\w+)'), 'class'),
            (re.compile(r'^\s*macro_rules!\s+(\w+)'), 'macro'),
        ]

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*'):
                continue

            for pattern, symbol_type in patterns:
                match = pattern.match(line)
                if match:
                    indent = len(line) - len(line.lstrip())
                    node = SymbolNode(
                        name=match.group(1),
                        type=symbol_type,
                        line=i,
                        col=indent,
                        indent=indent,
                    )
                    symbols.append(node)
                    break

        return symbols

    # --------------------------------------------------------
    # Ruby 解析
    # --------------------------------------------------------
    def _parse_ruby(self, text: str, lines: List[str]) -> List[SymbolNode]:
        """解析 Ruby 符号"""
        symbols = []

        patterns = [
            (re.compile(r'^\s*class\s+(\w+)'), 'class'),
            (re.compile(r'^\s*module\s+(\w+)'), 'module'),
            (re.compile(r'^\s*def\s+(\w+[?!]?)'), 'method'),
        ]

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue

            for pattern, symbol_type in patterns:
                match = pattern.match(line)
                if match:
                    indent = len(line) - len(line.lstrip())
                    node = SymbolNode(
                        name=match.group(1),
                        type=symbol_type,
                        line=i,
                        col=indent,
                        indent=indent,
                    )
                    symbols.append(node)
                    break

        return symbols

    # --------------------------------------------------------
    # PHP 解析
    # --------------------------------------------------------
    def _parse_php(self, text: str, lines: List[str]) -> List[SymbolNode]:
        """解析 PHP 符号"""
        symbols = []

        patterns = [
            (re.compile(r'^\s*(?:abstract\s+|final\s+)?class\s+(\w+)'),
             'class'),
            (re.compile(r'^\s*interface\s+(\w+)'), 'interface'),
            (re.compile(r'^\s*trait\s+(\w+)'), 'interface'),
            (re.compile(r'^\s*(?:public|private|protected|static|\s)*'
                        r'function\s+(\w+)'), 'function'),
            (re.compile(r'^\s*(?:public|private|protected)?\s*'
                        r'\$(\w+)\s*='), 'variable'),
        ]

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('/*'):
                continue

            for pattern, symbol_type in patterns:
                match = pattern.match(line)
                if match:
                    indent = len(line) - len(line.lstrip())
                    node = SymbolNode(
                        name=match.group(1),
                        type=symbol_type,
                        line=i,
                        col=indent,
                        indent=indent,
                    )
                    symbols.append(node)
                    break

        return symbols

    # --------------------------------------------------------
    # 通用解析
    # --------------------------------------------------------
    def _parse_generic(self, text: str,
                        lines: List[str]) -> List[SymbolNode]:
        """通用解析（fallback）"""
        symbols = []

        # 尝试匹配常见的函数/类定义
        patterns = [
            (re.compile(r'^\s*(?:class|struct)\s+(\w+)'), 'class'),
            (re.compile(r'^\s*def\s+(\w+)'), 'function'),
            (re.compile(r'^\s*function\s+(\w+)'), 'function'),
        ]

        for i, line in enumerate(lines):
            for pattern, symbol_type in patterns:
                match = pattern.match(line)
                if match:
                    indent = len(line) - len(line.lstrip())
                    node = SymbolNode(
                        name=match.group(1),
                        type=symbol_type,
                        line=i,
                        col=indent,
                        indent=indent,
                    )
                    symbols.append(node)
                    break

        return symbols

    # --------------------------------------------------------
    # 层级构建
    # --------------------------------------------------------
    def _build_hierarchy(self, flat_symbols: List[SymbolNode]
                          ) -> List[SymbolNode]:
        """
        从扁平符号列表构建层级结构。

        基于缩进判断父子关系。
        """
        if not flat_symbols:
            return []

        # 计算每个符号的结束行
        self._compute_end_lines(flat_symbols)

        # 构建层级
        root_symbols = []
        stack = []  # 栈：存放 (indent, symbol)

        for symbol in flat_symbols:
            # 弹出比当前缩进大或相等的符号
            while stack and stack[-1][0] >= symbol.indent:
                stack.pop()

            if stack:
                # 有父节点
                parent = stack[-1][1]
                parent.add_child(symbol)
            else:
                # 顶层
                root_symbols.append(symbol)

            # 当前符号入栈
            stack.append((symbol.indent, symbol))

        return root_symbols

    def _compute_end_lines(self, symbols: List[SymbolNode]):
        """计算每个符号的结束行。

        修复说明（P1-B2）:
            原实现只看"下一个符号的缩进"：
              - 有子节点的符号，end_line 被设为子节点起始行（错）
              - 最后一个符号 end_line = 自己起始行（错）
            结果：跟随光标高亮时命中错误的符号。

            修复：向后扫描第一个缩进 <= 自己的符号，
                 其前一行为自己的 end_line。最后一个符号延伸
                 到文件最末符号的位置。
        """
        if not symbols:
            return

        # P1-B2: 计算 end_line 的正确方式
        max_line = max(s.line for s in symbols)
        n = len(symbols)

        for i, symbol in enumerate(symbols):
            end_line = max_line
            for j in range(i + 1, n):
                if symbols[j].indent <= symbol.indent:
                    end_line = symbols[j].line - 1
                    break
            symbol.end_line = max(symbol.line, end_line)


# ============================================================
# 符号树控件
# ============================================================
class OutlineTree(QTreeWidget):
    """
    符号树控件。

    展示符号层级结构，支持:
    - 双击跳转
    - 右键菜单

    注意:
        渲染逻辑（筛选、排序、图标、颜色）由 OutlinePanel 负责，
        本类只负责树控件本身的行为与信号。
    """

    # 信号
    symbol_activated = pyqtSignal(int)  # 跳转到行号

    def __init__(self, parent=None, enhanced: bool = False):
        super().__init__(parent)

        self._enhanced = bool(enhanced)

        # 配置
        self.setHeaderHidden(False)
        if self._enhanced:
            self.setColumnCount(3)
            self.setHeaderLabels(["符号", "行", "类型"])
        else:
            self.setColumnCount(2)
            self.setHeaderLabels(["符号", "行"])

        self.setIndentation(14)
        self.setAnimated(True)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setExpandsOnDoubleClick(False)

        # 列宽
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(COL_SYMBOL, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_LINE, QHeaderView.ResizeToContents)
        if self._enhanced:
            header.setSectionResizeMode(COL_TYPE, QHeaderView.ResizeToContents)

        # 应用样式
        self._apply_style()

        # 连接信号
        self.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QTreeWidget {
                background-color: #252526;
                color: #d4d4d4;
                border: none;
                font-size: 12px;
                outline: none;
            }
            QTreeWidget::item {
                padding: 2px 4px;
                border-radius: 2px;
            }
            QTreeWidget::item:hover {
                background-color: #2a2d2e;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #888;
                border: none;
                padding: 2px 4px;
                font-size: 11px;
            }
        """)

    # --------------------------------------------------------
    # 交互
    # --------------------------------------------------------
    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """双击跳转"""
        line = item.data(COL_SYMBOL, Qt.UserRole + 1)
        if line is not None:
            self.symbol_activated.emit(line)

    def _show_context_menu(self, pos: QPoint):
        """右键菜单"""
        item = self.itemAt(pos)
        if item is None:
            # 空白区域
            menu = QMenu(self)
            expand_all = menu.addAction("⊞ 全部展开")
            expand_all.triggered.connect(self.expandAll)

            collapse_all = menu.addAction("⊟ 全部折叠")
            collapse_all.triggered.connect(self.collapseAll)

            menu.exec_(self.viewport().mapToGlobal(pos))
            return

        menu = QMenu(self)

        # 跳转
        goto_act = menu.addAction("➡ 跳转到定义")
        goto_act.triggered.connect(
            lambda: self._on_item_double_clicked(item, 0)
        )

        menu.addSeparator()

        # 复制符号名
        symbol = item.data(COL_SYMBOL, Qt.UserRole)
        if symbol:
            copy_name = menu.addAction("📋 复制符号名称")
            copy_name.triggered.connect(
                lambda: QApplication.clipboard().setText(symbol.name)
            )

            copy_line = menu.addAction(f"📋 复制行号 ({symbol.line + 1})")
            copy_line.triggered.connect(
                lambda: QApplication.clipboard().setText(str(symbol.line + 1))
            )

        menu.addSeparator()

        # 展开/折叠
        if item.isExpanded():
            collapse_act = menu.addAction("⊟ 折叠")
            collapse_act.triggered.connect(lambda: item.setExpanded(False))
        else:
            expand_act = menu.addAction("⊞ 展开")
            expand_act.triggered.connect(lambda: item.setExpanded(True))

        menu.addSeparator()

        expand_all = menu.addAction("⊞ 全部展开")
        expand_all.triggered.connect(self.expandAll)

        collapse_all = menu.addAction("⊟ 全部折叠")
        collapse_all.triggered.connect(self.collapseAll)

        menu.exec_(self.viewport().mapToGlobal(pos))


# ============================================================
# 大纲面板（合并版）
# ============================================================
class OutlinePanel(QDockWidget):
    """
    符号大纲面板（合并版，P3-8）。

    展示当前文件的函数、类、变量等符号。

    参数:
        main_window: 主窗口（用于访问 tabs）
        parent: 父控件
        enhanced: True 启用增强功能:
                  - 面包屑导航（显示当前光标所在符号路径）
                  - 类型筛选（只看类/函数/方法/...）
                  - 排序切换（按行号/名称/类型）
                  - 跟随光标高亮当前符号
                  - 3 列树（符号 / 行 / 类型）
                  False 时仅显示基础功能（2 列树）。

    信号:
        symbol_clicked(int): 符号点击（行号）
        symbol_selected(str, int): 符号选中（名称, 行号）
    """

    symbol_clicked = pyqtSignal(int)
    symbol_selected = pyqtSignal(str, int)

    def __init__(self, main_window=None, parent=None,
                 enhanced: bool = False):
        super().__init__("大纲", parent or main_window)

        self.main_window = main_window
        self._enhanced = bool(enhanced)

        # 标题（增强模式下加后缀，便于用户识别）
        if self._enhanced:
            self.setWindowTitle("大纲 (增强)")

        # 解析器
        self.parser = SymbolParser()

        # 当前文件
        self._current_filepath: Optional[str] = None
        self._current_language: str = ""

        # 当前解析出的符号（顶层）
        self._current_symbols: List[SymbolNode] = []

        # 筛选与排序（仅增强模式使用）
        self._current_filter: str = 'all'
        self._current_sort: str = 'line'

        # 更新定时器（防抖）
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(UPDATE_DELAY_MS)
        self._update_timer.timeout.connect(self._do_update)

        # 设置属性
        self.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
        )
        self.setObjectName("OutlinePanel")

        # 构建 UI
        self._build_ui()

        # 连接信号
        self._connect_signals()

    # ========================================================
    # UI 构建
    # ========================================================
    def _build_ui(self):
        """构建 UI"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部工具栏
        toolbar = QWidget()
        toolbar.setStyleSheet(
            "background-color: #2d2d2d; border-bottom: 1px solid #3c3c3c;"
        )
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(4, 4, 4, 4)
        toolbar_layout.setSpacing(4)

        # 刷新按钮
        self.refresh_btn = QToolButton()
        self.refresh_btn.setText("🔄")
        self.refresh_btn.setToolTip("刷新 (F5)")
        self.refresh_btn.setFixedSize(22, 22)
        self.refresh_btn.clicked.connect(self._do_update)
        toolbar_layout.addWidget(self.refresh_btn)

        # 折叠全部按钮
        self.collapse_btn = QToolButton()
        self.collapse_btn.setText("⊟")
        self.collapse_btn.setToolTip("折叠全部")
        self.collapse_btn.setFixedSize(22, 22)
        self.collapse_btn.clicked.connect(self._collapse_all)
        toolbar_layout.addWidget(self.collapse_btn)

        # 展开全部按钮
        self.expand_btn = QToolButton()
        self.expand_btn.setText("⊞")
        self.expand_btn.setToolTip("展开全部")
        self.expand_btn.setFixedSize(22, 22)
        self.expand_btn.clicked.connect(self._expand_all)
        toolbar_layout.addWidget(self.expand_btn)

        toolbar_layout.addStretch()

        # 筛选下拉（仅增强模式）
        self.filter_combo: Optional[QComboBox] = None
        if self._enhanced:
            self.filter_combo = QComboBox()
            self.filter_combo.setToolTip("按符号类型筛选")
            self.filter_combo.setFixedWidth(90)
            for key, name in FILTER_CATEGORIES.items():
                self.filter_combo.addItem(name, key)
            self.filter_combo.currentIndexChanged.connect(
                self._on_filter_changed
            )
            toolbar_layout.addWidget(self.filter_combo)

        # 排序下拉（仅增强模式）
        self.sort_combo: Optional[QComboBox] = None
        if self._enhanced:
            self.sort_combo = QComboBox()
            self.sort_combo.setToolTip("排序方式")
            self.sort_combo.setFixedWidth(90)
            for key, name in SORT_OPTIONS.items():
                self.sort_combo.addItem(name, key)
            self.sort_combo.currentIndexChanged.connect(
                self._on_sort_changed
            )
            toolbar_layout.addWidget(self.sort_combo)

        layout.addWidget(toolbar)

        # 搜索栏
        search_bar = QWidget()
        search_bar.setStyleSheet(
            "background-color: #2d2d2d; border-bottom: 1px solid #3c3c3c;"
        )
        sb_layout = QHBoxLayout(search_bar)
        sb_layout.setContentsMargins(4, 2, 4, 2)
        sb_layout.setSpacing(4)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("过滤符号...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_search_changed)
        sb_layout.addWidget(self.search_edit, 1)

        layout.addWidget(search_bar)

        # 面包屑（仅增强模式）
        self.breadcrumb_label: Optional[QLabel] = None
        if self._enhanced:
            self.breadcrumb_label = QLabel("")
            self.breadcrumb_label.setStyleSheet(
                "background-color: #2d2d2d; "
                "color: #7ec850; font-size: 11px; "
                "padding: 4px 8px; "
                "border-bottom: 1px solid #3c3c3c;"
            )
            self.breadcrumb_label.setTextInteractionFlags(
                Qt.TextSelectableByMouse
            )
            layout.addWidget(self.breadcrumb_label)

        # 符号树
        self.tree = OutlineTree(enhanced=self._enhanced)
        self.tree.symbol_activated.connect(self._on_symbol_activated)
        if self._enhanced:
            self.tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree, 1)

        # 状态栏
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            "background-color: #2d2d2d; color: #888; "
            "font-size: 11px; padding: 2px 8px; "
            "border-top: 1px solid #3c3c3c;"
        )
        self.status_label.setFixedHeight(20)
        layout.addWidget(self.status_label)

        self.setWidget(container)

        # 应用样式
        self._apply_style()

    def refresh_theme(self, theme):
        """主题变更时刷新样式（v3.0）"""
        try:
            from infrastructure.theme_loader import adapt_qss_colors
            if not hasattr(self, '_original_qss') or not self._original_qss:
                self._original_qss = self.styleSheet()
            if self._original_qss:
                qss = adapt_qss_colors(self._original_qss, theme)
                self.setStyleSheet(qss)
        except Exception as e:
            print(f"[{self.__class__.__name__}] refresh_theme 失败: {e}")

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDockWidget {
                background-color: #252526;
                color: #d4d4d4;
            }
            QDockWidget::title {
                background-color: #2d2d2d;
                padding: 4px 8px;
                border-bottom: 1px solid #3c3c3c;
                font-size: 12px;
            }
            QToolButton {
                background-color: transparent;
                color: #888;
                border: none;
                font-size: 12px;
            }
            QToolButton:hover {
                background-color: #3c3c3c;
                color: #fff;
                border-radius: 3px;
            }
            QLineEdit, QComboBox {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 11px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #007acc;
            }
            QComboBox::drop-down { border: none; width: 16px; }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: #d4d4d4;
                selection-background-color: #094771;
            }
        """)

    def _connect_signals(self):
        """连接事件总线信号"""
        try:
            bus.cursor_moved.connect(self._on_cursor_moved)
            bus.file_opened.connect(self._on_file_opened)
            # P1-B3: 监听文本变化，强制刷新大纲
            # 原实现只监听 file_opened，同一文件编辑后不刷新。
            try:
                bus.file_modified.connect(self._on_file_modified)
                bus.file_saved.connect(self._on_file_modified)
            except Exception:
                pass
        except Exception:
            pass

    def _on_file_modified(self, event):
        """文件内容变化 → 强制重新解析。

        P1-B3 修复：
            直接把 _current_filepath 置空，让 _do_update 中的
            "filepath != _current_filepath" 分支触发重新解析。
        """
        try:
            self._current_filepath = None
            self.schedule_update()
        except Exception:
            pass

    # ========================================================
    # 更新
    # ========================================================
    def schedule_update(self):
        """调度更新（防抖）"""
        self._update_timer.start()

    def _do_update(self):
        """执行更新"""
        try:
            if not self.main_window:
                return

            # 获取当前编辑器
            proxy = self.main_window.tabs.current_proxy()
            if not proxy:
                self.tree.clear()
                self._current_symbols = []
                self.status_label.setText("")
                self._current_filepath = None
                if self.breadcrumb_label:
                    self.breadcrumb_label.setText("")
                return

            # 获取文件路径和语言
            filepath = proxy.document.filepath if proxy.document else None
            language = ""

            if filepath:
                language = self._detect_language(filepath)

            # 文件或语言变化 → 重新解析
            if (filepath != self._current_filepath or
                    language != self._current_language):
                self._current_filepath = filepath
                self._current_language = language

                # P2-C6: 限制读取行数
                # 原实现直接 proxy.get_text()，100MB 文件会
                # 卡住主线程几秒甚至 OOM。
                MAX_LINES_READ = 50000
                text = ""
                try:
                    sc = getattr(proxy, 'sc', None)
                    if sc is not None:
                        total = sc.SendScintilla(sc.SCI_GETLINECOUNT)
                        n = min(MAX_LINES_READ, total)
                        lines = [sc.text(i) for i in range(n)]
                        text = "\n".join(lines)
                    else:
                        text = proxy.get_text()
                except Exception:
                    try:
                        text = proxy.get_text()[:500_000]
                    except Exception:
                        text = ""

                self._current_symbols = self.parser.parse(
                    text, language, filepath
                )

            self._render()

        except Exception as e:
            print(f"[OutlinePanel] 更新失败: {e}")
            self.status_label.setText(f"错误: {e}")

    def update_symbols(self, editor=None):
        """
        更新符号（外部调用接口）。

        参数:
            editor: 编辑器实例（忽略，使用 main_window 获取）
        """
        self.schedule_update()

    # ========================================================
    # 渲染
    # ========================================================
    def _render(self):
        """渲染符号树"""
        keyword = self.search_edit.text().strip().lower()
        filter_key = self._current_filter if self._enhanced else 'all'

        self.tree.setUpdatesEnabled(False)
        try:
            self.tree.clear()

            for symbol in self._current_symbols:
                self._add_symbol_item(None, symbol, keyword, filter_key)

            # 展开所有
            self.tree.expandAll()

            self._update_status()
        finally:
            self.tree.setUpdatesEnabled(True)

    def _add_symbol_item(self, parent_item, symbol,
                          keyword: str, filter_key: str) -> bool:
        """
        递归添加符号项。

        返回: 是否添加了该项（用于搜索过滤的父节点保留判断）
        """
        # 类型筛选
        if filter_key != 'all':
            if filter_key == 'class' and symbol.type not in (
                'class', 'interface', 'struct', 'enum'
            ):
                if not symbol.children:
                    return False
            elif filter_key == 'function' and symbol.type != 'function':
                if not symbol.children:
                    return False
            elif filter_key == 'method' and symbol.type != 'method':
                if not symbol.children:
                    return False
            elif filter_key == 'variable' and symbol.type != 'variable':
                if not symbol.children:
                    return False
            elif filter_key == 'constant' and symbol.type != 'constant':
                if not symbol.children:
                    return False

        # 搜索匹配
        text = (symbol.name + ' ' + symbol.signature).lower()
        self_match = (not keyword) or (keyword in text)

        # 创建项
        if parent_item:
            item = QTreeWidgetItem(parent_item)
        else:
            item = QTreeWidgetItem(self.tree)

        # 图标 + 名称
        icon = SYMBOL_TYPE_ICONS.get(symbol.type, '•')
        item.setText(COL_SYMBOL,
                     f"{icon} {symbol.name}{symbol.signature or ''}")
        item.setText(COL_LINE, str(symbol.line + 1))

        # 类型列（仅增强模式）
        if self._enhanced:
            type_name = SYMBOL_TYPES.get(symbol.type, symbol.type)
            item.setText(COL_TYPE, type_name)

        # 数据（供右键菜单和双击使用）
        item.setData(COL_SYMBOL, Qt.UserRole, symbol)
        item.setData(COL_SYMBOL, Qt.UserRole + 1, symbol.line)

        # 颜色
        color = SYMBOL_TYPE_COLORS.get(symbol.type)
        if color:
            item.setForeground(COL_SYMBOL, QBrush(color))

        # 加粗类/接口
        if symbol.type in ('class', 'interface', 'struct', 'namespace'):
            font = item.font(COL_SYMBOL)
            font.setBold(True)
            item.setFont(COL_SYMBOL, font)

        # 递归子节点
        any_child = False
        for child in symbol.children:
            if self._add_symbol_item(item, child, keyword, filter_key):
                any_child = True

        # 如果自己不匹配且无子节点匹配 → 删除
        if not self_match and not any_child:
            if parent_item:
                parent_item.removeChild(item)
            else:
                self.tree.takeTopLevelItem(
                    self.tree.indexOfTopLevelItem(item)
                )
            return False

        # 有子节点匹配时展开
        if any_child:
            item.setExpanded(True)

        return True

    # ========================================================
    # 语言检测
    # ========================================================
    def _detect_language(self, filepath: str) -> str:
        """根据文件扩展名检测语言"""
        ext = os.path.splitext(filepath)[1].lower()

        language_map = {
            '.py': 'Python',
            '.pyw': 'Python',
            '.js': 'JavaScript',
            '.jsx': 'JavaScript React',
            '.ts': 'TypeScript',
            '.tsx': 'TypeScript React',
            '.c': 'C',
            '.cpp': 'C++',
            '.cc': 'C++',
            '.cxx': 'C++',
            '.h': 'C',
            '.hpp': 'C++',
            '.java': 'Java',
            '.go': 'Go',
            '.rs': 'Rust',
            '.rb': 'Ruby',
            '.php': 'PHP',
        }

        return language_map.get(ext, '')

    # ========================================================
    # 跟随光标高亮（增强）
    # ========================================================
    def _on_item_clicked(self, item, column):
        """单击 — 更新面包屑 + 发出信号"""
        symbol = item.data(COL_SYMBOL, Qt.UserRole)
        if not symbol:
            return

        self._update_breadcrumb(item)
        self.symbol_selected.emit(symbol.name, symbol.line)

    def _update_breadcrumb(self, item):
        """更新面包屑显示"""
        if not self.breadcrumb_label:
            return

        parts = []
        current = item
        while current:
            s = current.data(COL_SYMBOL, Qt.UserRole)
            if s:
                parts.insert(0, s.name)
            current = current.parent()

        if parts:
            self.breadcrumb_label.setText(" › ".join(parts))
        else:
            self.breadcrumb_label.setText("")

    def _highlight_current_symbol(self, proxy):
        """跟随光标，高亮光标所在符号"""
        try:
            cursor_line, _ = proxy.get_cursor_position()

            def _find_symbol(item) -> Optional[QTreeWidgetItem]:
                symbol = item.data(COL_SYMBOL, Qt.UserRole)
                if not symbol:
                    return None

                if symbol.line <= cursor_line <= symbol.end_line:
                    # 优先匹配最深的子符号
                    for i in range(item.childCount()):
                        child = item.child(i)
                        found = _find_symbol(child)
                        if found:
                            return found
                    return item

                return None

            best_match = None
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                found = _find_symbol(item)
                if found:
                    best_match = found

            if best_match:
                self.tree.setCurrentItem(best_match)
                self.tree.scrollToItem(best_match)
        except Exception:
            pass

    # ========================================================
    # 交互
    # ========================================================
    def _on_symbol_activated(self, line: int):
        """符号激活（双击）"""
        self.symbol_clicked.emit(line)

        # 跳转到主编辑器
        if self.main_window:
            proxy = self.main_window.tabs.current_proxy()
            if proxy:
                try:
                    proxy.goto_line(line)
                    proxy.sc.setFocus()
                except Exception:
                    pass

        # 获取符号名称
        item = self.tree.currentItem()
        if item:
            symbol = item.data(COL_SYMBOL, Qt.UserRole)
            if symbol:
                self.symbol_selected.emit(symbol.name, line)

    def _on_search_changed(self, text: str):
        """搜索框变化"""
        self._render()

    def _on_filter_changed(self, index: int):
        """筛选变化（增强模式）"""
        if not self.filter_combo:
            return
        self._current_filter = self.filter_combo.currentData() or 'all'
        self._render()

    def _on_sort_changed(self, index: int):
        """排序变化（增强模式）"""
        if not self.sort_combo:
            return
        self._current_sort = self.sort_combo.currentData() or 'line'
        self._apply_sort()
        self._render()

    def _apply_sort(self):
        """对顶层符号列表排序"""
        if self._current_sort == 'line':
            self._current_symbols.sort(key=lambda s: s.line)
        elif self._current_sort == 'name':
            self._current_symbols.sort(key=lambda s: s.name.lower())
        elif self._current_sort == 'type':
            self._current_symbols.sort(key=lambda s: (s.type, s.line))

    def _collapse_all(self):
        """折叠全部"""
        self.tree.collapseAll()

    def _expand_all(self):
        """展开全部"""
        self.tree.expandAll()

    def _on_cursor_moved(self, event: CursorEvent):
        """光标移动（增强模式：跟随高亮）"""
        if not self._enhanced:
            return
        if self.main_window:
            proxy = self.main_window.tabs.current_proxy()
            if proxy:
                self._highlight_current_symbol(proxy)

    def _on_file_opened(self, event):
        """文件打开"""
        self.schedule_update()

    def _update_status(self):
        """更新状态栏"""
        # 统计各类型数量
        counts: Dict[str, int] = {}

        def _count(nodes):
            for s in nodes:
                counts[s.type] = counts.get(s.type, 0) + 1
                if s.children:
                    _count(s.children)

        _count(self._current_symbols)

        total = sum(counts.values())

        if total == 0:
            self.status_label.setText(
                f"{self._current_language or '未知'} · 无符号"
            )
        else:
            parts = [f"{self._current_language or '?'} · {total} 符号"]
            if self._enhanced:
                for t in ('class', 'function', 'method'):
                    if t in counts:
                        parts.append(
                            f"{SYMBOL_TYPES.get(t, t)}: {counts[t]}"
                        )
            self.status_label.setText(" · ".join(parts))

    # ========================================================
    # 显示/隐藏
    # ========================================================
    def showEvent(self, event):
        """显示事件"""
        super().showEvent(event)
        # 显示时更新一次
        self.schedule_update()

    # ========================================================
    # 公共接口
    # ========================================================
    def get_all_symbols(self) -> List[Tuple[str, int]]:
        """获取所有符号（供命令面板使用）"""
        result: List[Tuple[str, int]] = []

        def _collect(nodes):
            for s in nodes:
                result.append((s.name, s.line))
                if s.children:
                    _collect(s.children)

        _collect(self._current_symbols)
        return result

    def get_symbol_count(self) -> int:
        """获取符号数量"""
        return len(self.get_all_symbols())

    def clear(self):
        """清空"""
        self.tree.clear()
        self._current_symbols = []
        self._current_filepath = None
        self.status_label.setText("")
        if self.breadcrumb_label:
            self.breadcrumb_label.setText("")

    def focus_search(self):
        """聚焦搜索框"""
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出面板信息"""
        lines = ["OutlinePanel", "=" * 60]
        lines.append(f"当前文件: {self._current_filepath}")
        lines.append(f"当前语言: {self._current_language}")
        lines.append(f"符号数: {self.get_symbol_count()}")
        lines.append(f"过滤: {self.search_edit.text()}")
        lines.append(f"增强模式: {self._enhanced}")
        if self._enhanced:
            lines.append(f"筛选: {self._current_filter}")
            lines.append(f"排序: {self._current_sort}")

        # 符号列表
        symbols = self.get_all_symbols()
        if symbols:
            lines.append("")
            lines.append("符号列表:")
            for name, line in symbols[:20]:
                lines.append(f"  {line + 1:5d}  {name}")
            if len(symbols) > 20:
                lines.append(f"  ... 及其他 {len(symbols) - 20} 个")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<OutlinePanel file={self._current_filepath!r} "
                f"symbols={self.get_symbol_count()} "
                f"enhanced={self._enhanced}>")


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)

    # 创建主窗口
    win = QMainWindow()
    win.setWindowTitle("OutlinePanel 测试（合并版）")
    win.resize(1000, 700)

    # 测试代码
    test_python = '''#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os

MAX_VALUE = 100
MIN_VALUE = 0

@decorator
class MyClass:
    """示例类"""

    def __init__(self, value):
        self.value = value

    def get_value(self):
        return self.value

    @property
    def double_value(self):
        return self.value * 2


def main():
    """主函数"""
    obj = MyClass(42)
    print(obj.get_value())
    return 0


def helper_function(x, y):
    return x + y


if __name__ == '__main__':
    main()
'''

    print("=== 测试符号解析器 ===")
    parser = SymbolParser()
    symbols = parser.parse(test_python, 'Python')

    def print_symbols(nodes, indent=0):
        for node in nodes:
            print(f"{'  ' * indent}{node.display_name} (行 {node.line + 1})")
            print_symbols(node.children, indent + 1)

    print_symbols(symbols)
    print()

    # 测试 1：基础模式
    panel_basic = OutlinePanel(main_window=None, enhanced=False)
    panel_basic.show()
    panel_basic.tree.clear()
    for s in symbols:
        panel_basic._add_symbol_item(None, s, "", "all")
    panel_basic._current_symbols = symbols

    print("=== 基础模式 ===")
    print(panel_basic.dump())
    print()

    # 测试 2：增强模式
    panel_enhanced = OutlinePanel(main_window=None, enhanced=True)
    panel_enhanced.show()
    panel_enhanced.tree.clear()
    for s in symbols:
        panel_enhanced._add_symbol_item(None, s, "", "all")
    panel_enhanced._current_symbols = symbols
    panel_enhanced._current_language = "Python"

    print("=== 增强模式 ===")
    print(panel_enhanced.dump())
    print()

    # 测试筛选
    print("=== 测试筛选 '类/接口' ===")
    panel_enhanced._current_filter = 'class'
    panel_enhanced._render()
    print(f"筛选后（应该只显示类）")
    print()

    # 测试搜索
    print("=== 测试搜索 'value' ===")
    panel_enhanced._current_filter = 'all'
    panel_enhanced.search_edit.setText("value")
    print(f"搜索后（应该只显示含 'value' 的符号）")
    print()

    # 定时退出
    from PyQt5.QtCore import QTimer
    QTimer.singleShot(2000, app.quit)

    sys.exit(app.exec())