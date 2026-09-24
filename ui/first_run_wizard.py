# -*- coding: utf-8 -*-
"""首次启动向导"""
import os
from PyQt5.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout, QLabel,
    QRadioButton, QButtonGroup, QComboBox, QSpinBox, QCheckBox,
    QGroupBox, QFormLayout, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QFont


class WelcomePage(QWizardPage):
    """欢迎页"""

    def __init__(self):
        super().__init__()
        self.setTitle("欢迎使用青草编辑器")
        self.setSubTitle("青草枯荣，野火重生。")

        layout = QVBoxLayout(self)

        # Logo
        logo = QLabel("??")
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("font-size: 64px;")
        layout.addWidget(logo)

        # 说明
        desc = QLabel(
            "感谢您使用青草编辑器！\n\n"
            "本向导将帮助您完成初始配置，只需 1 分钟。\n"
            "所有设置都可以在之后随时修改。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 13px; color: #555; padding: 20px;")
        layout.addWidget(desc)

        layout.addStretch()


class LanguagePage(QWizardPage):
    """语言选择页"""

    def __init__(self):
        super().__init__()
        self.setTitle("选择界面语言")
        self.setSubTitle("选择您偏好的界面语言。")

        layout = QVBoxLayout(self)

        group = QGroupBox("语言")
        group_layout = QVBoxLayout(group)

        self.lang_group = QButtonGroup(self)

        languages = [
            ("简体中文", "zh_CN"),
            ("English", "en_US"),
            ("日本語", "ja_JP"),
            ("???", "ko_KR"),
        ]

        for i, (name, code) in enumerate(languages):
            radio = QRadioButton(name)
            radio.setProperty("code", code)
            self.lang_group.addButton(radio, i)
            group_layout.addWidget(radio)
            if i == 0:
                radio.setChecked(True)

        layout.addWidget(group)
        layout.addStretch()

    def get_language(self):
        btn = self.lang_group.checkedButton()
        return btn.property("code") if btn else "zh_CN"


class ThemePage(QWizardPage):
    """主题选择页"""

    def __init__(self):
        super().__init__()
        self.setTitle("选择主题")
        self.setSubTitle("选择您喜欢的配色方案。")

        layout = QVBoxLayout(self)

        group = QGroupBox("主题")
        group_layout = QVBoxLayout(group)

        self.theme_group = QButtonGroup(self)

        themes = [
            ("dark_night", "?? 暗夜", "深色主题，适合夜间使用"),
            ("light_clean", "? 晨曦", "浅色主题，适合白天使用"),
            ("eye_protect", "?? 护眼", "绿色主题，减少眼睛疲劳"),
            ("high_contrast", "? 高对比度", "极高对比度，适合视力较弱用户"),
        ]

        for i, (code, name, desc) in enumerate(themes):
            radio = QRadioButton(f"{name} - {desc}")
            radio.setProperty("code", code)
            self.theme_group.addButton(radio, i)
            group_layout.addWidget(radio)
            if i == 0:
                radio.setChecked(True)

        layout.addWidget(group)
        layout.addStretch()

    def get_theme(self):
        btn = self.theme_group.checkedButton()
        return btn.property("code") if btn else "dark_night"


class FontPage(QWizardPage):
    """字体选择页"""

    def __init__(self):
        super().__init__()
        self.setTitle("选择字体")
        self.setSubTitle("选择编辑器字体和字号。")

        layout = QFormLayout(self)

        # 字体
        self.font_combo = QComboBox()
        fonts = ["Consolas", "Fira Code", "JetBrains Mono",
                 "Cascadia Code", "Source Code Pro",
                 "Microsoft YaHei Mono", "Courier New"]
        self.font_combo.addItems(fonts)
        layout.addRow("字体:", self.font_combo)

        # 字号
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 32)
        self.font_size.setValue(12)
        self.font_size.setSuffix(" pt")
        layout.addRow("字号:", self.font_size)

        # 预览
        preview_group = QGroupBox("预览")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_label = QLabel(
            'def hello():\n'
            '    print("Hello, 青草！")\n'
            '    return 42'
        )
        self.preview_label.setFont(QFont("Consolas", 12))
        self.preview_label.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; "
            "padding: 10px; border-radius: 4px;"
        )
        preview_layout.addWidget(self.preview_label)
        layout.addRow(preview_group)

        # 连接信号更新预览
        self.font_combo.currentTextChanged.connect(self._update_preview)
        self.font_size.valueChanged.connect(self._update_preview)

    def _update_preview(self):
        font = QFont(self.font_combo.currentText(),
                     self.font_size.value())
        self.preview_label.setFont(font)

    def get_font_family(self):
        return self.font_combo.currentText()

    def get_font_size(self):
        return self.font_size.value()


