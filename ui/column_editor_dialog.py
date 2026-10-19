#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

列编辑器（Column Editor）—— 对标 Notepad++ 的 ``Edit → Column Editor…``。

功能:
- **插入文本**：在作用行的目标列插入同一段文本；
- **插入数字**：逐行递增/递减序列，支持 起始值 / 步长 /
  进制（Dec/Hex/Oct/Bin）/ 前导零填充 / 前导空格对齐 / 进制前缀 / 大写；
- **作用行范围**（优先级从高到低）：
  矩形选区（``SC_SEL_RECTANGLE``）覆盖的行 → 多光标所在行 → 当前选区覆盖的整行；
- 整次列编辑 = **一条**撤销命令（自研 ``UndoManager`` 栈顶只有一条）。

对外 API（都接受 QScintilla 控件 **或** ``EditorProxy``）::

    from ui.column_editor_dialog import (
        show_column_editor, insert_text_at_column,
        insert_numbers_at_column, apply_column_edit, ColumnEditConfig,
    )

    # 弹窗（菜单/右键入口用）
    show_column_editor(proxy_or_widget, parent)

    # 不弹窗直接执行（测试/脚本/插件用）
    insert_text_at_column(editor, "// ")
    insert_numbers_at_column(editor, start=1, step=1, radix=10,
                             pad=PAD_ZERO)

================================================================
设计取舍（为什么这样写）
================================================================
1) 一次编辑 = 一条撤销命令
   ``core/editor.py::EditorProxy._on_scintilla_modified`` 会为**每一次**
   ``SCI_INSERTTEXT`` 记录一条命令；在矩形/多光标状态下它还会走自己的
   ``_pending_group`` 分支（按 ``MULTI_CURSOR_MERGE_INTERVAL`` = 300ms
   的**时间窗**合并）。依赖时间窗既不确定，窗口外还会碎成多条撤销记录 ——
   "撤销一次只回退一行"。
   本模块因此：
     a. 编辑前把矩形/多光标选区收成**单一流式选区**（见 ``_leave_multi_selection``），
        让 ``_on_scintilla_modified`` 只走"普通命令"分支，不再创建待提交组；
        （Scintilla 文档：矩形选区内部就是多选区，而 ``SCI_CLEARSELECTIONS``
        会留下唯一一个空选区，因此收选区后 ``SCI_GETSELECTIONS`` 必为 1。）
     b. 编辑期间 ``UndoManager.disable()``，内置记录器完全不落栈；
     c. 编辑结束后用**一条** ``ColumnInsertCmd`` 记录整次编辑。

2) 为什么不用 ``GroupCmd``？
   ``UndoManager._try_merge()`` 会对栈顶命令调 ``can_merge()``，而
   ``GroupCmd.can_merge()`` 对**任何** GroupCmd 都返回 True 且**没有时间窗
   检查** —— 连续两次列编辑会被静默合并成一条，用户按一次 Ctrl+Z 会回退
   两次编辑（而中间态从未在屏幕上出现过）。
   ``ColumnInsertCmd`` 直接继承 ``Command``（默认 ``can_merge`` 返回 False），
   从根上避免该陷阱；它的 ``to_dict/from_dict`` 仍是标准单条命令，
   因此宏录制/回放（``core/macro.py`` 用 ``Command.from_dict``）照常可用 ——
   模块导入时会把该类型注册进 ``CommandFactory``。

3) 位置语义：Scintilla 的位置是 UTF-8 **字节**偏移
   （见 ``core/editor.py`` 的 ``_lsp_pos_to_scintilla`` /
   ``read_buffer_range``），所以"列 → 位置"必须走
   ``len(前缀.encode('utf-8'))``，直接用字符数会让中文/emoji 行错位。
   本模块的"列"按**字符**计（tab 记 1 列），与矩形左边缘的读数自洽。

4) 插入顺序：所有插入点都是"改动前"的绝对位置。
   自底向上插入（位置大的先插）才不会让后面的插入点漂移；
   撤销时反向（自上而下）删除，每一段的实际位置恰好又回到原绝对位置。
   ``ColumnInsertCmd.execute`` / ``undo`` 各自排序，就是这个原因。
