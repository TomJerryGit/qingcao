# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""合并对话框基类（v2.24 拆出）。"""

from ui.file_merge_dialog_common import *


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
                "font-size: 12px; padding: 2px 6px; color: #b06000;"
            )
        else:
            self._stat_label_widget.setStyleSheet("font-size: 12px; padding: 2px 6px;")

    def _make_legend(self) -> QLabel:
        """颜色图例 —— 用户要能看懂三种颜色分别代表什么"""
        label = QLabel(
            '<span style="background:%s;">&nbsp;&nbsp;&nbsp;&nbsp;</span> 新增 '
            '<span style="background:%s;">&nbsp;&nbsp;&nbsp;&nbsp;</span> 删除 '
            '<span style="background:%s;">&nbsp;&nbsp;&nbsp;&nbsp;</span> 修改 '
            '<span style="background:%s;">&nbsp;&nbsp;&nbsp;&nbsp;</span> 对侧空槽'
            % (COLOR_ADD_BG.name(), COLOR_DEL_BG.name(), COLOR_MOD_BG.name(), COLOR_GAP_BG.name())
        )
        label.setStyleSheet("font-size: 11px; color: #666;")
        label.setToolTip("深色字符高亮表示行内真正变化的字符（修改行里浅色部分是未变内容）")
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

    def _populate_plan(
        self,
        edit: QPlainTextEdit,
        lines: List[str],
        formats: List[List[QTextCharFormat]],
        side: str,
    ) -> None:
        """把渲染计划灌进控件（只读控件，``setPlainText`` 最快）"""
        edit.setPlainText("\n".join(lines))
        self._apply_formats(edit, formats, side)

    def _apply_formats(
        self, edit: QPlainTextEdit, formats: List[List[QTextCharFormat]], side: str
    ) -> None:
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
            length = block.length() - 1  # 不含段落分隔符
            if length <= 0:
                length = 1  # 空行也要能看见底色
            for fmt in fmts:
                cursor = QTextCursor(block)
                cursor.setPosition(block.position())
                cursor.setPosition(block.position() + length, QTextCursor.KeepAnchor)
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

    def _set_rows_visible(
        self, left: QPlainTextEdit, right: QPlainTextEdit, visible_rows: List[int]
    ) -> bool:
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
            "background: %s; padding: 4px 6px; font-weight: bold; font-size: 12px;" % header_bg
        )
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

    def _setup_sync_scroll(self, left: QPlainTextEdit, right: QPlainTextEdit) -> None:
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

    def _sync_axis(
        self, value: int, vertical: bool = True, src: Optional[QPlainTextEdit] = None
    ) -> None:
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
