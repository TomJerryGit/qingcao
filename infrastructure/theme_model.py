# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
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
            add(
                os.path.join(
                    os.path.dirname(os.path.abspath(sys.executable)), "_internal", "themes"
                )
            )
        except Exception:
            pass

    # 源码运行：<仓库根>/themes（本文件在 infrastructure/ 下）
    try:
        add(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "themes"))
    except Exception:
        pass

    # 兜底：exe / 脚本同级
    try:
        add(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "themes"))
    except Exception:
        pass

    return dirs


def find_theme_file(
    name: str,
    primary: str = DEFAULT_THEME_DIR,
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

    DARK = "dark"  # 深色
    LIGHT = "light"  # 浅色
    HIGH_CONTRAST = "high_contrast"  # 高对比度


@dataclass
class ThemeColors:
    """
    主题配色方案。

    定义所有 UI 元素的颜色。
    """

    # ============ 编辑器基础 ============
    background: str = "#1e1e1e"  # 编辑器背景
    foreground: str = "#d4d4d4"  # 编辑器前景（文字）
    caret: str = "#aeafad"  # 光标颜色
    current_line: str = "#2b2b2b"  # 当前行高亮
    selection: str = "#264f78"  # 选区背景
    selection_foreground: str = "#ffffff"

    # ============ 行号与边距 ============
    line_number_bg: str = "#2d2d2d"  # 行号背景
    line_number_fg: str = "#858585"  # 行号前景
    line_number_active_fg: str = "#c6c6c6"  # 活动行行号前景
    margin_bg: str = "#2d2d2d"  # 边距背景
    margin_fg: str = "#858585"  # 边距前景
    fold_margin_bg: str = "#2d2d2d"  # 折叠边距背景
    fold_margin_fg: str = "#858585"  # 折叠边距前景

    # ============ 语法高亮 ============
    comment: str = "#6a9955"  # 注释
    keyword: str = "#569cd6"  # 关键字
    number: str = "#b5cea8"  # 数字
    string: str = "#ce9178"  # 字符串
    character: str = "#ce9178"  # 字符
    operator: str = "#d4d4d4"  # 运算符
    identifier: str = "#d4d4d4"  # 标识符
    class_name: str = "#4ec9b0"  # 类名
    function_name: str = "#dcdcaa"  # 函数名
    decorator: str = "#c586c0"  # 装饰器
    tag: str = "#569cd6"  # HTML/XML 标签
    attribute: str = "#9cdcfe"  # 属性
    regex: str = "#d16969"  # 正则表达式

    # ============ 特殊标记 ============
    brace_light_fg: str = "#ffd700"  # 匹配括号前景
    brace_light_bg: str = "#444400"  # 匹配括号背景
    brace_bad_fg: str = "#ff0000"  # 不匹配括号
    indent_guide: str = "#404040"  # 缩进辅助线
    control_char: str = "#888888"  # 控制字符

    # ============ 搜索与高亮 ============
    search_highlight: str = "#ffff00"  # 搜索高亮
    search_current: str = "#ff8000"  # 当前匹配
    smart_highlight: str = "#646464"  # 智能高亮
    error_underline: str = "#f14c4c"  # 错误波浪线
    warning_underline: str = "#f0ad4e"  # 警告波浪线

    # ============ UI 元素 ============
    window_bg: str = "#1e1e1e"  # 窗口背景
    window_fg: str = "#d4d4d4"  # 窗口文字
    menubar_bg: str = "#252526"  # 菜单栏背景
    menubar_fg: str = "#d4d4d4"  # 菜单栏文字
    menu_bg: str = "#2d2d2d"  # 菜单背景
    menu_fg: str = "#d4d4d4"  # 菜单文字
    menu_selection: str = "#094771"  # 菜单选中
    toolbar_bg: str = "#252526"  # 工具栏背景
    statusbar_bg: str = "#007acc"  # 状态栏背景
    statusbar_fg: str = "#ffffff"  # 状态栏文字
    tab_bg: str = "#2d2d2d"  # 标签背景
    tab_fg: str = "#cccccc"  # 标签文字
    tab_active_bg: str = "#1e1e1e"  # 活动标签背景
    tab_active_fg: str = "#ffffff"  # 活动标签文字
    panel_bg: str = "#252526"  # 面板背景
    panel_fg: str = "#d4d4d4"  # 面板文字
    border: str = "#3c3c3c"  # 边框颜色
    scrollbar_bg: str = "#2b2b2b"  # 滚动条背景
    scrollbar_fg: str = "#555555"  # 滚动条滑块
    scrollbar_hover: str = "#777777"  # 滚动条滑块悬停

    # ============ 按钮与输入 ============
    button_bg: str = "#0e639c"  # 按钮背景
    button_fg: str = "#ffffff"  # 按钮文字
    button_hover: str = "#1177bb"  # 按钮悬停
    button_pressed: str = "#0a4d7a"  # 按钮按下
    input_bg: str = "#3c3c3c"  # 输入框背景
    input_fg: str = "#d4d4d4"  # 输入框文字
    input_border: str = "#555555"  # 输入框边框
    input_focus: str = "#007acc"  # 输入框焦点

    # ============ 强调色 ============
    accent: str = "#7ec850"  # 强调色（青草绿）
    accent_hover: str = "#9ed870"  # 强调色悬停
    warning: str = "#f0ad4e"  # 警告
    error: str = "#f14c4c"  # 错误
    success: str = "#7ec850"  # 成功
    info: str = "#4dabf7"  # 信息

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
    def from_dict(cls, d: Dict[str, str]) -> "ThemeColors":
        """从字典反序列化"""
        colors = cls()
        for key, value in d.items():
            if hasattr(colors, key) and isinstance(value, str):
                setattr(colors, key, value)
        return colors


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
            "name": self.name,
            "display_name": self.display_name,
            "type": self.type,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "colors": self.colors.to_dict(),
            "font_family": self.font_family,
            "font_size": self.font_size,
            "font_ligatures": self.font_ligatures,
            "qss": self.qss,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Theme":
        """从字典反序列化"""
        theme = cls()

        # 元数据
        theme.name = d.get("name", "未命名")
        theme.display_name = d.get("display_name", theme.name)
        theme.type = d.get("type", ThemeType.DARK.value)
        theme.version = d.get("version", THEME_FORMAT_VERSION)
        theme.author = d.get("author", "")
        theme.description = d.get("description", "")
        theme.created_at = d.get("created_at", "")
        theme.updated_at = d.get("updated_at", "")

        # 颜色
        colors_data = d.get("colors", {})
        if isinstance(colors_data, dict):
            theme.colors = ThemeColors.from_dict(colors_data)

        # 字体
        theme.font_family = d.get("font_family", "Consolas")
        theme.font_size = d.get("font_size", 12)
        theme.font_ligatures = d.get("font_ligatures", False)

        # QSS
        theme.qss = d.get("qss", "")

        # 保留原始数据
        theme._raw = dict(d)

        return theme

    def save(self, filepath: str) -> bool:
        """保存主题到文件"""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)

            self.updated_at = datetime.datetime.now().isoformat()

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

            return True

        except Exception as e:
            print(f"[Theme] 保存失败: {e}")
            return False

    @classmethod
    def load(cls, filepath: str) -> Optional["Theme"]:
        """从文件加载主题"""
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)

            theme = cls.from_dict(data)
            theme._raw["_filepath"] = filepath

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

    def clone(self, new_name: str = "") -> "Theme":
        """创建副本"""
        new_theme = Theme.from_dict(self.to_dict())
        if new_name:
            new_theme.name = new_name
            new_theme.display_name = new_name
        new_theme.created_at = datetime.datetime.now().isoformat()
        return new_theme

    def __repr__(self) -> str:
        return f"<Theme {self.name} type={self.type}>"


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
        ("#252526", c.panel_bg),
        ("#1e1e1e", c.background),
        ("#2d2d2d", c.menubar_bg),
        ("#3c3c3c", c.border),
        ("#d4d4d4", c.foreground),
        ("#cccccc", c.tab_fg),
        ("#888888", c.line_number_fg),
        ("#666666", c.line_number_fg),
        ("#555555", c.input_border),
        ("#888", c.line_number_fg),
        ("#666", c.line_number_fg),
        ("#555", c.input_border),
        ("#094771", c.menu_selection),
        ("#7ec850", c.accent),
        ("#0e639c", c.button_bg),
        ("#1177bb", c.button_hover),
        ("#f14c4c", c.error),
        ("#f0ad4e", c.warning),
        ("#4dabf7", c.info),
        # ==== A: 补充 ====
        # 终端/控制台背景（关键）
        ("#0d0d0d", c.background),
        # 目录树 hover
        ("#2a2d2e", c.panel_bg),
        # 面板变体
        ("#333333", c.panel_bg),
        ("#4c4c4c", c.border),
        # 次要文字
        ("#858585", c.line_number_fg),
        ("#808080", c.line_number_fg),
        ("#c0c0c0", c.tab_fg),
        # 缩进辅助线
        ("#404040", c.indent_guide),
        # 禁用/危险按钮
        ("#5a5a5a", c.border),
        ("#8f1e1e", c.error),
        # A(最终): 补齐 QSS 遗漏的颜色
        # #007acc 是 QCheckBox::indicator:checked / :focus、
        # QLineEdit:focus 等大量控件的聚焦色，之前未覆盖
        ("#007acc", c.input_focus),
        # 更多常见遗漏
        ("#0a4d7a", c.button_pressed),
        ("#0e639c", c.button_bg),  # 重复保险
        ("#2196f3", c.info),
        ("#4caf50", c.success),
        ("#f44336", c.error),
        ("#ff9800", c.warning),
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
        pattern = re.compile(r"#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}\b")
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
            fn = getattr(widget, "refresh_theme", None)
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
            theme = getattr(obj, "_pending_theme", None)
            if theme is None:
                return False
            try:
                obj._pending_theme = None
            except Exception:
                pass
            fn = getattr(obj, "refresh_theme", None)
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


_LAZY_THEME_FILTER = None
