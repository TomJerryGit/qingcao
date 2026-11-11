# -*- coding: utf-8 -*-
"""v2.24 W1：第二批架构拆分回归"""

import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lines(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return sum(1 for _ in f)


def test_plugin_api_split():
    from app.plugin_api import PluginAPI

    assert _lines("app/plugin_api.py") < 650
    assert _lines("app/plugin_api_common.py") < 250
    assert _lines("app/plugin_api_editor.py") < 350
    assert _lines("app/plugin_api_ui.py") < 750
    assert _lines("app/plugin_api_data.py") < 450
    assert _lines("app/plugin_api_events.py") < 650
    for m in (
        "current_editor",
        "insert_text",
        "add_menu",
        "show_status",
        "read_file",
        "http_get",
        "subscribe",
        "register_command",
        "run_command",
        "run_python",
    ):
        assert hasattr(PluginAPI, m), m
    for mixin in ("EditorAccessMixin", "UiMixin", "DataMixin", "EventMixin"):
        assert any(c.__name__ == mixin for c in PluginAPI.__mro__), mixin


def test_editor_view_split():
    from PyQt5.Qsci import QsciScintilla

    from ui.editor_view import EditorWidget

    assert _lines("ui/editor_view.py") < 650
    assert _lines("ui/editor_view_input.py") < 750
    assert _lines("ui/editor_view_paint.py") < 350
    assert _lines("ui/editor_view_completion.py") < 350
    for m in (
        "keyPressEvent",
        "paintEvent",
        "trigger_local_completion",
        "set_lexer_by_filename",
        "get_line_count",
    ):
        assert hasattr(EditorWidget, m), m
    assert issubclass(EditorWidget, QsciScintilla)
    for mixin in (
        "EditorInputMixin",
        "EditorPaintMixin",
        "EditorCompletionMixin",
        "EditorLexerMixin",
    ):
        assert any(c.__name__ == mixin for c in EditorWidget.__mro__), mixin


def test_ai_assistant_split():
    from plugins.ai_assistant import (
        AIConfigDialog,
        AIResultDialog,
        AIWorker,
        OllamaPanel,
        Plugin,
    )

    assert _lines("plugins/ai_assistant/__init__.py") < 1400
    assert _lines("plugins/ai_assistant/ai_common.py") < 400
    assert _lines("plugins/ai_assistant/ai_result_dialog.py") < 850
    assert _lines("plugins/ai_assistant/ai_panel.py") < 550
    for cls in (AIWorker, AIResultDialog, AIConfigDialog, OllamaPanel, Plugin):
        assert cls is not None


def test_loader_supports_package_plugins():
    src = open(os.path.join(ROOT, "infrastructure", "plugin_loader.py"), encoding="utf-8").read()
    assert "submodule_search_locations" in src


def test_batch3_split():
    from app.session import SessionAutosaveWorker, SessionManager
    from app.tabs import DetachedWindow, TabManager
    from core.content_provider import (
        ContentProvider,
        LocalFileProvider,
        ProviderFactory,
    )
    from core.document import Document, DocumentModel
    from core.editor import EditorProxy
    from ui.outline_panel import OutlinePanel, OutlineTree, SymbolParser

    for rel, limit in (
        ("app/tabs.py", 700),
        ("app/session.py", 500),
        ("core/editor.py", 900),
        ("core/content_provider.py", 120),
        ("core/document.py", 120),
        ("ui/outline_panel.py", 1100),
    ):
        assert _lines(rel) < limit, (rel, _lines(rel))
    for cls in (
        TabManager,
        DetachedWindow,
        SessionManager,
        SessionAutosaveWorker,
        EditorProxy,
        Document,
        DocumentModel,
        ContentProvider,
        LocalFileProvider,
        ProviderFactory,
        OutlinePanel,
        OutlineTree,
        SymbolParser,
    ):
        assert cls is not None
    names = [c.__name__ for c in TabManager.__mro__]
    assert "TabOpenCloseMixin" in names and "TabUiMixin" in names
    names = [c.__name__ for c in SessionManager.__mro__]
    assert "SessionSaveMixin" in names and "SessionRestoreMixin" in names
    names = [c.__name__ for c in EditorProxy.__mro__]
    for mixin in ("EditorEventsMixin", "EditorLspMixin", "EditorTextOpsMixin"):
        assert mixin in names


def test_no_py_file_over_1800_lines():
    """v2.25 阶段 2.6：全仓（除归档）无 >1,800 行文件。"""
    offenders = []
    for root, _dirs, files in os.walk(ROOT):
        if any(part in root for part in (".git", "__pycache__", "dist", "build", "_archive")):
            continue
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, ROOT).replace("\\", "/")
            n = _lines(rel)
            if n > 1800:
                offenders.append((rel, n))
    assert not offenders, offenders


