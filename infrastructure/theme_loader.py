#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为主题加载器模块，包含：
- ThemeLoader：主题加载器（JSON 加载、应用、导出）
- Theme：主题数据类
- ThemeColors：配色方案数据类
- ThemeManager：主题管理器（多主题管理）
- 主题目录扫描与发现
- 内置主题（暗夜/晨曦/护眼/高对比度）
- Scintilla 样式应用
- 全局 QSS 样式应用
- 跟随系统主题
- 主题切换与信号
- 主题导入/导出
- 主题校验与版本兼容
- 主题缓存
- 主题市场集成
"""

import datetime
import json
import os
import re
import sys
import time
import weakref
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.Qsci import QsciScintilla
from PyQt5.QtCore import QEvent, QObject, QSettings, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPalette
from PyQt5.QtWidgets import QApplication, QWidget


# ============================================================
# 常量
# ============================================================
# 主题文件格式版本
THEME_FORMAT_VERSION = 2

# 主题目录
#
# 注意（打包相关，踩过坑）：
#   这是**相对路径**，依赖当前工作目录。开发时 cwd=仓库根目录，能找到
#   themes/*.json；但打包后 themes/ 被 PyInstaller 放进 `_internal/themes`，
#   exe 同级只有一个空的 themes/（留给用户自定义主题），于是
#   `os.path.exists("themes/eye_protect.json")` 为假 ——
#   **JSON 主题永远不会被加载**，静默回退到内置定义（见下面的
#   `resolve_theme_dirs`）。这正是"护眼主题文字看不见"的根因之一。
DEFAULT_THEME_DIR = "themes"


def resolve_theme_dirs(primary: str = DEFAULT_THEME_DIR) -> List[str]:
    """返回按优先级排列的主题搜索目录

    顺序：
      1. 传入目录（通常是 "themes"，即用户自定义主题所在）
      2. 冻结运行时的内置目录 `_internal/themes`
      3. 源码运行时的仓库目录 `<仓库根>/themes`
      4. exe / 脚本所在目录下的 themes

    为什么要多目录：用户自定义主题应优先于内置主题，而内置主题在
    打包后位于 `_internal`。只查单一相对路径必然在某一种运行方式下失效。
    """
    dirs: List[str] = []

    def add(p: str):
        if p and p not in dirs:
            dirs.append(p)

    add(primary)

    # 冻结运行：主题随 datas 打到 _internal/themes
    if getattr(sys, "frozen", False):
        try:
            add(os.path.join(sys._MEIPASS, "themes"))
        except Exception:
            pass
        try:
            add(os.path.join(
                os.path.dirname(os.path.abspath(sys.executable)),
                "_internal", "themes"))
        except Exception:
            pass

    # 源码运行：<仓库根>/themes（本文件在 infrastructure/ 下）
    try:
        add(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "themes"))
    except Exception:
        pass

    # 兜底：exe / 脚本同级
    try:
        add(os.path.join(
            os.path.dirname(os.path.abspath(sys.executable)), "themes"))
    except Exception:
        pass

    return dirs


def find_theme_file(name: str, primary: str = DEFAULT_THEME_DIR,
                    ) -> Optional[str]:
    """按名称在候选目录中查找主题 JSON，返回绝对路径或 None"""
    fname = name if name.endswith(".json") else "%s.json" % name
    for d in resolve_theme_dirs(primary):
        p = os.path.join(d, fname)
        if os.path.isfile(p):
            return p
    return None

# 内置主题文件名
BUILTIN_THEMES = {
    "dark_night": "暗夜",
    "light_clean": "晨曦",
    "eye_protect": "护眼",
    "high_contrast": "高对比度",
}

# Scintilla 样式索引（标准映射）
SCI_STYLE_DEFAULT = 32
SCI_STYLE_LINENUMBER = 33
SCI_STYLE_BRACELIGHT = 34
SCI_STYLE_BRACEBAD = 35
SCI_STYLE_CONTROLCHAR = 36
SCI_STYLE_INDENTGUIDE = 37
SCI_STYLE_CALLTIP = 38
SCI_STYLE_FOLDDISPLAYTEXT = 39
SCI_STYLE_LASTPREDEFINED = 39
SCI_STYLE_MAX = 255

# 常用语言样式索引（以 Python 为例）
PY_STYLE_DEFAULT = 0
PY_STYLE_COMMENT = 1
PY_STYLE_NUMBER = 2
PY_STYLE_STRING = 3
PY_STYLE_CHARACTER = 4
PY_STYLE_KEYWORD = 5
PY_STYLE_TRIPLE = 6
PY_STYLE_TRIPLEDOUBLE = 7
PY_STYLE_CLASSNAME = 8
PY_STYLE_DEFNAME = 9
PY_STYLE_OPERATOR = 10
PY_STYLE_IDENTIFIER = 11
PY_STYLE_COMMENTBLOCK = 12
PY_STYLE_STRINGEOL = 13
PY_STYLE_DECORATOR = 14


# ============================================================
# 主题类型枚举
# ============================================================
class ThemeType(Enum):
    """主题类型"""
    DARK = "dark"              # 深色
    LIGHT = "light"            # 浅色
    HIGH_CONTRAST = "high_contrast"  # 高对比度


# ============================================================
# 配色方案
# ============================================================
@dataclass
class ThemeColors:
    """
    主题配色方案。

    定义所有 UI 元素的颜色。
    """

    # ============ 编辑器基础 ============
    background: str = "#1e1e1e"         # 编辑器背景
    foreground: str = "#d4d4d4"         # 编辑器前景（文字）
    caret: str = "#aeafad"              # 光标颜色
    current_line: str = "#2b2b2b"       # 当前行高亮
    selection: str = "#264f78"          # 选区背景
    selection_foreground: str = "#ffffff"

    # ============ 行号与边距 ============
    line_number_bg: str = "#2d2d2d"     # 行号背景
    line_number_fg: str = "#858585"     # 行号前景
    line_number_active_fg: str = "#c6c6c6"  # 活动行行号前景
    margin_bg: str = "#2d2d2d"          # 边距背景
    margin_fg: str = "#858585"          # 边距前景
    fold_margin_bg: str = "#2d2d2d"     # 折叠边距背景
    fold_margin_fg: str = "#858585"     # 折叠边距前景

    # ============ 语法高亮 ============
    comment: str = "#6a9955"            # 注释
    keyword: str = "#569cd6"            # 关键字
    number: str = "#b5cea8"             # 数字
    string: str = "#ce9178"             # 字符串
    character: str = "#ce9178"          # 字符
    operator: str = "#d4d4d4"           # 运算符
    identifier: str = "#d4d4d4"         # 标识符
    class_name: str = "#4ec9b0"         # 类名
    function_name: str = "#dcdcaa"      # 函数名
    decorator: str = "#c586c0"          # 装饰器
    tag: str = "#569cd6"                # HTML/XML 标签
    attribute: str = "#9cdcfe"          # 属性
    regex: str = "#d16969"              # 正则表达式

    # ============ 特殊标记 ============
    brace_light_fg: str = "#ffd700"     # 匹配括号前景
    brace_light_bg: str = "#444400"     # 匹配括号背景
    brace_bad_fg: str = "#ff0000"       # 不匹配括号
    indent_guide: str = "#404040"       # 缩进辅助线
    control_char: str = "#888888"       # 控制字符

    # ============ 搜索与高亮 ============
    search_highlight: str = "#ffff00"   # 搜索高亮
    search_current: str = "#ff8000"     # 当前匹配
    smart_highlight: str = "#646464"    # 智能高亮
    error_underline: str = "#f14c4c"    # 错误波浪线
    warning_underline: str = "#f0ad4e"  # 警告波浪线

    # ============ UI 元素 ============
    window_bg: str = "#1e1e1e"          # 窗口背景
    window_fg: str = "#d4d4d4"          # 窗口文字
    menubar_bg: str = "#252526"         # 菜单栏背景
    menubar_fg: str = "#d4d4d4"         # 菜单栏文字
    menu_bg: str = "#2d2d2d"            # 菜单背景
    menu_fg: str = "#d4d4d4"            # 菜单文字
    menu_selection: str = "#094771"     # 菜单选中
    toolbar_bg: str = "#252526"         # 工具栏背景
    statusbar_bg: str = "#007acc"       # 状态栏背景
    statusbar_fg: str = "#ffffff"       # 状态栏文字
    tab_bg: str = "#2d2d2d"             # 标签背景
    tab_fg: str = "#cccccc"             # 标签文字
    tab_active_bg: str = "#1e1e1e"      # 活动标签背景
    tab_active_fg: str = "#ffffff"      # 活动标签文字
    panel_bg: str = "#252526"           # 面板背景
    panel_fg: str = "#d4d4d4"           # 面板文字
    border: str = "#3c3c3c"             # 边框颜色
    scrollbar_bg: str = "#2b2b2b"       # 滚动条背景
    scrollbar_fg: str = "#555555"       # 滚动条滑块
    scrollbar_hover: str = "#777777"    # 滚动条滑块悬停

    # ============ 按钮与输入 ============
    button_bg: str = "#0e639c"          # 按钮背景
    button_fg: str = "#ffffff"          # 按钮文字
    button_hover: str = "#1177bb"       # 按钮悬停
    button_pressed: str = "#0a4d7a"     # 按钮按下
    input_bg: str = "#3c3c3c"           # 输入框背景
    input_fg: str = "#d4d4d4"           # 输入框文字
    input_border: str = "#555555"       # 输入框边框
    input_focus: str = "#007acc"        # 输入框焦点

    # ============ 强调色 ============
    accent: str = "#7ec850"             # 强调色（青草绿）
    accent_hover: str = "#9ed870"       # 强调色悬停
    warning: str = "#f0ad4e"            # 警告
    error: str = "#f14c4c"              # 错误
    success: str = "#7ec850"            # 成功
    info: str = "#4dabf7"               # 信息

    def get(self, key: str, default: str = "#000000") -> str:
        """获取颜色"""
        return getattr(self, key, default)

    def set(self, key: str, value: str):
        """设置颜色"""
        if hasattr(self, key):
            setattr(self, key, value)

    def to_dict(self) -> Dict[str, str]:
        """序列化为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, str]) -> 'ThemeColors':
        """从字典反序列化"""
        colors = cls()
        for key, value in d.items():
            if hasattr(colors, key) and isinstance(value, str):
                setattr(colors, key, value)
        return colors


