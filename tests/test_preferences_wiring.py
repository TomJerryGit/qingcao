# -*- coding: utf-8 -*-
"""
偏好设置接线防线测试（P7）。

背景
----
本项目反复出现同一类缺陷：**首选项里有开关、生产代码从不读取**，
用户改了毫无反应（"假开关"）。本文件把这条不变量变成可自动检测的。

三层断言
--------
1. 本次**删除**的键必须彻底消失：
   - 不在 ``DEFAULTS``
   - 不在 ``Preferences`` 的属性访问器上（``hasattr`` 精确检查）
   - 不在 ``ui/preferences_panel.py`` 的界面项里
   - 不在 ``tests/`` 与 ``tools/`` 中被引用
2. 本次**接线**的键必须确实被生产代码读取（静态断言：键字符串
   出现在接线文件里），并有 SearchOptions 的运行时行为验证。
3. **核心防线**：``DEFAULTS`` 里的每个键，要么出现在首选项面板
   （用户可见），要么作为字符串字面量出现在生产代码里（被读取）。
   两者都没有的键记为"孤儿"，必须落在 ``KNOWN_UNWIRED_ORPHANS``
   基线之内 —— **不允许出现基线之外的新孤儿**（新增假开关即红）。

为什么核心防线用"基线"而不是全量零孤儿断言
------------------------------------------
基线里的孤儿键分布在 ``ui/editor_view.py``、``core/editor.py``、
``ui/main_window.py``、``app/session.py``、``core/content_provider.py``
等文件里，这些文件由 P7 任务之外的写作用域持有，无法在本任务内
接线或删除。基线是**已确认的存量债务清单**，只允许缩小、不允许
扩大；键被接线或删除后必须从基线里移除（见
``test_known_orphan_baseline_is_honest``）。
"""

import os
import re

import pytest
from PyQt5.QtCore import QSettings

from app.preferences import DEFAULTS, Preferences


# ============================================================
# 路径与扫描工具
# ============================================================
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PANEL_PATH = os.path.join(ROOT, "ui", "preferences_panel.py")

#: 生产代码根（相对仓库路径）。只有这些位置的键字符串才算"被应用代码读取"。
PRODUCTION_DIRS = ("app", "core", "infrastructure", "ui", "plugins")
PRODUCTION_FILES = ("main.py",)

#: 声明文件（键的定义处）与首选项面板（UI 处）不算"读取方"，
#: 否则每个键都会因为自己的默认值/界面项而"自证被读取"。
_DECLARATION_REL = "app/preferences.py"
_PANEL_REL = "ui/preferences_panel.py"

#: 匹配字符串字面量里的标识符： "key" / 'key'
_QUOTED_IDENTIFIER = re.compile(r"""["']([A-Za-z_][A-Za-z0-9_]*)["']""")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _production_files():
    """产出所有生产代码 .py 的相对路径（POSIX 风格）。"""
    for name in PRODUCTION_DIRS:
        base = os.path.join(ROOT, name)
        for dirpath, _dirnames, filenames in os.walk(base):
            for filename in filenames:
                if filename.endswith(".py"):
                    full = os.path.join(dirpath, filename)
                    rel = os.path.relpath(full, ROOT)
                    yield rel.replace(os.sep, "/")
    yield from PRODUCTION_FILES


def _referenced_keys():
    """生产代码里以字符串字面量出现的标识符集合。"""
    keys = set()
    for rel in _production_files():
        if rel in (_DECLARATION_REL, _PANEL_REL):
            continue
        keys.update(_QUOTED_IDENTIFIER.findall(_read(os.path.join(ROOT, rel))))
    return keys


def _panel_keys():
    return set(_QUOTED_IDENTIFIER.findall(_read(PANEL_PATH)))


def _orphan_keys():
    """既不在首选项面板、也无生产代码引用的 DEFAULTS 键。"""
    referenced = _referenced_keys()
    panel = _panel_keys()
    return {key for key in DEFAULTS if key not in referenced and key not in panel}