def test_batch4_split():
    from core.lsp_client import LspClient, LspServerRegistry
    from core.search import FileSearcher, ReplaceEngine, SearchEngine
    from infrastructure.plugin_loader import PluginLoader
    from infrastructure.plugin_updater import PluginUpdater
    from infrastructure.sound_manager import SoundManager
    from ui.column_editor_dialog import ColumnEditorDialog
    from ui.directory_tree import DirectoryTree
    from ui.file_merge_dialog import FileDiffDialog
    from ui.panels import SearchBar
    from ui.python_console import PythonConsole

    for rel, limit in (
        ("ui/file_merge_dialog.py", 120),
        ("ui/directory_tree.py", 1550),
        ("core/lsp_client.py", 1550),
        ("infrastructure/plugin_updater.py", 1450),
        ("core/search.py", 200),
        ("infrastructure/plugin_loader.py", 1250),
        ("infrastructure/sound_manager.py", 780),
        ("ui/panels.py", 120),
        ("ui/column_editor_dialog.py", 400),
        ("ui/python_console.py", 1050),
    ):
        assert _lines(rel) < limit, (rel, _lines(rel))
    for cls in (
        LspClient,
        LspServerRegistry,
        SearchEngine,
        FileSearcher,
        ReplaceEngine,
        PluginLoader,
        PluginUpdater,
        SoundManager,
        SearchBar,
        ColumnEditorDialog,
        FileDiffDialog,
        DirectoryTree,
        PythonConsole,
    ):
        assert cls is not None
    # main.py 已最终拆分为薄入口（helpers/run 独立模块）
    assert _lines("main.py") < 200


def test_main_entry_split():
    import main
    from app.main_helpers import ensure_directories, load_theme, setup_logging

    assert _lines("main.py") < 200
    assert _lines("app/main_helpers.py") < 1200
    assert _lines("app/main_run.py") < 800
    for name in (
        "load_theme",
        "ensure_directories",
        "parse_arguments",
        "get_max_new_window_instances",
        "_pref",
        "__version__",
    ):
        assert hasattr(main, name), name
    assert ensure_directories is not None and setup_logging is not None


def test_main_run_has_version():
    import app.main_run as mr
    from version import __version__

    assert getattr(mr, "__version__", "") == __version__


def test_icon_manager_split():
    from infrastructure.icon_manager import (
        IconCache,
        IconManager,
        IconProvider,
        get_icon,
        get_pixmap,
    )

    for rel, limit in (
        ("infrastructure/icon_manager.py", 750),
        ("infrastructure/icon_manager_common.py", 220),
        ("infrastructure/icon_manager_cache.py", 140),
        ("infrastructure/icon_manager_providers.py", 800),
    ):
        assert _lines(rel) < limit, (rel, _lines(rel))
    assert all(x is not None for x in (IconCache, IconManager, IconProvider, get_icon, get_pixmap))


def test_welcome_widget_split():
    from ui.welcome_widget import (
        C,
        RecentFilesList,
        WelcomeFooter,
        WelcomeHeader,
        WelcomeWidget,
    )

    for rel, limit in (
        ("ui/welcome_widget.py", 650),
        ("ui/welcome_widget_common.py", 240),
        ("ui/welcome_cards.py", 260),
        ("ui/welcome_recent.py", 380),
        ("ui/welcome_stats.py", 460),
    ):
        assert _lines(rel) < limit, (rel, _lines(rel))
    assert all(
        x is not None for x in (C, WelcomeHeader, RecentFilesList, WelcomeFooter, WelcomeWidget)
    )