# ============================================================
# 主题
# ============================================================
@dataclass
class Theme:
    """
    主题对象。

    包含配色方案和元数据。
    """

    # 元数据
    name: str = "未命名"
    display_name: str = ""
    type: str = ThemeType.DARK.value
    version: int = THEME_FORMAT_VERSION
    author: str = ""
    description: str = ""
    created_at: str = ""
    updated_at: str = ""

    # 配色方案
    colors: ThemeColors = field(default_factory=ThemeColors)

    # 字体
    font_family: str = "Consolas"
    font_size: int = 12
    font_ligatures: bool = False

    # 全局 QSS
    qss: str = ""

    # 完整原始数据（用于保存）
    _raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def title(self) -> str:
        """显示标题"""
        return self.display_name or self.name

    @property
    def is_dark(self) -> bool:
        """是否深色主题"""
        return self.type == ThemeType.DARK.value

    @property
    def is_light(self) -> bool:
        """是否浅色主题"""
        return self.type == ThemeType.LIGHT.value

    @property
    def is_high_contrast(self) -> bool:
        """是否高对比度主题"""
        return self.type == ThemeType.HIGH_CONTRAST.value

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            'name': self.name,
            'display_name': self.display_name,
            'type': self.type,
            'version': self.version,
            'author': self.author,
            'description': self.description,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'colors': self.colors.to_dict(),
            'font_family': self.font_family,
            'font_size': self.font_size,
            'font_ligatures': self.font_ligatures,
            'qss': self.qss,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Theme':
        """从字典反序列化"""
        theme = cls()

        # 元数据
        theme.name = d.get('name', '未命名')
        theme.display_name = d.get('display_name', theme.name)
        theme.type = d.get('type', ThemeType.DARK.value)
        theme.version = d.get('version', THEME_FORMAT_VERSION)
        theme.author = d.get('author', '')
        theme.description = d.get('description', '')
        theme.created_at = d.get('created_at', '')
        theme.updated_at = d.get('updated_at', '')

        # 颜色
        colors_data = d.get('colors', {})
        if isinstance(colors_data, dict):
            theme.colors = ThemeColors.from_dict(colors_data)

        # 字体
        theme.font_family = d.get('font_family', 'Consolas')
        theme.font_size = d.get('font_size', 12)
        theme.font_ligatures = d.get('font_ligatures', False)

        # QSS
        theme.qss = d.get('qss', '')

        # 保留原始数据
        theme._raw = dict(d)

        return theme

    def save(self, filepath: str) -> bool:
        """保存主题到文件"""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)) or '.',
                        exist_ok=True)

            self.updated_at = datetime.datetime.now().isoformat()

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

            return True

        except Exception as e:
            print(f"[Theme] 保存失败: {e}")
            return False

    @classmethod
    def load(cls, filepath: str) -> Optional['Theme']:
        """从文件加载主题"""
        try:
            with open(filepath, encoding='utf-8') as f:
                data = json.load(f)

            theme = cls.from_dict(data)
            theme._raw['_filepath'] = filepath

            return theme

        except FileNotFoundError:
            print(f"[Theme] 文件不存在: {filepath}")
            return None
        except json.JSONDecodeError as e:
            print(f"[Theme] JSON 解析失败: {e}")
            return None
        except Exception as e:
            print(f"[Theme] 加载失败: {e}")
            return None

    def clone(self, new_name: str = "") -> 'Theme':
        """创建副本"""
        new_theme = Theme.from_dict(self.to_dict())
        if new_name:
            new_theme.name = new_name
            new_theme.display_name = new_name
        new_theme.created_at = datetime.datetime.now().isoformat()
        return new_theme

    def __repr__(self) -> str:
        return f"<Theme {self.name} type={self.type}>"


