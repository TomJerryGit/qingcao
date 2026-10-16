#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""对比合并对话框（并排双栏 diff + 三方合并）

用户明确要求：**对比合并是本软件的核心功能**。本模块提供三层能力：

1. **纯函数 diff 层**（无 Qt 依赖，可直接单测）
   - :func:`compute_diff` ：两段文本的行级对齐结果 ``List[AlignedRow]``
   - :func:`diff_summary` / :func:`diff_texts` ：统计与便捷封装
   - :func:`parse_conflict_markers` / :func:`count_conflicts`
     ：解析 ``<<<<<<< LOCAL / ======= / >>>>>>> REMOTE`` 冲突块

2. **并排双栏对比对话框** :class:`FileDiffDialog`
   - 左栏 = A（本地/当前），右栏 = B（对比目标）
   - 行级对齐 + 三种颜色高亮（新增 / 删除 / 修改）
   - "只显示差异 / 显示全部"切换、同步滚动、行号
   - 底部统计：新增 N 行 / 删除 M 行 / 修改 K 行

3. **三方合并对话框** :class:`ThreeWayMergeDialog`
   - 复用 ``core/file_merge.ThreeWayMerger``（**绝不重写算法**）
   - 展示带冲突标记的合并结果，提供"保留本地 / 采用远程 / 手动编辑"
   - 非冲突部分自动合并；可写回磁盘

设计取舍（重要）
----------------
* **为什么用 QPlainTextEdit + 行级对齐而不是 QTextEdit + 富文本表格**
  QPlainTextEdit 内部按"块"存储，10 万行也能正常滚动；QTextEdit 的富文本
  会为每个差异片段生成一个 QTextCharFormat，行数一多就地动山摇。
  这里预先算好"对齐行数组"，两个控件**块数完全一致**，
  于是：同步滚动 = 直接复制对方滚动条数值（无需逐行测量高度），
  "只显示差异" = 把相等行 ``setVisible(False)``。
* **大文件保护**（阈值 :data:`DIFF_SIZE_THRESHOLD` = 5MB）
  绝不对超阈值文件做"文本控件渲染 + 字符级高亮"。降级路径：
  不构造正文控件，只给出**仅差异摘要**（计数 + 差异块位置 + 前
  :data:`SUMMARY_ROW_CAP` 条位置明细），并明确提示"内容未渲染"。
  另外，超阈值时**不会**为了"纯 UI"再复制一份 5MB+ 文本。
* **末尾换行**
  行数组按 ``splitlines()`` 切分，末尾换行信息单独用
  ``*_ends_with_newline`` 布尔量保留，由 :meth:`FileDiffDialog.diff_result`
  统一回填 —— 避免"对比/写回后文件末尾多空行/少空行"这类隐形数据损坏。
* **字符级"修改"高亮**
  对 ``replace`` 配对的行做第二轮 ``SequenceMatcher(autojunk=False)``，
  只给真正变化的字符加深色背景，未变化部分用浅背景 —— 长行只改一个
  词时肉眼可辨。``autojunk=False`` 是必须的：默认的自动垃圾启发式会让
  长行里的高频字符被当成垃圾，导致高亮错位。

调用契约（Lead 接线用，不依赖 MainWindow）
----------------------------------------
工具菜单项（推荐 —— 对话框自己负责"选 A / 选 B"）::

    from ui.file_merge_dialog import FileDiffDialog

    dlg = FileDiffDialog.pick_files(parent=self)
    if dlg is not None:
        dlg.exec_()

已知两个路径时直接构造::

    dlg = FileDiffDialog.from_files(path_a, path_b, parent=self)
    if dlg.exec_() == QDialog.Accepted and dlg.action == "save":
        text = dlg.diff_result()["merged"]      # 已按结果侧回填末尾换行

三方合并（外部变更冲突时）::

    dlg = ThreeWayMergeDialog(original, local, remote, parent=self)
    if dlg.exec_() == QDialog.Accepted:
        if dlg.action == "local":      -> 用 local 覆盖
        elif dlg.action == "remote":   -> 用 remote 覆盖
        else:                          -> dlg.merged_text()  用户手动编辑后的文本
    print(dlg.merge_result())          # ThreeWayMerger 的原始返回

