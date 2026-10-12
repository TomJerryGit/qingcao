#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为用户偏好设置模块，包含：
- Preferences：全局偏好设置管理器
- 字体设置（字体族、字号、行高）
- 缩进设置（Tab宽度、使用空格、自动缩进）
- 编辑设置（自动换行、显示空白、光标闪烁、自动保存）
- 外观设置（主题、配色、行号、折叠标记）
- 行为设置（保存时清理、崩溃恢复、会话恢复）
- 性能设置（大文件阈值、虚拟滚动、搜索线程数）
- 语言与编码设置
- 快捷键相关设置
- 窗口与布局设置
- 导出/导入/重置功能
- 默认值定义
"""

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QObject, QSettings, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont


# ============================================================
# 应用常量
# ============================================================
ORG_NAME = "QingCao"
APP_NAME = "Editor"

# 设置分组前缀（用于 QSettings 中的键名）
PREFIX_GENERAL = "general"
PREFIX_FONT = "font"
PREFIX_INDENT = "indent"
PREFIX_EDITOR = "editor"
PREFIX_APPEARANCE = "appearance"
PREFIX_BEHAVIOR = "behavior"
PREFIX_PERFORMANCE = "performance"
PREFIX_LANGUAGE = "language"
PREFIX_WINDOW = "window"
PREFIX_KEYMAP = "keymap"
PREFIX_PLUGIN = "plugin"
PREFIX_ADVANCED = "advanced"


# ============================================================
# 默认值定义
# ============================================================
DEFAULTS: Dict[str, Any] = {
    # ---- 字体设置 ----
    "font_family": "Consolas",
    "font_family_alt": "Microsoft YaHei",  # 中文回退字体
    "font_size": 12,
    "font_line_height": 0,  # 0 表示自动
    "font_weight": 400,  # 400=Normal, 700=Bold
    "font_italic": False,
    "font_ligatures": False,  # 连字支持
    "font_antialias": True,
    "font_scale": 100,  # 缩放百分比

    # ---- 缩进设置 ----
    "tab_width": 4,
    "indent_use_tabs": False,
    "indent_auto": True,
    "indent_auto_detect": True,
    "indent_backspace_unindent": True,
    "indent_guides": True,
    "indent_rainbow": False,
    "indent_rainbow_colors": [
        "#FF0000", "#FF7F00", "#FFFF00", "#00FF00",
        "#0000FF", "#4B0082", "#9400D3"
    ],

    # ---- 编辑器设置 ----
    "word_wrap": False,
    "word_wrap_mode": "none",  # none / word / char / whitespace
    "word_wrap_column": 80,
    "show_whitespace": False,
    "show_eol": False,
    "show_line_numbers": True,
    "show_folding": True,
    "folding_style": "boxed",  # boxed / cirrus / plain / simple
    "show_current_line": True,
    "current_line_color": "#2b2b2b",
    "show_matching_braces": True,
    "brace_match_color": "#44FF44",
    "caret_width": 1,
    "caret_blink_rate": 500,  # 毫秒
    "caret_line_visible": True,
    "auto_close_brackets": True,
    "auto_close_quotes": True,
    "auto_indent": True,
    "smart_home": True,
    "scroll_past_end": True,
    "scroll_past_end_lines": 10,
    "drag_and_drop": True,
    "mouse_wheel_zoom": True,
    "triple_click_select_line": True,
    "backspace_unindent": True,
    "smooth_scroll": True,
    "cursor_trail": False,
    "smart_highlight": True,
    "smart_highlight_delay": 300,

    # ---- 外观设置 ----
    "theme_path": "",
    "theme_follow_system": True,
    "color_scheme": "dark",  # dark / light / high_contrast
    "sidebar_visible": True,
    "statusbar_visible": True,
    "toolbar_visible": True,
    "menubar_visible": True,
    "minimap_visible": True,
    "minimap_width": 100,
    "minimap_scale": 1,
    "selection_color": "#264F78",
    "line_highlight_color": "#2b2b2b",
    "search_highlight_color": "#FFFF00",
    "search_current_color": "#FF8000",
    "bracket_match_color": "#44FF44",
    "icon_theme": "default",

    # ---- 行为设置 ----
    "auto_save": False,
    "auto_save_interval": 120,  # 秒
    "auto_save_on_focus_loss": False,
    "trim_trailing_whitespace": True,
    "insert_final_newline": True,
    "ensure_single_final_newline": True,
    "auto_reload": True,
    "auto_reload_confirm": True,
    "restore_session": True,
    "restore_undo_history": False,
    "reopen_last_files": True,
    "save_backup": True,
    "backup_dir": "backup",
    "crash_recovery": True,
    "confirm_close_multiple": True,
    "confirm_close_modified": True,
    "confirm_exit": False,
    "default_encoding": "UTF-8",
    "default_line_ending": "auto",  # auto / lf / crlf / cr
    "detect_encoding": True,
    "encoding_confidence": 0.7,
    "follow_symlinks": False,

    # ---- 性能设置 ----
    "large_file_threshold": 10,  # MB
    "huge_file_threshold": 100,  # MB
    "virtual_scroll": True,
    "max_loaded_blocks": 2000,
    "search_threads": 4,
    "search_timeout": 30,  # 秒
    "use_hyperscan": True,
    "cache_lexer_results": True,
    "gc_interval": 50,  # 每N次保存触发GC
    "startup_delay_load": True,
    "splash_screen": True,
    "splash_duration": 800,  # 毫秒
    "delay_plugin_load": True,
    "delay_plugin_ms": 50,

    # ---- 语言设置 ----
    "language": "zh_CN",
    "language_auto_detect": True,
    "date_format": "%Y-%m-%d %H:%M:%S",
    "time_format": "%H:%M:%S",

    # ---- 窗口设置 ----
    "window_width": 1100,
    "window_height": 750,
    "window_x": -1,
    "window_y": -1,
    "window_maximized": False,
    "window_fullscreen": False,
    "remember_geometry": True,
    "remember_layout": True,
    "panel_layout": "{}",  # JSON 字符串
    "splitter_sizes": "[]",  # JSON 字符串
    "recent_files": "[]",  # JSON 字符串
    "recent_projects": "[]",  # JSON 字符串
    "recent_files_max": 15,

    # ---- 快捷键 ----
    "keybindings_file": "keybindings.json",
    "keybindings_custom": "{}",  # JSON 字符串

    # ---- 插件设置 ----
    "plugins_enabled": "{}",  # JSON: {plugin_name: true/false}
    "plugins_disabled": "[]",  # JSON 列表
    # 说明（P0-3）：编辑器的插件运行在**主进程内**，没有进程级
    # 隔离；此开关仅表示是否在 API 边界做权限门控与权限确认。
    "plugin_sandbox": True,
    "plugin_permissions_required": True,
    "plugin_auto_update": True,
    "plugin_update_check_interval": 24,  # 小时
    # P1-2: 监控到插件源码变更后自动重载（热重载）
    "plugin_hot_reload": True,

    # ---- 音效（P1-2 接线）----
    # 说明：修复前 infrastructure/sound_manager.py（1600+ 行）全仓
    # 零调用，是一个从未生效的"死模块"。现在由主窗口在文件打开/
    # 保存/出错时调用；默认关闭以免突然出声打扰用户。
    "sound_effects": False,
    "sound_volume": 0.5,

    # ---- 高级设置 ----
    "debug_mode": False,
    "log_level": "INFO",  # DEBUG / INFO / WARNING / ERROR
    "log_to_file": True,
    "log_max_size": 10,  # MB
    "crash_report": False,
    "telemetry": False,
    "check_update": True,
    "update_channel": "stable",  # stable / beta / dev
    "portable_mode": False,
    "config_sync": False,
    "sync_provider": "gist",  # gist / webdav / custom
    "gist_token": "",
    "gist_id": "",
}


# ============================================================
# 偏好设置类
# ============================================================
class Preferences(QObject):
    """
    全局偏好设置管理器。

    使用 QSettings 存储配置，通过属性访问器读写设置。

    特性:
    - 自动类型转换
    - 设置变更信号
    - 批量读写
    - 导出/导入
    - 重置默认
    - 分组管理
    """

    # 信号：设置项变更（键名, 新值, 旧值）
    changed = pyqtSignal(str, object, object)

    # 信号：批量设置变更（用于事务性操作）
    batch_changed = pyqtSignal(dict)

    def __init__(self, parent: Optional[QObject] = None,
                 portable: bool = False):
        """
        参数:
            parent: 父 QObject
            portable: 是否启用便携模式
        """
        super().__init__(parent)

        self.portable = portable

        # 创建 QSettings
        if portable:
            QSettings.setDefaultFormat(QSettings.IniFormat)
            data_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "data"
            )
            os.makedirs(data_dir, exist_ok=True)
            QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, data_dir)
            self.settings = QSettings(QSettings.IniFormat, QSettings.UserScope,
                                      ORG_NAME, APP_NAME)
        else:
            self.settings = QSettings(ORG_NAME, APP_NAME)

        # 变更记录（用于事务回滚）
        self._transaction_backup: Optional[Dict[str, Any]] = None

        # 延迟保存定时器（避免频繁写盘）
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush)
        self._pending_saves: set = set()

    # ========================================================
    # 底层读写
    # ========================================================
    def get(self, key: str, default: Any = None, type_hint: type = None) -> Any:
        """
        读取设置值。

        参数:
            key: 设置键
            default: 默认值（若为 None 则使用 DEFAULTS 中的值）
            type_hint: 类型提示（可选）

        返回:
            设置值
        """
        if default is None:
            default = DEFAULTS.get(key)

        # 特殊处理 JSON 存储的复杂类型
        if isinstance(default, (list, dict)):
            raw = self.settings.value(key, None)
            if raw is None:
                return default
            if isinstance(raw, (list, dict)):
                return raw
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return default

        # 布尔类型特殊处理
        if isinstance(default, bool):
            return self.settings.value(key, default, type=bool)

        # 整数
        if isinstance(default, int) and not isinstance(default, bool):
            return self.settings.value(key, default, type=int)

        # 浮点数
        if isinstance(default, float):
            return self.settings.value(key, default, type=float)

        # 其他类型
        return self.settings.value(key, default)

    def set(self, key: str, value: Any, notify: bool = True,
            save_immediately: bool = False):
        """
        写入设置值。

        参数:
            key: 设置键
            value: 值
            notify: 是否发射变更信号
            save_immediately: 是否立即写盘
        """
        old_value = self.get(key)

        # 复杂类型转为 JSON 字符串
        if isinstance(value, (list, dict)):
            self.settings.setValue(key, json.dumps(value, ensure_ascii=False))
        else:
            self.settings.setValue(key, value)

        # 发射信号
        if notify and old_value != value:
            self.changed.emit(key, value, old_value)

        # 延迟保存
        if save_immediately:
            self.settings.sync()
        else:
            self._pending_saves.add(key)
            self._save_timer.start(500)

    def _flush(self):
        """实际写盘"""
        if self._pending_saves:
            self.settings.sync()
            self._pending_saves.clear()

    def sync(self):
        """立即同步到磁盘"""
        self._save_timer.stop()
        self._flush()

    def remove(self, key: str):
        """删除设置项"""
        self.settings.remove(key)

    def contains(self, key: str) -> bool:
        """检查设置项是否存在"""
        return self.settings.contains(key)

    def all_keys(self) -> List[str]:
        """获取所有已存储的键"""
        return self.settings.allKeys()

    def clear(self):
        """清空所有设置"""
        self.settings.clear()

    # ========================================================
    # 属性访问器（字体）
    # ========================================================
    @property
    def font_family(self) -> str:
        return self.get("font_family")

    @font_family.setter
    def font_family(self, value: str):
        self.set("font_family", value)

    @property
    def font_family_alt(self) -> str:
        return self.get("font_family_alt")

    @font_family_alt.setter
    def font_family_alt(self, value: str):
        self.set("font_family_alt", value)

    @property
    def font_size(self) -> int:
        return self.get("font_size")

    @font_size.setter
    def font_size(self, value: int):
        self.set("font_size", max(6, min(72, value)))

    @property
    def font_line_height(self) -> int:
        return self.get("font_line_height")

    @font_line_height.setter
    def font_line_height(self, value: int):
        self.set("font_line_height", max(0, value))

    @property
    def font_weight(self) -> int:
        return self.get("font_weight")

    @font_weight.setter
    def font_weight(self, value: int):
        self.set("font_weight", value)

    @property
    def font_italic(self) -> bool:
        return self.get("font_italic")

    @font_italic.setter
    def font_italic(self, value: bool):
        self.set("font_italic", value)

    @property
    def font_ligatures(self) -> bool:
        return self.get("font_ligatures")

    @font_ligatures.setter
    def font_ligatures(self, value: bool):
        self.set("font_ligatures", value)

    @property
    def font_antialias(self) -> bool:
        return self.get("font_antialias")

    @font_antialias.setter
    def font_antialias(self, value: bool):
        self.set("font_antialias", value)

    @property
    def font_scale(self) -> int:
        return self.get("font_scale")

    @font_scale.setter
    def font_scale(self, value: int):
        self.set("font_scale", max(50, min(300, value)))

    # ========================================================
    # 属性访问器（缩进）
    # ========================================================
    @property
    def tab_width(self) -> int:
        return self.get("tab_width")

    @tab_width.setter
    def tab_width(self, value: int):
        self.set("tab_width", max(1, min(16, value)))

    @property
    def indent_use_tabs(self) -> bool:
        return self.get("indent_use_tabs")

    @indent_use_tabs.setter
    def indent_use_tabs(self, value: bool):
        self.set("indent_use_tabs", value)

    @property
    def indent_auto(self) -> bool:
        return self.get("indent_auto")

    @indent_auto.setter
    def indent_auto(self, value: bool):
        self.set("indent_auto", value)

    @property
    def indent_auto_detect(self) -> bool:
        return self.get("indent_auto_detect")

    @indent_auto_detect.setter
    def indent_auto_detect(self, value: bool):
        self.set("indent_auto_detect", value)

    @property
    def indent_guides(self) -> bool:
        return self.get("indent_guides")

    @indent_guides.setter
    def indent_guides(self, value: bool):
        self.set("indent_guides", value)

    @property
    def indent_rainbow(self) -> bool:
        return self.get("indent_rainbow")

    @indent_rainbow.setter
    def indent_rainbow(self, value: bool):
        self.set("indent_rainbow", value)

    @property
    def indent_rainbow_colors(self) -> List[str]:
        return self.get("indent_rainbow_colors")

    @indent_rainbow_colors.setter
    def indent_rainbow_colors(self, value: List[str]):
        self.set("indent_rainbow_colors", value)

    # ========================================================
    # 属性访问器（编辑器）
    # ========================================================
    @property
    def word_wrap(self) -> bool:
        return self.get("word_wrap")

    @word_wrap.setter
    def word_wrap(self, value: bool):
        self.set("word_wrap", value)

    @property
    def word_wrap_mode(self) -> str:
        return self.get("word_wrap_mode")

    @word_wrap_mode.setter
    def word_wrap_mode(self, value: str):
        self.set("word_wrap_mode", value)

    @property
    def show_whitespace(self) -> bool:
        return self.get("show_whitespace")

    @show_whitespace.setter
    def show_whitespace(self, value: bool):
        self.set("show_whitespace", value)

    @property
    def show_eol(self) -> bool:
        return self.get("show_eol")

    @show_eol.setter
    def show_eol(self, value: bool):
        self.set("show_eol", value)

    @property
    def show_line_numbers(self) -> bool:
        return self.get("show_line_numbers")

    @show_line_numbers.setter
    def show_line_numbers(self, value: bool):
        self.set("show_line_numbers", value)

    @property
    def show_folding(self) -> bool:
        return self.get("show_folding")

    @show_folding.setter
    def show_folding(self, value: bool):
        self.set("show_folding", value)

    @property
    def show_current_line(self) -> bool:
        return self.get("show_current_line")

    @show_current_line.setter
    def show_current_line(self, value: bool):
        self.set("show_current_line", value)

    @property
    def show_matching_braces(self) -> bool:
        return self.get("show_matching_braces")

    @show_matching_braces.setter
    def show_matching_braces(self, value: bool):
        self.set("show_matching_braces", value)

    @property
    def caret_width(self) -> int:
        return self.get("caret_width")

    @caret_width.setter
    def caret_width(self, value: int):
        self.set("caret_width", max(1, min(5, value)))

    @property
    def caret_blink_rate(self) -> int:
        return self.get("caret_blink_rate")

    @caret_blink_rate.setter
    def caret_blink_rate(self, value: int):
        self.set("caret_blink_rate", max(0, value))

    @property
    def auto_close_brackets(self) -> bool:
        return self.get("auto_close_brackets")

    @auto_close_brackets.setter
    def auto_close_brackets(self, value: bool):
        self.set("auto_close_brackets", value)

    @property
    def auto_close_quotes(self) -> bool:
        return self.get("auto_close_quotes")

    @auto_close_quotes.setter
    def auto_close_quotes(self, value: bool):
        self.set("auto_close_quotes", value)

    @property
    def smart_home(self) -> bool:
        return self.get("smart_home")

    @smart_home.setter
    def smart_home(self, value: bool):
        self.set("smart_home", value)

    @property
    def smooth_scroll(self) -> bool:
        return self.get("smooth_scroll")

    @smooth_scroll.setter
    def smooth_scroll(self, value: bool):
        self.set("smooth_scroll", value)

    @property
    def cursor_trail(self) -> bool:
        return self.get("cursor_trail")

    @cursor_trail.setter
    def cursor_trail(self, value: bool):
        self.set("cursor_trail", value)

    @property
    def smart_highlight(self) -> bool:
        return self.get("smart_highlight")

    @smart_highlight.setter
    def smart_highlight(self, value: bool):
        self.set("smart_highlight", value)

    # ========================================================
    # 属性访问器（外观）
    # ========================================================
    @property
    def theme_path(self) -> str:
        return self.get("theme_path")

    @theme_path.setter
    def theme_path(self, value: str):
        self.set("theme_path", value)

    @property
    def theme_follow_system(self) -> bool:
        return self.get("theme_follow_system")

    @theme_follow_system.setter
    def theme_follow_system(self, value: bool):
        self.set("theme_follow_system", value)

    @property
    def color_scheme(self) -> str:
        return self.get("color_scheme")

    @color_scheme.setter
    def color_scheme(self, value: str):
        self.set("color_scheme", value)

    @property
    def minimap_visible(self) -> bool:
        return self.get("minimap_visible")

    @minimap_visible.setter
    def minimap_visible(self, value: bool):
        self.set("minimap_visible", value)

    @property
    def minimap_width(self) -> int:
        return self.get("minimap_width")

    @minimap_width.setter
    def minimap_width(self, value: int):
        self.set("minimap_width", max(50, min(300, value)))

    # ========================================================
    # 属性访问器（行为）
    # ========================================================
    @property
    def auto_save(self) -> bool:
        return self.get("auto_save")

    @auto_save.setter
    def auto_save(self, value: bool):
        self.set("auto_save", value)

    @property
    def auto_save_interval(self) -> int:
        return self.get("auto_save_interval")

    @auto_save_interval.setter
    def auto_save_interval(self, value: int):
        self.set("auto_save_interval", max(10, value))

    @property
    def trim_trailing_whitespace(self) -> bool:
        return self.get("trim_trailing_whitespace")

    @trim_trailing_whitespace.setter
    def trim_trailing_whitespace(self, value: bool):
        self.set("trim_trailing_whitespace", value)

    @property
    def insert_final_newline(self) -> bool:
        return self.get("insert_final_newline")

    @insert_final_newline.setter
    def insert_final_newline(self, value: bool):
        self.set("insert_final_newline", value)

    @property
    def auto_reload(self) -> bool:
        return self.get("auto_reload")

    @auto_reload.setter
    def auto_reload(self, value: bool):
        self.set("auto_reload", value)

    @property
    def restore_session(self) -> bool:
        return self.get("restore_session")

    @restore_session.setter
    def restore_session(self, value: bool):
        self.set("restore_session", value)

    @property
    def crash_recovery(self) -> bool:
        return self.get("crash_recovery")

    @crash_recovery.setter
    def crash_recovery(self, value: bool):
        self.set("crash_recovery", value)

    @property
    def default_encoding(self) -> str:
        return self.get("default_encoding")

    @default_encoding.setter
    def default_encoding(self, value: str):
        self.set("default_encoding", value)

    @property
    def default_line_ending(self) -> str:
        return self.get("default_line_ending")

    @default_line_ending.setter
    def default_line_ending(self, value: str):
        self.set("default_line_ending", value)

    # ========================================================
    # 属性访问器（性能）
    # ========================================================
    @property
    def large_file_threshold(self) -> int:
        return self.get("large_file_threshold")

    @large_file_threshold.setter
    def large_file_threshold(self, value: int):
        self.set("large_file_threshold", max(1, value))

    @property
    def huge_file_threshold(self) -> int:
        return self.get("huge_file_threshold")

    @huge_file_threshold.setter
    def huge_file_threshold(self, value: int):
        self.set("huge_file_threshold", max(10, value))

    @property
    def virtual_scroll(self) -> bool:
        return self.get("virtual_scroll")

    @virtual_scroll.setter
    def virtual_scroll(self, value: bool):
        self.set("virtual_scroll", value)

    @property
    def search_threads(self) -> int:
        return self.get("search_threads")

    @search_threads.setter
    def search_threads(self, value: int):
        self.set("search_threads", max(1, min(16, value)))

    @property
    def use_hyperscan(self) -> bool:
        return self.get("use_hyperscan")

    @use_hyperscan.setter
    def use_hyperscan(self, value: bool):
        self.set("use_hyperscan", value)

    # ========================================================
    # 属性访问器（语言）
    # ========================================================
    @property
    def language(self) -> str:
        return self.get("language")

    @language.setter
    def language(self, value: str):
        self.set("language", value)

    @property
    def date_format(self) -> str:
        return self.get("date_format")

    @date_format.setter
    def date_format(self, value: str):
        self.set("date_format", value)

    # ========================================================
    # 属性访问器（窗口）
    # ========================================================
    @property
    def window_width(self) -> int:
        return self.get("window_width")

    @window_width.setter
    def window_width(self, value: int):
        self.set("window_width", max(400, value))

    @property
    def window_height(self) -> int:
        return self.get("window_height")

    @window_height.setter
    def window_height(self, value: int):
        self.set("window_height", max(300, value))

    @property
    def remember_geometry(self) -> bool:
        return self.get("remember_geometry")

    @remember_geometry.setter
    def remember_geometry(self, value: bool):
        self.set("remember_geometry", value)

    @property
    def remember_layout(self) -> bool:
        return self.get("remember_layout")

    @remember_layout.setter
    def remember_layout(self, value: bool):
        self.set("remember_layout", value)

    # ========================================================
    # 属性访问器（插件）
    # ========================================================
    @property
    def plugin_sandbox(self) -> bool:
        return self.get("plugin_sandbox")

    @plugin_sandbox.setter
    def plugin_sandbox(self, value: bool):
        self.set("plugin_sandbox", value)

    @property
    def plugin_hot_reload(self) -> bool:
        """P1-2: 插件热重载开关"""
        return self.get("plugin_hot_reload")

    @plugin_hot_reload.setter
    def plugin_hot_reload(self, value: bool):
        self.set("plugin_hot_reload", value)

    @property
    def sound_effects(self) -> bool:
        """P1-2: 操作音效开关"""
        return self.get("sound_effects")

    @sound_effects.setter
    def sound_effects(self, value: bool):
        self.set("sound_effects", value)

    @property
    def plugin_auto_update(self) -> bool:
        return self.get("plugin_auto_update")

    @plugin_auto_update.setter
    def plugin_auto_update(self, value: bool):
        self.set("plugin_auto_update", value)

    # ========================================================
    # 属性访问器（高级）
    # ========================================================
    @property
    def debug_mode(self) -> bool:
        return self.get("debug_mode")

    @debug_mode.setter
    def debug_mode(self, value: bool):
        self.set("debug_mode", value)

    @property
    def log_level(self) -> str:
        return self.get("log_level")

    @log_level.setter
    def log_level(self, value: str):
        self.set("log_level", value)

    @property
    def check_update(self) -> bool:
        return self.get("check_update")

    @check_update.setter
    def check_update(self, value: bool):
        self.set("check_update", value)

    @property
    def update_channel(self) -> str:
        return self.get("update_channel")

    @update_channel.setter
    def update_channel(self, value: str):
        self.set("update_channel", value)

    @property
    def portable_mode(self) -> bool:
        return self.get("portable_mode")

    @portable_mode.setter
    def portable_mode(self, value: bool):
        self.set("portable_mode", value)

    @property
    def config_sync(self) -> bool:
        return self.get("config_sync")

    @config_sync.setter
    def config_sync(self, value: bool):
        self.set("config_sync", value)

    # ========================================================
    # 字体构造
    # ========================================================
    def build_font(self, extra_size: int = 0) -> QFont:
        """
        根据当前偏好构建 QFont 对象。

        参数:
            extra_size: 相对字号增量（如 +1 或 -1）

        返回:
            QFont 实例
        """
        font = QFont(self.font_family, self.font_size + extra_size)
        font.setWeight(self.font_weight)
        font.setItalic(self.font_italic)
        if self.font_ligatures:
            try:
                font.setStyleStrategy(QFont.PreferAntialias)
                font.setStyleHint(QFont.Monospace)
            except Exception:
                pass
        return font

    # ========================================================
    # 批量操作
    # ========================================================
    def get_all(self) -> Dict[str, Any]:
        """获取所有设置项及其当前值"""
        result = {}
        for key, default in DEFAULTS.items():
            result[key] = self.get(key)
        return result

    def set_all(self, values: Dict[str, Any], notify: bool = True):
        """批量设置"""
        for key, value in values.items():
            if key in DEFAULTS:
                self.set(key, value, notify=notify)
        if notify:
            self.batch_changed.emit(values)

    def begin_transaction(self):
        """开始事务（备份当前设置）"""
        self._transaction_backup = self.get_all()

    def commit_transaction(self):
        """提交事务"""
        self._transaction_backup = None

    def rollback_transaction(self):
        """回滚事务"""
        if self._transaction_backup:
            self.set_all(self._transaction_backup, notify=True)
            self._transaction_backup = None

    # ========================================================
    # 导出/导入
    # ========================================================
    def export_json(self, filepath: str) -> bool:
        """
        导出设置为 JSON 文件。

        参数:
            filepath: 导出路径

        返回:
            是否成功
        """
        try:
            data = {
                'version': 2,
                'app': 'QingCao Editor',
                'exported_at': __import__('datetime').datetime.now().isoformat(),
                'settings': self.get_all()
            }
            os.makedirs(os.path.dirname(os.path.abspath(filepath)) or '.', exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[Preferences] 导出失败: {e}")
            return False

    def import_json(self, filepath: str, merge: bool = True) -> bool:
        """
        从 JSON 文件导入设置。

        参数:
            filepath: 文件路径
            merge: True 表示合并（仅覆盖提供的键），False 表示完全替换

        返回:
            是否成功
        """
        try:
            with open(filepath, encoding='utf-8') as f:
                data = json.load(f)

            settings = data.get('settings', data)
            if not isinstance(settings, dict):
                return False

            if not merge:
                self.reset_to_defaults()

            for key, value in settings.items():
                if key in DEFAULTS:
                    self.set(key, value, notify=False)

            self.batch_changed.emit(settings)
            self.sync()
            return True
        except Exception as e:
            print(f"[Preferences] 导入失败: {e}")
            return False

    def export_zip(self, filepath: str) -> bool:
        """
        导出完整配置包（设置 + 快捷键 + 主题 + 插件列表）为 ZIP。

        参数:
            filepath: ZIP 路径

        返回:
            是否成功
        """
        try:
            import zipfile
            with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
                # 设置
                settings_json = json.dumps(self.get_all(), indent=2, ensure_ascii=False)
                zf.writestr('settings.json', settings_json)

                # 快捷键
                kb_path = self.get("keybindings_file", "keybindings.json")
                if os.path.exists(kb_path):
                    zf.write(kb_path, 'keybindings.json')

                # 主题
                theme_path = self.theme_path
                if theme_path and os.path.exists(theme_path):
                    zf.write(theme_path, f"themes/{os.path.basename(theme_path)}")

                # 插件列表
                plugins_disabled = self.get("plugins_disabled", [])
                zf.writestr('plugins.json', json.dumps({
                    'disabled': plugins_disabled,
                    'enabled': self.get("plugins_enabled", {})
                }, indent=2))

            return True
        except Exception as e:
            print(f"[Preferences] 导出 ZIP 失败: {e}")
            return False

    def import_zip(self, filepath: str) -> bool:
        """从 ZIP 包导入配置"""
        try:
            import zipfile
            with zipfile.ZipFile(filepath, 'r') as zf:
                names = zf.namelist()
                if 'settings.json' in names:
                    settings = json.loads(zf.read('settings.json'))
                    for key, value in settings.items():
                        if key in DEFAULTS:
                            self.set(key, value, notify=False)
                    self.batch_changed.emit(settings)

                if 'keybindings.json' in names:
                    kb_path = self.get("keybindings_file", "keybindings.json")
                    with open(kb_path, 'wb') as f:
                        f.write(zf.read('keybindings.json'))

                if 'plugins.json' in names:
                    plugins_data = json.loads(zf.read('plugins.json'))
                    if 'disabled' in plugins_data:
                        self.set("plugins_disabled", plugins_data['disabled'])

            self.sync()
            return True
        except Exception as e:
            print(f"[Preferences] 导入 ZIP 失败: {e}")
            return False

    # ========================================================
    # 重置
    # ========================================================
    def reset_to_defaults(self, category: Optional[str] = None):
        """
        重置为默认值。

        参数:
            category: 分类前缀（如 "font_"），None 表示全部重置
        """
        if category is None:
            # 全部重置
            for key in DEFAULTS:
                self.set(key, DEFAULTS[key], notify=False)
            self.batch_changed.emit(DEFAULTS)
        else:
            # 按前缀重置
            changes = {}
            for key, default in DEFAULTS.items():
                if key.startswith(category):
                    self.set(key, default, notify=False)
                    changes[key] = default
            self.batch_changed.emit(changes)
        self.sync()

    def reset_font(self):
        """重置字体设置"""
        self.reset_to_defaults("font_")

    def reset_indent(self):
        """重置缩进设置"""
        self.reset_to_defaults("indent_")

    def reset_editor(self):
        """重置编辑器设置"""
        self.reset_to_defaults("editor_")

    def reset_appearance(self):
        """重置外观设置"""
        for key in ["theme_path", "color_scheme", "minimap_visible",
                    "minimap_width", "selection_color", "icon_theme"]:
            self.set(key, DEFAULTS[key], notify=False)
        self.sync()

    def reset_behavior(self):
        """重置行为设置"""
        self.reset_to_defaults("auto_")
        for key in ["trim_trailing_whitespace", "insert_final_newline",
                    "restore_session", "crash_recovery"]:
            self.set(key, DEFAULTS[key], notify=False)
        self.sync()

    def reset_performance(self):
        """重置性能设置"""
        self.reset_to_defaults("search_")
        for key in ["large_file_threshold", "huge_file_threshold",
                    "virtual_scroll", "use_hyperscan"]:
            self.set(key, DEFAULTS[key], notify=False)
        self.sync()

    # ========================================================
    # 检查默认值
    # ========================================================
    def has_default(self, key: str) -> bool:
        """检查键是否有默认值"""
        return key in DEFAULTS

    def get_default(self, key: str) -> Any:
        """获取键的默认值"""
        return DEFAULTS.get(key)

    def diff_from_defaults(self) -> Dict[str, Any]:
        """
        返回与默认值不同的设置项。

        返回:
            {key: (current_value, default_value)}
        """
        diff = {}
        for key, default in DEFAULTS.items():
            current = self.get(key)
            if current != default:
                diff[key] = (current, default)
        return diff

    # ========================================================
    # 调试与信息
    # ========================================================
    def dump(self) -> str:
        """导出所有设置的可读文本"""
        lines = ["Preferences 当前设置", "=" * 60]
        for key in sorted(DEFAULTS.keys()):
            default = DEFAULTS[key]
            current = self.get(key)
            marker = " *" if current != default else ""
            lines.append(f"  {key:35s} = {current!r}{marker}")
        lines.append("")
        lines.append("（带 * 表示与默认值不同）")
        return "\n".join(lines)

    def get_info(self) -> Dict[str, Any]:
        """获取设置信息摘要"""
        return {
            'total_keys': len(DEFAULTS),
            'modified_count': len(self.diff_from_defaults()),
            'settings_file': self.settings.fileName(),
            'portable': self.portable,
            'font': f"{self.font_family} {self.font_size}pt",
            'theme': self.theme_path or '(默认)',
            'language': self.language,
        }

    def __repr__(self) -> str:
        info = self.get_info()
        return (f"<Preferences {info['modified_count']}/{info['total_keys']} "
                f"modified, font={info['font']}>")


# ============================================================
# 全局单例（延迟初始化）
# ============================================================
_preferences_instance: Optional[Preferences] = None


def get_preferences() -> Preferences:
    """获取全局 Preferences 单例"""
    global _preferences_instance
    if _preferences_instance is None:
        _preferences_instance = Preferences()
    return _preferences_instance


def set_preferences(prefs: Preferences):
    """设置全局 Preferences 实例"""
    global _preferences_instance
    _preferences_instance = prefs


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    prefs = Preferences()

    # 测试读取默认值
    print("默认字体:", prefs.font_family, prefs.font_size)
    print("默认缩进:", prefs.tab_width)
    print("默认自动保存:", prefs.auto_save)
    print()

    # 测试设置
    prefs.font_size = 14
    prefs.auto_save = True
    prefs.tab_width = 2

    print("修改后字体:", prefs.font_family, prefs.font_size)
    print("修改后自动保存:", prefs.auto_save)
    print()

    # 测试变更信号
    def on_changed(key, new, old):
        print(f"  [变更] {key}: {old!r} -> {new!r}")

    prefs.changed.connect(on_changed)
    prefs.font_family = "Fira Code"
    prefs.language = "en_US"
    print()

    # 测试差异
    diff = prefs.diff_from_defaults()
    print(f"与默认值不同的项: {len(diff)} 个")
    for k, (cur, dft) in diff.items():
        print(f"  {k}: {cur!r} (默认 {dft!r})")
    print()

    # 测试信息摘要
    print("设置信息:", prefs.get_info())
    print()

    # 测试全量导出
    print(prefs.dump())

    # 测试重置
    prefs.reset_to_defaults()
    print("重置后字体:", prefs.font_family, prefs.font_size)
    print()

    # 测试构建字体
    font = prefs.build_font()
    print(f"构建的字体: {font.family()} {font.pointSize()}pt 权重{font.weight()}")

    print()
    print(prefs)