# ============================================================
# 内置主题
# ============================================================
class BuiltinThemes:
    """
    内置主题集合。

    定义 4 套内置主题。
    """

    @staticmethod
    def dark_night() -> Theme:
        """暗夜主题"""
        return Theme(
            name="dark_night",
            display_name="暗夜",
            type=ThemeType.DARK.value,
            author="青草编辑器",
            description="深色主题，适合夜间编码",
            colors=ThemeColors(
                background="#1e1e1e",
                foreground="#d4d4d4",
                caret="#aeafad",
                current_line="#2b2b2b",
                selection="#264f78",
                line_number_bg="#2d2d2d",
                line_number_fg="#858585",
                margin_bg="#2d2d2d",
                fold_margin_bg="#2d2d2d",
                comment="#6a9955",
                keyword="#569cd6",
                number="#b5cea8",
                string="#ce9178",
                class_name="#4ec9b0",
                function_name="#dcdcaa",
                decorator="#c586c0",
                window_bg="#1e1e1e",
                menubar_bg="#252526",
                menu_bg="#2d2d2d",
                toolbar_bg="#252526",
                statusbar_bg="#007acc",
                tab_bg="#2d2d2d",
                tab_active_bg="#1e1e1e",
                panel_bg="#252526",
                border="#3c3c3c",
                accent="#7ec850",
            ),
        )

    @staticmethod
    def light_clean() -> Theme:
        """晨曦主题"""
        return Theme(
            name="light_clean",
            display_name="晨曦",
            type=ThemeType.LIGHT.value,
            author="青草编辑器",
            description="明亮清爽的浅色主题",
            colors=ThemeColors(
                background="#ffffff",
                foreground="#333333",
                caret="#333333",
                current_line="#f5f5f5",
                selection="#b4d7ff",
                selection_foreground="#000000",
                line_number_bg="#f0f0f0",
                line_number_fg="#8a8a8a",
                line_number_active_fg="#333333",
                margin_bg="#f0f0f0",
                margin_fg="#8a8a8a",
                fold_margin_bg="#f0f0f0",
                fold_margin_fg="#8a8a8a",
                comment="#008000",
                keyword="#0000ff",
                number="#098658",
                string="#a31515",
                character="#a31515",
                operator="#333333",
                identifier="#333333",
                class_name="#267f99",
                function_name="#795e26",
                decorator="#af00db",
                brace_light_fg="#000000",
                brace_light_bg="#ffff00",
                brace_bad_fg="#ff0000",
                indent_guide="#d3d3d3",
                search_highlight="#ffff00",
                search_current="#ff8000",
                smart_highlight="#dddddd",
                error_underline="#e00000",
                warning_underline="#cc7700",
                window_bg="#ffffff",
                window_fg="#333333",
                menubar_bg="#f0f0f0",
                menubar_fg="#333333",
                menu_bg="#ffffff",
                menu_fg="#333333",
                menu_selection="#b4d7ff",
                toolbar_bg="#f0f0f0",
                statusbar_bg="#007acc",
                statusbar_fg="#ffffff",
                tab_bg="#e8e8e8",
                tab_fg="#666666",
                tab_active_bg="#ffffff",
                tab_active_fg="#333333",
                panel_bg="#f5f5f5",
                panel_fg="#333333",
                border="#d0d0d0",
                scrollbar_bg="#f0f0f0",
                scrollbar_fg="#c0c0c0",
                scrollbar_hover="#a0a0a0",
                button_bg="#007acc",
                button_fg="#ffffff",
                input_bg="#ffffff",
                input_fg="#333333",
                input_border="#c0c0c0",
                input_focus="#007acc",
                accent="#4caf50",
            ),
        )

    @staticmethod
    def eye_protect() -> Theme:
        """护眼主题"""
        return Theme(
            name="eye_protect",
            display_name="护眼",
            type=ThemeType.LIGHT.value,
            author="青草编辑器",
            description="柔和绿色，减少眼睛疲劳",
            colors=ThemeColors(
                background="#c7edcc",
                foreground="#2c3e2f",
                caret="#2c3e2f",
                current_line="#b8dfc0",
                selection="#8fc99a",
                selection_foreground="#1e2820",
                line_number_bg="#b8dfc0",
                line_number_fg="#5a7a5e",
                margin_bg="#b8dfc0",
                fold_margin_bg="#b8dfc0",
                comment="#526d48",
                keyword="#1a5f7a",
                number="#8b4513",
                string="#7d4e2e",
                class_name="#1a5f7a",
                function_name="#5f4a1a",
                decorator="#7a3f5f",
                window_bg="#c7edcc",
                menubar_bg="#b8dfc0",
                menu_bg="#d5f0d8",
                menu_selection="#8fc99a",
                toolbar_bg="#b8dfc0",
                statusbar_bg="#438355",
                statusbar_fg="#ffffff",
                tab_bg="#b8dfc0",
                tab_fg="#3a5f40",
                tab_active_bg="#c7edcc",
                tab_active_fg="#2c3e2f",
                panel_bg="#d5f0d8",
                panel_fg="#2c3e2f",
                border="#9cc9a5",
                accent="#4a8f5e",
                button_bg="#438355",
                indent_guide="#96c6a0",
            ),
        )

    @staticmethod
    def high_contrast() -> Theme:
        """高对比度主题"""
        return Theme(
            name="high_contrast",
            display_name="高对比度",
            type=ThemeType.HIGH_CONTRAST.value,
            author="青草编辑器",
            description="极高对比度，适合视力较弱用户",
            colors=ThemeColors(
                background="#000000",
                foreground="#ffffff",
                caret="#ffffff",
                current_line="#1a1a1a",
                selection="#ffff00",
                selection_foreground="#000000",
                line_number_bg="#000000",
                line_number_fg="#ffffff",
                line_number_active_fg="#ffff00",
                margin_bg="#000000",
                fold_margin_bg="#000000",
                comment="#00ff00",
                keyword="#00ffff",
                number="#ffff00",
                string="#ff8000",
                class_name="#00ffff",
                function_name="#ffff00",
                decorator="#ff00ff",
                brace_light_fg="#000000",
                brace_light_bg="#ffff00",
                brace_bad_fg="#ff0000",
                indent_guide="#333333",
                error_underline="#ff0000",
                warning_underline="#ffff00",
                window_bg="#000000",
                window_fg="#ffffff",
                menubar_bg="#000000",
                menubar_fg="#ffffff",
                menu_bg="#000000",
                menu_fg="#ffffff",
                menu_selection="#ffff00",
                toolbar_bg="#000000",
                statusbar_bg="#ffffff",
                statusbar_fg="#000000",
                tab_bg="#1a1a1a",
                tab_fg="#cccccc",
                tab_active_bg="#000000",
                tab_active_fg="#ffff00",
                panel_bg="#1a1a1a",
                panel_fg="#ffffff",
                border="#666666",
                accent="#00ff00",
            ),
        )

    @classmethod
    def all_themes(cls) -> List[Theme]:
        """获取所有内置主题"""
        return [
            cls.dark_night(),
            cls.light_clean(),
            cls.eye_protect(),
            cls.high_contrast(),
        ]

    @classmethod
    def get(cls, name: str) -> Optional[Theme]:
        """获取指定内置主题"""
        themes = {
            "dark_night": cls.dark_night,
            "light_clean": cls.light_clean,
            "eye_protect": cls.eye_protect,
            "high_contrast": cls.high_contrast,
        }

        factory = themes.get(name)
        if factory:
            return factory()
        return None


# ============================================================
# 主题色辅助（v3.0）
# ============================================================
def adapt_qss_colors(qss: str, theme) -> str:
    """
    把 QSS 中的硬编码深色替换为主题色。

    参数:
        qss: 原始 QSS 字符串
        theme: Theme 对象

    返回:
        替换后的 QSS

    修复（INV-T1，审计用例复现的"颜色互相覆盖"）：
        原实现是**顺序 `str.replace()` 链**：

            for old, new in replacements:
                qss = qss.replace(old, new)

        这会产生**级联覆盖**：前一条写入的 `new` 若恰好等于后面某条的
        `old`，就会被再替换一次。真实例子（浅色主题 light_clean）：

            '#d4d4d4' -> c.foreground  == '#333333'
            '#333333' -> c.panel_bg    == '#f5f5f5'   ← 又命中刚写入的值

        于是表示"正文前景"的 `#d4d4d4` 最终变成**面板背景色** ——
        文字与背景同色，界面看起来"少了一块"。同理 `#cccccc`
        （应映射 tab_fg）被二次替换成 line_number_fg。

        正确做法是**单次扫描**：对原串一次性匹配所有旧色，各自只替换一次，
        替换结果不再参与匹配。这样映射表即"最终语义"。
    """
    if not qss or theme is None:
        return qss

    try:
        c = theme.colors
    except Exception:
        return qss

    # 老深色 → 主题色（按优先级，先长后短）
    #
    # A: 补充终端/控制台/次要文字等颜色
    # 顺序重要：6 位色必须在 3 位色之前，避免误伤
    replacements = [
        # ==== 原表 ====
        ('#252526', c.panel_bg),
        ('#1e1e1e', c.background),
        ('#2d2d2d', c.menubar_bg),
        ('#3c3c3c', c.border),
        ('#d4d4d4', c.foreground),
        ('#cccccc', c.tab_fg),
        ('#888888', c.line_number_fg),
        ('#666666', c.line_number_fg),
        ('#555555', c.input_border),
        ('#888', c.line_number_fg),
        ('#666', c.line_number_fg),
        ('#555', c.input_border),
        ('#094771', c.menu_selection),
        ('#7ec850', c.accent),
        ('#0e639c', c.button_bg),
        ('#1177bb', c.button_hover),
        ('#f14c4c', c.error),
        ('#f0ad4e', c.warning),
        ('#4dabf7', c.info),

        # ==== A: 补充 ====
        # 终端/控制台背景（关键）
        ('#0d0d0d', c.background),
        # 目录树 hover
        ('#2a2d2e', c.panel_bg),
        # 面板变体
        ('#333333', c.panel_bg),
        ('#4c4c4c', c.border),
        # 次要文字
        ('#858585', c.line_number_fg),
        ('#808080', c.line_number_fg),
        ('#c0c0c0', c.tab_fg),
        # 缩进辅助线
        ('#404040', c.indent_guide),
        # 禁用/危险按钮
        ('#5a5a5a', c.border),
        ('#8f1e1e', c.error),

        # A(最终): 补齐 QSS 遗漏的颜色
        # #007acc 是 QCheckBox::indicator:checked / :focus、
        # QLineEdit:focus 等大量控件的聚焦色，之前未覆盖
        ('#007acc', c.input_focus),
        # 更多常见遗漏
        ('#0a4d7a', c.button_pressed),
        ('#0e639c', c.button_bg),   # 重复保险
        ('#2196f3', c.info),
        ('#4caf50', c.success),
        ('#f44336', c.error),
        ('#ff9800', c.warning),
    ]

    # 构建 "旧色 → 新色" 映射（6 位与 3 位分开，避免 '#888' 命中
    # '#888888' 的前 4 个字符）
    six = {}
    three = {}
    for old, new in replacements:
        if not old or not new or old == new:
            continue
        old_l = old.lower()
        if len(old_l) == 7:
            six.setdefault(old_l, new)
        elif len(old_l) == 4:
            three.setdefault(old_l, new)

    def _sub(match):
        token = match.group(0)
        new = six.get(token.lower()) or three.get(token.lower())
        return new if new else token

    # 单次扫描：替换结果不再参与匹配（根治级联覆盖）
    try:
        pattern = re.compile(r'#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}\b')
        return pattern.sub(_sub, qss)
    except Exception:
        return qss


