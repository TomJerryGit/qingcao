#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - 首选项面板
============================================================
- PreferencesDialog: 主对话框（左侧分类 + 右侧 StackedWidget）
- GeneralPage: 通用
- AppearancePage: 外观（主题）
- FontPage: 字体
- EditorPage: 编辑器
- AdvancedPage: 高级

用法：
    dlg = PreferencesDialog(main_window)
    dlg.exec_()
"""

import os
from typing import List, Optional

from PyQt5.QtCore import QSettings, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.preferences import Preferences


# ============================================================
# 分类页定义
# ============================================================
PAGES = [
    ("general", "通用", "⚙"),
    ("appearance", "外观", "🎨"),
    ("font", "字体", "🔤"),
    ("editor", "编辑器", "✏"),
    ("advanced", "高级", "🔧"),
]


# ============================================================
# 通用页
# ============================================================
class GeneralPage(QWidget):
    """通用设置"""

    def __init__(self, prefs: Preferences, parent=None):
        super().__init__(parent)
        self.prefs = prefs

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ---- 界面语言 ----
        lang_group = QGroupBox("界面语言")
        lang_layout = QFormLayout(lang_group)

        self.lang_combo = QComboBox()
        self.lang_combo.addItems([
            "简体中文 (zh_CN)",
            "English (en_US)",
            "日本語 (ja_JP)",
            "한국어 (ko_KR)",
        ])
        current = prefs.get("language", "zh_CN")
        idx = {'zh_CN': 0, 'en_US': 1, 'ja_JP': 2, 'ko_KR': 3}.get(current, 0)
        self.lang_combo.setCurrentIndex(idx)
        lang_layout.addRow("语言:", self.lang_combo)

        layout.addWidget(lang_group)

        # ---- 启动 ----
        startup_group = QGroupBox("启动")
        startup_layout = QVBoxLayout(startup_group)

        self.restore_session_cb = QCheckBox("恢复上次的会话")
        self.restore_session_cb.setChecked(
            prefs.get("restore_session", True)
        )
        startup_layout.addWidget(self.restore_session_cb)

        self.reopen_files_cb = QCheckBox("重新打开上次的文件")
        self.reopen_files_cb.setChecked(
            prefs.get("reopen_last_files", True)
        )
        startup_layout.addWidget(self.reopen_files_cb)

        self.splash_cb = QCheckBox("显示启动画面")
        self.splash_cb.setChecked(prefs.get("splash_screen", True))
        startup_layout.addWidget(self.splash_cb)

        # P7 接线：splash_duration 此前是"有默认值、无 UI、零读取"的
        # 假开关。现在 main.py 会用它保证启动画面的最小可见时长，
        # 这里补上对应的界面项。
        splash_dur_row = QHBoxLayout()
        splash_dur_row.addSpacing(20)
        splash_dur_row.addWidget(QLabel("显示时长:"))
        self.splash_duration_spin = QSpinBox()
        self.splash_duration_spin.setRange(0, 5000)
        self.splash_duration_spin.setSingleStep(100)
        self.splash_duration_spin.setSuffix(" ms")
        self.splash_duration_spin.setValue(
            prefs.get("splash_duration", 800)
        )
        self.splash_duration_spin.setEnabled(self.splash_cb.isChecked())
        self.splash_cb.toggled.connect(
            self.splash_duration_spin.setEnabled
        )
        splash_dur_row.addWidget(self.splash_duration_spin)
        splash_dur_row.addStretch()
        startup_layout.addLayout(splash_dur_row)

        layout.addWidget(startup_group)

        # ---- 更新 ----
        update_group = QGroupBox("更新")
        update_layout = QVBoxLayout(update_group)

        self.check_update_cb = QCheckBox("自动检查更新")
        self.check_update_cb.setChecked(prefs.get("check_update", True))
        update_layout.addWidget(self.check_update_cb)

        self.telemetry_cb = QCheckBox("发送匿名使用统计")
        self.telemetry_cb.setChecked(prefs.get("telemetry", False))
        update_layout.addWidget(self.telemetry_cb)

        layout.addWidget(update_group)
        layout.addStretch()

    def apply(self):
        """保存设置"""
        langs = ['zh_CN', 'en_US', 'ja_JP', 'ko_KR']
        self.prefs.set("language",
                       langs[self.lang_combo.currentIndex()])
        self.prefs.set("restore_session",
                       self.restore_session_cb.isChecked())
        self.prefs.set("reopen_last_files",
                       self.reopen_files_cb.isChecked())
        self.prefs.set("splash_screen", self.splash_cb.isChecked())
        self.prefs.set("splash_duration",
                       self.splash_duration_spin.value())
        self.prefs.set("check_update", self.check_update_cb.isChecked())
        self.prefs.set("telemetry", self.telemetry_cb.isChecked())


# ============================================================
# 外观页
# ============================================================
class AppearancePage(QWidget):
    """外观设置（主题）"""

    theme_changed = pyqtSignal(str)   # 主题路径

    def __init__(self, prefs: Preferences, main_window=None, parent=None):
        super().__init__(parent)
        self.prefs = prefs
        self.main_window = main_window

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ---- 主题 ----
        theme_group = QGroupBox("主题")
        theme_layout = QVBoxLayout(theme_group)

        # 主题选择行
        pick_row = QHBoxLayout()

        pick_row.addWidget(QLabel("当前主题:"))
        self.theme_combo = QComboBox()
        self.theme_combo.setMinimumWidth(200)
        self._load_theme_list()
        self.theme_combo.currentIndexChanged.connect(
            self._on_theme_selected
        )
        pick_row.addWidget(self.theme_combo, 1)

        edit_btn = QPushButton("✏ 编辑")
        edit_btn.clicked.connect(self._on_edit_theme)
        pick_row.addWidget(edit_btn)

        market_btn = QPushButton("🎨 市场")
        market_btn.clicked.connect(self._on_market)
        pick_row.addWidget(market_btn)

        open_dir_btn = QPushButton("📁 目录")
        open_dir_btn.clicked.connect(self._on_open_dir)
        pick_row.addWidget(open_dir_btn)

        theme_layout.addLayout(pick_row)

        # 跟随系统
        self.follow_system_cb = QCheckBox("跟随系统主题")
        self.follow_system_cb.setChecked(
            prefs.get("theme_follow_system", True)
        )
        theme_layout.addWidget(self.follow_system_cb)

        # 主题预览
        preview_label = QLabel("预览:")
        theme_layout.addWidget(preview_label)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(140)
        self.preview.setPlainText(
            "# 示例代码\n"
            "def hello(name):\n"
            "    \"\"\"打招呼\"\"\"\n"
            "    message = f'Hello, {name}!'\n"
            "    print(message)  # 输出\n"
            "    return True\n\n"
            "class Greeter:\n"
            "    def __init__(self):\n"
            "        self.count = 0\n"
        )
        theme_layout.addWidget(self.preview)

        layout.addWidget(theme_group)

        # ---- 界面元素 ----
        ui_group = QGroupBox("界面元素")
        ui_layout = QVBoxLayout(ui_group)

        self.show_toolbar_cb = QCheckBox("显示工具栏")
        self.show_toolbar_cb.setChecked(prefs.get("toolbar_visible", True))
        ui_layout.addWidget(self.show_toolbar_cb)

        self.show_statusbar_cb = QCheckBox("显示状态栏")
        self.show_statusbar_cb.setChecked(
            prefs.get("statusbar_visible", True)
        )
        ui_layout.addWidget(self.show_statusbar_cb)

        self.show_menubar_cb = QCheckBox("显示菜单栏")
        self.show_menubar_cb.setChecked(prefs.get("menubar_visible", True))
        ui_layout.addWidget(self.show_menubar_cb)

        layout.addWidget(ui_group)
        layout.addStretch()

        # 初始预览
        self._refresh_preview()

    def _load_theme_list(self):
        """扫描 themes/ 目录"""
        self.theme_combo.clear()

        # 跟随系统
        self.theme_combo.addItem("跟随系统", "__system__")

        # 扫描目录
        themes_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "themes"
        )
        current_theme = self.prefs.get("theme_name", "")

        if os.path.isdir(themes_dir):
            for f in sorted(os.listdir(themes_dir)):
                if f.endswith('.json'):
                    name = os.path.splitext(f)[0]
                    self.theme_combo.addItem(name, name)
                    if name == current_theme:
                        self.theme_combo.setCurrentIndex(
                            self.theme_combo.count() - 1
                        )

    def _on_theme_selected(self, index: int):
        name = self.theme_combo.currentData()
        if not name:
            return
        self.prefs.set("theme_name", name)
        self.theme_changed.emit(name)
        self._refresh_preview()

    def _refresh_preview(self):
        """刷新预览区"""
        try:
            from infrastructure.theme_loader import ThemeLoader
            loader = ThemeLoader()
            name = self.theme_combo.currentData()
            if name == "__system__":
                # 用默认主题预览
                theme = loader.load_by_name("dark_night")
            else:
                theme = loader.load_by_name(name)

            if theme:
                c = theme.colors
                # 用内联样式模拟主题
                self.preview.setStyleSheet(f"""
                    QTextEdit {{
                        background-color: {c.background};
                        color: {c.foreground};
                        border: 1px solid {c.border};
                        font-family: {theme.font_family};
                        font-size: {theme.font_size}pt;
                        padding: 8px;
                    }}
                """)
        except Exception as e:
            print(f"[AppearancePage] 预览失败: {e}")

    def _on_edit_theme(self):
        """打开主题编辑器"""
        try:
            from ui.theme_editor import ThemeEditor
            dlg = ThemeEditor(self)
            dlg.exec_()
            # 编辑后刷新列表
            self._load_theme_list()
            self._refresh_preview()
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))

    def _on_market(self):
        """打开主题市场"""
        try:
            from ui.theme_market import ThemeMarketDialog
            dlg = ThemeMarketDialog(self.main_window, self)
            dlg.theme_installed.connect(
                lambda name: self._load_theme_list()
            )
            dlg.theme_deleted.connect(
                lambda name: self._load_theme_list()
            )
            dlg.exec_()
            self._load_theme_list()
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))

    def _on_open_dir(self):
        """打开主题目录"""
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QDesktopServices
        themes_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "themes"
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(themes_dir))

    def apply(self):
        """保存设置"""
        self.prefs.set("theme_follow_system",
                       self.follow_system_cb.isChecked())
        self.prefs.set("toolbar_visible",
                       self.show_toolbar_cb.isChecked())
        self.prefs.set("statusbar_visible",
                       self.show_statusbar_cb.isChecked())
        self.prefs.set("menubar_visible",
                       self.show_menubar_cb.isChecked())


# ============================================================
# 字体页
# ============================================================
class FontPage(QWidget):
    """字体设置"""

    def __init__(self, prefs: Preferences, parent=None):
        super().__init__(parent)
        self.prefs = prefs

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form = QFormLayout()

        # 字体族
        self.family_combo = QFontComboBox()
        self.family_combo.setCurrentFont(
            QFont(prefs.get("font_family", "Consolas"))
        )
        self.family_combo.currentFontChanged.connect(self._update_preview)
        form.addRow("字体:", self.family_combo)

        # 字号
        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 72)
        self.size_spin.setValue(prefs.get("font_size", 12))
        self.size_spin.setSuffix(" pt")
        self.size_spin.valueChanged.connect(self._update_preview)
        form.addRow("字号:", self.size_spin)

        # 中文回退字体
        self.alt_combo = QFontComboBox()
        self.alt_combo.setCurrentFont(
            QFont(prefs.get("font_family_alt", "Microsoft YaHei"))
        )
        form.addRow("中文回退:", self.alt_combo)

        # 连字
        self.ligatures_cb = QCheckBox("启用字体连字")
        self.ligatures_cb.setChecked(prefs.get("font_ligatures", False))
        form.addRow("", self.ligatures_cb)

        layout.addLayout(form)

        # 预览
        preview_group = QGroupBox("预览")
        preview_layout = QVBoxLayout(preview_group)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(160)
        self.preview.setPlainText(
            "def hello(name):\n"
            "    \"\"\"打招呼\"\"\"\n"
            "    print(f'Hello, {name}!')\n"
            "    return 0\n"
        )
        preview_layout.addWidget(self.preview)

        layout.addWidget(preview_group)
        layout.addStretch()

        self._update_preview()

    def _update_preview(self):
        font = QFont(self.family_combo.currentFont())
        font.setPointSize(self.size_spin.value())
        self.preview.setFont(font)

    def apply(self):
        self.prefs.set("font_family",
                       self.family_combo.currentFont().family())
        self.prefs.set("font_size", self.size_spin.value())
        self.prefs.set("font_family_alt",
                       self.alt_combo.currentFont().family())
        self.prefs.set("font_ligatures", self.ligatures_cb.isChecked())


# ============================================================
# 编辑器页
# ============================================================
class EditorPage(QWidget):
    """编辑器设置"""

    def __init__(self, prefs: Preferences, parent=None):
        super().__init__(parent)
        self.prefs = prefs

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 缩进
        indent_group = QGroupBox("缩进")
        indent_form = QFormLayout(indent_group)

        self.tab_width_spin = QSpinBox()
        self.tab_width_spin.setRange(1, 16)
        self.tab_width_spin.setValue(prefs.get("tab_width", 4))
        indent_form.addRow("Tab 宽度:", self.tab_width_spin)

        self.use_tabs_cb = QCheckBox("使用 Tab 字符缩进")
        self.use_tabs_cb.setChecked(prefs.get("indent_use_tabs", False))
        indent_form.addRow("", self.use_tabs_cb)

        self.auto_indent_cb = QCheckBox("自动缩进")
        self.auto_indent_cb.setChecked(prefs.get("indent_auto", True))
        indent_form.addRow("", self.auto_indent_cb)

        self.indent_guides_cb = QCheckBox("显示缩进辅助线")
        self.indent_guides_cb.setChecked(
            prefs.get("indent_guides", True)
        )
        indent_form.addRow("", self.indent_guides_cb)

        self.rainbow_cb = QCheckBox("缩进彩虹线")
        self.rainbow_cb.setChecked(prefs.get("indent_rainbow", False))
        indent_form.addRow("", self.rainbow_cb)

        layout.addWidget(indent_group)

        # 编辑
        edit_group = QGroupBox("编辑")
        edit_layout = QVBoxLayout(edit_group)

        self.line_numbers_cb = QCheckBox("显示行号")
        self.line_numbers_cb.setChecked(
            prefs.get("show_line_numbers", True)
        )
        edit_layout.addWidget(self.line_numbers_cb)

        self.folding_cb = QCheckBox("启用代码折叠")
        self.folding_cb.setChecked(prefs.get("show_folding", True))
        edit_layout.addWidget(self.folding_cb)

        self.current_line_cb = QCheckBox("高亮当前行")
        self.current_line_cb.setChecked(
            prefs.get("show_current_line", True)
        )
        edit_layout.addWidget(self.current_line_cb)

        self.auto_close_cb = QCheckBox("自动闭合括号和引号")
        self.auto_close_cb.setChecked(
            prefs.get("auto_close_brackets", True)
        )
        edit_layout.addWidget(self.auto_close_cb)

        self.trim_ws_cb = QCheckBox("保存时清理行尾空白")
        self.trim_ws_cb.setChecked(
            prefs.get("trim_trailing_whitespace", True)
        )
        edit_layout.addWidget(self.trim_ws_cb)

        layout.addWidget(edit_group)

        # 保存
        save_group = QGroupBox("保存")
        save_layout = QVBoxLayout(save_group)

        self.auto_save_cb = QCheckBox("启用自动保存")
        self.auto_save_cb.setChecked(prefs.get("auto_save", False))
        save_layout.addWidget(self.auto_save_cb)

        self.trim_final_cb = QCheckBox("保存时确保末尾换行")
        self.trim_final_cb.setChecked(
            prefs.get("insert_final_newline", True)
        )
        save_layout.addWidget(self.trim_final_cb)

        layout.addWidget(save_group)
        layout.addStretch()

    def apply(self):
        self.prefs.set("tab_width", self.tab_width_spin.value())
        self.prefs.set("indent_use_tabs", self.use_tabs_cb.isChecked())
        self.prefs.set("indent_auto", self.auto_indent_cb.isChecked())
        self.prefs.set("indent_guides", self.indent_guides_cb.isChecked())
        self.prefs.set("indent_rainbow", self.rainbow_cb.isChecked())

        self.prefs.set("show_line_numbers",
                       self.line_numbers_cb.isChecked())
        self.prefs.set("show_folding", self.folding_cb.isChecked())
        self.prefs.set("show_current_line",
                       self.current_line_cb.isChecked())
        self.prefs.set("auto_close_brackets",
                       self.auto_close_cb.isChecked())
        self.prefs.set("trim_trailing_whitespace",
                       self.trim_ws_cb.isChecked())

        self.prefs.set("auto_save", self.auto_save_cb.isChecked())
        self.prefs.set("insert_final_newline",
                       self.trim_final_cb.isChecked())


# ============================================================
# 高级页
# ============================================================
class AdvancedPage(QWidget):
    """高级设置"""

    def __init__(self, prefs: Preferences, parent=None):
        super().__init__(parent)
        self.prefs = prefs

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        debug_group = QGroupBox("调试")
        debug_layout = QVBoxLayout(debug_group)

        self.debug_cb = QCheckBox("启用调试模式")
        self.debug_cb.setChecked(prefs.get("debug_mode", False))
        debug_layout.addWidget(self.debug_cb)

        self.log_file_cb = QCheckBox("输出日志到文件")
        self.log_file_cb.setChecked(prefs.get("log_to_file", True))
        debug_layout.addWidget(self.log_file_cb)

        layout.addWidget(debug_group)

        # 便携模式
        portable_group = QGroupBox("便携模式")
        portable_layout = QVBoxLayout(portable_group)

        self.portable_cb = QCheckBox("启用便携模式")
        self.portable_cb.setChecked(prefs.get("portable_mode", False))
        self.portable_cb.setToolTip(
            "启用后，配置存储在程序目录而非用户目录"
        )
        portable_layout.addWidget(self.portable_cb)

        hint = QLabel(
            "提示：便携模式需要重启编辑器生效。\n"
            "也可在程序目录创建 portable.txt 文件。"
        )
        hint.setStyleSheet("color: #888; font-size: 11px;")
        portable_layout.addWidget(hint)

        layout.addWidget(portable_group)

        # 重置按钮
        reset_btn = QPushButton("🔄 恢复所有设置为默认")
        reset_btn.setStyleSheet(
            "background-color: #8f1e1e; color: white;"
        )
        reset_btn.clicked.connect(self._on_reset_all)
        layout.addWidget(reset_btn)

        layout.addStretch()

    def _on_reset_all(self):
        reply = QMessageBox.question(
            self, "确认",
            "确定要将所有设置恢复为默认值吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.prefs.reset_to_defaults()
            QMessageBox.information(self, "完成", "已恢复默认设置")

    def apply(self):
        self.prefs.set("debug_mode", self.debug_cb.isChecked())
        self.prefs.set("log_to_file", self.log_file_cb.isChecked())
        self.prefs.set("portable_mode", self.portable_cb.isChecked())


# ============================================================
# 主对话框
# ============================================================
class PreferencesDialog(QDialog):
    """首选项主对话框"""

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.setWindowTitle("首选项")
        self.resize(820, 600)

        self.prefs = Preferences() if main_window is None \
            else getattr(main_window, 'prefs', None) or Preferences()

        # 页面实例
        self.pages = {}

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 左侧分类
        left = QWidget()
        left.setFixedWidth(160)
        left.setStyleSheet("background-color: #252526;")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 8, 4, 8)

        self.category_list = QListWidget()
        self.category_list.setObjectName("prefs_category_list")
        for key, name, icon in PAGES:
            item = QListWidgetItem(f"  {icon}  {name}")
            item.setData(Qt.UserRole, key)
            self.category_list.addItem(item)

        self.category_list.currentRowChanged.connect(self._on_category_changed)
        # 注：setCurrentRow(0) 挪到 _build_ui 末尾（stack 创建之后），
        # 否则会在 self.stack 创建前触发 _on_category_changed

        left_layout.addWidget(self.category_list)
        left_layout.addStretch()
        layout.addWidget(left)

        # 中间分隔
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("background-color: #3c3c3c;")
        layout.addWidget(sep)

        # 右侧内容
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 顶部标题
        self.title_label = QLabel("通用")
        self.title_label.setObjectName("prefs_title")
        self.title_label.setFixedHeight(40)
        right_layout.addWidget(self.title_label)

        # 内容区（滚动）
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.stack = QStackedWidget()
        self._create_pages()
        self.scroll.setWidget(self.stack)

        right_layout.addWidget(self.scroll, 1)

        # 底部按钮
        bottom = QWidget()
        bottom.setStyleSheet(
            "background-color: #252526; border-top: 1px solid #3c3c3c;"
        )
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(12, 8, 12, 8)

        bottom_layout.addStretch()

        ok_btn = QPushButton("确定")
        ok_btn.setStyleSheet(
            "background-color: #0e639c; color: white;"
        )
        ok_btn.clicked.connect(self._on_accept)
        bottom_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(cancel_btn)

        apply_btn = QPushButton("应用")
        apply_btn.clicked.connect(self._apply_all)
        bottom_layout.addWidget(apply_btn)

        right_layout.addWidget(bottom)
        layout.addWidget(right, 1)

        # 全部控件建好后再设置默认选中分类
        self.category_list.setCurrentRow(0)

    def _create_pages(self):
        """创建所有分类页"""
        p = self.prefs

        general = GeneralPage(p)
        appearance = AppearancePage(p, self.main_window)
        font = FontPage(p)
        editor = EditorPage(p)
        advanced = AdvancedPage(p)

        # 连接外观页的主题变更信号
        appearance.theme_changed.connect(self._on_theme_changed)

        self.pages = {
            'general': general,
            'appearance': appearance,
            'font': font,
            'editor': editor,
            'advanced': advanced,
        }

        for key, _, _ in PAGES:
            self.stack.addWidget(self.pages[key])

    def _on_category_changed(self, index: int):
        # 保护：_build_ui 早期 setCurrentRow(0) 时 stack 尚未创建
        if not hasattr(self, 'stack') or self.stack is None:
            return
        if index < 0 or index >= len(PAGES):
            return
        key, name, _ = PAGES[index]
        self.stack.setCurrentIndex(index)
        self.title_label.setText(f"  {name}")

    def _on_theme_changed(self, theme_name: str):
        """主题切换：实时应用到编辑器"""
        if not self.main_window:
            return
        try:
            from infrastructure.theme_loader import ThemeLoader
            loader = ThemeLoader()

            if theme_name == "__system__":
                loader.apply_system_theme(
                    QApplication.instance(),
                    self.main_window.tabs.currentWidget()
                )
                return

            theme = loader.load_by_name(theme_name)
            if not theme:
                return

            for i in range(self.main_window.tabs.count()):
                loader.apply(self.main_window.tabs.widget(i), theme)
            if theme.qss:
                self.main_window.setStyleSheet(theme.qss)
        except Exception as e:
            print(f"[PreferencesDialog] 应用主题失败: {e}")

    def _apply_all(self):
        """应用所有页面的设置"""
        for page in self.pages.values():
            try:
                page.apply()
            except Exception as e:
                print(f"[PreferencesDialog] 保存失败: {e}")

        # 同步到磁盘
        self.prefs.sync()

        # 应用到主窗口
        if self.main_window:
            try:
                for i in range(self.main_window.tabs.count()):
                    editor = self.main_window.tabs.widget(i)
                    if hasattr(editor, 'apply_preferences'):
                        editor.apply_preferences()
            except Exception as e:
                print(f"[PreferencesDialog] 应用失败: {e}")

    def _on_accept(self):
        self._apply_all()
        self.accept()

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; }
            QLabel#prefs_title {
                font-size: 14px;
                font-weight: bold;
                color: #7ec850;
                padding: 10px;
                background-color: #2d2d2d;
                border-bottom: 1px solid #3c3c3c;
            }
            QListWidget#prefs_category_list {
                background-color: #252526;
                color: #d4d4d4;
                border: none;
                outline: none;
                font-size: 12px;
            }
            QListWidget#prefs_category_list::item {
                padding: 8px 10px;
                border-radius: 3px;
                margin: 2px 4px;
            }
            QListWidget#prefs_category_list::item:hover {
                background-color: #2a2d2e;
            }
            QListWidget#prefs_category_list::item:selected {
                background-color: #094771;
                color: white;
            }
            QGroupBox {
                color: #7ec850;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 8px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QComboBox, QSpinBox, QFontComboBox, QLineEdit {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QComboBox:focus, QSpinBox:focus, QFontComboBox:focus {
                border-color: #007acc;
            }
            QCheckBox { color: #d4d4d4; padding: 4px; }
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                font-family: Consolas, monospace;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 16px;
                font-size: 12px;
                min-width: 70px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QScrollArea { background-color: #1e1e1e; border: none; }
        """)