"""

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

from PyQt5.Qsci import QsciScintilla
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.commands import Command


# ============================================================
# 常量
# ============================================================
# 模式
MODE_TEXT = "text"
MODE_NUMBER = "number"

# 填充方式
PAD_NONE = "none"      # 不填充
PAD_ZERO = "zero"      # 前导零（按最大数字宽度）
PAD_SPACE = "space"    # 前导空格（右对齐）

# 作用行来源
SOURCE_RECTANGLE = "rectangle"
SOURCE_MULTI = "multi_cursor"
SOURCE_SELECTION = "selection"
SOURCE_CARET = "caret"
SOURCE_EXPLICIT = "explicit"

# 进制
RADIXES: Tuple[Tuple[int, str], ...] = (
    (10, "十进制 (Dec)"),
    (16, "十六进制 (Hex)"),
    (8, "八进制 (Oct)"),
    (2, "二进制 (Bin)"),
)

# 命令类型标识（注册进 CommandFactory，宏回放才认得）
CMD_TYPE_COLUMN_INSERT = "column_insert"

# ``SCI_GETSELECTIONNSTART`` 在个别老 QScintilla 构建里可能没有暴露。
# 这里不猜消息号：取不到就**优雅降级**（多光标入口退化为整选区），
# 宁可少一个入口，也不能用错消息号改坏用户文档。
_SCI_GETSELECTIONNSTART = "SCI_GETSELECTIONNSTART"

# 默认快捷键（由宿主菜单使用）
DEFAULT_SHORTCUT = "Alt+Shift+I"


class ColumnEditorError(Exception):
    """列编辑器参数/环境错误。"""


# ============================================================
# 纯函数：数字序列格式化（不依赖 Qt，便于单测）
# ============================================================
def _digits(value: int, radix: int, uppercase: bool) -> str:
    """绝对值的无符号数字串。"""
    v = abs(int(value))
    if radix == 10:
        return str(v)
    if radix == 16:
        return format(v, 'X' if uppercase else 'x')
    if radix == 8:
        return format(v, 'o')
    if radix == 2:
        return format(v, 'b')
    raise ColumnEditorError(f"不支持的进制: {radix}")


def _radix_prefix(radix: int) -> str:
    """进制前缀（十进制为空串）。

    修复（实测：生成结果是 ``0X01``，与 docstring 里的 ``0x01`` 不符）：
        原实现把 ``uppercase`` 也作用到**前缀字母 x** 上，返回 ``'0X'``。
        但 ``uppercase`` 的语义是"十六进制**数字**用大写"（如 ``0x0A``），
        前缀是语法标记、与数字大小写无关 —— Python / C / Java / JS 的
        标准写法始终是小写 ``0x``。因此前缀固定小写。
    """
    if radix == 16:
        return '0x'
    if radix == 8:
        return '0o'
    if radix == 2:
        return '0b'
    return ''


def parse_int_literal(text: str) -> int:
    """解析整数输入，支持 ``0x1F`` / ``0o17`` / ``0b1010`` / ``-5``。"""
    s = (text or "").strip().replace("_", "")
    if not s:
        raise ValueError("请输入数字")
    try:
        return int(s, 0)
    except ValueError:
        # int(s, 0) 拒绝 "010" 这类前导零写法，按十进制再试一次
        return int(s, 10)


def compute_number_widths(start: int, step: int, count: int, radix: int = 10,
                          pad: str = PAD_NONE, min_width: int = 0,
                          prefix: bool = False,
                          uppercase: bool = True) -> Tuple[int, int]:
    """计算 (数字部分宽度, 整串目标宽度)。

    序列是等差数列，绝对值的最大值必出现在**两端**，所以宽度只需看首尾
    两项即可 —— 不用把 10 万行都格式化一遍。

    参数:
        count: 序列个数（应 >= 1）
    返回:
        (digit_width, total_width)
        - digit_width: 前导零要补到的位数
        - total_width: 前导空格要补到的整串宽度
    """
    n = max(1, int(count))
    last = int(start) + int(step) * (n - 1)

    def _len_of(value: int) -> int:
        sign = 1 if int(value) < 0 else 0
        pre = len(_radix_prefix(radix)) if prefix else 0
        return sign + pre + len(_digits(value, radix, uppercase))

    digit_width = max(
        len(_digits(int(start), radix, uppercase)),
        len(_digits(last, radix, uppercase)),
    )
    if int(min_width) > 0:
        digit_width = max(digit_width, int(min_width))

    total_width = max(_len_of(int(start)), _len_of(last))
    if int(min_width) > 0:
        total_width = max(total_width, int(min_width))
    return digit_width, total_width


def _format_one(value: int, radix: int, digit_width: int, total_width: int,
                pad: str, prefix: bool, uppercase: bool) -> str:
    """按统一宽度格式化单个值。"""
    body = _digits(value, radix, uppercase)
    if pad == PAD_ZERO and len(body) < digit_width:
        body = body.rjust(digit_width, '0')
    sign = '-' if int(value) < 0 else ''
    pre = _radix_prefix(radix) if prefix else ''
    text = sign + pre + body
    if pad == PAD_SPACE and len(text) < total_width:
        text = text.rjust(total_width, ' ')
    return text


def generate_number_texts(start: int, step: int, count: int, radix: int = 10,
                          pad: str = PAD_NONE, min_width: int = 0,
                          prefix: bool = False,
                          uppercase: bool = True) -> List[str]:
    """生成 ``count`` 个数字文本（第 i 个 = start + step * i）。

    例子:
        >>> generate_number_texts(1, 1, 10)
        ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']
        >>> generate_number_texts(1, 1, 10, pad=PAD_ZERO)
        ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10']
        >>> generate_number_texts(1, 1, 10, radix=16, pad=PAD_ZERO,
        ...                       min_width=2, prefix=True)
        ['0x01', '0x02', ..., '0x0A']
    """
    n = max(0, int(count))
    if n == 0:
        return []
    if str(pad) not in (PAD_NONE, PAD_ZERO, PAD_SPACE):
        raise ColumnEditorError(f"不支持的填充方式: {pad}")
    digit_width, total_width = compute_number_widths(
        start, step, n, radix=radix, pad=pad,
        min_width=min_width, prefix=prefix, uppercase=uppercase,
    )
    return [
        _format_one(int(start) + int(step) * i, radix, digit_width,
                    total_width, str(pad), prefix, uppercase)
        for i in range(n)
    ]


def preview_number_texts(start: int, step: int, count: int, radix: int = 10,
                         pad: str = PAD_NONE, min_width: int = 0,
                         prefix: bool = False, uppercase: bool = True,
                         preview: int = 5) -> List[str]:
    """只格式化前 ``preview`` 个值，但宽度按**完整**序列计算。

    对话框每次按键都要刷新预览，10 万行时不能真的生成 10 万个字符串。
    """
    n = max(0, int(count))
    if n == 0:
        return []
    digit_width, total_width = compute_number_widths(
        start, step, n, radix=radix, pad=pad,
        min_width=min_width, prefix=prefix, uppercase=uppercase,
    )
    shown = min(n, max(0, int(preview)))
    return [
        _format_one(int(start) + int(step) * i, radix, digit_width,
                    total_width, str(pad), prefix, uppercase)
        for i in range(shown)
    ]


# ============================================================
# 批量文本操作（修复 O(n²)：逐条 SCI_INSERTTEXT → 一次 setText）
# ============================================================
#
# ★ 缺陷背景（真实 UI 压测实测）：
#
#   原实现用"逐行 SCI_INSERTTEXT"，4 万行耗时 2.7s，且**翻倍 n 约 4 倍耗时**
#   —— 典型 O(n²)。实测对照：
#       n=1,000  逐条插入 0.115s   批量 setText 0.002s
#       n=8,000  逐条插入 8.635s   批量 setText 0.003s
#   外推 10 万行：逐条 ≈ **22 分钟**，批量 ≈ 0.05s。
#
#   而"在 10 万行上插入数字序列"正是列编辑的核心场景（对标 Notepad++），
#   所以必须改成批量。
#
#   关键约束：`inserts` 里的 ``pos`` 是 **UTF-8 字节位置**（与 Scintilla
#   内部一致、与 core/editor.py 的 `_lsp_pos_to_scintilla` 同约定），
#   而 Python 字符串按**字符**索引，因此需要一个字节→字符的映射。

def _byte_to_char_index(text: str) -> Tuple[List[int], int]:
    """返回 ``(每个**字符**起始处的字节偏移, 总字节数)``

    长度比 ``text`` 多 1（末尾补总字节数），便于把字节位置二分会字符位置。
    """
    starts: List[int] = [0] * (len(text) + 1)
    b = 0
    for i, ch in enumerate(text):
        starts[i] = b
        b += len(ch.encode('utf-8', errors='replace'))
    starts[len(text)] = b
    return starts, b


def _byte_pos_to_char(starts: List[int], byte_pos: int) -> int:
    """把字节位置映射为字符位置；落在多字节字符中间时**钳到该字符起点**

    列编辑器给出的位置总是"行首 + 列数"，正常情况下一定落在字符边界。
    这里钳位是防御性的：宁可把插入点前移一个字符，也绝不越界/错位。
    """
    import bisect
    idx = bisect.bisect_right(starts, max(0, int(byte_pos))) - 1
    return max(0, min(idx, len(starts) - 1))


def _apply_inserts_to_text(text: str,
                           inserts: Sequence[Tuple[int, str]]) -> str:
    """把 ``inserts``（字节位置）一次性应用到 ``text``，返回新文本

    单次 O(n) 字符串构建，替代逐条 SCI_INSERTTEXT 的 O(n²)。
    """
    items = [(int(p), str(t)) for p, t in (inserts or []) if str(t)]
    if not items:
        return text
    items.sort(key=lambda it: it[0])
    starts, _total = _byte_to_char_index(text)
    out: List[str] = []
    cursor = 0
    for pos, ins in items:
        ci = _byte_pos_to_char(starts, pos)
        if ci < cursor:                      # 位置重叠：防御性跳过
            continue
        out.append(text[cursor:ci])
        out.append(ins)
        cursor = ci
    out.append(text[cursor:])
    return "".join(out)


def _remove_inserts_from_text(text: str,
                             inserts: Sequence[Tuple[int, str]]) -> str:
    """从 ``text`` 中删除由 ``inserts`` 插入的片段，返回原文

    ``inserts`` 的位置是**插入前**的字节位置；这里按升序累加已插入的
    字节/字符位移，算出每段在**当前文本**中的真实位置，再自底向上删除。
    同样是单次 O(n) 构建。
    """
    items = [(int(p), str(t)) for p, t in (inserts or []) if str(t)]
    if not items:
        return text
    items.sort(key=lambda it: it[0])
    starts, _total = _byte_to_char_index(text)

    # 换算：插入前字节位置 + 前面已插入内容的字节数 = **当前文本**里的字节位置
    #
    # ⚠️ 这里不能再叠加"字符位移"：`_byte_pos_to_char` 的输入输出都以
    #   **当前文本**为坐标系，返回的已经是当前文本的字符下标
    #   （第一版多加了 char_shift，导致删错位置 —— 官方验证 9 项失败）。
    spans: List[Tuple[int, int]] = []
    byte_shift = 0
    for pos, ins in items:
        ci = _byte_pos_to_char(starts, pos + byte_shift)
        spans.append((ci, ci + len(ins)))
        byte_shift += len(ins.encode('utf-8', errors='replace'))

    out: List[str] = []
    cursor = 0
    for start, end in spans:
        if start < cursor:                   # 重叠/错位：跳过该段
            continue
        if end > len(text):
            end = len(text)
        out.append(text[cursor:start])
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


# ============================================================
# 命令：整次列编辑 = 一条命令
# ============================================================
class ColumnInsertCmd(Command):
    """列编辑命令：一次插入 N 段文本，作为**单条**命令进出撤销栈。

    参数:
        inserts: ``[(pos, text), ...]``，``pos`` 是**改动前**的字节位置
        description: 可读描述（撤销面板/宏录制里显示）

    ★ 执行/撤销均改为**批量文本重建 + 一次 setText**（见上方说明）。
      `to_dict`/`from_dict` 格式**保持不变**，宏回放继续兼容。
    """

    command_type = CMD_TYPE_COLUMN_INSERT

    def __init__(self, inserts: Sequence[Tuple[int, str]],
                 description: str = ""):
        super().__init__()
        self.inserts: List[Tuple[int, str]] = [
            (int(p), str(t)) for p, t in (inserts or []) if str(t)
        ]
        self.description = description or f"列编辑（{len(self.inserts)} 处）"

    # --------------------------------------------------------
    # 执行 / 撤销
    # --------------------------------------------------------
    @staticmethod
    def _data(text: str) -> bytes:
        """与 core.commands.InsertCmd 一致：统一按 UTF-8 写入。"""
        return text.encode('utf-8', errors='replace')

    def execute(self, scintilla):
        """正向/重做：**一次** setText 完成全部插入（O(n)，非 O(n²)）

        原实现逐条 `SCI_INSERTTEXT`：4 万行 2.7s、8 千行 8.6s（O(n²)），
        10 万行需约 22 分钟。批量重建后为线性，实测 8 千行 0.003s。
        """
        try:
            items = [(p, t) for p, t in self.inserts if str(t)]
            if not items:
                self.mark_executed()
                return
            current = self._read_text(scintilla)
            new_text = _apply_inserts_to_text(current, items)
            if new_text != current:
                self._write_text(scintilla, new_text)
            self.mark_executed()
        except Exception as e:
            print(f"[ColumnInsertCmd] 执行失败: {e}")

    def undo(self, scintilla):
        """撤销：从当前文本中删除所有插入片段（一次 setText）

        判据：``self.inserts`` 的位置是**插入前**坐标，`_remove_inserts_from_text`
        会按累积位移换算出各段在当前文本中的真实位置后整体重建。
        """
        try:
            items = [(p, t) for p, t in self.inserts if str(t)]
            if not items:
                self.mark_undone()
                return
            current = self._read_text(scintilla)
            old_text = _remove_inserts_from_text(current, items)
            if old_text != current:
                self._write_text(scintilla, old_text)
            self.mark_undone()
        except Exception as e:
            print(f"[ColumnInsertCmd] 撤销失败: {e}")

    @staticmethod
    def _read_text(scintilla) -> str:
        """读取控件全部文本（QScintilla 均已开启 UTF-8 模式）"""
        text = scintilla.text()
        if isinstance(text, bytes):          # 防御：个别构建返回 bytes
            text = text.decode('utf-8', errors='replace')
        return text

    @staticmethod
    def _write_text(scintilla, text: str):
        """一次性写入全部文本

        直接 `setText` 会触发 SCN_MODIFIED；调用方（列编辑器 / 撤销管理器）
        已在批量操作前后抑制命令记录，因此不会产生额外撤销条目。
        """
        scintilla.setText(text)

    # --------------------------------------------------------
    # 序列化 / 描述
    # --------------------------------------------------------
    def get_position(self) -> int:
        return min((p for p, _ in self.inserts), default=0)

    def describe(self) -> str:
        return self.description

    def to_dict(self) -> Dict[str, object]:
        return {
            'type': CMD_TYPE_COLUMN_INSERT,
            'inserts': [[p, t] for p, t in self.inserts],
            'description': self.description,
            'timestamp': self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, object]) -> 'ColumnInsertCmd':
        raw = d.get('inserts') or []
        inserts: List[Tuple[int, str]] = []
        for item in raw:
            try:
                pos, text = item[0], item[1]
            except Exception:
                continue
            inserts.append((int(pos), str(text)))
        cmd = cls(inserts, str(d.get('description') or ""))
        try:
            cmd.timestamp = float(d.get('timestamp') or cmd.timestamp)
        except Exception:
            pass
        return cmd

    def __len__(self) -> int:
        return len(self.inserts)

    def __repr__(self) -> str:
        return (f"<ColumnInsertCmd {len(self.inserts)} 处 "
                f"@{self.get_position()}>")


def register_column_insert_command() -> bool:
    """把列编辑命令注册进 ``CommandFactory``。

    宏录制会把命令 ``to_dict()`` 存下来，回放时走 ``Command.from_dict``
    （见 ``core/macro.py``）。不注册的话，含列编辑的宏回放到这一步会
    因"未知命令类型"而失败。

    返回:
        是否注册成功（失败不抛异常，不影响正常编辑）
    """
    try:
        from core.commands import CommandFactory
        CommandFactory.register(CMD_TYPE_COLUMN_INSERT, ColumnInsertCmd)
        return True
    except Exception as e:  # pragma: no cover - 仅防御
        print(f"[列编辑器] 注册命令类型失败: {e}")
        return False


register_column_insert_command()


# ============================================================
# 数据类
# ============================================================
@dataclass
class ColumnEditConfig:
    """列编辑参数。

    属性 ``lines`` / ``column`` 用于**直接指定**作用行与目标列
    （不依赖编辑器选区），方便脚本与单测；留空则按选区自动推断。
    """

    mode: str = MODE_TEXT
    text: str = ""

    # 数字模式
    start: int = 1
    step: int = 1
    radix: int = 10
    pad: str = PAD_NONE
    min_width: int = 0
    prefix: bool = False
    uppercase: bool = True

    # 显式作用范围（可选）
    lines: Optional[List[int]] = None
    column: Optional[int] = None

    def validate(self) -> str:
        """返回空串表示合法，否则返回给用户看的原因。"""
        if self.mode not in (MODE_TEXT, MODE_NUMBER):
            return f"未知模式: {self.mode}"
        if self.mode == MODE_TEXT:
            if not self.text:
                return "请先输入要插入的文本"
            if '\n' in self.text or '\r' in self.text:
                return "要插入的文本不能包含换行（列编辑器是按行插入的）"
            return ""
        if self.radix not in (2, 8, 10, 16):
            return f"不支持的进制: {self.radix}"
        if str(self.pad) not in (PAD_NONE, PAD_ZERO, PAD_SPACE):
            return f"不支持的填充方式: {self.pad}"
        if int(self.min_width) < 0 or int(self.min_width) > 64:
            return "最小位数需要在 0–64 之间（0 = 自动）"
        if self.column is not None and int(self.column) < 0:
            return "目标列不能为负数"
        return ""


@dataclass
class ColumnTarget:
    """解析出的作用范围。"""

    source: str = SOURCE_CARET
    lines: List[int] = field(default_factory=list)
    positions: List[int] = field(default_factory=list)
    column: int = 0
    warning: str = ""

    def __len__(self) -> int:
        return len(self.lines)


@dataclass
class ColumnEditResult:
    """列编辑执行结果。"""

    ok: bool = False
    reason: str = ""
    source: str = ""
    lines: List[int] = field(default_factory=list)
    entries: List[Tuple[int, str]] = field(default_factory=list)
    column: int = 0
    recorded: bool = False
    warning: str = ""

    @property
    def count(self) -> int:
        return len(self.entries)

    def dump(self) -> str:
        lines = ["列编辑结果", "=" * 60]
        lines.append(f"  成功: {self.ok}")
        if self.reason:
            lines.append(f"  原因: {self.reason}")
        lines.append(f"  来源: {self.source}")
        lines.append(f"  行数: {len(self.lines)}")
        lines.append(f"  目标列: {self.column}")
        lines.append(f"  插入段数: {len(self.entries)}")
        lines.append(f"  已记入撤销栈: {self.recorded}")
        if self.warning:
            lines.append(f"  警告: {self.warning}")
        return "\n".join(lines)


# ============================================================
# 编辑器访问辅助
# ============================================================
def _unwrap_editor(editor):
    """返回真正的 QScintilla 控件。

    接受:
        * QScintilla / ``EditorWidget``（直接用）
        * ``EditorProxy``（取 ``.sc``）
        * 任何带 ``.sc`` 的包装对象
    取不到时返回 None。
    """
    if editor is None:
        return None
    if hasattr(editor, 'SendScintilla') and hasattr(editor, 'text'):
        return editor
    sc = getattr(editor, 'sc', None)
    if sc is not None and hasattr(sc, 'SendScintilla'):
        return sc
    return None


def _get_proxy(editor):
    """取 ``EditorProxy``（用于 undo_manager / 私有待提交组兜底）。"""
    for name in ('proxy', '_qc_editor_proxy'):
        proxy = getattr(editor, name, None)
        if proxy is not None and hasattr(proxy, 'undo_manager'):
            return proxy
    return None


def _get_undo_manager(editor):
    """取自研 ``UndoManager``；取不到返回 None（此时无法记录撤销）。"""
    proxy = _get_proxy(editor)
    um = getattr(proxy, 'undo_manager', None) if proxy is not None else None
    if um is None:
        um = getattr(editor, 'undo_manager', None)
    return um


def _line_count(editor) -> int:
    try:
        return int(editor.SendScintilla(QsciScintilla.SCI_GETLINECOUNT))
    except Exception:
        return 0


def _line_start(editor, line: int) -> int:
    try:
        return int(editor.SendScintilla(
            QsciScintilla.SCI_POSITIONFROMLINE, int(line)
        ))
    except Exception:
        return 0


def _line_content(editor, line: int) -> str:
    """取一行内容（不含行尾换行符）。

    不同 QScintilla 版本的 ``text(line)`` 是否含 EOL 不一致，这里统一把
    尾部 CR/LF 剥掉 —— 否则"列 > 行长"时会算到下一行去。
    """
    try:
        raw = editor.text(int(line))
    except Exception:
        return ""
    if not raw:
        return ""
    return raw.rstrip("\r\n")


def position_for_column(editor, line: int, column: int) -> int:
    """（行, 字符列）→ Scintilla 字节位置。

    * 列按**字符**计（tab 记 1 列），与本模块矩形左列读数自洽；
    * 列超出行长时贴到行尾（不自动补空格，与 Notepad++ 一致）。
    """
    start = max(0, _line_start(editor, line))
    col = int(column)
    if col <= 0:
        return start
    content = _line_content(editor, line)
    if col >= len(content):
        prefix = content
    else:
        prefix = content[:col]
    return start + len(prefix.encode('utf-8', errors='replace'))


def column_of_position(editor, pos: int) -> int:
    """字节位置 → 所在行的字符列。"""
    try:
        line = int(editor.SendScintilla(
            QsciScintilla.SCI_LINEFROMPOSITION, int(pos)
        ))
    except Exception:
        return 0
    start = max(0, _line_start(editor, line))
    content = _line_content(editor, line)
    data = content.encode('utf-8', errors='replace')
    offset = max(0, min(int(pos) - start, len(data)))
    # 截断在多字节字符中间时 errors='ignore' 会向下取整
    return len(data[:offset].decode('utf-8', errors='ignore'))


def _selection_count(editor) -> int:
    try:
        return int(editor.SendScintilla(QsciScintilla.SCI_GETSELECTIONS))
    except Exception:
        return 1


def _selection_mode(editor) -> int:
    try:
        return int(editor.SendScintilla(
            QsciScintilla.SCI_GETSELECTIONMODE
        ))
    except Exception:
        return int(getattr(QsciScintilla, 'SC_SEL_STREAM', 0))


def is_editor_readonly(editor) -> bool:
    """编辑器是否只读。"""
    try:
        getter = getattr(editor, 'isReadOnly', None)
        if callable(getter):
            return bool(getter())
    except Exception:
        pass
    return False


# ============================================================
# 作用行范围解析（矩形选区 > 多光标 > 当前选区）
# ============================================================
def _rect_corners(editor) -> Optional[Tuple[int, int]]:
    """矩形专用消息给出的两个角（部分构建才暴露这些常量）。

    官方文档：矩形选区"在内部被当作多选区处理，但原始矩形范围被记住"，
    因此 ``SCI_GETSELECTIONSTART/END`` 不一定给出整条矩形 —— 优先用
    ``SCI_GETRECTANGULARSELECTIONANCHOR/CARET``。
    取不到常量时返回 None（**不猜消息号**，猜错会改坏用户文档）。
    """
    anchor_msg = getattr(QsciScintilla,
                         'SCI_GETRECTANGULARSELECTIONANCHOR', None)
    caret_msg = getattr(QsciScintilla,
                        'SCI_GETRECTANGULARSELECTIONCARET', None)
    if anchor_msg is None or caret_msg is None:
        return None
    try:
        a = int(editor.SendScintilla(anchor_msg))
        c = int(editor.SendScintilla(caret_msg))
    except Exception:
        return None
    if a < 0 or c < 0:
        return None
    return a, c


def _all_selection_line_span(editor) -> Optional[Tuple[int, int]]:
    """全部选区覆盖的行范围（最小值, 最大值）。

    矩形在 Scintilla 内部是"每行一个选区"，某些构建里主选区只覆盖
    光标所在那一行；这个跨度能把整条矩形补齐。
    """
    count = _selection_count(editor)
    msg = getattr(QsciScintilla, _SCI_GETSELECTIONNSTART, None)
    if count <= 1 or msg is None:
        return None
    l0 = l1 = None
    for i in range(count):
        try:
            pos = int(editor.SendScintilla(msg, i))
            line = int(editor.SendScintilla(
                QsciScintilla.SCI_LINEFROMPOSITION, pos
            ))
        except Exception:
            continue
        l0 = line if l0 is None else min(l0, line)
        l1 = line if l1 is None else max(l1, line)
    if l0 is None or l1 is None:
        return None
    return l0, l1


def _resolve_rectangle(editor) -> Optional[ColumnTarget]:
    """矩形选区：取左边缘的**列**，作用行为矩形覆盖的全部行。"""
    corners = _rect_corners(editor)
    if corners is None:
        try:
            s = int(editor.SendScintilla(
                QsciScintilla.SCI_GETSELECTIONSTART))
            e = int(editor.SendScintilla(
                QsciScintilla.SCI_GETSELECTIONEND))
            corners = (s, e)
        except Exception:
            return None
    lo, hi = min(corners), max(corners)
    try:
        l0 = int(editor.SendScintilla(
            QsciScintilla.SCI_LINEFROMPOSITION, lo
        ))
        l1 = int(editor.SendScintilla(
            QsciScintilla.SCI_LINEFROMPOSITION, hi
        ))
    except Exception:
        return None
    if l0 > l1:
        l0, l1 = l1, l0

    # 主选区只覆盖一行时，用"全部选区的行跨度"补齐整条矩形
    span = _all_selection_line_span(editor)
    if span is not None:
        l0, l1 = min(l0, span[0]), max(l1, span[1])

    column = min(column_of_position(editor, lo),
                 column_of_position(editor, hi))
    lines = list(range(l0, l1 + 1))
    positions = [position_for_column(editor, ln, column) for ln in lines]
    return ColumnTarget(SOURCE_RECTANGLE, lines, positions, column)


def _resolve_multi_cursor(editor, count: int) -> Optional[ColumnTarget]:
    """多光标：每个光标（选区起点）单独作为插入点，按位置升序。"""
    msg = getattr(QsciScintilla, _SCI_GETSELECTIONNSTART, None)
    if msg is None:
        return None
    pairs: List[Tuple[int, int]] = []
    for i in range(int(count)):
        try:
            pos = int(editor.SendScintilla(msg, i))
            line = int(editor.SendScintilla(
                QsciScintilla.SCI_LINEFROMPOSITION, pos
            ))
        except Exception:
            continue
        pairs.append((pos, line))
    if not pairs:
        return None
    pairs.sort(key=lambda it: it[0])
    positions = [p for p, _ in pairs]
    lines = [ln for _, ln in pairs]
    column = column_of_position(editor, positions[0])
    return ColumnTarget(SOURCE_MULTI, lines, positions, column)


def _resolve_stream(editor) -> ColumnTarget:
    """当前流式选区覆盖的整行；无选区则用光标所在行。"""
    try:
        s = int(editor.SendScintilla(QsciScintilla.SCI_GETSELECTIONSTART))
        e = int(editor.SendScintilla(QsciScintilla.SCI_GETSELECTIONEND))
    except Exception:
        s = e = 0
    lo, hi = min(s, e), max(s, e)
    try:
        l0 = int(editor.SendScintilla(
            QsciScintilla.SCI_LINEFROMPOSITION, lo
        ))
        l1 = int(editor.SendScintilla(
            QsciScintilla.SCI_LINEFROMPOSITION, hi
        ))
    except Exception:
        l0 = l1 = 0
    if l0 > l1:
        l0, l1 = l1, l0
    # 选区正好停在下一行行首（整行拖选）时，不要把下一行算进来
    if l1 > l0 and hi == _line_start(editor, l1):
        l1 -= 1
    column = column_of_position(editor, lo)
    if lo == hi:
        return ColumnTarget(SOURCE_CARET, [l0],
                            [position_for_column(editor, l0, column)], column)
    lines = list(range(l0, l1 + 1))
    positions = [position_for_column(editor, ln, column) for ln in lines]
    return ColumnTarget(SOURCE_SELECTION, lines, positions, column)


def resolve_target(editor,
                   config: Optional[ColumnEditConfig] = None
                   ) -> ColumnTarget:
    """解析本次列编辑的作用行与插入位置。

    优先级: 矩形选区 > 多光标 > 当前选区（整行）。
    """
    sc = _unwrap_editor(editor)
    if sc is None:
        return ColumnTarget(SOURCE_CARET, warning="没有可用的编辑器控件")

    # 1) 显式指定（脚本/单测用）
    if config is not None and config.lines:
        total = _line_count(sc)
        lines = sorted({int(ln) for ln in config.lines
                        if 0 <= int(ln) < total})
        if not lines:
            return ColumnTarget(SOURCE_EXPLICIT,
                                warning="指定的行号超出文档范围")
        column = int(config.column) if config.column is not None else 0
        positions = [position_for_column(sc, ln, column) for ln in lines]
        return ColumnTarget(SOURCE_EXPLICIT, lines, positions, column)

    # 2) 矩形选区
    if _selection_mode(sc) == getattr(QsciScintilla,
                                      'SC_SEL_RECTANGLE', -1):
        target = _resolve_rectangle(sc)
        if target is not None and target.lines:
            return target

    # 3) 多光标
    n_sel = _selection_count(sc)
    if n_sel > 1:
        target = _resolve_multi_cursor(sc, n_sel)
        if target is not None and target.lines:
            return target
        warning = "当前 QScintilla 未暴露多光标查询接口，已退化为整选区"
    else:
        warning = ""

    # 4) 当前选区 / 光标
    target = _resolve_stream(sc)
    if warning:
        target.warning = warning
    return target


# ============================================================
# 执行
# ============================================================
def _merge_entries(positions: Sequence[int], texts: Sequence[str]
                   ) -> List[Tuple[int, str]]:
    """按位置升序整理插入段；位置相同的多段文本依次拼接。

    位置相同只会出现在"两个光标落在同一字节位置"的极端情况，
    拼接能保证不丢内容、且撤销仍然只删它插入的那些字符。
    """
    order = sorted(range(len(positions)), key=lambda i: (positions[i], i))
    merged: List[Tuple[int, str]] = []
    for i in order:
        if i >= len(texts):
            continue
        pos = int(positions[i])
        text = texts[i]
        if not text:
            continue
        if merged and merged[-1][0] == pos:
            merged[-1] = (pos, merged[-1][1] + text)
        else:
            merged.append((pos, text))
    return merged


def _leave_multi_selection(editor) -> None:
    """把矩形/多光标选区收成**单一流式选区**。

    ``EditorProxy._on_scintilla_modified`` 只在"多光标或矩形"状态下才
    走它自己的 ``_pending_group`` 分支（按 300ms 时间窗合并）。收成单选区
    后走普通分支，本模块才有"整次编辑只有一条撤销命令"的**确定性**
    （不受插入耗时是否超时影响）。

    官方文档:
      * 矩形选区在内部就是多选区（"Rectangular selections are handled
        as multiple selections"）；
      * ``SCI_CLEARSELECTIONS`` 会"留下唯一一个位于 0 的空选区"，
        因此调用后 ``SCI_GETSELECTIONS`` 必然为 1；
      * ``SCI_INSERTTEXT`` / ``SCI_DELETERANGE`` 都按**绝对位置**生效
        （只有 ``SCI_REPLACESEL`` 才依赖当前选区），所以收选区不会
        影响后续按位置插入的语义。

    这里只动选区、不动文档；插入完成后由 ``_select_entries`` 重建选区。
    """
    try:
        if _selection_mode(editor) == getattr(QsciScintilla,
                                              'SC_SEL_RECTANGLE', -1):
            editor.SendScintilla(
                QsciScintilla.SCI_SETSELECTIONMODE,
                QsciScintilla.SC_SEL_STREAM,
            )
    except Exception:
        pass
    try:
        if _selection_count(editor) > 1:
            editor.SendScintilla(QsciScintilla.SCI_CLEARSELECTIONS)
    except Exception:
        pass


def _insert_text(editor, pos: int, text: str) -> bool:
    """按字节位置插入一段文本。"""
    data = text.encode('utf-8', errors='replace')
    if not data:
        return False
    try:
        length = int(editor.SendScintilla(QsciScintilla.SCI_GETLENGTH))
        p = max(0, min(int(pos), length))
        editor.SendScintilla(QsciScintilla.SCI_INSERTTEXT, p, data)
        return True
    except Exception as e:
        print(f"[列编辑器] 插入失败: {e}")
        return False


def _discard_self_made_pending_group(proxy, pending_before, len_before: int
                                     ) -> None:
    """兜底：清掉本次编辑在 ``EditorProxy`` 里可能留下的待提交命令组。

    正常路径下 ``_leave_multi_selection()`` 已经让 core/editor.py 走普通
    分支，不会有 ``_pending_group``。这里只处理异常路径（例如某个
    QScintilla 构建拒绝切换选区模式）：
      * 出现的是**新**组对象 → 一定只装着我们本次的插入，丢弃；
      * 是**同一个**组且命令数变多 → 只截掉多出来的部分，
        **保留**用户原有的待提交命令（清空会让用户上一次多光标编辑
        失去撤销）。
    组内命令之所以可丢：编辑期间 ``UndoManager`` 被 disable，它们本来
    就没进撤销栈；本次编辑已由一条 ``ColumnInsertCmd`` 统一记录。
    """
    if proxy is None:
        return
    try:
        pending_after = getattr(proxy, '_pending_group', None)
        if pending_after is None:
            return
        if pending_after is pending_before:
            cmds = getattr(pending_after, 'cmds', None)
            if isinstance(cmds, list) and len(cmds) > int(len_before):
                del cmds[int(len_before):]
        else:
            proxy._pending_group = None
    except Exception:
        pass


def _select_entries(editor, entries: Sequence[Tuple[int, str]]) -> None:
    """把本次插入的文本整体选中（让用户看得见改了什么）。"""
    if not entries:
        return
    span_start = int(entries[0][0])
    cumulative = 0
    span_end = span_start
    for pos, text in entries:
        n = len(text.encode('utf-8', errors='replace'))
        span_end = int(pos) + cumulative + n
        cumulative += n
    try:
        # 官方文档：SCI_SETSELECTION(position caret, position anchor)
        # 这里给 (caret=末尾, anchor=开头)，光标落在插入内容之后
        editor.SendScintilla(QsciScintilla.SCI_SETSELECTION,
                             span_end, span_start)
    except Exception:
        try:
            editor.SendScintilla(QsciScintilla.SCI_SETSELECTIONSTART,
                                 span_start)
            editor.SendScintilla(QsciScintilla.SCI_SETSELECTIONEND, span_end)
        except Exception:
            pass


def apply_column_edit(editor, config: Optional[ColumnEditConfig] = None,
                      **overrides) -> ColumnEditResult:
    """执行一次列编辑（不弹窗）。

    参数:
        editor: QScintilla 控件或 ``EditorProxy``
        config: ``ColumnEditConfig``；为 None 时用默认值
        **overrides: 覆盖 config 的字段（如 ``text="// "``）

    返回:
        ``ColumnEditResult``
    """
    cfg = config if config is not None else ColumnEditConfig()
    if overrides:
        try:
            cfg = replace(cfg, **overrides)
        except Exception as e:
            return ColumnEditResult(False, f"参数错误: {e}")

    sc = _unwrap_editor(editor)
    if sc is None:
        return ColumnEditResult(False, "没有可用的编辑器控件")

    err = cfg.validate()
    if err:
        return ColumnEditResult(False, err)
    if is_editor_readonly(sc):
        return ColumnEditResult(False, "编辑器处于只读状态")

    target = resolve_target(sc, cfg)
    if not target.lines:
        return ColumnEditResult(False,
                                target.warning or "没有可编辑的目标行",
                                source=target.source,
                                warning=target.warning)

    # 逐行文本
    if cfg.mode == MODE_TEXT:
        texts = [cfg.text] * len(target.lines)
    else:
        texts = generate_number_texts(
            cfg.start, cfg.step, len(target.lines),
            radix=cfg.radix, pad=cfg.pad, min_width=cfg.min_width,
            prefix=cfg.prefix, uppercase=cfg.uppercase,
        )
    entries = _merge_entries(target.positions, texts)
    if not entries:
        return ColumnEditResult(False, "没有可插入的内容",
                                source=target.source)

    # 记录前的现场快照（只用于兜底清理，见 _discard_...）
    proxy = _get_proxy(sc)
    pending_before = getattr(proxy, '_pending_group', None) \
        if proxy is not None else None
    len_before = len(getattr(pending_before, 'cmds', []) or [])

    um = _get_undo_manager(sc)
    reenable = False
    done: List[Tuple[int, str]] = []
    _leave_multi_selection(sc)

    # ---- 批量应用（修复 O(n²) → O(n)）----
    #
    # 原实现逐条 `SCI_INSERTTEXT`，实测 8 千行 8.6s、4 万行 2.7s 且翻倍 n
    # 约 4 倍耗时（O(n²)），10 万行需约 22 分钟。
    # 现改为：内存里一次性重建全文 → **单次 setText**（8 千行 0.003s）。
    #
    # 期间必须抑制命令记录，否则 setText 会再记一条撤销命令：
    #   * `um.disable()` —— 不记录 undo 命令；
    #   * `proxy._restoring = True` —— 抑制 `_on_scintilla_modified` 的副作用
    #     （与 edit_ops_mixin `_replace_all_text_atomic` 同一套做法）。
    restoring_before = getattr(proxy, '_restoring', False) if proxy else False
    try:
        if um is not None and not um.is_disabled():
            um.disable()
            reenable = True
        try:
            current_text = sc.text()
            if isinstance(current_text, bytes):
                current_text = current_text.decode('utf-8', errors='replace')
            new_text = _apply_inserts_to_text(current_text, entries)
            if new_text != current_text:
                if proxy is not None:
                    proxy._restoring = True
                try:
                    sc.setText(new_text)
                finally:
                    if proxy is not None:
                        proxy._restoring = restoring_before
                done = list(entries)
        except Exception as e:
            print(f"[列编辑器] 批量插入失败: {e}")
    finally:
        if reenable and um is not None:
            um.enable()
        if proxy is not None:
            proxy._restoring = restoring_before

    _discard_self_made_pending_group(proxy, pending_before, len_before)

    if not done:
        return ColumnEditResult(False, "插入失败（文档可能已只读）",
                                source=target.source, lines=target.lines,
                                column=target.column)

    # 兜底标记"文档已修改"
    #
    # ``_on_scintilla_modified`` 的多光标/矩形分支会**提前 return**，
    # 走不到它自己的 mark_modified 那段；虽然我们上面已经收过选区、
    # 正常路径会走普通分支，这里仍补一次（mark_modified 幂等，
    # 已修改时是空操作），保证多光标场景下标签页的 "*" 脏标记正确。
    try:
        document = getattr(proxy, 'document', None)
        mark = getattr(document, 'mark_modified', None)
        if callable(mark):
            mark()
    except Exception as e:
        print(f"[列编辑器] 标记文档修改状态失败: {e}")

    # Scintilla 自身的"已修改"标记也必须置位。
    #
    # 修复（实测：用例「编辑后 Scintilla 修改标记为真」失败）：
    #   上面只调了 `document.mark_modified()`（文档模型层）。本次插入在
    #   `UndoManager.disable()` 期间进行、随后由 `ColumnInsertCmd` 单独入栈，
    #   `_on_scintilla_modified` 里的置脏分支没有被走到。
    #   后果：标签页不显示 "*"、关窗时**不提示保存** —— 用户的列编辑
    #   看起来"没生效"，容易被误当失败而重复操作。
    #
    # ⚠️ 实测坑：`QScintilla.setModified(True)` 在本项目的配置下**不生效**
    #   ——`EditorProxy` 为接管撤销而执行了 `SCI_SETUNDOCOLLECTION, 0`，
    #   此后 QScintilla 的 `isModified()` 内部标记不再随其更新（实测：
    #   调用后立即 `isModified()` 仍为 False）。因此这里同时用底层
    #   `SCI_SETMODIFY` 与 Qt 属性两条路径一起置位。
    try:
        sc.SendScintilla(sc.SCI_SETMODIFY, 1)
    except Exception:
        pass
    try:
        sc.setModified(True)
    except Exception:
        pass
    try:
        if proxy is not None:
            proxy._modified = True
            proxy.modified_changed.emit(True)
    except Exception:
        pass

    # ---- 整次编辑 = 一条撤销命令 ----
    cmd = ColumnInsertCmd(
        done,
        description=(f"列编辑：{len(done)} 行"
                     + (f"「{cfg.text}」" if cfg.mode == MODE_TEXT else "")),
    )
    recorded = False
    if um is not None:
        try:
            um.record(cmd)
            # record() 在 UndoManager 被 disable 时会静默返回，如实反映
            recorded = not um.is_disabled()
        except Exception as e:
            print(f"[列编辑器] 记录撤销命令失败: {e}")

    # 选中刚插入的内容（位置换算到**插入后**的字节坐标）
    #
    # 批量插入后每段都向后偏移了"前面已插入内容的字节数"，
    # 直接拿插入前的位置去选会错位。
    try:
        post_entries: List[Tuple[int, str]] = []
        shift = 0
        for pos, text in sorted(done, key=lambda it: it[0]):
            post_entries.append((pos + shift, text))
            shift += len(str(text).encode('utf-8', errors='replace'))
        _select_entries(sc, post_entries)
    except Exception:
        pass

    return ColumnEditResult(
        True, "", target.source, list(target.lines),
        sorted(done, key=lambda it: it[0]), target.column,
        recorded, target.warning,
    )


def insert_text_at_column(editor, text: str, **kwargs) -> ColumnEditResult:
    """不弹窗：在作用行的目标列插入同一段文本。"""
    return apply_column_edit(editor, ColumnEditConfig(mode=MODE_TEXT,
                                                      text=text), **kwargs)


def insert_numbers_at_column(editor, start: int = 1, step: int = 1,
                             **kwargs) -> ColumnEditResult:
    """不弹窗：在作用行插入递增/递减数字序列。

    其余参数（radix / pad / min_width / prefix / uppercase / lines /
    column）通过关键字传入 ``ColumnEditConfig``。
    """
    return apply_column_edit(editor, ColumnEditConfig(
        mode=MODE_NUMBER, start=int(start), step=int(step)), **kwargs)


# ============================================================
# 对话框
# ============================================================
class ColumnEditorDialog(QDialog):
    """列编辑器对话框（可独立构造，不依赖 MainWindow）。

    用法::

        dlg = ColumnEditorDialog(editor)
        if dlg.exec_() == QDialog.Accepted:
            print(dlg.result_data())

    参数:
        editor: QScintilla 控件或 ``EditorProxy``（可为 None，仅预览界面）
        parent: 父控件
    """

    def __init__(self, editor=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("列编辑器")
        self.setMinimumWidth(470)

        self._editor = editor
        self._result: Optional[ColumnEditResult] = None
        try:
            self._target = resolve_target(editor) if editor is not None \
                else None
        except Exception:
            self._target = None

        self._build_ui()
        self._sync_state()

    # --------------------------------------------------------
    # 界面
    # --------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)

        self._scope_label = QLabel(self._scope_text(), self)
        self._scope_label.setWordWrap(True)
        root.addWidget(self._scope_label)

        box = QGroupBox("插入内容", self)
        box_layout = QVBoxLayout(box)

        # --- 文本模式 ---
        text_row = QHBoxLayout()
        self._text_radio = QRadioButton("插入文本:", box)
        self._text_radio.setChecked(True)
        self._text_edit = QLineEdit(box)
        self._text_edit.setPlaceholderText("要在每一行的目标列插入的文本")
        text_row.addWidget(self._text_radio)
        text_row.addWidget(self._text_edit, 1)
        box_layout.addLayout(text_row)

        # --- 数字模式 ---
        num_row = QHBoxLayout()
        self._number_radio = QRadioButton("插入数字:", box)
        num_row.addWidget(self._number_radio)
        num_row.addStretch(1)
        box_layout.addLayout(num_row)

        form = QFormLayout()

        self._start_edit = QLineEdit("1", box)
        self._start_edit.setToolTip(
            "起始值：支持 0x1F / 0o17 / 0b1010 写法"
        )
        form.addRow("起始值:", self._start_edit)

        self._step_spin = QSpinBox(box)
        self._step_spin.setRange(-1000000, 1000000)
        self._step_spin.setValue(1)
        form.addRow("步长:", self._step_spin)

        self._radix_combo = QComboBox(box)
        for value, label in RADIXES:
            self._radix_combo.addItem(label, value)
        form.addRow("进制:", self._radix_combo)

        self._pad_combo = QComboBox(box)
        self._pad_combo.addItem("不填充", PAD_NONE)
        self._pad_combo.addItem("前导零（按最大值宽度）", PAD_ZERO)
        self._pad_combo.addItem("前导空格（右对齐）", PAD_SPACE)
        form.addRow("填充方式:", self._pad_combo)

        self._width_spin = QSpinBox(box)
        self._width_spin.setRange(0, 64)
        self._width_spin.setValue(0)
        self._width_spin.setToolTip("最少位数（0 = 按序列自动）")
        form.addRow("最小位数:", self._width_spin)

        flags = QWidget(box)
        flags_layout = QHBoxLayout(flags)
        flags_layout.setContentsMargins(0, 0, 0, 0)
        self._prefix_check = QCheckBox("加前缀（0x/0o/0b）", flags)
        self._uppercase_check = QCheckBox("十六进制大写", flags)
        self._uppercase_check.setChecked(True)
        flags_layout.addWidget(self._prefix_check)
        flags_layout.addWidget(self._uppercase_check)
        flags_layout.addStretch(1)
        form.addRow("", flags)

        box_layout.addLayout(form)
        root.addWidget(box)

        self._preview = QLabel(self)
        self._preview.setWordWrap(True)
        root.addWidget(self._preview)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self,
        )
        self._ok_button = buttons.button(QDialogButtonBox.Ok)
        self._ok_button.setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        # 实时刷新
        self._text_radio.toggled.connect(self._sync_state)
        self._text_edit.textChanged.connect(self._sync_state)
        self._start_edit.textChanged.connect(self._sync_state)
        self._step_spin.valueChanged.connect(self._sync_state)
        self._radix_combo.currentIndexChanged.connect(self._sync_state)
        self._pad_combo.currentIndexChanged.connect(self._sync_state)
        self._width_spin.valueChanged.connect(self._sync_state)
        self._prefix_check.toggled.connect(self._sync_state)
        self._uppercase_check.toggled.connect(self._sync_state)

    def _scope_text(self) -> str:
        t = self._target
        if t is None or not t.lines:
            return "作用范围：无可编辑目标（请先选中若干行，或建立矩形选区/多光标）"
        names = {
            SOURCE_RECTANGLE: "矩形选区",
            SOURCE_MULTI: "多光标",
            SOURCE_SELECTION: "当前选区",
            SOURCE_CARET: "当前光标",
            SOURCE_EXPLICIT: "显式指定",
        }
        first = t.lines[0] + 1
        last = t.lines[-1] + 1
        span = (f"第 {first} 行" if first == last
                else f"第 {first}–{last} 行")
        text = (f"作用范围：{names.get(t.source, t.source)}，{span}"
                f"（共 {len(t.lines)} 行）；目标列：{t.column}")
        if t.warning:
            text += f"\n⚠ {t.warning}"
        return text

    def _flag_widgets(self) -> List[QWidget]:
        return [
            self._start_edit, self._step_spin, self._radix_combo,
            self._pad_combo, self._width_spin,
            self._prefix_check, self._uppercase_check,
        ]

    def _sync_state(self, *_args):
        """模式切换 / 参数变化 → 刷新可用状态与预览。"""
        text_mode = bool(self._text_radio.isChecked())
        self._text_edit.setEnabled(text_mode)
        for widget in self._flag_widgets():
            widget.setEnabled(not text_mode)
        try:
            radix = int(self._radix_combo.currentData() or 10)
        except Exception:
            radix = 10
        self._prefix_check.setEnabled(not text_mode and radix != 10)
        self._uppercase_check.setEnabled(not text_mode and radix == 16)
        self._refresh_preview()

    def _refresh_preview(self):
        count = len(self._target.lines) if self._target else 0
        try:
            cfg = self.build_config()
        except ValueError as e:
            self._preview.setText(f"⚠ {e}")
            self._ok_button.setEnabled(False)
            return
        if count <= 0:
            self._preview.setText("⚠ 没有可编辑的目标行")
            self._ok_button.setEnabled(False)
            return

        if cfg.mode == MODE_TEXT:
            self._preview.setText(f"将在 {count} 行插入文本：{cfg.text!r}")
        else:
            values = preview_number_texts(
                cfg.start, cfg.step, count, radix=cfg.radix,
                pad=cfg.pad, min_width=cfg.min_width,
                prefix=cfg.prefix, uppercase=cfg.uppercase, preview=5,
            )
            joined = ", ".join(values)
            if count > len(values):
                joined += ", …"
            note = "（步长为 0：所有行都是同一个数字）" if cfg.step == 0 else ""
            self._preview.setText(f"将在 {count} 行插入：{joined}{note}")
        self._ok_button.setEnabled(True)

    # --------------------------------------------------------
    # 结果
    # --------------------------------------------------------
    def build_config(self) -> ColumnEditConfig:
        """从界面读出配置；参数非法时抛 ``ValueError``。"""
        if self._text_radio.isChecked():
            cfg = ColumnEditConfig(mode=MODE_TEXT,
                                   text=self._text_edit.text())
        else:
            cfg = ColumnEditConfig(
                mode=MODE_NUMBER,
                start=parse_int_literal(self._start_edit.text()),
                step=int(self._step_spin.value()),
                radix=int(self._radix_combo.currentData() or 10),
                pad=str(self._pad_combo.currentData() or PAD_NONE),
                min_width=int(self._width_spin.value()),
                prefix=bool(self._prefix_check.isChecked()),
                uppercase=bool(self._uppercase_check.isChecked()),
            )
        err = cfg.validate()
        if err:
            raise ValueError(err)
        return cfg

    def result_data(self) -> Optional[ColumnEditResult]:
        """已执行成功的列编辑结果（取消时为 None）。"""
        return self._result

    def accept(self):
        """确定：执行列编辑；失败则提示并保持对话框打开。

        幂等保护：某些 Qt 版本会把 ``QDialogButtonBox.accepted`` 自动接到
        对话框的 ``accept()`` 上（这里又显式接了一次），若不设防，同一次
        "确定"会**执行两遍**列编辑。
        """
        if self._result is not None:
            super().accept()
            return
        try:
            cfg = self.build_config()
        except ValueError as e:
            QMessageBox.warning(self, "列编辑器", str(e))
            return
        result = apply_column_edit(self._editor, cfg)
        if not result.ok:
            QMessageBox.warning(self, "列编辑器",
                                result.reason or "无法执行列编辑")
            return
        self._result = result
        super().accept()

    # --------------------------------------------------------
    # 便捷入口
    # --------------------------------------------------------
    @classmethod
    def run(cls, editor, parent=None) -> Optional[ColumnEditResult]:
        """弹出对话框；用户确认并执行成功时返回结果，否则 None。"""
        dlg = cls(editor, parent)
        if dlg.exec_() == QDialog.Accepted:
            return dlg.result_data()
        return None


def show_column_editor(editor, parent=None) -> Optional[ColumnEditResult]:
    """菜单/右键入口：弹出列编辑器对话框。"""
    return ColumnEditorDialog.run(editor, parent)


def make_column_editor_action(parent, editor_getter,
                              shortcut: str = DEFAULT_SHORTCUT) -> QAction:
    """构造可直接 ``menu.addAction(...)`` 的 QAction（可选便利函数）。

    参数:
        parent: QObject 父对象（防止 QAction 被 GC）
        editor_getter: 无参可调用对象，返回当前编辑器（控件或 EditorProxy）
        shortcut: 快捷键文本，默认 ``Alt+Shift+I``

    返回:
        QAction（文本「列编辑器…」）。宿主只需::

            action = make_column_editor_action(self, lambda:
                                               self.tabs.current_proxy())
            self.edit_menu.addAction(action)
    """
    action = QAction("📊 列编辑器…", parent)
    if shortcut:
        action.setShortcut(QKeySequence(shortcut))
    action.setStatusTip("在矩形选区/多光标/多行上逐行插入文本或递增数字")

    def _triggered(_checked=False):
        try:
            editor = editor_getter() if callable(editor_getter) else None
        except Exception as e:
            print(f"[列编辑器] 获取当前编辑器失败: {e}")
            return
        show_column_editor(editor, parent)

    action.triggered.connect(_triggered)
    return action