def notify_widgets(root, theme, visible_only: bool = False):
    """
    遍历控件树，通知所有 refresh_theme 方法（v3.0）。

    参数:
        root: 根控件（通常是 QMainWindow）
        theme: Theme 对象
        visible_only: 只立即刷新**可见**控件；隐藏控件的主题先挂起，
            等它第一次显示时由 `_LazyThemeApplier` 应用。

            ★ 为什么需要（性能实测）：启动时主窗口只显示 1~2 个面板，
            其余几十个隐藏面板的 `refresh_theme()`（内部 setStyleSheet）
            实测占 0.4~0.6s 的启动主题耗时。它们大多在用户实际打开前
            根本不需要样式；挂起到 Show 事件再套，视觉上不可感知。

            ★ 正确性：不能简单"跳过"隐藏控件 —— 那会复现真实桌面缺陷
            （面板保持写死的深色 QSS = 一块黑矩形）。所以这里是"挂起 +
            首次显示时应用"，而不是跳过。
    """
    if root is None or theme is None:
        return
    pending = 0
    try:
        for widget in root.findChildren(QWidget):
            fn = getattr(widget, 'refresh_theme', None)
            if not callable(fn):
                continue
            if visible_only and not widget.isVisible():
                try:
                    widget._pending_theme = theme
                    pending += 1
                except Exception:
                    pass
                continue
            try:
                fn(theme)
            except Exception:
                pass
    except Exception:
        pass

    if pending:
        _ensure_lazy_theme_applier(QApplication.instance())


# ============================================================
# 隐藏控件的"首次显示时套主题"
# ============================================================
_LAZY_THEME_FILTER = None


class _LazyThemeApplier(QObject):
    """应用级事件过滤器：控件第一次显示时应用挂起的主题

    为什么不用窗口直接装：与 `_KeySequenceAppFilter` 同源的教训 ——
    QApplication 持有过滤器指针，窗口销毁后会访问违例。这里对象本身
    **不持有任何窗口引用**，只读取控件上的 `_pending_theme` 属性，安全。
    """

    def eventFilter(self, obj, event):
        try:
            if event.type() != QEvent.Show:
                return False
            theme = getattr(obj, '_pending_theme', None)
            if theme is None:
                return False
            try:
                obj._pending_theme = None
            except Exception:
                pass
            fn = getattr(obj, 'refresh_theme', None)
            if callable(fn):
                try:
                    fn(theme)
                except Exception:
                    pass
            # 顺带 polish 一次，确保 QSS 生效
            try:
                obj.style().unpolish(obj)
                obj.style().polish(obj)
                obj.update()
            except Exception:
                pass
        except Exception:
            pass
        return False


def _ensure_lazy_theme_applier(app):
    """惰性主题过滤器（模块级单例），仅在首次需要时安装"""
    global _LAZY_THEME_FILTER
    if app is None or _LAZY_THEME_FILTER is not None:
        return
    try:
        _LAZY_THEME_FILTER = _LazyThemeApplier()
        app.installEventFilter(_LAZY_THEME_FILTER)
    except Exception:
        _LAZY_THEME_FILTER = None


