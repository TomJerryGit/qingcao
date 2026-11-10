# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""三路合并对话框（v2.24 拆出）。"""

from ui.file_merge_base import _BaseMergeDialog
from ui.file_merge_dialog_common import *


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

    def __init__(
        self,
        original: str,
        local: str,
        remote: str,
        local_path: Optional[str] = None,
        parent=None,
        size_threshold: int = DIFF_SIZE_THRESHOLD,
    ):
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
        self._conflict_blocks: List[Dict[str, Any]] = parse_conflict_markers("")
        self._conflict_lines: List[int] = []
        self._conflict_cursor = -1

        self.setWindowTitle("三方合并")
        self._merge_result = self._run_merge()
        self._conflict_blocks = parse_conflict_markers(self._merge_result["merged"])
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
        self._show_merge_result()  # 合并结果（大文件时降级为摘要）

        if not self._large_mode:
            # A/B 两栏渲染（大文件时保持空白，绝不灌入巨型文本）
            self._plan = _rows_to_plan(self._rows, only_diff=False, char_highlight=char_level)
            self._populate_plan(
                self.left_edit, self._plan["left_lines"], self._plan["left_formats"], "left"
            )
            self._populate_plan(
                self.right_edit, self._plan["right_lines"], self._plan["right_formats"], "right"
            )
            self._keep_block_counts_equal()
            self._apply_conflict_formats()

        self._highlight_conflicts()

    # ---------- 合并 ----------

    def _run_merge(self) -> Dict[str, Any]:
        """调用算法引擎（延迟导入，避免 ui 层硬依赖 core 的导入顺序）"""
        try:
            from core.file_merge import ThreeWayMerger
        except Exception as exc:  # pragma: no cover
            return {
                "merged": self._local,
                "conflicts": [],
                "auto_merged": False,
                "strategy": "import_error: %s" % exc,
            }
        try:
            return ThreeWayMerger.merge(self._original, self._local, self._remote)
        except Exception as exc:  # pragma: no cover
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
                "&gt;&gt;&gt;&gt;&gt;&gt;&gt; REMOTE</code> 标记。" % (n_conf, strategy)
            )
            info.setStyleSheet("color: #b00020;")
        else:
            info.setText(
                "未检测到冲突，已自动合并（策略 <code>%s</code>）。可直接采用合并结果。" % strategy
            )
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
            "A（当前本地）", self.left_edit, "#eef6ff"
        )
        self.right_panel, self.right_header, self.right_edit = self._wrap_pane(
            "B（磁盘远程）", self.right_edit, "#f2fff4"
        )
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
            "background: #fff3cc; padding: 4px 6px; font-weight: bold; font-size: 12px;"
        )
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
                cur.setPosition(
                    block.position() + max(0, block.length() - 1), QTextCursor.KeepAnchor
                )
                sel = QTextEdit.ExtraSelection()
                sel.cursor = cur
                line_text = block.text()
                sel.format = (
                    marker_fmt
                    if line_text.startswith(("<<<<<<<", "=======", ">>>>>>>"))
                    else block_fmt
                )
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
        out = [
            self._SUMMARY_HINT,
            "策略: %s" % self._merge_result.get("strategy", "?"),
            "合并后总大小: %s" % _human(len(self._merge_result["merged"])),
            "冲突数: %d" % len(blocks),
            "",
        ]
        for i, blk in enumerate(blocks, 1):
            out.append("冲突 #%d（结果第 %d-%d 行）" % (i, blk["start"], blk["end"]))
            out.append("  LOCAL : " + (" / ".join(blk["local"])[:160] or "(空)"))
            out.append("  REMOTE: " + (" / ".join(blk["remote"])[:160] or "(空)"))
        if not blocks:
            out.append("无冲突：两侧改动可自动合并。")
            out.append(
                "但由于文件超过 %.1f MB，未在界面中渲染完整正文。"
                % (DIFF_SIZE_THRESHOLD / 1024.0 / 1024.0)
            )
        return "\n".join(out)

    def _update_merge_stat_label(self) -> None:
        extra = "冲突 %d 处" % len(self._merge_result.get("conflicts", []))
        if not self._merge_result.get("auto_merged", True):
            extra += "（需人工处理）"
        self._update_stat_label("本地↔远程 " + self._stats.text() + "  |  " + extra)

    # ---------- 开关 ----------

    def set_only_diff(self, flag: bool) -> None:
        """ "只显示差异"（作用于上方的 A/B 两栏）"""
        self._only_diff = bool(flag)
        if not hasattr(self, "_plan") or not self._plan:
            return
        visible = self._plan["visible_rows"] if flag else list(range(len(self._plan["left_lines"])))
        if not self._set_rows_visible(self.left_edit, self.right_edit, visible):
            self._only_diff = not bool(flag)  # 不支持隐藏块则回滚状态
            self.only_diff_check.setChecked(self._only_diff)
            return
        self.only_diff_check.setChecked(bool(flag))

    # ---------- 冲突导航 ----------

    def goto_next_conflict(self) -> int:
        """跳到下一个冲突（返回 0-based 冲突序号，-1 表示没有冲突）"""
        if not getattr(self, "_conflict_lines", None):
            return -1
        self._conflict_cursor = (self._conflict_cursor + 1) % len(self._conflict_lines)
        line_no = self._conflict_lines[self._conflict_cursor]
        block = self._merged_edit.document().findBlockByNumber(max(0, line_no - 1))
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
                self, "保存合并结果", default, "文本文件 (*.txt);;所有文件 (*)"
            )
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