# ============================================================
# P7 数据
# ============================================================
#: 本次删除的"假开关"（半成品 / 零读取 / 价值低）。
#: 注意：app/sync.py 仍然使用同名键 'gist_token'，但那是它**自己的
#: 配置文件**（self.config），与 Preferences 无关，因此不在下面的
#: tests/tools 扫描范围内也不构成悬空引用。
DELETED_KEYS = frozenset({
    "caret_blink_rate",
    "smooth_scroll",
    "virtual_scroll",
    "icon_theme",
    "max_loaded_blocks",
    "cache_lexer_results",
    "startup_delay_load",
    "delay_plugin_load",
    "delay_plugin_ms",
    "config_sync",
    "sync_provider",
    "gist_token",
    "encoding_confidence",
    "follow_symlinks",
    "restore_undo_history",
})

#: 本次接线的键 -> 必须出现该键字符串的接线文件。
WIRED_KEYS = {
    "splash_screen": ("main.py",),
    "splash_duration": ("main.py", "ui/preferences_panel.py"),
    "search_threads": ("core/search.py",),
    "use_hyperscan": ("core/search.py",),
    "search_timeout": ("core/search.py",),
    "log_level": ("main.py",),
    "log_max_size": ("main.py",),
    "language_auto_detect": ("main.py",),
}

#: 已确认的存量孤儿键（P7 之后仍然既无 UI、也无生产代码引用）。
#: 它们分布在 P7 写作用域之外的文件里，属于**已知债务**：
#: 本测试只断言"没有新增孤儿"，不要求这些立刻消失。
KNOWN_UNWIRED_ORPHANS = frozenset({
    # ui/editor_view.py 与 core/editor.py 的编辑体验键（他人写作用域）
    "font_line_height",
    "font_weight",
    "font_italic",
    "font_antialias",
    "font_scale",
    "indent_auto_detect",
    "indent_rainbow_colors",
    "word_wrap_mode",
    "word_wrap_column",
    "folding_style",
    "current_line_color",
    "brace_match_color",
    "caret_line_visible",
    "auto_indent",
    "smart_home",
    "scroll_past_end",
    "scroll_past_end_lines",
    "drag_and_drop",
    "mouse_wheel_zoom",
    "triple_click_select_line",
    "backspace_unindent",
    "smart_highlight_delay",
    # 外观 / 面板可见性（ui/main_window.py, ui/minimap.py）
    "color_scheme",
    "sidebar_visible",
    "minimap_visible",
    "minimap_width",
    "minimap_scale",
    "line_highlight_color",
    "search_highlight_color",
    "search_current_color",
    "bracket_match_color",
    # 行为 / 编码（app/session.py, core/content_provider.py）
    "auto_save_interval",
    "auto_save_on_focus_loss",
    "ensure_single_final_newline",
    "auto_reload",
    "auto_reload_confirm",
    "save_backup",
    "backup_dir",
    "crash_recovery",
    "confirm_close_multiple",
    "confirm_close_modified",
    "confirm_exit",
    "default_encoding",
    "default_line_ending",
    "detect_encoding",
    # 性能
    "huge_file_threshold",
    "gc_interval",
    # 语言 / 时间格式（date_format / time_format 由 P8 任务在
    # core/editor.py 内接线，接线后应从基线移除）
    "date_format",
    "time_format",
    # 窗口几何（ui/main_window.py）
    "window_width",
    "window_height",
    "window_x",
    "window_y",
    "window_maximized",
    "window_fullscreen",
    "remember_geometry",
    "remember_layout",
    "panel_layout",
    "splitter_sizes",
    "recent_files_max",
    # 快捷键 / 插件
    "keybindings_file",
    "keybindings_custom",
    "plugins_enabled",
    "plugins_disabled",
    "plugin_permissions_required",
    "plugin_auto_update",
    "plugin_update_check_interval",
    # 高级
    "sound_volume",
    "crash_report",
})


# ============================================================
# 1. 删除的键：三处清理 + tests/tools 无引用
# ============================================================
def test_deleted_keys_are_fully_removed():
    """删键必须同时清理 DEFAULTS、属性访问器与首选项面板 UI。"""
    assert DELETED_KEYS, "删除清单不能为空"
    panel_src = _read(PANEL_PATH)

    for key in sorted(DELETED_KEYS):
        assert key not in DEFAULTS, f"{key} 仍在 DEFAULTS 里"
        assert not hasattr(Preferences, key), (
            f"{key} 的属性访问器未删除（Preferences.{key} 仍存在）"
        )
        assert f'"{key}"' not in panel_src and f"'{key}'" not in panel_src, (
            f"{key} 仍出现在 ui/preferences_panel.py 的界面项里"
        )