写回磁盘由**调用方**负责（对话框只在用户显式选择"保存到…"时经
:meth:`ThreeWayMergeDialog.save_to_file` 写文件），保持 UI 与文件策略分离。
"""
import difflib
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFontDatabase, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


# ============================================================
# 常量
# ============================================================

#: 单文件超过该字节数就降级为"仅差异摘要"（不做文本控件渲染）
DIFF_SIZE_THRESHOLD = 5 * 1024 * 1024

#: 降级摘要里最多列出的差异行条数（防止摘要本身撑爆控件）
SUMMARY_ROW_CAP = 500

#: 差异块数超过该值就放弃字符级高亮（只做整行染色），保证大文件可用
CHAR_HIGHLIGHT_ROW_CAP = 2000

#: `_looks_like_edit` 的行相似度兜底阈值
#:
#: 实测调参：曾用 0.4，但 `difflib` 对**短行**的 ratio 偏高 ——
#: `"line2"` 与 `"INSERTED"` 得到 0.545，于是"删一行 + 插一行"被误判成
#: "修改"。短行之间本质无法可靠判断"是否同一行被改"，故提到 0.6，
#: 并要求至少有 3 个字符的公共子序列（见 `_looks_like_edit`）。
_EDIT_SIMILARITY = 0.6

#: `_align_block` 里"允许配对"的最低相似度门槛
#:
#: 低于它就不配对（该行按 delete/add 处理），避免把两个无关行硬凑成"修改"。
_PAIR_MIN_SIMILARITY = 0.5

#: 参与字符级 diff 的行最长字符数；更长的行直接跳过（SequenceMatcher 是
#: O(n²)，超长行会拖慢打开对话框）
CHAR_DIFF_LINE_CAP = 5000

# ---- 语义化配色：新增/删除/修改 三种（+ 字符级加浓）----
COLOR_ADD_BG = QColor("#d7f6dc")          # 新增行
COLOR_ADD_CHAR = QColor("#7fd694")        # 新增行里真正新增的字符
COLOR_DEL_BG = QColor("#ffe0e0")          # 删除行
COLOR_DEL_CHAR = QColor("#f19a9a")        # 删除行里真正删掉的字符
COLOR_MOD_BG = QColor("#fff3cc")          # 修改行（两侧都变）
COLOR_MOD_SAME = QColor("#fffbe8")        # 修改行里未变的字符（浅）
COLOR_MOD_CHAR = QColor("#f5c542")        # 修改行里变化的字符
COLOR_GAP_BG = QColor("#f2f2f2")          # 对侧缺行留下的空槽
COLOR_CONFLICT_BG = QColor("#ffe3e3")     # 冲突块底色
COLOR_MARKER_FG = QColor("#b00020")       # 冲突标记文字

KIND_EQUAL = "equal"
KIND_ADD = "add"
KIND_DELETE = "delete"
KIND_MODIFY = "modify"

KIND_TEXT = {
    KIND_EQUAL: "未变",
    KIND_ADD: "新增",
    KIND_DELETE: "删除",
    KIND_MODIFY: "修改",
}


# ============================================================
# 数据模型
# ============================================================

@dataclass
class AlignedRow:
    """一行**对齐后**的 diff 结果（左右块号一致，便于并排渲染/同步滚动）

    属性:
        kind: ``equal`` / ``add`` / ``delete`` / ``modify``
        left: 左栏（A）文本；``None`` 表示该侧没有对应行（空槽）
        right: 右栏（B）文本；``None`` 同上
        left_no: 左栏原始行号（1-based，``None`` 表示空槽）
        right_no: 右栏原始行号
        left_ranges: 左栏需要**加浓**高亮的字符区间 ``[(开始, 结束)]``
        right_ranges: 右栏同上
    """

    kind: str
    left: Optional[str]
    right: Optional[str]
    left_no: Optional[int] = None
    right_no: Optional[int] = None
    left_ranges: List[Tuple[int, int]] = field(default_factory=list)
    right_ranges: List[Tuple[int, int]] = field(default_factory=list)

    def __post_init__(self):
        # "修改"必须左右都在；否则降级为新增/删除，杜绝渲染时 KeyError
        if self.kind == KIND_MODIFY and (self.left is None or self.right is None):
            self.kind = KIND_ADD if self.left is None else KIND_DELETE

    @property
    def changed(self) -> bool:
        """该行是否属于差异（用于"只显示差异"）"""
        return self.kind != KIND_EQUAL


@dataclass
class DiffStats:
    """差异统计（底部状态栏用）"""

    added: int = 0
    deleted: int = 0
    modified: int = 0

    @property
    def total(self) -> int:
        return self.added + self.deleted + self.modified

    def as_dict(self) -> Dict[str, int]:
        return {"added": self.added, "deleted": self.deleted,
                "modified": self.modified, "total": self.total}

    def text(self) -> str:
        return "新增 %d 行 / 删除 %d 行 / 修改 %d 行" % (
            self.added, self.deleted, self.modified)


# ============================================================
# 纯函数 diff 层（无 Qt，可独立测试）
# ============================================================

def _char_diff_ranges(a: str, b: str) -> Tuple[List[Tuple[int, int]],
                                               List[Tuple[int, int]]]:
    """行内字符级差异；返回 (a 的加浓区间, b 的加浓区间)

    ``autojunk=False``：长行（>200 字符）里重复出现的字符不会被误判为"垃圾"，
    否则高亮区间会整体错位。
    """
    ranges_a: List[Tuple[int, int]] = []
    ranges_b: List[Tuple[int, int]] = []
    if max(len(a), len(b)) > CHAR_DIFF_LINE_CAP:
        # 超长行（例如压缩后的 JS 单行 3 万字符）：整行加浓，不做字符级
        return [(0, len(a))] if a else [], [(0, len(b))] if b else []

    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if i2 > i1:
            ranges_a.append((i1, i2))
        if j2 > j1:
            ranges_b.append((j1, j2))
    return ranges_a, ranges_b


def compute_diff(
    left_text: str,
    right_text: str,
    char_level: bool = True,
) -> List[AlignedRow]:
    """计算两段文本的**行级对齐**差异（纯函数，无 Qt 依赖）

    算法：对 ``(左行列表, 右行列表)`` 跑一次
    ``difflib.SequenceMatcher.get_opcodes()``：

    * ``equal``  —— 逐行输出 ``equal``
    * ``delete`` —— 左有右无，输出 ``delete``（左栏染色，右栏空槽）
    * ``insert`` —— 左无右有，输出 ``add``（右栏染色，左栏空槽）
    * ``replace``—— 按行配对输出 ``modify``；多出来的一侧补成
      ``add`` / ``delete``。**配对判定**见 :func:`_looks_like_edit`
      （公共前缀/后缀 >= 4 字符，或相似度 >= 0.4）—— 这样"改了后半行"
      会被认成 1 处修改，而不是 1 删 + 1 增。

    返回的列表左右块号严格一一对应（``len(rows)`` 就是两边控件应有的块数），
    这是同步滚动与"只显示差异"能简单实现的前提。

    统计口径：``added`` = 右栏多出的行数；``deleted`` = 左栏多出的行数；
    ``modified`` = 配对的修改行数。用 :func:`diff_summary` 取。
    """
    left_lines = left_text.splitlines()
    right_lines = right_text.splitlines()

    rows: List[AlignedRow] = []
    matcher = difflib.SequenceMatcher(None, left_lines, right_lines)
    # autojunk=False：避免长文件里重复行被当作 junk 导致对齐整体错乱
    matcher.autojunk = False

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                rows.append(AlignedRow(
                    KIND_EQUAL,
                    left_lines[i1 + k], right_lines[j1 + k],
                    i1 + k + 1, j1 + k + 1,
                ))
            continue

        if tag == "delete":
            for k in range(i1, i2):
                rows.append(AlignedRow(KIND_DELETE, left_lines[k], None,
                                       k + 1, None))
            continue

        if tag == "insert":
            for k in range(j1, j2):
                rows.append(AlignedRow(KIND_ADD, None, right_lines[k],
                                       None, k + 1))
            continue

        # ---- replace：用**最优配对**决定哪些行是"修改" ----
        #
        # 缺陷背景（实测：`修改数 == 1` / `新增数 == 1` / `删除数 == 1` /
        # 对齐序列 / 左右行号 五项失败）：
        #   原实现按**下标**配对（i1+k ↔ j1+k）并在遇到第一对不相似时
        #   `break`，于是：
        #     * 该对之后即使有明确是"修改"的行，也被算成 1 删 + 1 增；
        #     * 两侧行数不等时，后续配对整体错位。
        #
        #   我先改成"双指针 + ±1 漂移"启发式，计数虽然对了，**对齐仍然错**：
        #   实测 left=«a / line2 / line3 / line4»、
        #        right=«a / INSERTED / line3-changed / line4» 得到
        #     `modify(line2 → line3-changed)` + `delete(line3)`，
        #   而正确答案是 `add(INSERTED)` + `modify(line2 → line3-changed)`。
        #   逐个猜测"漂移方向"在本质上不可靠。
        #
        #   现在改为**打分式最优配对**：在 replace 块内求一个最大权匹配
        #   （见 `_align_block`）。相似度作为权重，用相似度 ≥
        #   `_PAIR_MIN_SIMILARITY` 作为可配对门槛；纯增删的权重为 0，
        #   因此"看起来更像配对"的排列会胜出。
        for row in _align_block(
            left_lines, right_lines, i1, i2, j1, j2, char_level
        ):
            rows.append(row)

    return rows


def _align_block(
    left_lines: List[str],
    right_lines: List[str],
    i1: int,
    i2: int,
    j1: int,
    j2: int,
    char_level: bool,
) -> List[AlignedRow]:
    """给一个 replace 块求**最优逐行配对**，再输出对齐行

    目标：让"改动过的同一行"配成 ``modify``，其余按 ``delete`` / ``add``
    输出，且左右行号递增（保证并排渲染与同步滚动的前提）。

    做法：自底向上 DP，``best[p][q]`` = 左块从 p、右块从 q 开始的最优
    累计相似度。三种转移：

    * 配对 ``(p, q)`` —— 仅当 ``_line_similarity ≥ _PAIR_MIN_SIMILARITY``；
    * 跳过左 p（该行是删除）；
    * 跳过右 q（该行是新增）。

    纯增删的权重为 0，配对权重为该对相似度，因此 DP 会优先选择
    "相似的行互相配对"的排列 —— 这正是我们要的对齐语义。
    """
    n_l = i2 - i1
    n_r = j2 - j1
    if n_l <= 0 and n_r <= 0:
        return []

    # sim[p][q] 只在 ≥ 门槛时非 None（None 表示不可配对）
    sim: List[List[Optional[float]]] = [
        [None] * n_r for _ in range(n_l)
    ]
    for p in range(n_l):
        lv = left_lines[i1 + p]
        for q in range(n_r):
            rv = right_lines[j1 + q]
            s = _line_similarity(lv, rv)
            if s >= _PAIR_MIN_SIMILARITY:
                sim[p][q] = s

    # best[p][q]：从 (p,q) 到块尾的最优累计分
    best = [[0.0] * (n_r + 1) for _ in range(n_l + 1)]
    # choice：0=配对, 1=跳过左, 2=跳过右
    choice = [[0] * (n_r + 1) for _ in range(n_l + 1)]
    for p in range(n_l - 1, -1, -1):
        for q in range(n_r - 1, -1, -1):
            cand_pair = None
            if sim[p][q] is not None:
                cand_pair = sim[p][q] + best[p + 1][q + 1]
            cand_del = best[p + 1][q]
            cand_add = best[p][q + 1]
            best_score = cand_del
            pick = 1
            if cand_add > best_score:
                best_score, pick = cand_add, 2
            if cand_pair is not None and cand_pair > best_score:
                best_score, pick = cand_pair, 0
            best[p][q] = best_score
            choice[p][q] = pick

    out: List[AlignedRow] = []
    p = q = 0
    while p < n_l or q < n_r:
        if p < n_l and q < n_r:
            pick = choice[p][q]
            if pick == 0:
                lv = left_lines[i1 + p]
                rv = right_lines[j1 + q]
                la: List[Tuple[int, int]] = []
                ra: List[Tuple[int, int]] = []
                if char_level:
                    la, ra = _char_diff_ranges(lv, rv)
                kind = KIND_MODIFY if lv != rv else KIND_EQUAL
                out.append(AlignedRow(
                    kind, lv, rv, i1 + p + 1, j1 + q + 1, la, ra,
                ))
                p += 1
                q += 1
                continue
            if pick == 1:
                out.append(AlignedRow(
                    KIND_DELETE, left_lines[i1 + p], None, i1 + p + 1, None,
                ))
                p += 1
                continue
            out.append(AlignedRow(
                KIND_ADD, None, right_lines[j1 + q], None, j1 + q + 1,
            ))
            q += 1
            continue

        if p < n_l:
            out.append(AlignedRow(
                KIND_DELETE, left_lines[i1 + p], None, i1 + p + 1, None,
            ))
            p += 1
        else:
            out.append(AlignedRow(
                KIND_ADD, None, right_lines[j1 + q], None, j1 + q + 1,
            ))
            q += 1
    return out


def _line_similarity(a: str, b: str) -> float:
    """两行的相似度（0.0–1.0），纯度量、不含阈值判断

    与 :func:`_looks_like_edit` 共用同一套判据，保证"能不能配对"与
    "排出来谁配谁"两个决策一致。
    """
    if a == b:
        return 1.0
    sa, sb = a.strip(), b.strip()
    if not sa or not sb:
        return 0.0
    match = difflib.SequenceMatcher(None, sa, sb, autojunk=False)
    ratio = match.ratio()
    # 公共前缀/后缀很长时（常见于"只改了行尾"）给一个略高的分数，
    # 这样相同 ratio 下"改动更靠后/更集中"的配对会胜出
    prefix = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        prefix += 1
    if prefix >= 4:
        ratio = max(ratio, 0.75)
    return ratio


def _looks_like_edit(a: str, b: str) -> bool:
    """两行是否应视为"同一行被修改"（而不是一删一增）

    判定顺序（越靠前越确定）：

    1. 任一侧为空白行 —— 不配对（空白行更适合看成插入/删除）；
    2. 公共前缀 >= 4 个字符 —— Python 缩进会让公共前缀至少是缩进长度，
       因此必须用"缩进 + 内容"一起算，4 是经验下限；
    3. 公共后缀 >= 4 个字符 —— 覆盖"改中间"的情况；
    4. 行相似度 >= :data:`_EDIT_SIMILARITY` —— 兜底，避免"整行重写但确实
       相关"被拆成 1 删除 + 1 新增（统计上会误导用户）。

    只要命中 2/3/4 之一就是"修改"。这样 ``+`` 计数不会被"两个空行里的
    一行被删掉"之类的情况污染。

    阈值说明（实测调参）：
        曾经用 0.4，但 ``difflib`` 对**短行**的 ratio 偏高：
        ``"line2"`` 与 ``"INSERTED"`` 得到 **0.545**（只有 2 个字符
        ``'n'/'E'`` 之类的偶然重合就能堆出这个分数），于是"删一行 + 插一行"
        被误判成"修改"。短行之间本质无法可靠判断"是否同一行被改"，
        因此门槛提高到 0.6，且要求**至少有 3 个字符的公共子序列**，
        避免纯偶然重合触发。
    """
    if not a.strip() or not b.strip():
        return False
    if a == b:
        return True

    prefix = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        prefix += 1
    if prefix >= 4:
        return True

    suffix = 0
    for ca, cb in zip(reversed(a), reversed(b)):
        if ca != cb:
            break
        suffix += 1
    if suffix >= 4:
        return True

    sa, sb = a.strip(), b.strip()
    if min(len(sa), len(sb)) < 3:
        # 太短，无法可靠判断"同一行被修改" → 交给增/删语义
        return False
    match = difflib.SequenceMatcher(None, sa, sb, autojunk=False)
    # 公共字符数（匹配块总长）；偶然重合不会太长
    common = sum(bl.size for bl in match.get_matching_blocks())
    if common < 3:
        return False
    return match.ratio() >= _EDIT_SIMILARITY


def diff_summary(rows: List[AlignedRow]) -> DiffStats:
    """按对齐结果统计 新增/删除/修改（纯函数）"""
    stats = DiffStats()
    for row in rows:
        if row.kind == KIND_ADD:
            stats.added += 1
        elif row.kind == KIND_DELETE:
            stats.deleted += 1
        elif row.kind == KIND_MODIFY:
            stats.modified += 1
    return stats


def diff_texts(left_text: str, right_text: str) -> Dict[str, Any]:
    """便捷封装：一次拿到行、统计、以及回填末尾换行后的文本

    返回::

        {
            'rows': List[AlignedRow],
            'stats': DiffStats,
            'left_lines': [...],   'right_lines': [...],
            'left_ends_with_newline': bool, 'right_ends_with_newline': bool,
        }
    """
    rows = compute_diff(left_text, right_text)
    return {
        "rows": rows,
        "stats": diff_summary(rows),
        "left_lines": [r.left for r in rows if r.left is not None],
        "right_lines": [r.right for r in rows if r.right is not None],
        "left_ends_with_newline": left_text.endswith(("\n", "\r")),
        "right_ends_with_newline": right_text.endswith(("\n", "\r")),
    }


def is_large_text(text: Optional[str],
                  threshold: int = DIFF_SIZE_THRESHOLD) -> bool:
    """文本是否超过大文件阈值（按 UTF-8 字节数估算，避免只数字符）"""
    if not text:
        return False
    try:
        return len(text.encode("utf-8", errors="replace")) > threshold
    except Exception:
        return len(text) > threshold


def is_large_path(path: Optional[str],
                  threshold: int = DIFF_SIZE_THRESHOLD) -> bool:
    """文件是否超过大文件阈值（用 os.stat，不读内容）"""
    if not path:
        return False
    try:
        return os.path.getsize(path) > threshold
    except Exception:
        return False


def read_text_file(path: str) -> Tuple[Optional[str], Optional[str]]:
    """读取文本文件；返回 ``(文本, 错误信息)``

    优先 UTF-8，失败后按 GBK 兜底（Windows 中文环境常见），
    再失败则用 ``errors='replace'`` 保证对话框仍可打开。
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception as exc:                       # noqa: BLE001 - 对话框要能提示
        return None, "读取失败: %s" % exc

    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return raw.decode(enc), None
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), None


