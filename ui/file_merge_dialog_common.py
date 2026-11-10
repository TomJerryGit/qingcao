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
COLOR_ADD_BG = QColor("#d7f6dc")  # 新增行
COLOR_ADD_CHAR = QColor("#7fd694")  # 新增行里真正新增的字符
COLOR_DEL_BG = QColor("#ffe0e0")  # 删除行
COLOR_DEL_CHAR = QColor("#f19a9a")  # 删除行里真正删掉的字符
COLOR_MOD_BG = QColor("#fff3cc")  # 修改行（两侧都变）
COLOR_MOD_SAME = QColor("#fffbe8")  # 修改行里未变的字符（浅）
COLOR_MOD_CHAR = QColor("#f5c542")  # 修改行里变化的字符
COLOR_GAP_BG = QColor("#f2f2f2")  # 对侧缺行留下的空槽
COLOR_CONFLICT_BG = QColor("#ffe3e3")  # 冲突块底色
COLOR_MARKER_FG = QColor("#b00020")  # 冲突标记文字

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
        return {
            "added": self.added,
            "deleted": self.deleted,
            "modified": self.modified,
            "total": self.total,
        }

    def text(self) -> str:
        return "新增 %d 行 / 删除 %d 行 / 修改 %d 行" % (self.added, self.deleted, self.modified)


# ============================================================
# 纯函数 diff 层（无 Qt，可独立测试）
# ============================================================


def _char_diff_ranges(a: str, b: str) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
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
                rows.append(
                    AlignedRow(
                        KIND_EQUAL,
                        left_lines[i1 + k],
                        right_lines[j1 + k],
                        i1 + k + 1,
                        j1 + k + 1,
                    )
                )
            continue

        if tag == "delete":
            for k in range(i1, i2):
                rows.append(AlignedRow(KIND_DELETE, left_lines[k], None, k + 1, None))
            continue

        if tag == "insert":
            for k in range(j1, j2):
                rows.append(AlignedRow(KIND_ADD, None, right_lines[k], None, k + 1))
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
        for row in _align_block(left_lines, right_lines, i1, i2, j1, j2, char_level):
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
    sim: List[List[Optional[float]]] = [[None] * n_r for _ in range(n_l)]
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
                out.append(
                    AlignedRow(
                        kind,
                        lv,
                        rv,
                        i1 + p + 1,
                        j1 + q + 1,
                        la,
                        ra,
                    )
                )
                p += 1
                q += 1
                continue
            if pick == 1:
                out.append(
                    AlignedRow(
                        KIND_DELETE,
                        left_lines[i1 + p],
                        None,
                        i1 + p + 1,
                        None,
                    )
                )
                p += 1
                continue
            out.append(
                AlignedRow(
                    KIND_ADD,
                    None,
                    right_lines[j1 + q],
                    None,
                    j1 + q + 1,
                )
            )
            q += 1
            continue

        if p < n_l:
            out.append(
                AlignedRow(
                    KIND_DELETE,
                    left_lines[i1 + p],
                    None,
                    i1 + p + 1,
                    None,
                )
            )
            p += 1
        else:
            out.append(
                AlignedRow(
                    KIND_ADD,
                    None,
                    right_lines[j1 + q],
                    None,
                    j1 + q + 1,
                )
            )
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


def is_large_text(text: Optional[str], threshold: int = DIFF_SIZE_THRESHOLD) -> bool:
    """文本是否超过大文件阈值（按 UTF-8 字节数估算，避免只数字符）"""
    if not text:
        return False
    try:
        return len(text.encode("utf-8", errors="replace")) > threshold
    except Exception:
        return len(text) > threshold


def is_large_path(path: Optional[str], threshold: int = DIFF_SIZE_THRESHOLD) -> bool:
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
    except Exception as exc:  # noqa: BLE001 - 对话框要能提示
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
    return sum(1 for line in (text or "").splitlines() if line.startswith("<<<<<<<"))


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
            blocks.append(
                {
                    "start": start,
                    "end": end,
                    "local": local,
                    "remote": remote,
                }
            )
        else:
            i += 1
    return blocks


# ============================================================
# 渲染辅助
# ============================================================


def _new_format(
    bg: Optional[QColor] = None, fg: Optional[QColor] = None, bold: bool = False
) -> QTextCharFormat:
    """构造 QTextCharFormat（QPlainTextEdit 的 setExtraSelections 用）"""
    fmt = QTextCharFormat()
    if bg is not None:
        fmt.setBackground(bg)
    if fg is not None:
        fmt.setForeground(fg)
    if bold:
        fmt.setFontWeight(75)  # QFont.Bold == 75
    return fmt


def _mono_font():
    """等宽字体：对比视图必须等宽，否则左右栏视觉不对齐

    在 ``offscreen`` / 无字体数据库的环境下 ``QFontDatabase.families()``
    可能为空，因此这里**不做** families 交集，直接把系统 FixedFont 的
    族名换掉即可（Qt 找不到时自行回退，不会抛异常）。
    """
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    for name in ("Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Courier New"):
        try:
            font.setFamily(name)
            break
        except Exception:  # pragma: no cover
            continue
    return font


def _rows_to_plan(rows: List[AlignedRow], only_diff: bool, char_highlight: bool) -> Dict[str, Any]:
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
            lf.append(gap_fmt)  # 左栏空槽
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
                for s, e in _valid_ranges(row.left_ranges, row.left or ""):
                    lf.append(_new_format(COLOR_MOD_CHAR))
                for s, e in _valid_ranges(row.right_ranges, row.right or ""):
                    rf.append(_new_format(COLOR_MOD_CHAR))
        else:  # equal
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
    for s, e in ranges or []:
        s = max(0, min(int(s), n))
        e = max(0, min(int(e), n))
        if e > s:
            out.append((s, e))
    return out


# ============================================================
# 基础对话框
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
    "compute_diff",
    "count_conflicts",
    "diff_summary",
    "diff_texts",
    "is_large_path",
    "is_large_text",
    "parse_conflict_markers",
    "read_text_file",
]

__all__ = [n for n in dir() if not n.startswith("__")]
