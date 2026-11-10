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