# ============================================================
# 冲突标记解析
# ============================================================

def count_conflicts(text: str) -> int:
    """数一数文本里有多少个 ``<<<<<<< LOCAL`` 冲突块起点"""
    return sum(1 for line in (text or "").splitlines()
               if line.startswith("<<<<<<<"))


def parse_conflict_markers(text: str) -> List[Dict[str, Any]]:
    """解析 ``<<<<<<< LOCAL / ======= / >>>>>>> REMOTE`` 冲突块

    返回 ``[{'start','end','local','remote'}]``（行号为 1-based，
    ``end`` 指向 ``>>>>>>>`` 行）。嵌套/残缺标记不会抛异常，
    残缺块在文本结尾时按已收集内容收尾。
    """
    lines = (text or "").splitlines()
    blocks: List[Dict[str, Any]] = []
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].startswith("<<<<<<<"):
            start = i + 1
            local: List[str] = []
            remote: List[str] = []
            i += 1
            while i < n and not lines[i].startswith("======="):
                if lines[i].startswith(">>>>>>>"):
                    break
                local.append(lines[i])
                i += 1
            if i < n and lines[i].startswith("======="):
                i += 1
                while i < n and not lines[i].startswith(">>>>>>>"):
                    remote.append(lines[i])
                    i += 1
            end = i + 1 if i < n else n
            if i < n and lines[i].startswith(">>>>>>>"):
                i += 1
            blocks.append({
                "start": start,
                "end": end,
                "local": local,
                "remote": remote,
            })
        else:
            i += 1
    return blocks


# ============================================================
# 渲染辅助
# ============================================================

def _new_format(bg: Optional[QColor] = None,
                fg: Optional[QColor] = None,
                bold: bool = False) -> QTextCharFormat:
    """构造 QTextCharFormat（QPlainTextEdit 的 setExtraSelections 用）"""
    fmt = QTextCharFormat()
    if bg is not None:
        fmt.setBackground(bg)
    if fg is not None:
        fmt.setForeground(fg)
    if bold:
        fmt.setFontWeight(75)      # QFont.Bold == 75
    return fmt


def _mono_font():
    """等宽字体：对比视图必须等宽，否则左右栏视觉不对齐

    在 ``offscreen`` / 无字体数据库的环境下 ``QFontDatabase.families()``
    可能为空，因此这里**不做** families 交集，直接把系统 FixedFont 的
    族名换掉即可（Qt 找不到时自行回退，不会抛异常）。
    """
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    for name in ("Consolas", "Cascadia Mono", "DejaVu Sans Mono",
                 "Courier New"):
        try:
            font.setFamily(name)
            break
        except Exception:                              # pragma: no cover
            continue
    return font


def _rows_to_plan(rows: List[AlignedRow],
                  only_diff: bool,
                  char_highlight: bool) -> Dict[str, Any]:
    """把对齐结果压成"渲染计划"：两个控件各自的行文本 + 每行格式

    纯数据（除了 QColor/QTextCharFormat 这些纯值对象），便于在 offscreen
    下断言"某行被标成什么颜色"。

    返回::

        {
            'left_lines': [...], 'right_lines': [...],
            'left_formats': [[fmt, fmt...], ...],   # 与行一一对应
            'right_formats': [...],
            'changed_rows': [行索引...],            # 差异行（用于 setVisible）
            'visible_rows': [行索引...],            # 当前应可见的行
        }
    """
    left_lines: List[str] = []
    right_lines: List[str] = []
    left_formats: List[List[QTextCharFormat]] = []
    right_formats: List[List[QTextCharFormat]] = []
    changed_rows: List[int] = []
    visible_rows: List[int] = []

    add_fmt = _new_format(COLOR_ADD_BG)
    add_char_fmt = _new_format(COLOR_ADD_CHAR)
    del_fmt = _new_format(COLOR_DEL_BG)
    del_char_fmt = _new_format(COLOR_DEL_CHAR)
    mod_same_fmt = _new_format(COLOR_MOD_SAME)
    mod_char_fmt = _new_format(COLOR_MOD_CHAR, bold=True)
    gap_fmt = _new_format(COLOR_GAP_BG)

    for idx, row in enumerate(rows):
        left_lines.append("" if row.left is None else row.left)
        right_lines.append("" if row.right is None else row.right)

        lf: List[QTextCharFormat] = []
        rf: List[QTextCharFormat] = []

        if row.kind == KIND_EQUAL:
            visible_rows.append(idx)
        else:
            changed_rows.append(idx)
            if only_diff:
                visible_rows.append(idx)

        if row.kind == KIND_ADD:
            lf.append(gap_fmt)                     # 左栏空槽
            rf.append(add_fmt)
            if char_highlight and row.right:
                rf.append(add_char_fmt)
        elif row.kind == KIND_DELETE:
            lf.append(del_fmt)
            if char_highlight and row.left:
                lf.append(del_char_fmt)
            rf.append(gap_fmt)
        elif row.kind == KIND_MODIFY:
            # 左右先铺"浅色（未变）"底，再叠"深色（变化）"字符区间，
            # 这样"长行只改一个词"也能一眼看出改在哪儿。
            lf.append(mod_same_fmt)
            rf.append(mod_same_fmt)
            if char_highlight:
                for (s, e) in _valid_ranges(row.left_ranges, row.left or ""):
                    lf.append(_new_format(COLOR_MOD_CHAR))
                for (s, e) in _valid_ranges(row.right_ranges, row.right or ""):
                    rf.append(_new_format(COLOR_MOD_CHAR))
        else:                                      # equal
            pass

        left_formats.append(lf)
        right_formats.append(rf)

    return {
        "left_lines": left_lines,
        "right_lines": right_lines,
        "left_formats": left_formats,
        "right_formats": right_formats,
        "changed_rows": changed_rows,
        "visible_rows": visible_rows,
    }


