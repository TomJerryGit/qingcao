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


def test_no_py_file_over_2000_lines():
    """第三批目标达成：全仓（除归档）无 >2,000 行文件。

    六目标文件均 ≤1,100 行；其余历史文件（1,500–1,920 行）为下一批候选。
    """
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
            if n > 2000:
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
    # main.py 作为启动入口保留（测试大量依赖 main 的模块级函数）
    assert _lines("main.py") < 2000