# ============================================================
# 主题加载器
# ============================================================
class ThemeLoader(QObject):
    """
    主题加载器。

    负责:
    - 加载主题文件
    - 应用主题到编辑器
    - 应用全局 QSS
    - 主题缓存
    - 主题导入/导出

    信号:
        theme_loaded(str): 主题加载完成（名称）
        theme_applied(str): 主题应用完成（名称）
        theme_error(str, str): 主题错误（名称, 错误）
    """

    theme_loaded = pyqtSignal(str)
    theme_applied = pyqtSignal(str)
    theme_error = pyqtSignal(str, str)

    def notify_widgets(self, root, theme):
        """
        v3.1: notify_widgets 实例方法。

        遍历 root 控件树，通知所有带 refresh_theme 的子控件刷新样式。
        内部调用模块级函数 notify_widgets(root, theme)。
        """
        try:
            # 调用同模块内的模块级函数
            notify_widgets(root, theme)
        except NameError:
            # 兜底：模块级函数不存在时手动实现
            try:
                from PyQt5.QtWidgets import QWidget
                for widget in root.findChildren(QWidget):
                    fn = getattr(widget, 'refresh_theme', None)
                    if callable(fn):
                        try:
                            fn(theme)
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception as e:
            print(f"[ThemeLoader] notify_widgets 失败: {e}")

    def __init__(self, parent: Optional[QObject] = None,
                 theme_dir: str = DEFAULT_THEME_DIR):
        """
        参数:
            parent: 父 QObject
            theme_dir: 主题目录
        """
        super().__init__(parent)

        self.theme_dir = theme_dir

        # 当前主题
        self.current_theme: Optional[Theme] = None

        # 主题缓存：name -> Theme
        self._theme_cache: Dict[str, Theme] = {}

        # 确保目录存在
        os.makedirs(theme_dir, exist_ok=True)

    # ========================================================
    # 加载主题
    # ========================================================
    def load(self, filepath: str) -> Optional[Theme]:
        """
        加载主题文件。

        参数:
            filepath: 主题 JSON 文件路径

        返回:
            Theme 或 None
        """
        try:
            # 检查缓存
            if filepath in self._theme_cache:
                theme = self._theme_cache[filepath]
                self.current_theme = theme
                self.theme_loaded.emit(theme.name)
                return theme

            # 从文件加载
            theme = Theme.load(filepath)

            if theme:
                # 存储文件路径
                theme._raw['_filepath'] = filepath

                # 缓存
                self._theme_cache[filepath] = theme

                self.current_theme = theme
                self.theme_loaded.emit(theme.name)

                return theme

            return None

        except Exception as e:
            self.theme_error.emit("", str(e))
            print(f"[ThemeLoader] 加载失败: {e}")
            return None

    def load_by_name(self, name: str) -> Optional[Theme]:
        """
        按名称加载主题。

        **优先级：JSON 文件 > 内置定义**

        为什么必须这样（真实缺陷）：
            原实现**先**返回内置定义 `BuiltinThemes.get(name)`，而内置的
            `eye_protect()` 只显式设置 32 个键（JSON 有 70 个），缺失的键
            回退到 `ThemeColors` 的**暗色默认值**：

                window_fg / menubar_fg / menu_fg -> #d4d4d4（浅灰）
                button_bg                        -> #0e639c（暗蓝）

            于是护眼主题（浅绿底 #c7edcc）上，菜单栏与工具栏文字变成浅灰，
            **几乎不可见**。内置 `eye_protect.type` 还错标成 dark
            （JSON 是 light）。

            两个真相来源必然漂移。让完整的 JSON 优先，内置定义只作为
            JSON 缺失时的后备。

        参数:
            name: 主题名称

        返回:
            Theme 或 None
        """
        # 1) 优先磁盘上的 JSON（完整定义；用户自定义主题也在此）
        filepath = find_theme_file(name, self.theme_dir)
        if filepath:
            theme = self.load(filepath)
            if theme is not None:
                self.current_theme = theme
                return theme

        # 2) 后备：内置定义（可能与 JSON 不同步，仅用于兜底）
        builtin = BuiltinThemes.get(name)
        if builtin:
            self.current_theme = builtin
            self.theme_loaded.emit(builtin.name)
            return builtin

        return None

    def load_all(self) -> List[Theme]:
        """
        加载所有可用主题。

        优先级与去重：**同名时 JSON 覆盖内置定义**。

        原因同 `load_by_name`：内置定义可能不完整（`eye_protect` 只显式
        设置 32/70 个键），而 JSON 是完整的。若两者都返回，主题列表里会
        出现两个同名项，选择到哪个取决于顺序 —— 这正是难以复现的
        "主题时好时坏"的来源。

        搜索目录用 `resolve_theme_dirs()`，覆盖打包后 `_internal/themes`
        与源码运行的仓库 themes/ 两种情况。

        返回:
            Theme 列表
        """
        by_name: Dict[str, Theme] = {}

        # 1) 内置定义（后备，先放进来会被 JSON 覆盖）
        for t in BuiltinThemes.all_themes():
            by_name[t.name] = t

        # 2) JSON 主题（优先）——按目录优先级覆盖同名内置定义
        for d in resolve_theme_dirs(self.theme_dir):
            if not os.path.isdir(d):
                continue
            for filename in sorted(os.listdir(d)):
                if not filename.endswith(".json"):
                    continue
                try:
                    theme = self.load(os.path.join(d, filename))
                except Exception as e:
                    print(f"[ThemeLoader] 加载 {filename} 失败: {e}")
                    continue
                if theme is not None:
                    by_name[theme.name] = theme

        return list(by_name.values())

    # ========================================================
    # 应用主题
    # ========================================================
    def apply(self, editor, theme: Optional[Theme] = None):
        """
        应用主题到编辑器。

        参数:
            editor: QScintilla 实例
            theme: 主题（None 则使用当前主题）
        """
        if theme is None:
            theme = self.current_theme

        if theme is None or editor is None:
            return

        try:
            colors = theme.colors

            # ============ 基础颜色 ============
            editor.setColor(QColor(colors.foreground))
            editor.setPaper(QColor(colors.background))

            # 光标颜色
            editor.setCaretForegroundColor(QColor(colors.caret))

            # 当前行高亮
            #
            # 修复（INV-T2，审计用例复现）：
            #   原先无条件 `setCaretLineVisible(True)` —— 切换主题会把
            #   "高亮当前行"**强制打开**，静默覆盖用户的
            #   `show_current_line=False`（首选项里明确关掉的设置）。
            #
            #   主题只负责**颜色**，不应改变"是否显示"这类用户行为设置。
            #   因此这里只设置背景色；可见性由 `ui/editor_view.py` 依据
            #   首选项决定（已存在该逻辑）。
            editor.setCaretLineBackgroundColor(QColor(colors.current_line))

            # 选区颜色
            editor.setSelectionBackgroundColor(QColor(colors.selection))

            try:
                # 选区前景
                palette = editor.palette()
                palette.setColor(QPalette.Highlight,
                                  QColor(colors.selection))
                palette.setColor(
                    QPalette.HighlightedText,
                    QColor(colors.selection_foreground)
                )
                editor.setPalette(palette)
            except Exception:
                pass

            # ============ 行号与边距 ============
            # 行号边距
            editor.setMarginsBackgroundColor(QColor(colors.line_number_bg))
            editor.setMarginsForegroundColor(QColor(colors.line_number_fg))

            # 折叠边距
            editor.setFoldMarginColors(
                QColor(colors.fold_margin_bg),
                QColor(colors.fold_margin_fg)
            )

            # ============ 括号匹配 ============
            editor.setMatchedBraceForegroundColor(
                QColor(colors.brace_light_fg)
            )
            editor.setMatchedBraceBackgroundColor(
                QColor(colors.brace_light_bg)
            )
            editor.setUnmatchedBraceForegroundColor(
                QColor(colors.brace_bad_fg)
            )

            # ============ 缩进辅助线 ============
            editor.setIndentationGuidesForegroundColor(
                QColor(colors.indent_guide)
            )

            # ============ 通过 Scintilla API 设置更多样式 ============
            # P2-C9: 删除对 no-op 方法的调用
            # _apply_scintilla_styles 已改为 no-op（见方法内注释），
            # 调用它没有意义，反而增加阅读负担。
            # 颜色已由 apply() 中的高层 API 设置。

            # ============ 词法器颜色 ============
            lexer = editor.lexer()
            if lexer:
                self._apply_lexer_colors(lexer, colors)

            # ============ 字体 ============
            try:
                font = QFont(theme.font_family, theme.font_size)
                font.setStyleHint(QFont.Monospace)
                editor.setFont(font)
                editor.setMarginsFont(font)

                if lexer:
                    lexer.setDefaultFont(font)
            except Exception:
                pass

            self.theme_applied.emit(theme.name)

        except Exception as e:
            self.theme_error.emit(theme.name if theme else "", str(e))
            print(f"[ThemeLoader] 应用主题失败: {e}")

    def _apply_scintilla_styles(self, editor, colors: ThemeColors):
        """通过 Scintilla API 设置样式

        v3.1: 本方法已改为 no-op。

        原因：
            PyQt5 的 QsciScintilla 类不导出 SCI_STYLE_DEFAULT /
            SCI_STYLESETFORE 等常量（它们是实例属性），
            原代码 `QsciScintilla.SCI_STYLE_DEFAULT` 会抛
            AttributeError，在控制台反复刷警告。

        替代：
            apply() 中已通过 QsciScintilla 高层 API 设置：
              - setColor / setPaper
              - setMarginsBackgroundColor / setMarginsForegroundColor
              - setMatchedBraceForegroundColor / BackgroundColor
              - setUnmatchedBraceForegroundColor
              - setIndentationGuidesForegroundColor
            已覆盖本方法原本要做的全部工作。
        """
        # 无需实现，颜色已由 apply() 中的高层 API 设置
        pass

    def _apply_lexer_colors(self, lexer, colors: ThemeColors):
        """应用词法器颜色（P2-3: 按 lexer 类型选择样式索引）

        不同 QsciLexer 子类的样式索引完全不同。例如：
          - Python: keyword=5, class=8, function=9, decorator=14
          - C++:    keyword=5/16, class=19, function=19, decorator=9
          - JavaScript 继承自 CPP，索引与 CPP 一致

        原实现硬编码 Python 的索引，导致 C++/JS 文件主题化失效。
        """
        # 样式索引映射表
        PYTHON_MAP = {
            'comment': 1, 'number': 2, 'string': 3,
            'character': 4, 'keyword': 5, 'class_name': 8,
            'function_name': 9, 'operator': 10,
            'identifier': 11, 'decorator': 14,
        }
        CPP_MAP = {
            'comment': 1, 'number': 4, 'keyword': 5,
            'string': 6, 'character': 7, 'operator': 10,
            'identifier': 11, 'class_name': 19,
            'function_name': 19, 'decorator': 9,
        }

        try:
            lexer.setDefaultColor(QColor(colors.foreground))
            lexer.setDefaultPaper(QColor(colors.background))

            # P2-3: 按 lexer 类型选择样式索引
            style_map = PYTHON_MAP  # 默认
            try:
                from PyQt5.Qsci import (
                    QsciLexerCPP,
                    QsciLexerPython,
                )
                if isinstance(lexer, QsciLexerPython):
                    style_map = PYTHON_MAP
                elif isinstance(lexer, QsciLexerCPP):
                    # JavaScript / TypeScript 继承自 CPP
                    style_map = CPP_MAP
            except Exception:
                pass

            for attr, style_id in style_map.items():
                color = getattr(colors, attr, None)
                if color:
                    try:
                        lexer.setColor(QColor(color), style_id)
                    except Exception:
                        pass

            # 背景纸
            for i in range(0, 128):
                try:
                    lexer.setPaper(QColor(colors.background), i)
                except Exception:
                    pass

        except Exception as e:
            print(f"[ThemeLoader] 应用词法器颜色失败: {e}")

    # ========================================================
    # 应用 QSS
    # ========================================================
    def apply_palette(self, app, theme: Optional[Theme] = None):
        """根据主题设置 QPalette。

        B(调色板): 根据主题设置 QPalette
        QSS 只能控制显式命名的控件；Qt 原生对话框、下拉菜单、
        Tooltip 等很多控件从 QPalette 读颜色，QSS 覆盖不到。
        必须同时设置 QPalette，否则深色系统下会显示白色文字。
        """
        if theme is None:
            theme = self.current_theme
        if theme is None or app is None:
            return

        try:
            from PyQt5.QtGui import QColor, QPalette

            c = theme.colors
            p = QPalette()

            p.setColor(QPalette.Window, QColor(c.window_bg))
            p.setColor(QPalette.WindowText, QColor(c.window_fg))
            p.setColor(QPalette.Base, QColor(c.background))
            p.setColor(QPalette.AlternateBase, QColor(c.panel_bg))
            p.setColor(QPalette.Text, QColor(c.foreground))
            p.setColor(QPalette.Button, QColor(c.menubar_bg))
            p.setColor(QPalette.ButtonText, QColor(c.window_fg))
            p.setColor(QPalette.BrightText, QColor(c.error))
            p.setColor(QPalette.Highlight, QColor(c.selection))
            p.setColor(
                QPalette.HighlightedText,
                QColor(c.selection_foreground)
            )
            p.setColor(QPalette.ToolTipBase, QColor(c.menu_bg))
            p.setColor(QPalette.ToolTipText, QColor(c.menu_fg))
            p.setColor(QPalette.Link, QColor(c.info))
            p.setColor(QPalette.LinkVisited, QColor(c.info))

            # 禁用态
            p.setColor(
                QPalette.Disabled, QPalette.Text,
                QColor(c.line_number_fg)
            )
            p.setColor(
                QPalette.Disabled, QPalette.ButtonText,
                QColor(c.line_number_fg)
            )
            p.setColor(
                QPalette.Disabled, QPalette.WindowText,
                QColor(c.line_number_fg)
            )

            app.setPalette(p)
        except Exception as e:
            print(f"[ThemeLoader] 应用 palette 失败: {e}")

    def apply_qss(self, app, theme: Optional[Theme] = None,
                  lazy: bool = False):
        """
        应用全局 QSS 到应用。

        TF 增强:
            1. 每次都重新生成 QSS（不只空时），避免返回旧值
            2. 应用后遍历所有 widget 调 unpolish/polish
               强制 Qt 重新读取 QSS
            3. 显式刷新 menuBar/toolBar 的 palette + styleSheet
        """
        if theme is None:
            theme = self.current_theme

        if theme is None or app is None:
            return

        try:
            qss = theme.qss
            # TF: 每次都重新生成，避免 theme.qss 为空时返回旧值
            if not qss:
                qss = self._generate_qss(theme.colors)

            if not qss:
                print("[ThemeLoader] 警告: 生成的 QSS 为空")
                return

            # 主题未变（启动链路里 main.load_theme 已应用过一次同主题）
            # → 跳过全局 setStyleSheet：Qt 会因此对所有控件全量 repolish。
            try:
                if app.styleSheet() == qss:
                    print(f"[ThemeLoader] apply_qss: theme={theme.name} "
                          f"已是当前样式，跳过")
                    return
            except Exception:
                pass

            print(f"[ThemeLoader] apply_qss: theme={theme.name} "
                  f"qss_len={len(qss)}")

            app.setStyleSheet(qss)

            # 绑定"当前主题颜色"给欢迎页等使用**内联样式**的控件。
            # 它们不随全局 QSS 更新（setStyleSheet 只在构建时求值一次），
            # 因此需要知道当前主题色以便重放样式。
            try:
                from ui.welcome_widget import C as _welcome_colors
                _welcome_colors.bind(theme.colors)
            except Exception:
                pass

            # B(调色板): 同时应用 QPalette
            self.apply_palette(app, theme)

            # TF: 强制刷新 widget（unpolish/polish）；lazy 只刷可见的
            self._force_refresh(app, lazy=lazy)

        except Exception as e:
            print(f"[ThemeLoader] 应用 QSS 失败: {e}")
            import traceback
            traceback.print_exc()

    def _force_refresh(self, app, lazy: bool = False):
        """TF: 强制刷新 widget（unpolish/polish）

        Qt 在 setStyleSheet 后不会自动重绘所有 widget，
        尤其是 QMenuBar / QToolBar / QDockWidget 标题栏。
        必须显式 unpolish + polish，或对每个 widget 调
        style().unpolish(w); style().polish(w)。

        `lazy=True` 时跳过不可见控件（启动阶段隐藏面板占绝大多数，
        实测 polish 一个隐藏面板与可见面板成本相同，但视觉上不可见）。
        """
        try:
            from PyQt5.QtWidgets import QMenuBar, QToolBar

            # 1. 刷新所有 widget
            for w in app.allWidgets():
                if lazy:
                    # 隐藏控件留给 _LazyThemeApplier（首次显示时处理）
                    try:
                        if not w.isVisible():
                            continue
                    except Exception:
                        continue
                try:
                    w.style().unpolish(w)
                    w.style().polish(w)
                    w.update()
                except Exception:
                    pass

            # 2. 显式刷新顶层窗口的 menuBar / toolBar
            for top in app.topLevelWidgets():
                if lazy:
                    try:
                        if not top.isVisible():
                            continue
                    except Exception:
                        continue
                try:
                    mb = top.menuBar() if hasattr(top, 'menuBar') else None
                    if mb is not None:
                        mb.style().unpolish(mb)
                        mb.style().polish(mb)
                        mb.update()
                        mb.repaint()
                except Exception:
                    pass

                try:
                    for tb in top.findChildren(QToolBar):
                        tb.style().unpolish(tb)
                        tb.style().polish(tb)
                        tb.update()
                        tb.repaint()
                except Exception:
                    pass

            print("[ThemeLoader] _force_refresh: 已刷新所有 widget")
        except Exception as e:
            print(f"[ThemeLoader] 强制刷新失败: {e}")

    def _generate_qss(self, c: ThemeColors) -> str:
        """从配色方案生成 QSS"""
        return f"""
            /* ============ 全局 ============ */
            QWidget {{
                background-color: {c.window_bg};
                color: {c.window_fg};
                font-size: 12px;
            }}

            /* ============ 主窗口 ============ */
            QMainWindow {{
                background-color: {c.window_bg};
            }}

            /* ============ 菜单栏 ============ */
            QMenuBar {{
                background-color: {c.menubar_bg};
                color: {c.menubar_fg};
                border-bottom: 1px solid {c.border};
                padding: 2px;
            }}
            QMenuBar::item {{
                padding: 4px 10px;
                border-radius: 3px;
            }}
            QMenuBar::item:selected {{
                background-color: {c.menu_selection};
            }}

            /* ============ 菜单 ============ */
            QMenu {{
                background-color: {c.menu_bg};
                color: {c.menu_fg};
                border: 1px solid {c.border};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 24px 6px 12px;
                border-radius: 3px;
            }}
            QMenu::item:selected {{
                background-color: {c.menu_selection};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {c.border};
                margin: 4px 8px;
            }}

            /* ============ 工具栏 ============ */
            /* A(调色板): QToolBar/QToolButton 必须有 color，
               否则 Qt 默认用系统文字色（深色系统下是白色），
               在浅色主题上看不清 */
            QToolBar {{
                background-color: {c.toolbar_bg};
                color: {c.window_fg};
                border: none;
                border-bottom: 1px solid {c.border};
                spacing: 4px;
                padding: 2px;
            }}
            QToolBar QToolButton {{
                color: {c.window_fg};
                background-color: transparent;
                border: none;
                padding: 3px 6px;
                border-radius: 3px;
            }}
            QToolBar QToolButton:hover {{
                background-color: {c.menu_selection};
                color: {c.selection_foreground};
            }}
            QToolBar QToolButton:pressed {{
                background-color: {c.button_pressed};
            }}
            QToolBar QToolButton:checked {{
                background-color: {c.menu_selection};
                color: {c.selection_foreground};
            }}

            /* ============ 状态栏 ============ */
            QStatusBar {{
                background-color: {c.statusbar_bg};
                color: {c.statusbar_fg};
                font-weight: bold;
            }}
            /* ★ 真实桌面验证发现的缺陷：状态栏标签"白字白底"完全不可见
               
               本 QSS 顶部有全局规则 `QWidget {{ background-color:
               {c.window_bg}; }}`（浅色主题下是纯白）。状态栏里的
               行/列、编码、行尾符等**都是 QLabel**，会继承那条全局背景，
               于是变成「白色方块 + 白色文字」——
               实测在 1000x700 窗口里，状态栏底部只见一排白块，
               用户根本看不到"编码 / 行尾符"等关键信息
               （而这些正是切换编码/换行后最需要确认的反馈）。

               修复：标签背景显式透明，让状态栏底色透出来。 */
            QStatusBar QLabel {{
                color: {c.statusbar_fg};
                background: transparent;
            }}
            QStatusBar::item {{
                border: none;
            }}

            /* ============ 标签栏 ============ */
            QTabWidget::pane {{
                border: 0;
                background-color: {c.panel_bg};
            }}
            QTabBar::tab {{
                background-color: {c.tab_bg};
                color: {c.tab_fg};
                padding: 6px 14px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {c.tab_active_bg};
                color: {c.tab_active_fg};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {c.menu_selection};
                color: {c.tab_active_fg};
            }}

            /* ============ 按钮 ============ */
            QPushButton {{
                background-color: {c.button_bg};
                color: {c.button_fg};
                border: none;
                border-radius: 3px;
                padding: 6px 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {c.button_hover};
            }}
            QPushButton:pressed {{
                background-color: {c.button_pressed};
            }}
            QPushButton:disabled {{
                background-color: {c.border};
                color: {c.line_number_fg};
            }}

            /* ============ 输入框 ============ */
            QLineEdit, QPlainTextEdit, QTextEdit {{
                background-color: {c.input_bg};
                color: {c.input_fg};
                border: 1px solid {c.input_border};
                border-radius: 3px;
                padding: 4px 8px;
                selection-background-color: {c.selection};
                selection-color: {c.selection_foreground};
            }}
            QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
                border-color: {c.input_focus};
            }}

            /* ============ 下拉框 ============ */
            QComboBox {{
                background-color: {c.input_bg};
                color: {c.input_fg};
                border: 1px solid {c.input_border};
                border-radius: 3px;
                padding: 4px 8px;
                min-width: 80px;
            }}
            QComboBox:focus {{
                border-color: {c.input_focus};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {c.menu_bg};
                color: {c.menu_fg};
                selection-background-color: {c.menu_selection};
                border: 1px solid {c.border};
            }}

            /* ============ 复选框 ============ */
            QCheckBox {{
                color: {c.window_fg};
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border: 1px solid {c.input_border};
                border-radius: 2px;
                background-color: {c.input_bg};
            }}
            QCheckBox::indicator:checked {{
                background-color: {c.input_focus};
                border-color: {c.input_focus};
            }}

            /* ============ 滚动条 ============ */
            QScrollBar:vertical {{
                background-color: {c.scrollbar_bg};
                width: 12px;
                border-radius: 6px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background-color: {c.scrollbar_fg};
                border-radius: 6px;
                min-height: 20px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {c.scrollbar_hover};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar:horizontal {{
                background-color: {c.scrollbar_bg};
                height: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {c.scrollbar_fg};
                border-radius: 6px;
                min-width: 20px;
                margin: 2px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: {c.scrollbar_hover};
            }}

            /* ============ 停靠面板 ============ */
            QDockWidget {{
                color: {c.panel_fg};
                titlebar-close-icon: url(none);
                titlebar-normal-icon: url(none);
            }}
            QDockWidget::title {{
                background-color: {c.menubar_bg};
                padding: 4px 8px;
                border-bottom: 1px solid {c.border};
            }}

            /* ============ 树/列表 ============ */
            QTreeWidget, QListWidget, QTreeView, QListView {{
                background-color: {c.panel_bg};
                color: {c.panel_fg};
                border: 1px solid {c.border};
                outline: none;
            }}
            QTreeWidget::item:hover,
            QListWidget::item:hover,
            QTreeView::item:hover,
            QListView::item:hover {{
                background-color: {c.menu_selection};
            }}
            QTreeWidget::item:selected,
            QListWidget::item:selected,
            QTreeView::item:selected,
            QListView::item:selected {{
                background-color: {c.menu_selection};
                color: {c.tab_active_fg};
            }}
            QHeaderView::section {{
                background-color: {c.menubar_bg};
                color: {c.panel_fg};
                border: none;
                border-bottom: 1px solid {c.border};
                padding: 4px 6px;
            }}

            /* ============ 分割器 ============ */
            QSplitter::handle {{
                background-color: {c.border};
            }}
            QSplitter::handle:hover {{
                background-color: {c.input_focus};
            }}

            /* ============ 对话框 ============ */
            QDialog {{
                background-color: {c.window_bg};
                color: {c.window_fg};
            }}

            /* ============ 提示 ============ */
            QToolTip {{
                background-color: {c.menu_bg};
                color: {c.menu_fg};
                border: 1px solid {c.border};
                padding: 4px 8px;
            }}
        """

    # ========================================================
    # 便捷应用（编辑器 + QSS）
    # ========================================================
    def apply_all(self, app, editor, theme: Optional[Theme] = None):
        """
        同时应用主题到编辑器和全局 QSS。

        参数:
            app: QApplication
            editor: QScintilla 实例
            theme: 主题
        """
        if theme is None:
            theme = self.current_theme

        if theme is None:
            return

        self.apply(editor, theme)
        self.apply_qss(app, theme)

    # ========================================================
    # 主题切换
    # ========================================================
    def switch_theme(self, name_or_path: str) -> bool:
        """
        切换主题。

        参数:
            name_or_path: 主题名称或文件路径

        返回:
            是否成功
        """
        # 尝试作为文件路径
        if os.path.exists(name_or_path):
            theme = self.load(name_or_path)
        else:
            theme = self.load_by_name(name_or_path)

        if theme:
            # 保存偏好
            try:
                settings = QSettings("QingCao", "Editor")
                settings.setValue("theme_name", theme.name)
                settings.setValue(
                    "theme_path", theme._raw.get('_filepath', '')
                )
            except Exception:
                pass

            self.theme_applied.emit(theme.name)
            return True

        return False

    # ========================================================
    # 导入/导出
    # ========================================================
    def export_theme(self, theme: Theme, filepath: str) -> bool:
        """
        导出主题到文件。

        参数:
            theme: 主题对象
            filepath: 导出路径

        返回:
            是否成功
        """
        return theme.save(filepath)

    def import_theme(self, filepath: str) -> Optional[Theme]:
        """
        导入主题（加载并复制到主题目录）。

        参数:
            filepath: 源文件路径

        返回:
            导入的 Theme 或 None
        """
        theme = Theme.load(filepath)

        if not theme:
            return None

        # 复制到主题目录
        target_name = f"{theme.name}.json"
        target_path = os.path.join(self.theme_dir, target_name)

        # 处理重名
        counter = 1
        while os.path.exists(target_path):
            target_name = f"{theme.name}_{counter}.json"
            target_path = os.path.join(self.theme_dir, target_name)
            counter += 1

        # 保存
        if theme.save(target_path):
            return theme

        return None

    # ========================================================
    # 跟随系统
    # ========================================================
    def apply_system_theme(self, app, editor, dark_theme: str = "dark_night",
                            light_theme: str = "light_clean"):
        """
        根据系统主题应用深色或浅色主题。

        参数:
            app: QApplication
            editor: QScintilla
            dark_theme: 系统深色时使用的主题
            light_theme: 系统浅色时使用的主题
        """
        try:
            # Qt 6.5+ 支持查询系统主题
            hints = QApplication.styleHints()
            is_dark = False

            if hasattr(hints, 'colorScheme'):
                scheme = hints.colorScheme()
                is_dark = (scheme == Qt.ColorScheme.Dark)

            # 应用对应主题
            theme_name = dark_theme if is_dark else light_theme
            self.switch_theme(theme_name)

            self.apply_all(app, editor)

        except Exception as e:
            print(f"[ThemeLoader] 应用系统主题失败: {e}")

    # ========================================================
    # 查询
    # ========================================================
    def list_themes(self) -> List[Tuple[str, str]]:
        """
        列出所有可用主题。

        返回:
            [(名称, 显示名), ...]
        """
        themes = []

        # 内置主题
        for name, display in BUILTIN_THEMES.items():
            themes.append((name, display))

        # 目录中的自定义主题
        if os.path.isdir(self.theme_dir):
            for filename in sorted(os.listdir(self.theme_dir)):
                if not filename.endswith('.json'):
                    continue

                name = os.path.splitext(filename)[0]

                # 跳过内置（已添加）
                if name in BUILTIN_THEMES:
                    continue

                display = name

                # 尝试读取显示名
                try:
                    filepath = os.path.join(self.theme_dir, filename)
                    with open(filepath, encoding='utf-8') as f:
                        data = json.load(f)
                    display = data.get('display_name', name)
                except Exception:
                    pass

                themes.append((name, display))

        return themes

    def get_theme_names(self) -> List[str]:
        """获取所有主题名称"""
        return [name for name, _ in self.list_themes()]

    def theme_exists(self, name: str) -> bool:
        """检查主题是否存在"""
        if name in BUILTIN_THEMES:
            return True

        filepath = os.path.join(self.theme_dir, f"{name}.json")
        return os.path.exists(filepath)

    def get_current_theme(self) -> Optional[Theme]:
        """获取当前主题"""
        return self.current_theme

    def clear_cache(self):
        """清空缓存"""
        self._theme_cache.clear()

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出加载器信息"""
        lines = ["ThemeLoader", "=" * 60]
        lines.append(f"主题目录: {self.theme_dir}")

        if self.current_theme:
            lines.append(f"当前主题: {self.current_theme.name} "
                         f"({self.current_theme.display_name})")
            lines.append(f"主题类型: {self.current_theme.type}")

        themes = self.list_themes()
        lines.append(f"可用主题: {len(themes)} 个")

        for name, display in themes:
            marker = " ← 当前" if (
                self.current_theme and self.current_theme.name == name
            ) else ""
            lines.append(f"  • {name} ({display}){marker}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        current = self.current_theme.name if self.current_theme else None
        return f"<ThemeLoader current={current}>"


# ============================================================
# 主题管理器
# ============================================================
class ThemeManager(QObject):
    """
    主题管理器。

    在 ThemeLoader 基础上提供:
    - 主题切换的持久化
    - 主题切换信号
    - 多编辑器批量应用
    - 跟随系统主题的自动切换
    """

    theme_changed = pyqtSignal(str)  # 主题名称

    def __init__(self, app=None, parent: Optional[QObject] = None,
                 theme_dir: str = DEFAULT_THEME_DIR):
        super().__init__(parent)

        self.app = app
        self.loader = ThemeLoader(self, theme_dir=theme_dir)
        self._editors: List[Any] = []
        self._follow_system = False

        # 连接信号
        self.loader.theme_applied.connect(self._on_theme_applied)

        # 加载设置
        self._settings = QSettings("QingCao", "Editor")
        self._load_settings()

    def _load_settings(self):
        """加载设置"""
        try:
            self._follow_system = self._settings.value(
                "theme_follow_system", True, type=bool
            )
        except Exception:
            pass

    # --------------------------------------------------------
    # 编辑器注册
    # --------------------------------------------------------
    def register_editor(self, editor):
        """注册编辑器"""
        if editor not in self._editors:
            self._editors.append(editor)
            # 立即应用当前主题
            if self.loader.current_theme:
                self.loader.apply(editor, self.loader.current_theme)

    def unregister_editor(self, editor):
        """注销编辑器"""
        if editor in self._editors:
            self._editors.remove(editor)

    def clear_editors(self):
        """清空编辑器列表"""
        self._editors.clear()

    # --------------------------------------------------------
    # 切换主题
    # --------------------------------------------------------
    def switch_theme(self, name_or_path: str) -> bool:
        """切换主题"""
        success = self.loader.switch_theme(name_or_path)

        if success:
            theme = self.loader.current_theme

            # 应用到所有注册的编辑器
            for editor in self._editors:
                try:
                    self.loader.apply(editor, theme)
                except Exception:
                    pass

            # 应用 QSS
            if self.app:
                self.loader.apply_qss(self.app, theme)

        return success

    def _on_theme_applied(self, name: str):
        """主题应用回调"""
        self.theme_changed.emit(name)

    def initialize(self, default_theme: str = "dark_night"):
        """初始化：加载设置中的主题或默认主题"""
        try:
            # 优先跟随系统
            if self._follow_system and self.app:
                self.loader.apply_system_theme(
                    self.app,
                    self._editors[0] if self._editors else None,
                )
                return

            # 从设置加载
            saved_name = self._settings.value("theme_name", "", type=str)

            if saved_name and self.loader.theme_exists(saved_name):
                self.switch_theme(saved_name)
            else:
                self.switch_theme(default_theme)

        except Exception as e:
            print(f"[ThemeManager] 初始化失败: {e}")
            self.switch_theme(default_theme)

    # --------------------------------------------------------
    # 跟随系统
    # --------------------------------------------------------
    def set_follow_system(self, follow: bool):
        """设置是否跟随系统"""
        self._follow_system = follow

        try:
            self._settings.setValue("theme_follow_system", follow)
        except Exception:
            pass

        if follow and self.app:
            self.loader.apply_system_theme(
                self.app,
                self._editors[0] if self._editors else None,
            )

    def is_following_system(self) -> bool:
        """是否跟随系统"""
        return self._follow_system

    # --------------------------------------------------------
    # 查询
    # --------------------------------------------------------
    def get_current_theme(self) -> Optional[Theme]:
        """获取当前主题"""
        return self.loader.current_theme

    def list_themes(self) -> List[Tuple[str, str]]:
        """列出所有主题"""
        return self.loader.list_themes()

    def dump(self) -> str:
        """导出信息"""
        lines = ["ThemeManager", "=" * 60]
        lines.append(f"跟随系统: {self._follow_system}")
        lines.append(f"编辑器数: {len(self._editors)}")
        lines.append("")
        lines.append(self.loader.dump())
        return "\n".join(lines)


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys
    import tempfile

    from PyQt5.Qsci import QsciLexerPython, QsciScintilla
    from PyQt5.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)

    # 创建主窗口
    win = QMainWindow()
    win.setWindowTitle("ThemeLoader 测试")
    win.resize(900, 700)

    # 创建编辑器
    editor = QsciScintilla()
    editor.setUtf8(True)
    editor.setLexer(QsciLexerPython())
    editor.setMarginType(0, QsciScintilla.NumberMargin)
    editor.setMarginWidth(0, 50)
    editor.setFolding(QsciScintilla.BoxedFoldStyle)

    # 测试内容
    test_code = '''#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os


class MyClass:
    """示例类"""
    
    def __init__(self, value):
        self.value = value
    
    def get_value(self):
        return self.value


def main():
    """主函数"""
    obj = MyClass(42)
    print(f"Value: {obj.get_value()}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
'''

    editor.setText(test_code)
    win.setCentralWidget(editor)
    win.show()

    # 创建加载器
    # F821 修复：QTimer 在此处被使用但未导入（原代码把
    # `from PyQt5.QtCore import QTimer` 放在使用之后的文件末尾），
    # 直接运行本文件的自测块会 NameError。
    from PyQt5.QtCore import QTimer

    loader = ThemeLoader()

    # 连接信号
    loader.theme_loaded.connect(
        lambda name: print(f"[信号] 主题加载: {name}")
    )
    loader.theme_applied.connect(
        lambda name: print(f"[信号] 主题应用: {name}")
    )

    print("=== ThemeLoader 测试 ===")
    print(loader.dump())
    print()

    # 测试各内置主题
    themes_to_test = ["dark_night", "light_clean", "eye_protect", "high_contrast"]

    def test_themes():
        for theme_name in themes_to_test:
            print(f"测试主题: {theme_name}")

            theme = loader.load_by_name(theme_name)
            if theme:
                loader.apply(editor, theme)
                loader.apply_qss(app, theme)

                print(f"  ✓ {theme.display_name} ({theme.type})")
                print(f"    背景: {theme.colors.background}")
                print(f"    前景: {theme.colors.foreground}")
            else:
                print("  ✗ 加载失败")

            app.processEvents()

    # 定时切换测试
    QTimer.singleShot(1000, test_themes)

    def cleanup_and_quit():
        print()
        print(loader.dump())
        app.quit()

    QTimer.singleShot(5000, cleanup_and_quit)


    sys.exit(app.exec())