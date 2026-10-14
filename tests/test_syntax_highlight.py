# -*- coding: utf-8 -*-
"""P5 语法高亮补齐：ui/editor_view.py 的"扩展名 -> QScintilla 词法器"映射表

覆盖点：
1. 任务要求的每个扩展名都能拿到**非 None** 的词法器，且词法器类型正确
2. 未知扩展名 / 无扩展名 / 空路径 -> lexer() is None 且不抛异常
3. 原有行为（.py / .pyw / .c / .hpp / .log）未回归
4. 词法器缺失（本构建没有该类）或构造失败时优雅降级，不崩溃
5. 插件注册表 _custom_lexers 的优先级高于内置映射表
6. 映射表登记的类名必须**可实例化** —— QsciLexerAsm 是 C++ 抽象类，
   光断言"类存在"会漏掉它（本次实测踩到的坑）
7. 无 QObject parent 的词法器必须被编辑器接管，否则 Python 侧引用
   归零后被回收，而 Scintilla 只持裸指针 -> lexer() 变成 None
"""

import gc
import inspect
import os

import pytest
from PyQt5.Qsci import QsciLexerCPP, QsciLexerPython
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QMainWindow

import ui.editor_view as editor_view
from ui.editor_view import (
    LEXER_BY_EXTENSION,
    EditorWidget,
    create_lexer_for_extension,
    is_instantiable_lexer,
    resolve_lexer_class,
)


# ============================================================
# 任务要求的扩展名 -> 期望词法器类名
# ============================================================
REQUIRED_LEXERS = {
    # Python（原有）
    ".py": "QsciLexerPython",
    ".pyw": "QsciLexerPython",
    # C / C++（原有）
    ".c": "QsciLexerCPP",
    ".h": "QsciLexerCPP",
    ".cpp": "QsciLexerCPP",
    # JSON
    ".json": "QsciLexerJSON",
    ".jsonc": "QsciLexerJSON",
    # JavaScript（含 TypeScript 兜底）
    ".js": "QsciLexerJavaScript",
    ".mjs": "QsciLexerJavaScript",
    ".cjs": "QsciLexerJavaScript",
    ".jsx": "QsciLexerJavaScript",
    ".ts": "QsciLexerJavaScript",
    ".tsx": "QsciLexerJavaScript",
    # HTML / XML
    ".html": "QsciLexerHTML",
    ".htm": "QsciLexerHTML",
    ".xml": "QsciLexerXML",
    ".svg": "QsciLexerXML",
    ".xsl": "QsciLexerXML",
    # CSS
    ".css": "QsciLexerCSS",
    ".scss": "QsciLexerCSS",
    ".less": "QsciLexerCSS",
    # Markdown
    ".md": "QsciLexerMarkdown",
    ".markdown": "QsciLexerMarkdown",
    # YAML
    ".yml": "QsciLexerYAML",
    ".yaml": "QsciLexerYAML",
    # SQL
    ".sql": "QsciLexerSQL",
    # Shell
    ".sh": "QsciLexerBash",
    ".bash": "QsciLexerBash",
    ".zsh": "QsciLexerBash",
    # 批处理
    ".bat": "QsciLexerBatch",
    ".cmd": "QsciLexerBatch",
    # 其他语言
    ".java": "QsciLexerJava",
    ".cs": "QsciLexerCSharp",
    ".rb": "QsciLexerRuby",
    ".pl": "QsciLexerPerl",
    ".pm": "QsciLexerPerl",
    ".lua": "QsciLexerLua",
    ".tex": "QsciLexerTeX",
    # diff
    ".diff": "QsciLexerDiff",
    ".patch": "QsciLexerDiff",
    # 配置 / 构建 / 汇编
    ".ini": "QsciLexerProperties",
    ".cfg": "QsciLexerProperties",
    ".conf": "QsciLexerProperties",
    ".properties": "QsciLexerProperties",
    ".cmake": "QsciLexerCMake",
    ".mk": "QsciLexerMakefile",
    # 汇编：QsciLexerAsm 是 C++ 抽象类（实例化即 TypeError），
    # 必须用可实例化的 NASM 具体类
    ".asm": "QsciLexerNASM",
    ".s": "QsciLexerNASM",
    # 无官方词法器 -> 兜底
    ".go": "QsciLexerCPP",
    ".rs": "QsciLexerCPP",
}