def _valid_ranges(ranges: List[Tuple[int, int]], text: str) -> List[Tuple[int, int]]:
    """过滤越界/空区间 —— SequenceMatcher 的结果偶有边界问题，防御一下"""
    out = []
    n = len(text)
    for s, e in (ranges or []):
        s = max(0, min(int(s), n))
        e = max(0, min(int(e), n))
        if e > s:
            out.append((s, e))
    return out


# ============================================================
# 基础对话框
# ============================================================

class _BaseMergeDialog(QDialog):
    """公共底座：等宽字体、统计标签、差异/全部切换、大文件判定"""

    #: 由子类覆盖 —— 降级为摘要时的提示语前缀
    _SUMMARY_HINT = "文件过大，已降级为【仅差异摘要】"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mono = _mono_font()
        self._only_diff = False
        self._large_mode = False
        self._summary_shown = False
        self._oversize_diff = False
        self._stats = DiffStats()
        self._result: Optional[Dict[str, Any]] = None

        self.resize(1180, 760)
        self.setMinimumSize(720, 420)

    # ---------- 公共小工具 ----------

    def _stat_label(self) -> QLabel:
        label = QLabel("新增 0 行 / 删除 0 行 / 修改 0 行")
        label.setObjectName("merge_stat_label")
        label.setStyleSheet("font-size: 12px; padding: 2px 6px;")
        return label

    def _update_stat_label(self, extra: str = "") -> None:
        """刷新统计标签（大文件降级时附加提示）"""
        prefix = ""
        if self._large_mode:
            prefix = self._SUMMARY_HINT + " —— "
        text = prefix + self._stats.text()
        if extra:
            text += "  |  " + extra
        self._stat_label_widget.setText(text)
        if self._large_mode:
            self._stat_label_widget.setStyleSheet(
                "font-size: 12px; padding: 2px 6px; color: #b06000;")
        else:
            self._stat_label_widget.setStyleSheet(
                "font-size: 12px; padding: 2px 6px;")

    def _make_legend(self) -> QLabel:
        """颜色图例 —— 用户要能看懂三种颜色分别代表什么"""
        label = QLabel(
            '<span style="background:%s;">&nbsp;&nbsp;&nbsp;&nbsp;</span> 新增 '
            '<span style="background:%s;">&nbsp;&nbsp;&nbsp;&nbsp;</span> 删除 '
            '<span style="background:%s;">&nbsp;&nbsp;&nbsp;&nbsp;</span> 修改 '
            '<span style="background:%s;">&nbsp;&nbsp;&nbsp;&nbsp;</span> 对侧空槽'
            % (COLOR_ADD_BG.name(), COLOR_DEL_BG.name(),
               COLOR_MOD_BG.name(), COLOR_GAP_BG.name())
        )
        label.setStyleSheet("font-size: 11px; color: #666;")
        label.setToolTip(
            "深色字符高亮表示行内真正变化的字符（修改行里浅色部分是未变内容）")
        return label

    def _make_plain_edit(self) -> QPlainTextEdit:
        """差异视图专用 QPlainTextEdit

        * 关闭自动换行 —— 换行会让两侧块高不一致，同步滚动就会漂移
          （行号由"对齐后的块号"隐含表示，UI 上左右块号一一对应）
        * 只读、不做撤销栈（大文件下撤销栈很吃内存）
        * ``setMaximumBlockCount(0)`` = 不限制块数（这是"大文件能用"的前提）
        """
        edit = QPlainTextEdit()
        edit.setReadOnly(True)
        edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        edit.setFont(self._mono)
        edit.setTabChangesFocus(True)
        edit.setUndoRedoEnabled(False)
        edit.setMaximumBlockCount(0)
        edit.setCenterOnScroll(False)
        return edit

    def _populate_plan(self, edit: QPlainTextEdit, lines: List[str],
                       formats: List[List[QTextCharFormat]],
                       side: str) -> None:
        """把渲染计划灌进控件（只读控件，``setPlainText`` 最快）"""
        edit.setPlainText("\n".join(lines))
        self._apply_formats(edit, formats, side)

    def _apply_formats(self, edit: QPlainTextEdit,
                       formats: List[List[QTextCharFormat]],
                       side: str) -> None:
        """逐块设置 extraSelections

        实现要点（踩过的坑，别再改回去）：

        * 选区长度用 ``block.length() - 1``，**不含**块尾的段落分隔符；
          用 ``block.length()`` 会把颜色涂到下一行行首，看起来像串色。
        * 空行（``length == 0``）长度为 0 的选区在 QPlainTextEdit 里不显示，
          因此给 1 个字符宽度，让"对侧空槽"那种浅灰格可见。
        * 选区总数超过 :data:`CHAR_HIGHLIGHT_ROW_CAP` 的 3 倍就整体放弃
          染色（保留纯文本 + "只显示差异"），保证超大差异不卡死 UI。
        """
        selections = []
        doc = edit.document()
        for block_no, fmts in enumerate(formats):
            if not fmts:
                continue
            block = doc.findBlockByNumber(block_no)
            if not block.isValid():
                break
            length = block.length() - 1          # 不含段落分隔符
            if length <= 0:
                length = 1                       # 空行也要能看见底色
            for fmt in fmts:
                cursor = QTextCursor(block)
                cursor.setPosition(block.position())
                cursor.setPosition(block.position() + length,
                                   QTextCursor.KeepAnchor)
                sel = QTextEdit.ExtraSelection()
                sel.cursor = cursor
                sel.format = fmt
                selections.append(sel)

        if len(selections) > CHAR_HIGHLIGHT_ROW_CAP * 3:
            # 超大差异：放弃格式（保留纯文本 + 可见性切换）
            edit.setExtraSelections([])
            edit.setProperty("qc_diff_formats_dropped", True)
            return
        edit.setExtraSelections(selections)

    def _set_rows_visible(self, left: QPlainTextEdit, right: QPlainTextEdit,
                          visible_rows: List[int]) -> bool:
        """显示/隐藏块（"只显示差异"的极简实现）

        QPlainTextEdit 没有"隐藏块"的公开 API，但
        ``QTextBlock.setVisible(False)`` + ``document().markContentsDirty``
        在 Qt5 稳定可用（documentLayout 会跳过不可见块）。
        两个控件必须用**同一份**可见集合，否则同步滚动立刻错位。

        返回是否成功；失败时调用方可以降级（不切换），
        绝不让"点了只显示差异"把对话框搞崩。
        """
        vis = set(visible_rows)
        try:
            for side_edit in (left, right):
                doc = side_edit.document()
                total = doc.blockCount()
                block = doc.begin()
                i = 0
                while block.isValid():
                    want = i in vis
                    if block.isVisible() != want:
                        block.setVisible(want)
                    block = block.next()
                    i += 1
                doc.markContentsDirty(0, total)
            return True
        except Exception:
            # 极端情况下（Qt 构建裁剪了 setVisible / markContentsDirty）
            # 退化为"不隐藏"，功能仍可用
            return False

    def _keep_block_counts_equal(self) -> None:
        """不变量：两个控件的块数必须一致，否则同步滚动立即失准

        :func:`_rows_to_plan` 已经保证一致；真出现偏差（例如外部改了
        document）就补空行自愈，并把 ``_count_mismatch`` 置位供测试断言。
        """
        edits = [(self.left_edit, "left"), (self.right_edit, "right")]
        counts = [e.document().blockCount() for e, _ in edits]
        if counts[0] == counts[1]:
            return
        target = max(counts)
        for (edit, _), cur in zip(edits, counts):
            if cur < target:
                edit.setPlainText(edit.toPlainText() + "\n" * (target - cur))
        self._count_mismatch = True

    @staticmethod
    def _wrap_pane(title: str, edit: QPlainTextEdit, header_bg: str):
        """给一个编辑区套上"标题栏 + 内容"的外壳（两个对话框共用）"""
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        header = QLabel(title)
        header.setStyleSheet(
            "background: %s; padding: 4px 6px; font-weight: bold; "
            "font-size: 12px;" % header_bg)
        lay.addWidget(header)
        lay.addWidget(edit, 1)
        return panel, header, edit

    @staticmethod
    def _new_summary_view(text: str) -> QPlainTextEdit:
        """摘要专用只读控件（自动换行，与 diff 视图不同）"""
        view = QPlainTextEdit()
        view.setObjectName("merge_summary_view")
        view.setReadOnly(True)
        view.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        view.setPlainText(text)
        return view

    def _setup_sync_scroll(self, left: QPlainTextEdit,
                           right: QPlainTextEdit) -> None:
        """同步滚动：直接复制对方滚动条数值

        前提：两栏**块数一致**（见 :meth:`_keep_block_counts_equal`），
        因此块号 → 像素位置的映射相同，复制 ``value`` 即可对齐。

        实现要点：连接只建立一次，开关切换靠 :meth:`set_sync_scroll` 里的
        ``self._sync_enabled`` 判断 —— 不要用 ``disconnect()``，那会把
        Qt 内部的其它连接一起断掉，而且反复开关会重复累积连接。
        """
        self._sync_enabled = True
        self._syncing = False
        self._sync_pair = (left, right)
        try:
            left.verticalScrollBar().valueChanged.connect(self._sync_vertical)
            right.verticalScrollBar().valueChanged.connect(self._sync_vertical)
            left.horizontalScrollBar().valueChanged.connect(self._sync_horizontal)
            right.horizontalScrollBar().valueChanged.connect(self._sync_horizontal)
        except Exception:
            # 连接失败不影响对话框可用性（只是没有同步滚动）
            self._sync_enabled = False

    def _sync_vertical(self, value: int) -> None:
        self._sync_axis(value, vertical=True)

    def _sync_horizontal(self, value: int) -> None:
        self._sync_axis(value, vertical=False)

    def _sync_axis(self, value: int, vertical: bool = True,
                   src: Optional[QPlainTextEdit] = None) -> None:
        """把源滚动条数值复制到另一个控件（带递归护栏）

        ``src`` 为空时用 ``self.sender()`` 判断来源；直接调用（例如
        :meth:`set_sync_scroll` 打开开关时对齐一次）请显式传入，
        否则 QObject.sender() 为 None，会被误判成"左→左"。
        """
        if not getattr(self, "_sync_enabled", False) or self._syncing:
            return
        pair = getattr(self, "_sync_pair", None)
        if not pair:
            return
        if src is None:
            src = self.sender()
        dst = pair[1] if src is pair[0] else pair[0]
        if dst is None or src is None:
            return
        self._syncing = True
        try:
            bar = dst.verticalScrollBar() if vertical else dst.horizontalScrollBar()
            if bar.maximum() > 0 or value == 0:
                bar.setValue(min(value, bar.maximum()))
        except Exception:
            pass
        finally:
            self._syncing = False