def test_capability_wiring_split():
    from ui.mixins.capability_wiring_mixin import CapabilityWiringMixin

    for rel, limit in (
        ("ui/mixins/capability_wiring_mixin.py", 160),
        ("ui/mixins/capability_wiring_common.py", 140),
        ("ui/mixins/capability_keyseq_mixin.py", 360),
        ("ui/mixins/capability_plugins_mixin.py", 420),
        ("ui/mixins/capability_panels_mixin.py", 650),
        ("ui/mixins/capability_commands_mixin.py", 380),
    ):
        assert _lines(rel) < limit, (rel, _lines(rel))
    bases = [b.__name__ for b in CapabilityWiringMixin.__mro__]
    assert "KeySequenceMixin" in bases and "PluginsMixin" in bases
    assert "PanelsExportMixin" in bases and "CommandsThemeMixin" in bases


def test_phase24_splits():
    from core.lsp_client import LspClient, LspServerRegistry
    from ui.global_search_panel import GlobalSearchPanel, SearchResultTree
    from ui.keymap_editor import (
        KeyCaptureDialog,
        KeymapEditor,
        KeymapProfile,
        KeymapTable,
        apply_saved_scheme,
        load_saved_scheme,
    )

    for rel, limit in (
        ("ui/global_search_panel.py", 1100),
        ("ui/global_search_tree.py", 450),
        ("ui/keymap_editor.py", 800),
        ("ui/keymap_dialogs.py", 600),
        ("core/lsp_client.py", 1300),
        ("core/lsp_client_utils.py", 420),
    ):
        assert _lines(rel) < limit, (rel, _lines(rel))
    assert all(
        x is not None
        for x in (
            GlobalSearchPanel,
            SearchResultTree,
            KeymapEditor,
            KeymapTable,
            KeyCaptureDialog,
            KeymapProfile,
            apply_saved_scheme,
            load_saved_scheme,
            LspClient,
            LspServerRegistry,
        )
    )


# v2.25 阶段 2.6：新代码默认上限 1,300 行；
# 历史长尾文件列入白名单（附当前上限），已达标后必须从白名单移除。
_ALLOWLIST = {
    "ui/directory_tree.py": 1480,
    "core/macro.py": 1460,
    "infrastructure/theme_loader.py": 1420,
    "core/document_core.py": 1420,
    "ui/plugin_client.py": 1410,
    "ui/column_editor_dialog_common.py": 1385,
    "infrastructure/plugin_updater.py": 1370,
    "app/preferences.py": 1340,
    "ui/command_palette.py": 1335,
    "ui/plugin_store.py": 1325,
}


def test_v225_architecture_ratchet():
    """业务代码 ≤1,300；白名单文件必须仍 >1,300（达标即移除）。"""
    import glob

    biz = []
    for base in ("app", "core", "ui", "infrastructure", "plugins"):
        biz.extend(glob.glob(os.path.join(base, "**", "*.py"), recursive=True))
    biz.append("main.py")
    problems = []
    for path in biz:
        rel = path.replace("\\", "/")
        if "_archive" in rel or "__pycache__" in rel:
            continue
        n = _lines(rel)
        limit = _ALLOWLIST.get(rel, 1300)
        if n > limit:
            problems.append((rel, n, limit))
    assert not problems, problems
    # 白名单不得变成"永久豁免"：已 ≤1,300 的必须移除
    stale = []
    for rel, cap in _ALLOWLIST.items():
        assert cap <= 1500, (rel, cap)
        if _lines(rel) <= 1300:
            stale.append(rel)
    assert not stale, "已达标，请从 _ALLOWLIST 移除: %s" % stale
    assert len(_ALLOWLIST) <= 12