# 无对应词法器、必须靠兜底的扩展名（实现注释必须与之一致）
FALLBACK_EXTENSIONS = (".go", ".rs", ".ts", ".tsx")

_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\consola.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
)


# ============================================================
# fixtures
# ============================================================
@pytest.fixture(scope="session", autouse=True)
def _inject_fonts(qapp):
    """注入 Windows 字体，避免 offscreen 下因缺字体导致 segfault。"""
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                QFontDatabase.addApplicationFont(path)
            except Exception:
                pass
    yield


@pytest.fixture(scope="module")
def editor(qapp):
    """共享的 EditorWidget（offscreen）"""
    widget = EditorWidget()
    yield widget
    try:
        widget.deleteLater()
    except Exception:
        pass


# ============================================================
# 1. 每个要求的扩展名都能拿到正确类型的词法器
# ============================================================
@pytest.mark.parametrize("ext,lexer_name", sorted(REQUIRED_LEXERS.items()))
def test_required_extension_gets_lexer(editor, ext, lexer_name):
    editor.set_lexer_by_filename("sample" + ext)

    lexer = editor.lexer()
    assert lexer is not None, f"{ext} 没有得到词法器（零高亮）"
    assert type(lexer).__name__ == lexer_name, (
        f"{ext} 期望 {lexer_name}，实际 {type(lexer).__name__}"
    )


def test_fallback_extensions_actually_use_fallbacks():
    """兜底说明必须与实现一致：.go/.rs 用 CPP，.ts/.tsx 用 JavaScript"""
    expected = {
        ".go": "QsciLexerCPP",
        ".rs": "QsciLexerCPP",
        ".ts": "QsciLexerJavaScript",
        ".tsx": "QsciLexerJavaScript",
    }
    assert set(expected) == set(FALLBACK_EXTENSIONS)
    for ext, lexer_name in expected.items():
        assert LEXER_BY_EXTENSION[ext] == lexer_name


def test_extension_coverage_is_broad():
    """P5 目标：从 3 种语言扩到覆盖常用语言（本表 >= 60 个扩展名）"""
    print(
        f"[P5 高亮覆盖] LEXER_BY_EXTENSION 共 {len(LEXER_BY_EXTENSION)} 个扩展名，"
        f"涉及 {len(set(LEXER_BY_EXTENSION.values()))} 个词法器类"
        f"（另有 .log -> LogLexer 走专用分支，不登记在表里）"
    )
    assert len(LEXER_BY_EXTENSION) >= 60


def test_log_is_handled_by_dedicated_lexer_not_the_table():
    """.log 走 core.log_lexer.LogLexer 专用分支，不登记在映射表里"""
    assert ".log" not in LEXER_BY_EXTENSION


def test_every_mapped_lexer_class_exists_and_is_instantiable(qapp):
    """映射表登记的类名必须存在，**且能真正实例化**

    实测坑（本次 P5 漏网的原因）：`QsciLexerAsm` / `QsciLexerCustom`
    是 C++ 抽象类 —— `hasattr`/`getattr`/`resolve_lexer_class` 全都能
    拿到类对象，但实例化抛 TypeError，结果静默变成零高亮。
    所以这里必须同时断言"可实例化"，光断言"类存在"不够。
    """
    missing = sorted(
        {
            name
            for name in LEXER_BY_EXTENSION.values()
            if resolve_lexer_class(name) is None
        }
    )
    assert missing == [], f"本构建缺少这些词法器类: {missing}"

    not_instantiable = sorted(
        {
            name
            for name in LEXER_BY_EXTENSION.values()
            if not is_instantiable_lexer(name)
        }
    )
    assert not_instantiable == [], (
        f"这些词法器是 C++ 抽象类 / 无法实例化，登记它们会静默零高亮: "
        f"{not_instantiable}"
    )


