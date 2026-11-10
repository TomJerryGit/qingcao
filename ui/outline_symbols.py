# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""符号类型/解析（v2.24 从 outline_panel.py 拆出）。"""

from ui.outline_common import *  # noqa: F401,F403,F405


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

    name: str = ""  # 符号名称
    type: str = "unknown"  # 符号类型（class/function/...）
    line: int = 0  # 起始行号（0 开始）
    col: int = 0  # 起始列（0 开始）
    end_line: int = 0  # 结束行号（0 开始）
    indent: int = 0  # 缩进层级
    parent_name: Optional[str] = None  # 父符号名称
    signature: str = ""  # 签名（如参数列表）
    doc: str = ""  # 文档字符串
    children: List["SymbolNode"] = field(default_factory=list)

    def add_child(self, child: "SymbolNode"):
        """添加子节点"""
        child.parent_name = self.name
        self.children.append(child)

    @property
    def display_name(self) -> str:
        """显示名称"""
        icon = SYMBOL_TYPE_ICONS.get(self.type, "•")
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
        return (
            f"<SymbolNode {self.type} {self.name} line={self.line} children={len(self.children)}>"
        )


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
            "Python": self._parse_python,
            "JavaScript": self._parse_javascript,
            "TypeScript": self._parse_typescript,
            "JavaScript React": self._parse_javascript,
            "TypeScript React": self._parse_typescript,
            "C": self._parse_c_cpp,
            "C++": self._parse_c_cpp,
            "Java": self._parse_java,
            "Go": self._parse_go,
            "Rust": self._parse_rust,
            "Ruby": self._parse_ruby,
            "PHP": self._parse_php,
        }

    # --------------------------------------------------------
    # 主入口
    # --------------------------------------------------------
    def parse(self, text: str, language: str, filepath: Optional[str] = None) -> List[SymbolNode]:
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
            text = "\n".join(lines)

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
        class_pattern = re.compile(r"^(\s*)class\s+(\w+)(?:\s*\(([^)]*)\))?\s*:")

        # 函数/方法定义
        def_pattern = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)")

        # 装饰器
        decorator_pattern = re.compile(r"^(\s*)@(\w+)")

        # 模块级常量（大写字母）
        constant_pattern = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*")

        # 模块级变量
        variable_pattern = re.compile(r"^(\w+)\s*=\s*")

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
                    type="class",
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
                symbol_type = "method" if indent > 0 else "function"

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
            if const_match and not line.strip().startswith("#"):
                name = const_match.group(1)
                if not any(s.name == name and s.line == i for s in symbols):
                    node = SymbolNode(
                        name=name,
                        type="constant",
                        line=i,
                        col=0,
                        indent=0,
                    )
                    symbols.append(node)
                continue

            # 重置装饰器
            if line.strip() and not line.strip().startswith("@"):
                pending_decorators = []

        return symbols

    # --------------------------------------------------------
    # JavaScript 解析
    # --------------------------------------------------------
    def _parse_javascript(self, text: str, lines: List[str]) -> List[SymbolNode]:
        """解析 JavaScript 符号"""
        return self._parse_js_like(text, lines, is_ts=False)

    def _parse_typescript(self, text: str, lines: List[str]) -> List[SymbolNode]:
        """解析 TypeScript 符号"""
        return self._parse_js_like(text, lines, is_ts=True)

    def _parse_js_like(self, text: str, lines: List[str], is_ts: bool) -> List[SymbolNode]:
        """解析类 JavaScript 语言"""
        symbols = []

        patterns = [
            # class Foo {  /  class Foo extends Bar {
            (re.compile(r"^(\s*)class\s+(\w+)(?:\s+extends\s+(\w+))?"), "class"),
            # function foo() {  /  async function foo() {
            (re.compile(r"^(\s*)(?:async\s+)?function\s+(\w+)\s*\("), "function"),
            # const foo = () => {  /  const foo = function() {
            (
                re.compile(
                    r"^(\s*)(?:const|let|var)\s+(\w+)\s*=\s*"
                    r"(?:async\s+)?(?:function|\()"
                ),
                "function",
            ),
            # foo() {  (class method)
            (re.compile(r"^(\s{2,})(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{"), "method"),
            # interface Foo {
            (re.compile(r"^(\s*)interface\s+(\w+)"), "interface"),
            # type Foo =
            (re.compile(r"^(\s*)type\s+(\w+)"), "type"),
            # enum Foo {
            (re.compile(r"^(\s*)enum\s+(\w+)"), "enum"),
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
        class_pattern = re.compile(r"^\s*(class|struct|union)\s+(\w+)")

        # 函数（简单匹配）
        func_pattern = re.compile(r"^(\w[\w\s\*&:<>]*?)\s+(\w+)\s*\([^)]*\)\s*(?:const)?\s*\{?")

        # 命名空间
        namespace_pattern = re.compile(r"^\s*namespace\s+(\w+)")

        # #define 宏
        macro_pattern = re.compile(r"^\s*#define\s+(\w+)")

        # 枚举
        enum_pattern = re.compile(r"^\s*enum\s+(?:class\s+)?(\w+)")

        for i, line in enumerate(lines):
            # 跳过注释
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*"):
                continue

            # 宏
            macro_match = macro_pattern.match(line)
            if macro_match:
                node = SymbolNode(
                    name=macro_match.group(1),
                    type="macro",
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
                    type="namespace",
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
                    type="enum",
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
                if name not in (
                    "if",
                    "else",
                    "for",
                    "while",
                    "switch",
                    "return",
                    "case",
                    "break",
                    "continue",
                ):
                    node = SymbolNode(
                        name=name,
                        type="function",
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
            r"^\s*(?:public|private|protected)?\s*"
            r"(?:abstract|final|static)?\s*"
            r"(class|interface|enum)\s+(\w+)"
        )

        method_pattern = re.compile(
            r"^\s*(?:public|private|protected|static|final|abstract|"
            r"synchronized|native|\s)+\s*"
            r"(\w+(?:<[^>]+>)?)\s+(\w+)\s*\([^)]*\)"
        )

        field_pattern = re.compile(
            r"^\s*(?:public|private|protected|static|final|"
            r"transient|volatile|\s)+\s*"
            r"(\w+(?:<[^>]+>)?)\s+(\w+)\s*(?:=|;)"
        )

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
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
                if name not in ("if", "else", "for", "while", "switch"):
                    node = SymbolNode(
                        name=name,
                        type="method",
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
                    type="field",
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

        func_pattern = re.compile(r"^\s*func\s+(?:\([^)]+\)\s+)?(\w+)\s*\([^)]*\)")

        type_pattern = re.compile(r"^\s*type\s+(\w+)\s+(struct|interface)")

        var_pattern = re.compile(r"^\s*(?:var|const)\s+(\w+)")

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("//"):
                continue

            func_match = func_pattern.match(line)
            if func_match:
                name = func_match.group(1)
                # 判断是否为方法（带接收者）
                is_method = ")" in line.split("func")[1].split("(")[0] if "func" in line else False
                node = SymbolNode(
                    name=name,
                    type="method" if is_method else "function",
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
                    type="variable",
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
            (re.compile(r"^\s*(?:pub\s+)?fn\s+(\w+)"), "function"),
            (re.compile(r"^\s*(?:pub\s+)?struct\s+(\w+)"), "struct"),
            (re.compile(r"^\s*(?:pub\s+)?enum\s+(\w+)"), "enum"),
            (re.compile(r"^\s*(?:pub\s+)?trait\s+(\w+)"), "interface"),
            (re.compile(r"^\s*(?:pub\s+)?mod\s+(\w+)"), "namespace"),
            (re.compile(r"^\s*(?:pub\s+)?type\s+(\w+)"), "type"),
            (re.compile(r"^\s*(?:pub\s+)?const\s+(\w+)"), "constant"),
            (re.compile(r"^\s*(?:pub\s+)?static\s+(\w+)"), "variable"),
            (re.compile(r"^\s*impl\s+(?:<[^>]*>\s+)?(\w+)"), "class"),
            (re.compile(r"^\s*macro_rules!\s+(\w+)"), "macro"),
        ]

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*"):
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
            (re.compile(r"^\s*class\s+(\w+)"), "class"),
            (re.compile(r"^\s*module\s+(\w+)"), "module"),
            (re.compile(r"^\s*def\s+(\w+[?!]?)"), "method"),
        ]

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
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
            (re.compile(r"^\s*(?:abstract\s+|final\s+)?class\s+(\w+)"), "class"),
            (re.compile(r"^\s*interface\s+(\w+)"), "interface"),
            (re.compile(r"^\s*trait\s+(\w+)"), "interface"),
            (
                re.compile(
                    r"^\s*(?:public|private|protected|static|\s)*"
                    r"function\s+(\w+)"
                ),
                "function",
            ),
            (
                re.compile(
                    r"^\s*(?:public|private|protected)?\s*"
                    r"\$(\w+)\s*="
                ),
                "variable",
            ),
        ]

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*"):
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
    def _parse_generic(self, text: str, lines: List[str]) -> List[SymbolNode]:
        """通用解析（fallback）"""
        symbols = []

        # 尝试匹配常见的函数/类定义
        patterns = [
            (re.compile(r"^\s*(?:class|struct)\s+(\w+)"), "class"),
            (re.compile(r"^\s*def\s+(\w+)"), "function"),
            (re.compile(r"^\s*function\s+(\w+)"), "function"),
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
    def _build_hierarchy(self, flat_symbols: List[SymbolNode]) -> List[SymbolNode]:
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
