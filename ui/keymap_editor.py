# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""快捷键编辑器（v2.25 拆分：common/dialogs/editor）。"""

from ui.keymap_dialogs import *  # noqa: F401,F403
from ui.keymap_editor_common import *  # noqa: F401,F403


class KeymapEditor(QDialog):
    """
    快捷键编辑器对话框。

    功能:
    - 显示所有命令及其快捷键
    - 双击编辑快捷键
    - 搜索过滤
    - 冲突检测
    - 恢复默认
    - 导入/导出
    - 多方案切换

    信号:
        keymap_changed(str, str): 快捷键变更（动作名, 新快捷键）
        keymap_reset(): 恢复默认
    """

    keymap_changed = pyqtSignal(str, str)
    keymap_reset = pyqtSignal()

    def __init__(self, action_manager: ActionManager, parent=None):
        """
        参数:
            action_manager: ActionManager 实例
            parent: 父窗口
        """
        super().__init__(parent)

        self.act_mgr = action_manager
        self._settings = QSettings("QingCao", "KeymapEditor")

        # 条目列表
        self._entries: List[KeymapEntry] = []

        # 冲突映射：shortcut -> [action_names]
        self._conflicts: Dict[str, List[str]] = {}

        # 构建 UI
        self.setWindowTitle("快捷键编辑器")
        self.resize(700, 600)

        self._build_ui()

        # 加载
        QTimer.singleShot(0, self._load_entries)

    # --------------------------------------------------------
    # UI 构建
    # --------------------------------------------------------
    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ========== 顶部工具栏 ==========
        top_bar = self._build_top_bar()
        layout.addWidget(top_bar)

        # ========== 表格 ==========
        self.table = KeymapTable()
        self.table.shortcut_changed.connect(self._on_shortcut_changed)
        layout.addWidget(self.table, 1)

        # ========== 状态栏 ==========
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")
        layout.addWidget(self.status_label)

        # ========== 底部按钮 ==========
        bottom_bar = self._build_bottom_bar()
        layout.addWidget(bottom_bar)

        # 应用样式
        self._apply_style()

    def _build_top_bar(self) -> QWidget:
        """构建顶部工具栏"""
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索命令或快捷键...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_edit, 1)

        # 只看冲突
        self.conflict_only_cb = QCheckBox("只看冲突")
        self.conflict_only_cb.toggled.connect(self._on_conflict_filter)
        layout.addWidget(self.conflict_only_cb)

        # 只看已修改
        self.modified_only_cb = QCheckBox("只看已修改")
        self.modified_only_cb.toggled.connect(self._on_modified_filter)
        layout.addWidget(self.modified_only_cb)

        # ---- 快捷键方案预设（core/keymap_profiles）----
        #
        # 此前 `core/keymap_profiles.py`（102 行）**零引用** ——
        # VSCode/Sublime/Vim 方案预设写好了却没有任何入口，
        # 用户只能在表格里逐个手改快捷键。
        layout.addWidget(QLabel("方案:"))
        self.scheme_combo = QComboBox()
        for key, label in get_scheme_names():
            self.scheme_combo.addItem(label, key)
        # 回显用户上次选的方案
        saved = load_saved_scheme()
        idx = self.scheme_combo.findData(saved)
        if idx >= 0:
            self.scheme_combo.setCurrentIndex(idx)
        self.scheme_combo.setToolTip(
            "一键套用 VSCode / Sublime / Vim 风格的快捷键布局。\n"
            "应用前会先校验方案本身是否存在重复快捷键或拼错的命令名。"
        )
        layout.addWidget(self.scheme_combo)

        self.apply_scheme_btn = QPushButton("套用")
        self.apply_scheme_btn.setToolTip(
            "把当前选中的方案应用到全部快捷键，并记住该选择（下次启动自动生效）"
        )
        self.apply_scheme_btn.clicked.connect(self._on_apply_scheme)
        layout.addWidget(self.apply_scheme_btn)

        return bar

    def _on_apply_scheme(self):
        """套用选中的快捷键方案（core/keymap_profiles）

        失败时**必须可见**：`apply_scheme` 会拒绝含重复快捷键的方案
        （历史上 vscode 方案就有这个缺陷），这里把原因原样告诉用户，
        而不是静默什么都不做。
        """
        key = self.scheme_combo.currentData()
        if not key:
            return

        ok, problems = validate_scheme(key, action_manager=self.act_mgr)
        if not ok:
            QMessageBox.warning(
                self,
                "无法套用该方案",
                "该快捷键方案存在问题，已**拒绝套用**（你的现有快捷键未被改动）：\n\n"
                + "\n".join("  · " + p for p in problems),
            )
            return

        label = self.scheme_combo.currentText()
        if key == "default":
            # 默认方案 = 恢复 ActionManager 的默认值
            try:
                self.act_mgr.reset_to_defaults()
            except Exception as e:
                QMessageBox.warning(self, "套用失败", str(e))
                return
        else:
            if not apply_scheme(self.act_mgr, key):
                QMessageBox.warning(self, "套用失败", "方案 %s 应用失败，请查看输出日志。" % label)
                return

        # 记住选择，下次启动自动生效
        save_scheme(key)

        # 刷新表格（重新从 ActionManager 读实际快捷键）
        try:
            self._load_entries()
        except Exception:
            try:
                self.table.load_entries(self._entries)
            except Exception:
                pass
        try:
            self._detect_conflicts()
            self._update_status()
        except Exception:
            pass

        bus.emit_status("已套用「%s」快捷键方案" % label, 3000, "success")

    def _build_bottom_bar(self) -> QWidget:
        """构建底部按钮栏"""
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 恢复默认
        self.reset_btn = QPushButton("↺ 恢复默认")
        self.reset_btn.clicked.connect(self._reset_to_defaults)
        layout.addWidget(self.reset_btn)

        # 导入
        self.import_btn = QPushButton("📥 导入")
        self.import_btn.clicked.connect(self._import_keymap)
        layout.addWidget(self.import_btn)

        # 导出
        self.export_btn = QPushButton("📤 导出")
        self.export_btn.clicked.connect(self._export_keymap)
        layout.addWidget(self.export_btn)

        layout.addStretch()

        # 保存
        self.save_btn = QPushButton("💾 保存")
        self.save_btn.setStyleSheet("background-color: #7ec850; color: white;")
        self.save_btn.clicked.connect(self._save_keymap)
        layout.addWidget(self.save_btn)

        # 关闭
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        layout.addWidget(self.close_btn)

        return bar

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #007acc;
            }
            QCheckBox {
                color: #d4d4d4;
                font-size: 12px;
                spacing: 4px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #555;
                border-radius: 2px;
                background-color: #3c3c3c;
            }
            QCheckBox::indicator:checked {
                background-color: #007acc;
                border-color: #007acc;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0a4d7a;
            }
        """)

    # --------------------------------------------------------
    # 加载条目
    # --------------------------------------------------------
    def _load_entries(self):
        """从 ActionManager 加载条目"""
        entries = []

        try:
            for name, action in self.act_mgr.actions.items():
                if not action.text():
                    continue

                entry = KeymapEntry(
                    name=name,
                    text=action.text(),
                    category=self.act_mgr.categories.get(name, "其他"),
                    shortcut=action.shortcut().toString(),
                    default=self.act_mgr.defaults.get(name, ""),
                    description=self.act_mgr.descriptions.get(name, ""),
                )
                entries.append(entry)

            # 排序
            entries.sort(key=lambda e: (e.category, e.text))

            self._entries = entries

            # 检测冲突
            self._detect_conflicts()

            # 加载到表格
            self.table.load_entries(entries)

            # 更新状态
            self._update_status()

        except Exception as e:
            print(f"[KeymapEditor] 加载失败: {e}")
            QMessageBox.warning(self, "加载失败", str(e))

    # --------------------------------------------------------
    # 冲突检测
    # --------------------------------------------------------
    def _detect_conflicts(self):
        """检测快捷键冲突"""
        # 构建映射：快捷键 -> [动作名]
        shortcut_map: Dict[str, List[str]] = {}

        for entry in self._entries:
            if not entry.shortcut:
                continue
            shortcut_map.setdefault(entry.shortcut, []).append(entry.name)

        # 记录冲突
        self._conflicts = {sc: names for sc, names in shortcut_map.items() if len(names) > 1}

        # 更新每个条目的冲突信息
        for entry in self._entries:
            if entry.shortcut in self._conflicts:
                entry.conflicts = [n for n in self._conflicts[entry.shortcut] if n != entry.name]
            else:
                entry.conflicts = []

    # --------------------------------------------------------
    # 事件处理
    # --------------------------------------------------------
    def _on_shortcut_changed(self, action_name: str, new_shortcut: str):
        """快捷键变更"""
        # 更新 ActionManager
        if new_shortcut:
            try:
                self.act_mgr.set_shortcut(action_name, new_shortcut)
            except Exception:
                pass
        else:
            # 清除快捷键
            action = self.act_mgr.get(action_name)
            if action:
                action.setShortcut(QKeySequence())

        # 更新条目
        for entry in self._entries:
            if entry.name == action_name:
                entry.shortcut = new_shortcut
                break

        # 重新检测冲突
        self._detect_conflicts()

        # 刷新显示
        self.table.load_entries(self._entries)

        # 发射信号
        self.keymap_changed.emit(action_name, new_shortcut)

        # 更新状态
        self._update_status()

    def _on_search_changed(self, text: str):
        """搜索变化"""
        self.table.filter_entries(text)

    def _on_conflict_filter(self, checked: bool):
        """只看冲突"""
        if checked:
            # 过滤出冲突项
            self._filter_by_predicate(lambda e: e.has_conflict)
        else:
            self.table.filter_entries(self.search_edit.text())

    def _on_modified_filter(self, checked: bool):
        """只看已修改"""
        if checked:
            self._filter_by_predicate(lambda e: not e.is_default and e.shortcut)
        else:
            self.table.filter_entries(self.search_edit.text())

    def _filter_by_predicate(self, predicate: Callable[[KeymapEntry], bool]):
        """按条件过滤显示"""
        # 简单实现：直接重载表格
        filtered = [e for e in self._entries if predicate(e)]

        if not filtered:
            self.table.clear()
            empty_item = QTreeWidgetItem(self.table)
            empty_item.setText(0, "没有符合条件的项")
            empty_item.setForeground(0, QBrush(QColor("#888")))
            self.status_label.setText("0 项匹配")
            return

        self.table.load_entries(filtered)
        self.status_label.setText(f"{len(filtered)} 项匹配")

    def _update_status(self):
        """更新状态栏"""
        total = len(self._entries)
        conflicts = self.table.get_conflict_count()
        modified = self.table.get_modified_count()

        parts = [f"共 {total} 个命令"]

        if modified > 0:
            parts.append(f"{modified} 个已修改")

        if conflicts > 0:
            parts.append(f"⚠ {conflicts} 个冲突")

        self.status_label.setText(" · ".join(parts))

        # 冲突时变色
        if conflicts > 0:
            self.status_label.setStyleSheet(
                "color: #f14c4c; font-size: 11px; padding: 4px; font-weight: bold;"
            )
        else:
            self.status_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")

    # --------------------------------------------------------
    # 恢复默认
    # --------------------------------------------------------
    def _reset_to_defaults(self):
        """恢复默认快捷键"""
        reply = QMessageBox.question(
            self,
            "确认恢复默认",
            "确定要将所有快捷键恢复为默认值吗？\n\n此操作会覆盖你的自定义快捷键。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            # 恢复每个动作
            for entry in self._entries:
                action = self.act_mgr.get(entry.name)
                if action:
                    if entry.default:
                        action.setShortcut(QKeySequence(entry.default))
                    else:
                        action.setShortcut(QKeySequence())

                    entry.shortcut = entry.default

            # 重新加载
            self.table.load_entries(self._entries)
            self._detect_conflicts()
            self.table.load_entries(self._entries)

            # 更新状态
            self._update_status()

            # 发射信号
            self.keymap_reset.emit()

            # 提示
            bus.emit_status("已恢复默认快捷键", 2000, "success")

        except Exception as e:
            QMessageBox.warning(self, "恢复失败", str(e))

    # --------------------------------------------------------
    # 导入/导出
    # --------------------------------------------------------
    def _import_keymap(self):
        """导入快捷键配置"""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "导入快捷键配置", "", "JSON 文件 (*.json);;所有文件 (*.*)"
        )

        if not filepath:
            return

        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                QMessageBox.warning(self, "导入失败", "配置文件格式错误")
                return

            # 确认
            reply = QMessageBox.question(
                self,
                "确认导入",
                f"将导入 {len(data)} 个快捷键配置。\n\n是否覆盖当前设置？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )

            if reply != QMessageBox.Yes:
                return

            # 应用
            applied = 0
            for name, shortcut in data.items():
                action = self.act_mgr.get(name)
                if action:
                    try:
                        action.setShortcut(QKeySequence(shortcut))
                        applied += 1
                    except Exception:
                        pass

            # 刷新
            self._load_entries()

            QMessageBox.information(self, "导入成功", f"已导入 {applied} 个快捷键配置。")

        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))

    def _export_keymap(self):
        """导出快捷键配置"""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出快捷键配置", KEYBINDINGS_FILE, "JSON 文件 (*.json);;所有文件 (*.*)"
        )

        if not filepath:
            return

        try:
            # 收集所有非默认快捷键
            data = {}
            for entry in self._entries:
                if entry.shortcut and entry.shortcut != entry.default:
                    data[entry.name] = entry.shortcut

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)

            QMessageBox.information(self, "导出成功", f"已导出 {len(data)} 个自定义快捷键。")

        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    # --------------------------------------------------------
    # 保存
    # --------------------------------------------------------
    def _save_keymap(self):
        """保存快捷键配置到文件"""
        try:
            # 保存
            success = self.act_mgr.save_custom(KEYBINDINGS_FILE)

            if success:
                bus.emit_status("快捷键配置已保存", 2000, "success")
                QMessageBox.information(
                    self, "保存成功", f"快捷键已保存到 {KEYBINDINGS_FILE}。\n\n重启编辑器后生效。"
                )
            else:
                QMessageBox.warning(self, "保存失败", "无法写入配置文件")

        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    # --------------------------------------------------------
    # 调试
    # --------------------------------------------------------
    def dump(self) -> str:
        """导出编辑器信息"""
        lines = ["KeymapEditor", "=" * 60]
        lines.append(f"命令总数: {len(self._entries)}")
        lines.append(f"冲突数: {len(self._conflicts)}")
        lines.append(f"已修改: {self.table.get_modified_count()}")

        if self._conflicts:
            lines.append("")
            lines.append("冲突列表:")
            for shortcut, names in self._conflicts.items():
                lines.append(f"  {shortcut}: {', '.join(names)}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<KeymapEditor entries={len(self._entries)} conflicts={len(self._conflicts)}>"


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication, QMainWindow

    from app.actions import ActionManager, create_action

    app = QApplication(sys.argv)

    # 创建主窗口
    win = QMainWindow()
    win.setWindowTitle("KeymapEditor 测试")
    win.resize(900, 700)
    win.show()

    # 创建动作管理器
    mgr = ActionManager()

    def dummy():
        pass

    # 添加测试动作
    actions_data = [
        ("file.new", "新建文件", "Ctrl+N"),
        ("file.open", "打开文件", "Ctrl+O"),
        ("file.save", "保存文件", "Ctrl+S"),
        ("file.save_as", "另存为", "Ctrl+Shift+S"),
        ("file.close", "关闭", "Ctrl+W"),
        ("file.exit", "退出", "Ctrl+Q"),
        ("edit.undo", "撤销", "Ctrl+Z"),
        ("edit.redo", "重做", "Ctrl+Y"),
        ("edit.cut", "剪切", "Ctrl+X"),
        ("edit.copy", "复制", "Ctrl+C"),
        ("edit.paste", "粘贴", "Ctrl+V"),
        ("edit.find", "查找", "Ctrl+F"),
        ("edit.replace", "替换", "Ctrl+H"),
        ("edit.goto_line", "跳转到行", "Ctrl+G"),
        ("edit.toggle_comment", "注释切换", "Ctrl+/"),
        ("view.zoom_in", "放大", "Ctrl+="),
        ("view.zoom_out", "缩小", "Ctrl+-"),
        ("view.fullscreen", "全屏", "F11"),
        ("view.distraction_free", "无干扰模式", "Shift+F11"),
        ("tools.command_palette", "命令面板", "Ctrl+Shift+P"),
        ("tools.macro_record", "录制宏", "Ctrl+Shift+R"),
        ("tools.macro_play", "回放宏", "Ctrl+Shift+M"),
        ("help.about", "关于", "F1"),
    ]

    for name, text, shortcut in actions_data:
        create_action(win, name, text, shortcut, dummy, mgr)

    # 制造一个冲突
    create_action(win, "edit.duplicate", "复制行", "Ctrl+C", dummy, mgr)

    print(f"已注册 {len(mgr.actions)} 个动作")
    print()

    # 打开编辑器
    dlg = KeymapEditor(mgr)
    dlg.show()

    # 3 秒后打印信息
    from PyQt5.QtCore import QTimer

    def print_info():
        print("=== KeymapEditor 信息 ===")
        print(dlg.dump())
        print()

    QTimer.singleShot(3000, print_info)

    # 8 秒后退出
    QTimer.singleShot(8000, app.quit)

    sys.exit(app.exec())