def test_asm_uses_instantiable_nasm_lexer(qapp):
    """.asm/.s 必须用可实例化的 QsciLexerNASM

    QsciLexerAsm 是抽象类，用它会让 .asm/.s 静默零高亮（已实测）。
    """
    assert LEXER_BY_EXTENSION[".asm"] == "QsciLexerNASM"
    assert LEXER_BY_EXTENSION[".s"] == "QsciLexerNASM"
    assert resolve_lexer_class("QsciLexerAsm") is not None, (
        "QsciLexerAsm 应当存在（这才让'抽象类'这个坑更难发现）"
    )
    assert is_instantiable_lexer("QsciLexerAsm") is False, (
        "QsciLexerAsm 是 C++ 抽象类，不应被判定为可实例化"
    )
    assert is_instantiable_lexer("QsciLexerNASM") is True


def test_uninstantiable_lexer_name_degrades_without_crashing(editor, monkeypatch):
    """若将来有人把抽象类填进映射表，必须降级为 None 且打印告警（不崩）"""
    monkeypatch.setitem(
        editor_view.LEXER_BY_EXTENSION, ".abstract", "QsciLexerAsm"
    )
    editor.set_lexer_by_filename("a.abstract")
    assert editor.lexer() is None


# ============================================================
# 2. 未知扩展名 / 空路径 -> None 且不抛异常
# ============================================================
def test_uppercase_extension_is_normalized(editor):
    editor.set_lexer_by_filename("SAMPLE.JSON")
    assert type(editor.lexer()).__name__ == "QsciLexerJSON"


@pytest.mark.parametrize(
    "filename",
    ["noext", "archive.xyz", "weird.", ".hidden", "a.b.c.zzz"],
)
def test_unknown_extension_yields_none_without_raising(editor, filename):
    editor.set_lexer_by_filename(filename)
    assert editor.lexer() is None


def test_none_and_empty_path_clear_lexer(editor):
    editor.set_lexer_by_filename("a.py")
    assert editor.lexer() is not None

    editor.set_lexer_by_filename(None)
    assert editor.lexer() is None

    editor.set_lexer_by_filename("a.py")
    assert editor.lexer() is not None

    editor.set_lexer_by_filename("")
    assert editor.lexer() is None


def test_directory_only_path_is_safe(editor):
    """路径没有文件名/扩展名时不能崩"""
    editor.set_lexer_by_filename(os.path.join("some", "dir", "file."))
    assert editor.lexer() is None


# ============================================================
# 3. 原有行为未回归
# ============================================================
def test_legacy_python_and_cpp_still_work(editor):
    editor.set_lexer_by_filename("main.py")
    assert type(editor.lexer()).__name__ == "QsciLexerPython"

    editor.set_lexer_by_filename("main.pyw")
    assert type(editor.lexer()).__name__ == "QsciLexerPython"

    editor.set_lexer_by_filename("main.c")
    assert type(editor.lexer()).__name__ == "QsciLexerCPP"

    editor.set_lexer_by_filename("main.hpp")
    assert type(editor.lexer()).__name__ == "QsciLexerCPP"


def test_log_lexer_still_works(editor):
    editor.set_lexer_by_filename("run.log")
    lexer = editor.lexer()
    assert lexer is not None, ".log 失去了专用词法器（回归）"
    assert type(lexer).__name__ == "LogLexer"


def test_set_lexer_by_filename_uses_the_font_applying_override():
    """必须走 set_lexer()（顺带设默认字体），而不是直接 setLexer()

    这是任务书的硬性要求：set_lexer_by_filename 若绕开 set_lexer，
    新建的词法器就不会应用编辑器字体。
    """
    src = inspect.getsource(EditorWidget.set_lexer_by_filename)
    assert "self.set_lexer(" in src
    assert "self.setLexer(" not in src