class KeymapPage(QWizardPage):
    """快捷键方案选择页"""

    def __init__(self):
        super().__init__()
        self.setTitle("快捷键方案")
        self.setSubTitle("选择快捷键布局。")

        layout = QVBoxLayout(self)

        group = QGroupBox("方案")
        group_layout = QVBoxLayout(group)

        self.keymap_group = QButtonGroup(self)

        schemes = [
            ("default", "青草默认", "默认的快捷键布局"),
            ("vscode", "VSCode 兼容", "使用 VSCode 风格的快捷键"),
            ("sublime", "Sublime Text 兼容", "使用 Sublime 风格的快捷键"),
            ("vim", "Vim 模式", "使用 Vim 风格的操作"),
        ]

        for i, (code, name, desc) in enumerate(schemes):
            radio = QRadioButton(f"{name} - {desc}")
            radio.setProperty("code", code)
            self.keymap_group.addButton(radio, i)
            group_layout.addWidget(radio)
            if i == 0:
                radio.setChecked(True)

        layout.addWidget(group)
        layout.addStretch()

    def get_scheme(self):
        btn = self.keymap_group.checkedButton()
        return btn.property("code") if btn else "default"


class FinishPage(QWizardPage):
    """完成页"""

    def __init__(self):
        super().__init__()
        self.setTitle("设置完成")
        self.setSubTitle("点击\"完成\"开始使用。")

        layout = QVBoxLayout(self)

        info = QLabel(
            "所有设置都可以在\"工具 → 首选项\"中修改。\n\n"
            "快速上手：\n"
            "  ? Ctrl+Shift+P 打开命令面板\n"
            "  ? Ctrl+P 快速打开文件\n"
            "  ? Ctrl+Shift+F 全局搜索\n"
            "  ? F11 无干扰模式\n\n"
            "青草枯荣，野火重生。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 13px; line-height: 1.8;")
        layout.addWidget(info)

        self.auto_update_cb = QCheckBox("启用自动检查更新")
        self.auto_update_cb.setChecked(True)
        layout.addWidget(self.auto_update_cb)

        self.telemetry_cb = QCheckBox("发送匿名使用统计（帮助改进）")
        self.telemetry_cb.setChecked(False)
        layout.addWidget(self.telemetry_cb)

        layout.addStretch()

    def is_auto_update(self):
        return self.auto_update_cb.isChecked()

    def is_telemetry(self):
        return self.telemetry_cb.isChecked()


class FirstRunWizard(QWizard):
    """首次启动向导"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("青草编辑器 - 首次启动向导")
        self.resize(600, 500)
        self.setWizardStyle(QWizard.ModernStyle)

        # 添加页面
        self.welcome_page = WelcomePage()
        self.language_page = LanguagePage()
        self.theme_page = ThemePage()
        self.font_page = FontPage()
        self.keymap_page = KeymapPage()
        self.finish_page = FinishPage()

        self.addPage(self.welcome_page)
        self.addPage(self.language_page)
        self.addPage(self.theme_page)
        self.addPage(self.font_page)
        self.addPage(self.keymap_page)
        self.addPage(self.finish_page)

        # 样式
        self.setStyleSheet("""
            QWizard { background-color: #1e1e1e; color: #d4d4d4; }
            QWizardPage { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; }
            QGroupBox { color: #d4d4d4; border: 1px solid #3c3c3c;
                        border-radius: 4px; margin-top: 8px; padding-top: 8px; }
            QGroupBox::title { color: #7ec850; }
            QRadioButton { color: #d4d4d4; padding: 4px; }
            QCheckBox { color: #d4d4d4; padding: 4px; }
            QComboBox, QSpinBox {
                background-color: #3c3c3c; color: #d4d4d4;
                border: 1px solid #555; border-radius: 3px; padding: 4px;
            }
            QPushButton {
                background-color: #0e639c; color: white;
                border: none; border-radius: 3px; padding: 6px 16px;
                min-width: 80px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:disabled { background-color: #3c3c3c; color: #666; }
        """)


def should_show_wizard():
    """检查是否需要显示向导"""
    settings = QSettings("QingCao", "Editor")
    return not settings.value("first_run_completed", False, type=bool)


def mark_wizard_completed():
    """标记向导已完成"""
    settings = QSettings("QingCao", "Editor")
    settings.setValue("first_run_completed", True)
    settings.sync()


def apply_wizard_settings(wizard):
    """应用向导设置"""
    from app.preferences import Preferences

    prefs = Preferences()

    # 语言
    prefs.set("language", wizard.language_page.get_language())

    # 主题
    prefs.set("theme_name", wizard.theme_page.get_theme())

    # 字体
    prefs.set("font_family", wizard.font_page.get_font_family())
    prefs.set("font_size", wizard.font_page.get_font_size())

    # 快捷键方案
    prefs.set("keymap_scheme", wizard.keymap_page.get_scheme())

    # 高级选项
    prefs.set("check_update", wizard.finish_page.is_auto_update())
    prefs.set("telemetry", wizard.finish_page.is_telemetry())

    prefs.sync()