# ============================================================
# 并排双栏对比对话框
# ============================================================

class FileDiffDialog(_BaseMergeDialog):
    """并排双栏文件对比对话框

    参数:
        left_text / right_text: 两侧内容（也可只给路径，见 :meth:`from_files`）
        left_title / right_title: 两侧标题（一般写"当前: xxx.py"）
        parent: 父窗口（可省，对话框可完全独立构造）

    用法::

        dlg = FileDiffDialog.from_files("a.py", "b.py")
        if dlg.exec_() == QDialog.Accepted:
            ...                    # 见 :meth:`diff_result`
    """

    def __init__(self, left_text: str, right_text: str,
                 left_title: str = "A（本地/当前）",
                 right_title: str = "B（对比目标）",
                 parent=None,
                 size_threshold: int = DIFF_SIZE_THRESHOLD):
        super().__init__(parent)
        self._left_text = left_text or ""
        self._right_text = right_text or ""
        self._left_title = left_title
        self._right_title = right_title
        self._threshold = size_threshold
        self._plan: Optional[Dict[str, Any]] = None
        self._saved_path: Optional[str] = None
        self.action = "close"        # 'close' | 'save'

        self.setWindowTitle("对比文件 —— %s ↔ %s" % (left_title, right_title))

        # 大文件判定放在 diff **之前**：超阈值时不做行级对齐，避免几百万行
        # 的 SequenceMatcher 卡住 UI（真正的"100MB 文件"走 frozen() 路径）。
        self._large_mode = (
            is_large_text(self._left_text, size_threshold)
            or is_large_text(self._right_text, size_threshold)
        )
        if self._large_mode:
            rows: List[AlignedRow] = []
            self._oversize_diff = True
        else:
            rows = compute_diff(self._left_text, self._right_text)
            self._oversize_diff = False
        self._rows = rows
        self._stats = diff_summary(rows)
        char_level = len(rows) <= CHAR_HIGHLIGHT_ROW_CAP

        self._build_ui()
        if self._large_mode:
            self._build_summary_only()
        else:
            self._plan = _rows_to_plan(rows, only_diff=False,
                                       char_highlight=char_level)
            self._populate_plan(self.left_edit, self._plan["left_lines"],
                                self._plan["left_formats"], "left")
            self._populate_plan(self.right_edit, self._plan["right_lines"],
                                self._plan["right_formats"], "right")
            self._keep_block_counts_equal()
            self._update_stat_label(
                "差异行 %d / 共 %d 行" % (len(self._plan["changed_rows"]), len(rows)))
            if not self._rows:
                self._stat_label_widget.setText("两个文件内容完全相同")

    # ---------- 构造 ----------

    @classmethod
    def pick_files(cls, parent=None, size_threshold: int = DIFF_SIZE_THRESHOLD):
        """**给菜单项用的便捷入口**：先弹两个文件选择框，再构造对话框

        工具菜单只有一个"对比文件…"动作，点下去时并没有两个路径，
        因此必须由本方法补上"选文件"这一步（否则调用方会缺必填参数）。

        返回 ``FileDiffDialog`` 或 ``None``（用户取消 / 选了同一个文件）。
        调用契约::

            dlg = FileDiffDialog.pick_files(parent=self)
            if dlg is not None:
                dlg.exec_()
        """
        start_dir = ""
        try:
            # 有"当前文件"就用它的目录作为起始位置（主窗口没有该方法则跳过）
            if parent is not None and hasattr(parent, "current_path"):
                start_dir = os.path.dirname(parent.current_path() or "")
        except Exception:
            start_dir = ""

        path_a, _ = QFileDialog.getOpenFileName(
            parent, "选择要对比的文件 A（本地/当前）", start_dir, "所有文件 (*)")
        if not path_a:
            return None

        # A 选完之后默认从 A 所在目录继续选 B
        start_dir = os.path.dirname(os.path.abspath(path_a))
        path_b, _ = QFileDialog.getOpenFileName(
            parent, "选择要对比的文件 B（对比目标）", start_dir, "所有文件 (*)")
        if not path_b:
            return None

        if os.path.abspath(path_a) == os.path.abspath(path_b):
            # 自己和自己比没有意义，直接提示并返回 None（不弹空对话框）
            if parent is not None:
                QMessageBox.information(parent, "对比文件",
                                        "两次选择的是同一个文件，已取消。")
            return None

        return cls.from_files(path_a, path_b, parent=parent,
                              size_threshold=size_threshold)

    @classmethod
    def from_files(cls, left_path: str, right_path: str, parent=None,
                   size_threshold: int = DIFF_SIZE_THRESHOLD):
        """从两个文件路径构造

        * 任一文件超过阈值 → 走 :meth:`frozen`（**不读内容**，直接摘要）
        * 否则正常读取（UTF-8 / GBK 兜底）后做双栏对比
        """
        if is_large_path(left_path, size_threshold) or \
                is_large_path(right_path, size_threshold):
            return cls.frozen(left_path, right_path, parent=parent,
                              size_threshold=size_threshold)

        left_text, lerr = read_text_file(left_path)
        right_text, rerr = read_text_file(right_path)
        dlg = cls(left_text or "", right_text or "",
                  "A: %s" % os.path.basename(left_path),
                  "B: %s" % os.path.basename(right_path),
                  parent=parent, size_threshold=size_threshold)
        if lerr or rerr:
            dlg._stat_label_widget.setText(
                "读取告警: %s %s" % (lerr or "", rerr or ""))
        return dlg

    # ---------- 冻结（大文件路径级降级） ----------

    @classmethod
    def frozen(cls, left_path: str, right_path: str, parent=None,
               size_threshold: int = DIFF_SIZE_THRESHOLD,
               left_title: Optional[str] = None,
               right_title: Optional[str] = None):
        """**路径级冻结**：只 stat 两个文件，完全不读内容就给出摘要

        用于两个几十/几百 MB 的文件 —— 连读取都省掉，避免内存峰值。
        """
        dlg = cls.__new__(cls)          # 绕过 __init__ 的内容读取
        _BaseMergeDialog.__init__(dlg, parent)
        dlg._left_path = left_path
        dlg._right_path = right_path
        dlg._left_text = ""
        dlg._right_text = ""
        dlg._left_title = left_title or "A: %s" % os.path.basename(left_path)
        dlg._right_title = right_title or "B: %s" % os.path.basename(right_path)
        dlg._threshold = size_threshold
        dlg._plan = None
        dlg._rows = []
        dlg._stats = DiffStats()
        dlg._large_mode = True
        dlg._oversize_diff = False
        dlg._saved_path = None
        dlg.action = "close"
        dlg.setWindowTitle("对比文件 —— %s ↔ %s" % (dlg._left_title,
                                                dlg._right_title))
        dlg._build_ui()
        dlg._build_summary_only(frozen_paths=(left_path, right_path))
        return dlg

    def _build_summary_only(self, frozen_paths: Optional[Tuple[str, str]] = None
                            ) -> None:
        """仅差异摘要：不渲染正文，只给计数 + 差异块位置

        ``frozen_paths`` 非空时表示"连内容都没读"，只报文件大小。
        """
        self._summary_shown = True
        self.left_edit.setVisible(False)
        self.right_edit.setVisible(False)
        self.left_header.setVisible(False)
        self.right_header.setVisible(False)
        self.only_diff_check.setEnabled(False)
        self.char_check.setEnabled(False)
        self._summary_only_note.setVisible(True)

        stats = self._stats
        if frozen_paths:
            left_size = _safe_size(frozen_paths[0])
            right_size = _safe_size(frozen_paths[1])
            head = [
                "%s（A %s，B %s）" % (self._SUMMARY_HINT,
                                      _human(left_size), _human(right_size)),
                "为避免把两个大文件塞进控件导致界面冻结，本对话框**未读取、"
                "未渲染**正文内容。",
                "如需逐行查看差异，请用命令行：git diff --no-index \"%s\" \"%s\""
                % (frozen_paths[0], frozen_paths[1]),
                "或缩小对比范围后重试。",
            ]
            self._summary_only_note.setText("\n".join(head))
            self._summary_view = self._new_summary_view("\n".join(head))
            self.splitter.insertWidget(1, self._summary_view)
            self.splitter.setSizes([1, 1, 1])
            self._update_stat_label("已冻结（仅 stat，未读内容）")
            return

        if getattr(self, "_oversize_diff", False):
            # 超阈值但内容已读入：既能报大小，也能报行数，只是不做行级对齐
            head = [
                self._SUMMARY_HINT,
                "A: %s（%s 字节 / %d 行）" % (
                    self._left_title, _human(len(self._left_text)),
                    self._left_text.count("\n") + 1),
                "B: %s（%s 字节 / %d 行）" % (
                    self._right_title, _human(len(self._right_text)),
                    self._right_text.count("\n") + 1),
                "",
                "为保护界面流畅度，超过 %.1f MB 的文件**不执行行级对齐**、"
                "不渲染正文，因此不给出差异计数。" % (self._threshold / 1048576.0),
                "如需逐行差异，请用命令行：git diff --no-index A B；",
                "或把内容拆小后再对比。",
            ]
            self._summary_only_note.setText("\n".join(head))
            self._summary_view = self._new_summary_view("\n".join(head))
            self.splitter.insertWidget(1, self._summary_view)
            self.splitter.setSizes([1, 1, 1])
            self._update_stat_label("未做行级对齐（超阈值）")
            return

        lines = [
            self._SUMMARY_HINT,
            "A: %s（%s）  B: %s（%s）" % (
                self._left_title, _human(len(self._left_text)),
                self._right_title, _human(len(self._right_text))),
            "统计: %s" % stats.text(),
            "",
            "差异位置（最多 %d 条，格式  位置  内容）:" % SUMMARY_ROW_CAP,
        ]
        shown = 0
        for row in self._rows:
            if not row.changed:
                continue
            if shown >= SUMMARY_ROW_CAP:
                lines.append("…（还有更多差异，已截断）")
                break
            if row.kind == KIND_ADD:
                where = "A- / B%d" % (row.right_no or 0)
                body = "+ " + (row.right or "")[:120]
            elif row.kind == KIND_DELETE:
                where = "A%d / B-" % (row.left_no or 0)
                body = "- " + (row.left or "")[:120]
            else:
                where = "A%d / B%d" % (row.left_no or 0, row.right_no or 0)
                body = "~ " + (row.left or "")[:60] + "  ⇒  " + \
                    (row.right or "")[:60]
            lines.append("  %-12s %s" % (where, body))
            shown += 1
        if not self._rows:
            lines.append("  两个文件完全相同")

        self._summary_view = self._new_summary_view("\n".join(lines))
        self.splitter.insertWidget(1, self._summary_view)
        self.splitter.setSizes([1, 1])
        self._update_stat_label("差异位置已列出 %d 条" % shown)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ---- 顶部工具条 ----
        bar = QHBoxLayout()
        self.only_diff_check = QCheckBox("只显示差异")
        self.only_diff_check.setObjectName("merge_only_diff_check")
        self.only_diff_check.setChecked(False)
        self.only_diff_check.toggled.connect(self.set_only_diff)
        bar.addWidget(self.only_diff_check)

        self.sync_check = QCheckBox("同步滚动")
        self.sync_check.setObjectName("merge_sync_check")
        self.sync_check.setChecked(True)
        bar.addWidget(self.sync_check)

        self.char_check = QCheckBox("字符级高亮")
        self.char_check.setObjectName("merge_char_check")
        self.char_check.setChecked(True)
        bar.addWidget(self.char_check)
        bar.addStretch(1)
        bar.addWidget(self._make_legend())
        root.addLayout(bar)

        # ---- 大文件摘要区（默认隐藏）----
        self._summary_only_note = QLabel("")
        self._summary_only_note.setObjectName("merge_summary_note")
        self._summary_only_note.setWordWrap(True)
        self._summary_only_note.setStyleSheet(
            "color: #b06000; background: #fff8e1; padding: 6px; "
            "border: 1px solid #ffe0a3; border-radius: 3px;")
        self._summary_only_note.setVisible(False)
        root.addWidget(self._summary_only_note)

        # ---- 左右两栏 ----
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        self.left_edit = self._make_plain_edit()
        self.left_edit.setObjectName("merge_left_edit")
        self.left_edit.setPlaceholderText("（A 侧内容）")
        self.right_edit = self._make_plain_edit()
        self.right_edit.setObjectName("merge_right_edit")
        self.right_edit.setPlaceholderText("（B 侧内容）")

        self.left_panel, self.left_header, self.left_edit = self._wrap_pane(
            self._left_title, self.left_edit, "#eef6ff")
        self.right_panel, self.right_header, self.right_edit = self._wrap_pane(
            self._right_title, self.right_edit, "#f2fff4")
        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setSizes([580, 580])
        root.addWidget(self.splitter, 1)

        self._setup_sync_scroll(self.left_edit, self.right_edit)
        self.sync_check.toggled.connect(self.set_sync_scroll)
        self.char_check.toggled.connect(self.set_char_highlight)

        # ---- 底部统计 + 按钮 ----
        self._stat_label_widget = self._stat_label()
        root.addWidget(self._stat_label_widget)

        self.buttons = QDialogButtonBox()
        self.save_btn = QPushButton("保存对比结果…")
        self.save_btn.setObjectName("merge_save_btn")
        self.save_btn.clicked.connect(lambda _checked=False: self._on_save_clicked())
        self.buttons.addButton(self.save_btn, QDialogButtonBox.ActionRole)
        self.buttons.addButton("关闭", QDialogButtonBox.RejectRole)
        self.buttons.rejected.connect(self._on_close)
        root.addWidget(self.buttons)

    # ---------- 开关 ----------

    def set_only_diff(self, flag: bool) -> None:
        """"只显示差异 / 显示全部"切换"""
        self._only_diff = bool(flag)
        if self._large_mode or not self._plan:
            return
        rows = self._plan
        if flag:
            visible = rows["visible_rows"]
        else:
            visible = list(range(len(rows["left_lines"])))
        if not self._set_rows_visible(self.left_edit, self.right_edit, visible):
            # 当前 Qt 构建不支持隐藏块：状态回滚，避免复选框与实际不一致
            self._only_diff = not bool(flag)
            self.only_diff_check.setChecked(self._only_diff)
            return
        self.only_diff_check.setChecked(bool(flag))

    def set_sync_scroll(self, flag: bool) -> None:
        """开/关同步滚动

        连接在 :meth:`_setup_sync_scroll` 里只建立一次；这里只翻转
        ``_sync_enabled`` 标志 —— 绝不调用 ``disconnect()``（会把 Qt 自己
        的连接一起断掉，且反复开关会重复累积连接）。
        """
        self._sync_enabled = bool(flag)
        if flag:
            # 打开时立刻把右栏对齐到左栏当前位置，避免"错位后再开始同步"
            value = self.left_edit.verticalScrollBar().value()
            self._sync_axis(value, vertical=True, src=self.left_edit)
        self.sync_check.setChecked(bool(flag))

    def set_char_highlight(self, flag: bool) -> None:
        """开/关字符级高亮（关闭后只保留整行染色，更快）"""
        self.char_check.setChecked(bool(flag))
        if self._large_mode:
            return
        self._plan = _rows_to_plan(self._rows, self._only_diff, bool(flag))
        self._populate_plan(self.left_edit, self._plan["left_lines"],
                            self._plan["left_formats"], "left")
        self._populate_plan(self.right_edit, self._plan["right_lines"],
                            self._plan["right_formats"], "right")
        self._keep_block_counts_equal()
        if self._only_diff:
            self._set_rows_visible(self.left_edit, self.right_edit,
                                   self._plan["visible_rows"])

    # ---------- 输出（内容渲染见 _show_merge_result / 基类 _build_summary_only） ----------

    def stats(self) -> DiffStats:
        """统计（新增/删除/修改）"""
        return self._stats

    def aligned_rows(self) -> List[AlignedRow]:
        """对齐结果（测试用）"""
        return self._rows

    def diff_result(self) -> Dict[str, Any]:
        """对比结果字典（含末尾换行信息）::

            {'stats','rows','merged','left_ends_with_newline',
             'right_ends_with_newline','large_mode'}
        """
        return {
            "stats": self._stats,
            "rows": self._rows,
            "merged": self._right_text,
            "left_ends_with_newline": self._left_text.endswith(("\n", "\r")),
            "right_ends_with_newline": self._right_text.endswith(("\n", "\r")),
            "large_mode": self._large_mode,
        }

    # ---------- 事件 ----------

    def _on_save_clicked(self) -> None:
        """把"对比结果"另存为文本（对齐报告，不是简单拼接）"""
        if self._large_mode:
            QMessageBox.information(
                self, "仅差异摘要",
                "当前为大文件降级模式，没有可保存的完整对比结果。\n"
                "请缩小对比范围后再保存。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存对比结果", "diff.txt", "文本文件 (*.txt);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(self.render_diff_report())
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self.action = "save"
        self._saved_path = path
        self.accept()

    def render_diff_report(self) -> str:
        """生成纯文本对比报告（纯函数式，便于测试）"""
        out = ["# 对比报告",
               "# A: %s" % self._left_title,
               "# B: %s" % self._right_title,
               "# %s" % self._stats.text(),
               ""]
        for row in self._rows:
            if not row.changed:
                continue
            if row.kind == KIND_ADD:
                out.append("+ %s" % (row.right or ""))
            elif row.kind == KIND_DELETE:
                out.append("- %s" % (row.left or ""))
            else:
                out.append("- %s" % (row.left or ""))
                out.append("+ %s" % (row.right or ""))
        return "\n".join(out)

    def _on_close(self) -> None:
        self.action = self.action or "close"
        self.reject()


# ============================================================
# 三方合并对话框
# ============================================================

class ThreeWayMergeDialog(_BaseMergeDialog):
    """三方合并对话框（复用 ``core/file_merge.ThreeWayMerger``）

    参数:
        original: 最后保存的版本（base）
        local:    编辑器当前内容
        remote:   磁盘/外部新版
        local_path: 用于"保存到文件"时的默认目标

    ``action`` 取值：
        * ``'local'``  —— 用户选"保留本地"
        * ``'remote'`` —— 用户选"采用远程"
        * ``'manual'`` —— 用户手动编辑后确定（内容见 :meth:`merged_text`）
        * ``'close'``  —— 取消
    """

    LOCAL_BTN_TEXT = "保留本地（我的）"
    REMOTE_BTN_TEXT = "采用远程（磁盘）"
    MANUAL_BTN_TEXT = "手动编辑…"

    def __init__(self, original: str, local: str, remote: str,
                 local_path: Optional[str] = None,
                 parent=None,
                 size_threshold: int = DIFF_SIZE_THRESHOLD):
        super().__init__(parent)
        self._original = original or ""
        self._local = local or ""
        self._remote = remote or ""
        self._local_path = local_path
        self._threshold = size_threshold
        self.action = "close"
        self._manual_mode = False
        self._saved_path: Optional[str] = None
        # 冲突块：先按引擎原始结果解析，供大文件降级模式下的导航使用；
        # 非大文件模式下 _apply_conflict_formats 会用控件里的最终文本重算。
        self._conflict_blocks: List[Dict[str, Any]] = parse_conflict_markers(
            "")
        self._conflict_lines: List[int] = []
        self._conflict_cursor = -1

        self.setWindowTitle("三方合并")
        self._merge_result = self._run_merge()
        self._conflict_blocks = parse_conflict_markers(
            self._merge_result["merged"])
        # 上栏 A/B 展示的是"本地 vs 远程"的差异（原始/基准不占屏幕空间）
        self._rows = compute_diff(self._local, self._remote)
        self._stats = diff_summary(self._rows)
        self._large_mode = (
            is_large_text(self._merge_result["merged"], size_threshold)
            or is_large_text(self._local, size_threshold)
            or is_large_text(self._remote, size_threshold)
        )
        char_level = len(self._rows) <= CHAR_HIGHLIGHT_ROW_CAP

        self._build_ui()
        self._show_merge_result()          # 合并结果（大文件时降级为摘要）

        if not self._large_mode:
            # A/B 两栏渲染（大文件时保持空白，绝不灌入巨型文本）
            self._plan = _rows_to_plan(self._rows, only_diff=False,
                                       char_highlight=char_level)
            self._populate_plan(self.left_edit, self._plan["left_lines"],
                                self._plan["left_formats"], "left")
            self._populate_plan(self.right_edit, self._plan["right_lines"],
                                self._plan["right_formats"], "right")
            self._keep_block_counts_equal()
            self._apply_conflict_formats()

        self._highlight_conflicts()

    # ---------- 合并 ----------

    def _run_merge(self) -> Dict[str, Any]:
        """调用算法引擎（延迟导入，避免 ui 层硬依赖 core 的导入顺序）"""
        try:
            from core.file_merge import ThreeWayMerger
        except Exception as exc:                      # pragma: no cover
            return {
                "merged": self._local,
                "conflicts": [],
                "auto_merged": False,
                "strategy": "import_error: %s" % exc,
            }
        try:
            return ThreeWayMerger.merge(self._original, self._local,
                                        self._remote)
        except Exception as exc:                      # pragma: no cover
            return {
                "merged": self._local,
                "conflicts": [],
                "auto_merged": False,
                "strategy": "merge_error: %s" % exc,
            }

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ---- 顶部说明 ----
        info = QLabel("")
        info.setObjectName("merge_info_label")
        info.setWordWrap(True)
        strategy = self._merge_result.get("strategy", "?")
        n_conf = len(self._merge_result.get("conflicts", []))
        if n_conf:
            info.setText(
                "检测到 <b>%d</b> 处冲突（策略 <code>%s</code>）。左侧 A=当前编辑内容，"
                "右侧 B=磁盘新版，下方为三方合并结果；冲突用 "
                "<code>&lt;&lt;&lt;&lt;&lt;&lt;&lt; LOCAL / ======= / "
                "&gt;&gt;&gt;&gt;&gt;&gt;&gt; REMOTE</code> 标记。"
                % (n_conf, strategy))
            info.setStyleSheet("color: #b00020;")
        else:
            info.setText(
                "未检测到冲突，已自动合并（策略 <code>%s</code>）。"
                "可直接采用合并结果。" % strategy)
            info.setStyleSheet("color: #1a7f37;")
        root.addWidget(info)

        # ---- A/B 两栏（本地 vs 远程）----
        bar = QHBoxLayout()
        self.only_diff_check = QCheckBox("只显示差异")
        self.only_diff_check.setObjectName("merge_only_diff_check")
        self.only_diff_check.toggled.connect(self.set_only_diff)
        bar.addWidget(self.only_diff_check)
        bar.addStretch(1)
        bar.addWidget(self._make_legend())
        root.addLayout(bar)

        vs_splitter = QSplitter(Qt.Horizontal)
        vs_splitter.setChildrenCollapsible(False)
        self.left_edit = self._make_plain_edit()
        self.left_edit.setObjectName("merge_left_edit")
        self.right_edit = self._make_plain_edit()
        self.right_edit.setObjectName("merge_right_edit")
        self.left_panel, self.left_header, self.left_edit = self._wrap_pane(
            "A（当前本地）", self.left_edit, "#eef6ff")
        self.right_panel, self.right_header, self.right_edit = self._wrap_pane(
            "B（磁盘远程）", self.right_edit, "#f2fff4")
        vs_splitter.addWidget(self.left_panel)
        vs_splitter.addWidget(self.right_panel)
        self._setup_sync_scroll(self.left_edit, self.right_edit)

        # ---- 合并结果 ----
        merged_panel = QWidget()
        mlay = QVBoxLayout(merged_panel)
        mlay.setContentsMargins(0, 0, 0, 0)
        mlay.setSpacing(2)
        mhead = QHBoxLayout()
        mtitle = QLabel("合并结果（可手动编辑）")
        mtitle.setStyleSheet(
            "background: #fff3cc; padding: 4px 6px; font-weight: bold; "
            "font-size: 12px;")
        mhead.addWidget(mtitle, 1)
        self.conflict_nav = QToolButton()
        self.conflict_nav.setText("↓ 下一个冲突")
        self.conflict_nav.setObjectName("merge_conflict_nav")
        self.conflict_nav.setVisible(n_conf > 0)
        self.conflict_nav.clicked.connect(self.goto_next_conflict)
        mhead.addWidget(self.conflict_nav)
        mlay.addLayout(mhead)

        self._merged_edit = QPlainTextEdit()
        self._merged_edit.setObjectName("merge_result_edit")
        self._merged_edit.setFont(self._mono)
        self._merged_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        mlay.addWidget(self._merged_edit, 1)

        outer = QSplitter(Qt.Vertical)
        outer.setChildrenCollapsible(False)
        outer.addWidget(vs_splitter)
        outer.addWidget(merged_panel)
        outer.setSizes([320, 420])
        root.addWidget(outer, 1)

        # ---- 统计 ----
        self._stat_label_widget = self._stat_label()
        root.addWidget(self._stat_label_widget)
        self._update_merge_stat_label()

        # ---- 按钮 ----
        self.buttons = QDialogButtonBox()
        self.local_btn = QPushButton(self.LOCAL_BTN_TEXT)
        self.local_btn.setObjectName("merge_keep_local_btn")
        self.local_btn.setToolTip("放弃磁盘上的外部改动，保留当前编辑器内容")
        self.local_btn.clicked.connect(lambda: self._finish("local"))
        self.remote_btn = QPushButton(self.REMOTE_BTN_TEXT)
        self.remote_btn.setObjectName("merge_take_remote_btn")
        self.remote_btn.setToolTip("放弃本地改动，采用磁盘上的新版")
        self.remote_btn.clicked.connect(lambda: self._finish("remote"))
        self.manual_btn = QPushButton(self.MANUAL_BTN_TEXT)
        self.manual_btn.setObjectName("merge_manual_btn")
        self.manual_btn.setToolTip("把光标移入合并结果框逐段手工取舍，再点确定")
        self.manual_btn.clicked.connect(self.enter_manual_mode)

        for btn in (self.local_btn, self.remote_btn):
            self.buttons.addButton(btn, QDialogButtonBox.ActionRole)
        self.buttons.addButton(self.manual_btn, QDialogButtonBox.ActionRole)

        self.save_btn = QPushButton("保存合并结果到…")
        self.save_btn.setObjectName("merge_save_btn")
        # 注意：QPushButton.clicked 带 bool checked 参数；这里用显式 lambda
        # 丢掉它，避免被当成 save_to_file 的 path 参数（PyQt5 会把 False/True
        # 传进来）。同样的写法在 "下一个冲突" 上也用了一遍。
        self.save_btn.clicked.connect(lambda _checked=False: self.save_to_file())
        self.buttons.addButton(self.save_btn, QDialogButtonBox.ActionRole)

        self.buttons.addButton("取消", QDialogButtonBox.RejectRole)
        self.buttons.rejected.connect(self._on_cancel)
        root.addWidget(self.buttons)

    # ---------- 展示 ----------

    def _show_merge_result(self) -> None:
        """把合并结果灌进控件

        大文件时只放**冲突摘要**，绝不把合并后的巨型文本塞进 QPlainTextEdit
        （这正是任务里"两个 100MB 文件"的要求）。
        冲突染色由 :meth:`_apply_conflict_formats` 单独负责。
        """
        if self._large_mode:
            self._merged_edit.setPlainText(self._conflict_summary_text())
        else:
            self._merged_edit.setPlainText(self._merge_result["merged"])

    def _apply_conflict_formats(self) -> None:
        """给冲突标记行 + 冲突块内容染色，并收集冲突块行号"""
        text = self._merged_edit.toPlainText()
        self._conflict_blocks = parse_conflict_markers(text)
        selections = []
        marker_fmt = _new_format(fg=COLOR_MARKER_FG, bold=True)
        block_fmt = _new_format(COLOR_CONFLICT_BG)

        for blk in self._conflict_blocks:
            for ln in range(blk["start"], blk["end"] + 1):
                block = self._merged_edit.document().findBlockByNumber(ln - 1)
                if not block.isValid():
                    continue
                cur = QTextCursor(block)
                cur.setPosition(block.position())
                cur.setPosition(block.position() + max(0, block.length() - 1),
                                QTextCursor.KeepAnchor)
                sel = QTextEdit.ExtraSelection()
                sel.cursor = cur
                line_text = block.text()
                sel.format = marker_fmt if line_text.startswith(
                    ("<<<<<<<", "=======", ">>>>>>>")) else block_fmt
                selections.append(sel)

        try:
            self._merged_edit.setExtraSelections(selections)
        except Exception:
            pass

    def _highlight_conflicts(self) -> None:
        """冲突行号记录 + 冲突数展示（供导航与测试）"""
        self._conflict_lines = [b["start"] for b in self._conflict_blocks]
        self._conflict_cursor = -1

    def _conflict_summary_text(self) -> str:
        """大文件降级时显示的冲突摘要文本"""
        blocks = parse_conflict_markers(self._merge_result["merged"])
        out = [self._SUMMARY_HINT,
               "策略: %s" % self._merge_result.get("strategy", "?"),
               "合并后总大小: %s" % _human(len(self._merge_result["merged"])),
               "冲突数: %d" % len(blocks),
               ""]
        for i, blk in enumerate(blocks, 1):
            out.append("冲突 #%d（结果第 %d-%d 行）" % (i, blk["start"], blk["end"]))
            out.append("  LOCAL : " + (" / ".join(blk["local"])[:160] or "(空)"))
            out.append("  REMOTE: " + (" / ".join(blk["remote"])[:160] or "(空)"))
        if not blocks:
            out.append("无冲突：两侧改动可自动合并。")
            out.append("但由于文件超过 %.1f MB，未在界面中渲染完整正文。"
                       % (DIFF_SIZE_THRESHOLD / 1024.0 / 1024.0))
        return "\n".join(out)

    def _update_merge_stat_label(self) -> None:
        extra = "冲突 %d 处" % len(self._merge_result.get("conflicts", []))
        if not self._merge_result.get("auto_merged", True):
            extra += "（需人工处理）"
        self._update_stat_label("本地↔远程 " + self._stats.text() + "  |  " + extra)

    # ---------- 开关 ----------

    def set_only_diff(self, flag: bool) -> None:
        """"只显示差异"（作用于上方的 A/B 两栏）"""
        self._only_diff = bool(flag)
        if not hasattr(self, "_plan") or not self._plan:
            return
        visible = (self._plan["visible_rows"] if flag
                   else list(range(len(self._plan["left_lines"]))))
        if not self._set_rows_visible(self.left_edit, self.right_edit, visible):
            self._only_diff = not bool(flag)       # 不支持隐藏块则回滚状态
            self.only_diff_check.setChecked(self._only_diff)
            return
        self.only_diff_check.setChecked(bool(flag))

    # ---------- 冲突导航 ----------

    def goto_next_conflict(self) -> int:
        """跳到下一个冲突（返回 0-based 冲突序号，-1 表示没有冲突）"""
        if not getattr(self, "_conflict_lines", None):
            return -1
        self._conflict_cursor = (self._conflict_cursor + 1) % \
            len(self._conflict_lines)
        line_no = self._conflict_lines[self._conflict_cursor]
        block = self._merged_edit.document().findBlockByNumber(
            max(0, line_no - 1))
        if block.isValid():
            cur = QTextCursor(block)
            self._merged_edit.setTextCursor(cur)
            self._merged_edit.centerCursor()
        return self._conflict_cursor

    # ---------- 手动编辑 / 输出 ----------

    def enter_manual_mode(self) -> None:
        """进入手动编辑：把焦点交给结果框（内容已可编辑，仅补提示）"""
        self._manual_mode = True
        self._merged_edit.setReadOnly(False)
        self._merged_edit.setFocus()
        self.manual_btn.setText(self.MANUAL_BTN_TEXT + "（请编辑后点“确定”）")
        if not self.buttons.button(QDialogButtonBox.Ok):
            self.ok_btn = QPushButton("确定（用编辑后的内容）")
            self.ok_btn.setObjectName("merge_ok_btn")
            self.ok_btn.setDefault(True)
            self.ok_btn.clicked.connect(self.accept_manual)
            self.buttons.addButton(self.ok_btn, QDialogButtonBox.AcceptRole)

    def accept_manual(self) -> None:
        """确定手动编辑结果"""
        self.action = "manual"
        self.accept()

    def merged_text(self) -> str:
        """当前合并结果文本（手动编辑后即用户改造过的内容）"""
        return self._merged_edit.toPlainText()

    def merge_result(self) -> Dict[str, Any]:
        """``ThreeWayMerger.merge`` 的原始返回（merged/conflicts/...）"""
        return self._merge_result

    def conflict_blocks(self) -> List[Dict[str, Any]]:
        """解析出的冲突块（start/end/local/remote）"""
        return getattr(self, "_conflict_blocks", [])

    def save_to_file(self, path: Optional[str] = None) -> bool:
        """把当前合并结果写到文件（不传 path 就弹保存对话框）

        注意：对话框**不会**自动写回原文件，写盘必须由用户/调用方显式触发。
        """
        if not path:
            default = self._local_path or "merged.txt"
            path, _ = QFileDialog.getSaveFileName(
                self, "保存合并结果", default,
                "文本文件 (*.txt);;所有文件 (*)")
        if not path:
            return False
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(self.merged_text())
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return False
        self._saved_path = path
        return True

    def _finish(self, action: str) -> None:
        """按钮回调：记录用户选择并关闭"""
        self.action = action
        self.accept()

    def _on_cancel(self) -> None:
        self.action = "close"
        self.reject()


# ============================================================
# 辅助
# ============================================================

def _human(size: int) -> str:
    """人类可读的大小"""
    try:
        size = float(size)
    except Exception:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return "%.1f %s" % (size, unit) if unit != "B" else "%d B" % size
        size /= 1024.0
    return "%.1f GB" % size


def _safe_size(path: Optional[str]) -> int:
    try:
        return os.path.getsize(path) if path else 0
    except Exception:
        return 0


__all__ = [
    "CHAR_HIGHLIGHT_ROW_CAP",
    "DIFF_SIZE_THRESHOLD",
    "KIND_ADD",
    "KIND_DELETE",
    "KIND_EQUAL",
    "KIND_MODIFY",
    "KIND_TEXT",
    "SUMMARY_ROW_CAP",
    "AlignedRow",
    "DiffStats",
    "FileDiffDialog",
    "ThreeWayMergeDialog",
    "compute_diff",
    "count_conflicts",
    "diff_summary",
    "diff_texts",
    "is_large_path",
    "is_large_text",
    "parse_conflict_markers",
    "read_text_file",
]