def test_deleted_keys_not_referenced_by_tests_or_tools():
    """删除后 tests/ 与 tools/ 里不允许残留同名引用。

    例外：本文件自身需要在 DELETED_KEYS 里列出这些键，因此跳过自己。
    """
    this_file = os.path.abspath(__file__)
    for sub in ("tests", "tools"):
        base = os.path.join(ROOT, sub)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                path = os.path.join(dirpath, filename)
                if os.path.abspath(path) == this_file:
                    continue
                src = _read(path)
                for key in sorted(DELETED_KEYS):
                    assert f'"{key}"' not in src and f"'{key}'" not in src, (
                        f"{os.path.relpath(path, ROOT)} 仍引用已删除的键 {key}"
                    )


# ============================================================
# 2. 接线的键：静态证据
# ============================================================
@pytest.mark.parametrize("key", sorted(WIRED_KEYS))
def test_wired_keys_are_read_by_production_code(key):
    assert key in DEFAULTS, f"{key} 不在 DEFAULTS 里，接线无从谈起"
    for rel in WIRED_KEYS[key]:
        src = _read(os.path.join(ROOT, rel.replace("/", os.sep)))
        assert key in src, f"{key} 未在接线文件 {rel} 中出现（预期被读取）"


# ============================================================
# 3. 核心防线：不允许出现新的孤儿键
# ============================================================
def test_no_new_fake_switches():
    orphans = _orphan_keys()
    new_orphans = sorted(orphans - KNOWN_UNWIRED_ORPHANS)
    hint = (
        "发现新的假开关（既不在 ui/preferences_panel.py，也无任何生产代码读取）：\n  "
        + "\n  ".join(new_orphans)
        + "\n请接线、删除，或（仅当确认属于他人写作用域内的存量债务时）"
        + "把它加入 KNOWN_UNWIRED_ORPHANS 并写明原因。"
    )
    assert not new_orphans, hint


def test_known_orphan_baseline_is_honest():
    """基线只能包含真实存在的键，且不得残留已接线/已删除的键。"""
    assert set(DEFAULTS) >= KNOWN_UNWIRED_ORPHANS, (
        "基线里存在不在 DEFAULTS 中的键："
        + str(sorted(KNOWN_UNWIRED_ORPHANS - set(DEFAULTS)))
    )
    wired_left = sorted(KNOWN_UNWIRED_ORPHANS & set(WIRED_KEYS))
    assert not wired_left, f"这些键已接线，应从 KNOWN_UNWIRED_ORPHANS 移除: {wired_left}"
    deleted_left = sorted(KNOWN_UNWIRED_ORPHANS & DELETED_KEYS)
    assert not deleted_left, f"这些键已删除，应从 KNOWN_UNWIRED_ORPHANS 移除: {deleted_left}"


def test_orphan_scan_actually_scans_production_code():
    """元测试：扫描器必须真的覆盖到生产代码，否则防线是空的。"""
    production = set(_production_files())
    assert "core/search.py" in production
    assert "ui/editor_view.py" in production
    assert "main.py" in production

    referenced = _referenced_keys()
    # 已确认被生产代码读取的键必须被扫出来
    assert "restore_session" in referenced
    assert "sound_effects" in referenced
    # 声明文件与面板本身不参与"读取方"统计：
    # font_line_height 只存在于 app/preferences.py（DEFAULTS + 访问器），
    # 若它被扫出来，说明扫描范围没有排除声明文件，防线会自证通过。
    assert "font_line_height" not in referenced


# ============================================================
# 4. 运行时行为：SearchOptions 真正读到 Preferences
# ============================================================
class _FakePrefs:
    """最小 Preferences 替身，只实现 get()。"""

    def __init__(self, values):
        self._values = dict(values)

    def get(self, key, default=None):
        return self._values.get(key, default)


def _patch_preferences(monkeypatch, fake):
    import app.preferences as prefs_module

    monkeypatch.setattr(prefs_module, "get_preferences", lambda: fake)