# ============================================================
# 4. 容错：词法器缺失 / 构造失败必须优雅降级
# ============================================================
def test_missing_lexer_class_degrades_to_none(editor, monkeypatch):
    """模拟"某些 QScintilla 构建缺少该词法器" -> 零高亮但不崩"""
    monkeypatch.setattr(editor_view, "resolve_lexer_class", lambda name: None)

    editor.set_lexer_by_filename("data.json")
    assert editor.lexer() is None

    editor.set_lexer_by_filename("notes.md")
    assert editor.lexer() is None


def test_lexer_constructor_failure_degrades_to_none(editor, monkeypatch):
    class _BoomLexer:
        def __init__(self, parent=None):
            raise RuntimeError("构造失败")

    monkeypatch.setitem(editor_view.LEXER_BY_EXTENSION, ".boom", "QsciLexerBoom")
    monkeypatch.setattr(
        editor_view,
        "resolve_lexer_class",
        lambda name: _BoomLexer if name == "QsciLexerBoom" else None,
    )

    editor.set_lexer_by_filename("x.boom")
    assert editor.lexer() is None


def test_create_lexer_for_extension_normalizes_input():
    assert type(create_lexer_for_extension(".json")).__name__ == "QsciLexerJSON"
    assert type(create_lexer_for_extension("json")).__name__ == "QsciLexerJSON"
    assert type(create_lexer_for_extension(".JSON")).__name__ == "QsciLexerJSON"
    assert create_lexer_for_extension(".xyz") is None
    assert create_lexer_for_extension("") is None
    assert create_lexer_for_extension(None) is None


# ============================================================
# 5. 插件注册表优先级 + 词法器生命周期
# ============================================================
def test_unparented_lexer_survives_python_gc(qapp):
    """无 QObject parent 的词法器必须被编辑器接管

    P5 实测发现：插件工厂返回的词法器通常**没有 parent**；
    若编辑器不接管，函数返回后 Python 侧引用归零，PyQt 会回收它，
    而 Scintilla 只持有裸指针 —— 于是 `lexer()` 变成 None，静默零高亮。
    （这正是 test_custom_lexer_registry_has_higher_priority 之前失败的原因。）
    """
    widget = EditorWidget()
    try:
        widget.set_lexer(QsciLexerPython())  # 故意不传 parent
        gc.collect()
        lexer = widget.lexer()
        assert lexer is not None, "无 parent 的词法器被回收了（零高亮）"
        assert type(lexer).__name__ == "QsciLexerPython"
    finally:
        widget.deleteLater()


def test_custom_lexer_registry_has_higher_priority(qapp):
    win = QMainWindow()
    win._custom_lexers = {}
    widget = EditorWidget(parent=win)
    try:
        # 未注册 -> 走内置映射表
        widget.set_lexer_by_filename("a.json")
        assert type(widget.lexer()).__name__ == "QsciLexerJSON"

        # 插件注册后，覆盖内置映射表（同一扩展名）
        win._custom_lexers[".json"] = lambda: QsciLexerPython()
        widget.set_lexer_by_filename("a.json")
        assert type(widget.lexer()).__name__ == "QsciLexerPython"

        # 只被插件注册的扩展名也能命中
        win._custom_lexers[".xyz"] = lambda: QsciLexerCPP()
        widget.set_lexer_by_filename("a.xyz")
        assert type(widget.lexer()).__name__ == "QsciLexerCPP"

        # 工厂返回 None -> 回退到内置映射表
        win._custom_lexers[".md"] = lambda: None
        widget.set_lexer_by_filename("a.md")
        assert type(widget.lexer()).__name__ == "QsciLexerMarkdown"

        # 工厂抛异常 -> 同样回退到内置映射表，不崩
        def _bad_factory():
            raise RuntimeError("factory boom")

        win._custom_lexers[".cfg"] = _bad_factory
        widget.set_lexer_by_filename("a.cfg")
        assert type(widget.lexer()).__name__ == "QsciLexerProperties"
    finally:
        widget.deleteLater()
        win.deleteLater()
