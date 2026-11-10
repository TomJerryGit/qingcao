# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""文件差异对话框（v2.24 拆出）。"""

from ui.file_merge_base import _BaseMergeDialog
from ui.file_merge_dialog_common import *


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

    def __init__(
        self,
        left_text: str,
        right_text: str,
        left_title: str = "A（本地/当前）",
        right_title: str = "B（对比目标）",
        parent=None,
        size_threshold: int = DIFF_SIZE_THRESHOLD,
    ):
        super().__init__(parent)
        self._left_text = left_text or ""
        self._right_text = right_text or ""
        self._left_title = left_title
        self._right_title = right_title
        self._threshold = size_threshold
        self._plan: Optional[Dict[str, Any]] = None
        self._saved_path: Optional[str] = None
        self.action = "close"  # 'close' | 'save'

        self.setWindowTitle("对比文件 —— %s ↔ %s" % (left_title, right_title))

        # 大文件判定放在 diff **之前**：超阈值时不做行级对齐，避免几百万行
        # 的 SequenceMatcher 卡住 UI（真正的"100MB 文件"走 frozen() 路径）。
        self._large_mode = is_large_text(self._left_text, size_threshold) or is_large_text(
            self._right_text, size_threshold
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
            self._plan = _rows_to_plan(rows, only_diff=False, char_highlight=char_level)
            self._populate_plan(
                self.left_edit, self._plan["left_lines"], self._plan["left_formats"], "left"
            )
            self._populate_plan(
                self.right_edit, self._plan["right_lines"], self._plan["right_formats"], "right"
            )
            self._keep_block_counts_equal()
            self._update_stat_label(
                "差异行 %d / 共 %d 行" % (len(self._plan["changed_rows"]), len(rows))
            )
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
            parent, "选择要对比的文件 A（本地/当前）", start_dir, "所有文件 (*)"
        )
        if not path_a:
            return None

        # A 选完之后默认从 A 所在目录继续选 B
        start_dir = os.path.dirname(os.path.abspath(path_a))
        path_b, _ = QFileDialog.getOpenFileName(
            parent, "选择要对比的文件 B（对比目标）", start_dir, "所有文件 (*)"
        )
        if not path_b:
            return None

        if os.path.abspath(path_a) == os.path.abspath(path_b):
            # 自己和自己比没有意义，直接提示并返回 None（不弹空对话框）
            if parent is not None:
                QMessageBox.information(parent, "对比文件", "两次选择的是同一个文件，已取消。")
            return None

        return cls.from_files(path_a, path_b, parent=parent, size_threshold=size_threshold)

    @classmethod
    def from_files(
        cls, left_path: str, right_path: str, parent=None, size_threshold: int = DIFF_SIZE_THRESHOLD
    ):
        """从两个文件路径构造

        * 任一文件超过阈值 → 走 :meth:`frozen`（**不读内容**，直接摘要）
        * 否则正常读取（UTF-8 / GBK 兜底）后做双栏对比
        """
        if is_large_path(left_path, size_threshold) or is_large_path(right_path, size_threshold):
            return cls.frozen(left_path, right_path, parent=parent, size_threshold=size_threshold)

        left_text, lerr = read_text_file(left_path)
        right_text, rerr = read_text_file(right_path)
        dlg = cls(
            left_text or "",
            right_text or "",
            "A: %s" % os.path.basename(left_path),
            "B: %s" % os.path.basename(right_path),
            parent=parent,
            size_threshold=size_threshold,
        )
        if lerr or rerr:
            dlg._stat_label_widget.setText("读取告警: %s %s" % (lerr or "", rerr or ""))
        return dlg

    # ---------- 冻结（大文件路径级降级） ----------

    @classmethod
    def frozen(
        cls,
        left_path: str,
        right_path: str,
        parent=None,
        size_threshold: int = DIFF_SIZE_THRESHOLD,
        left_title: Optional[str] = None,
        right_title: Optional[str] = None,
    ):
        """**路径级冻结**：只 stat 两个文件，完全不读内容就给出摘要

        用于两个几十/几百 MB 的文件 —— 连读取都省掉，避免内存峰值。
        """
        dlg = cls.__new__(cls)  # 绕过 __init__ 的内容读取
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
        dlg.setWindowTitle("对比文件 —— %s ↔ %s" % (dlg._left_title, dlg._right_title))
        dlg._build_ui()
        dlg._build_summary_only(frozen_paths=(left_path, right_path))
        return dlg

    def _build_summary_only(self, frozen_paths: Optional[Tuple[str, str]] = None) -> None:
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
                "%s（A %s，B %s）" % (self._SUMMARY_HINT, _human(left_size), _human(right_size)),
                "为避免把两个大文件塞进控件导致界面冻结，本对话框**未读取、未渲染**正文内容。",
                '如需逐行查看差异，请用命令行：git diff --no-index "%s" "%s"'
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
                "A: %s（%s 字节 / %d 行）"
                % (self._left_title, _human(len(self._left_text)), self._left_text.count("\n") + 1),
                "B: %s（%s 字节 / %d 行）"
                % (
                    self._right_title,
                    _human(len(self._right_text)),
                    self._right_text.count("\n") + 1,
                ),
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
            "A: %s（%s）  B: %s（%s）"
            % (
                self._left_title,
                _human(len(self._left_text)),
                self._right_title,
                _human(len(self._right_text)),
            ),
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
                body = "~ " + (row.left or "")[:60] + "  ⇒  " + (row.right or "")[:60]
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
            "border: 1px solid #ffe0a3; border-radius: 3px;"
        )
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
            self._left_title, self.left_edit, "#eef6ff"
        )
        self.right_panel, self.right_header, self.right_edit = self._wrap_pane(
            self._right_title, self.right_edit, "#f2fff4"
        )
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
        """ "只显示差异 / 显示全部"切换"""
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
        self._populate_plan(
            self.left_edit, self._plan["left_lines"], self._plan["left_formats"], "left"
        )
        self._populate_plan(
            self.right_edit, self._plan["right_lines"], self._plan["right_formats"], "right"
        )
        self._keep_block_counts_equal()
        if self._only_diff:
            self._set_rows_visible(self.left_edit, self.right_edit, self._plan["visible_rows"])

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
                self,
                "仅差异摘要",
                "当前为大文件降级模式，没有可保存的完整对比结果。\n请缩小对比范围后再保存。",
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存对比结果", "diff.txt", "文本文件 (*.txt);;所有文件 (*)"
        )
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
        out = [
            "# 对比报告",
            "# A: %s" % self._left_title,
            "# B: %s" % self._right_title,
            "# %s" % self._stats.text(),
            "",
        ]
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