def test_search_options_reads_preferences(monkeypatch):
    from core.search import SearchOptions

    fake = _FakePrefs({
        "search_threads": 7,
        "use_hyperscan": False,
        "search_timeout": 12,
    })
    _patch_preferences(monkeypatch, fake)

    options = SearchOptions.from_preferences(pattern="hello")

    assert options.pattern == "hello"
    assert options.threads == 7, "search_threads 未接线到 SearchOptions.threads"
    assert options.use_hyperscan is False, (
        "use_hyperscan 未接线到 SearchOptions.use_hyperscan"
    )
    assert options.timeout_seconds == 12, (
        "search_timeout 未接线到 SearchOptions.timeout_seconds"
    )


def test_search_options_clamps_and_falls_back(monkeypatch):
    from core.search import (
        DEFAULT_SEARCH_TIMEOUT,
        DEFAULT_THREADS,
        MAX_THREADS,
        SearchOptions,
    )

    # 越界值必须被夹紧到 [1, MAX_THREADS]
    _patch_preferences(monkeypatch, _FakePrefs({"search_threads": 999}))
    assert SearchOptions.from_preferences().threads == MAX_THREADS

    _patch_preferences(monkeypatch, _FakePrefs({"search_threads": 0}))
    assert SearchOptions.from_preferences().threads == 1

    # 偏好不可用时回退默认值，绝不抛异常
    def _boom():
        raise RuntimeError("preferences unavailable")

    import app.preferences as prefs_module

    monkeypatch.setattr(prefs_module, "get_preferences", _boom)
    options = SearchOptions.from_preferences()
    assert options.threads == DEFAULT_THREADS
    assert options.timeout_seconds == DEFAULT_SEARCH_TIMEOUT


def test_search_engine_uses_preference_options(monkeypatch, qapp):
    from core.search import SearchEngine

    _patch_preferences(monkeypatch, _FakePrefs({"search_threads": 3}))

    engine = SearchEngine(None)

    assert engine.options.threads == 3, (
        "SearchEngine 未走 SearchOptions.from_preferences()"
    )


# ============================================================
# 5. 运行时行为：main.py 的偏好读取
# ============================================================
def test_pref_helper_reads_qsettings(qapp):
    """`main._pref` 必须真的去读偏好，而不是永远返回默认值

    注意（测试隔离）：本文件在模块层 `from PyQt5.QtCore import QSettings`，
    该绑定发生在 conftest 的会话级隔离 fixture **打补丁之前**，因此这里的
    `QSettings` 仍是真实类（会写注册表）。而 `main._pref` 走
    `Preferences()`（已被补丁重定向到临时 ini）—— 两者路径不同，
    直接 `QSettings(org, app).setValue()` 会"写了读不到"。

    所以必须**显式用 IniFormat 构造**，才能落到与生产代码相同的隔离路径。
    """
    import main as main_module

    settings = QSettings(QSettings.IniFormat, QSettings.UserScope,
                         main_module.ORG_NAME, "Editor")
    original = settings.value("splash_screen", True, type=bool)
    try:
        settings.setValue("splash_screen", False)
        settings.sync()
        assert main_module._pref("splash_screen", True) is False, (
            "main._pref 未读到 splash_screen"
        )
    finally:
        settings.setValue("splash_screen", original)
        settings.sync()


def test_log_settings_reads_log_level(qapp):
    import main as main_module

    # 同 test_pref_helper_reads_qsettings：必须显式 IniFormat 才能落到
    # 与生产代码（Preferences）相同的隔离路径
    settings = QSettings(QSettings.IniFormat, QSettings.UserScope,
                         main_module.ORG_NAME, "Editor")
    original = settings.value("log_level", "INFO", type=str)
    original_debug = settings.value("debug_mode", False, type=bool)
    try:
        # debug_mode 优先级最高，先关掉，避免影响本断言
        settings.setValue("debug_mode", False)
        settings.setValue("log_level", "WARNING")
        settings.sync()
        level_name, _max_bytes = main_module._log_settings()
        assert level_name == "WARNING", "log_level 未接线到 setup_logging"
    finally:
        settings.setValue("log_level", original or "INFO")
        settings.setValue("debug_mode", original_debug)
        settings.sync()
