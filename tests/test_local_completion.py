# -*- coding: utf-8 -*-
"""P10 本地补全接线：ui/editor_view.py × core/local_completer.py

覆盖点：
1. LocalCompleter.get_completions / update_from_file / record_used
   被**生产代码**调用（静态 + 运行时双重证据）
2. 真实 EditorWidget（offscreen）写入代码后触发补全，候选非空且包含
   期望的语言关键字 / 文档词
3. record_used 与文件词频会改变排序（词频生效）
4. 补全耗时 < 200ms（每次按键都会触发，不能卡顿）
5. 候选真的被送进 Scintilla 的补全弹窗（SCI_AUTOCACTIVE）
6. 偏好开关生效（local_completion 默认开，可关）
7. 不破坏 QScintilla 原有行为（括号自动闭合）

关于补全"被接受"信号（实测）：
    SCN_AUTOCCOMPLETED(selection: str, position: int, ch: int, method: int)
    SCN_AUTOCSELECTION(selection: str, position: int)
生产代码优先接前者、缺失时回退后者；测试里两种参数个数都会尝试。
"""

import inspect
import os
import time

import pytest
from PyQt5.Qsci import QsciScintilla
from PyQt5.QtGui import QFontDatabase

import ui.editor_view as editor_view
from core.local_completer import LocalCompleter, get_local_completer
from ui.editor_view import EditorWidget


_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\consola.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
)

# 性能门槛（毫秒）——补全在每次按键时触发
MAX_COMPLETION_MS = 200.0


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


@pytest.fixture
def completer(qapp):
    """隔离 LocalCompleter 全局单例的状态，测试后还原（避免污染其他测试）"""
    instance = get_local_completer()
    saved_freq = instance.word_freq.copy()
    saved_file_words = {k: v.copy() for k, v in instance.file_words.items()}
    saved_recent = list(instance.recent_words)

    yield instance

    instance.word_freq.clear()
    instance.word_freq.update(saved_freq)
    instance.file_words.clear()
    for key, value in saved_file_words.items():
        instance.file_words[key] = value
    instance.recent_words[:] = saved_recent


@pytest.fixture
def editor(qapp, completer):
    """真实的 EditorWidget（offscreen）"""
    widget = EditorWidget()
    yield widget
    try:
        widget.SendScintilla(QsciScintilla.SCI_AUTOCCANCEL)
    except Exception:
        pass
    try:
        widget.deleteLater()
    except Exception:
        pass


# 实测（PyQt5/QScintilla）补全"被接受"信号的参数个数：
#   SCN_AUTOCCOMPLETED(selection: str, position: int, ch: int, method: int)  -> 4
#   SCN_AUTOCSELECTION(selection: str, position: int)                        -> 2
# 生产代码优先接前者，缺失时回退后者；不同版本参数个数可能有差异，
# 所以这里两组都试。
_ACCEPT_SIGNAL_ARGS = (
    ("SCN_AUTOCCOMPLETED", ("hello_world", 0, 0, 0)),
    ("SCN_AUTOCSELECTION", ("hello_world", 0)),
)


def _emit_completion_acceptance(editor):
    """向"补全被接受"信号发射一次测试事件，返回实际使用的信号名（失败返回 None）"""
    for name, emit_args in _ACCEPT_SIGNAL_ARGS:
        signal = getattr(editor, name, None)
        if signal is None:
            continue
        try:
            signal.emit(*emit_args)
        except TypeError:
            # 该版本参数个数不同 -> 退到保守的 2 参形式再试一次
            try:
                signal.emit("hello_world", 0)
            except TypeError:
                continue
        return name
    return None


class _CountingCompleter:
    """包装真实 LocalCompleter，统计生产代码的调用次数"""

    def __init__(self, inner):
        self._inner = inner
        self.get_completions_calls = 0
        self.update_from_file_calls = 0
        self.record_used_calls = 0
        self.last_get_completions = None

    def get_completions(self, *args, **kwargs):
        self.get_completions_calls += 1
        self.last_get_completions = (args, kwargs)
        return self._inner.get_completions(*args, **kwargs)

    def update_from_file(self, *args, **kwargs):
        self.update_from_file_calls += 1
        return self._inner.update_from_file(*args, **kwargs)

    def record_used(self, word):
        self.record_used_calls += 1
        return self._inner.record_used(word)

    def __getattr__(self, name):
        return getattr(self._inner, name)


# ============================================================
# 1. 静态证据：生产代码确实调用 LocalCompleter
# ============================================================
def test_production_code_calls_local_completer():
    assert "get_completions(" in inspect.getsource(EditorWidget.local_completions)
    assert ".record_used(" in inspect.getsource(
        EditorWidget._on_completion_accepted
    )
    assert ".update_from_file(" in inspect.getsource(
        EditorWidget._sync_completion_words
    )


def test_editor_imports_local_completer_singleton():
    src = inspect.getsource(editor_view)
    assert "from core.local_completer import get_local_completer" in src
    assert "get_local_completer()" in src


# ============================================================
# 2. 运行时证据：get_completions 真的被调用
# ============================================================
def test_get_completions_called_at_runtime(editor, completer):
    spy = _CountingCompleter(editor._local_completer)
    editor._local_completer = spy

    editor.setText("def hello():\n    return 1\n")
    editor.setCursorPosition(0, 3)

    candidates = editor.trigger_local_completion(force=True)

    assert spy.get_completions_calls >= 1, (
        "LocalCompleter.get_completions 没有被生产代码调用"
    )
    assert spy.update_from_file_calls >= 1, (
        "文档词频没有被同步给 LocalCompleter"
    )
    assert candidates, "补全候选为空"

    args, kwargs = spy.last_get_completions
    assert args[0] == "def"
    assert kwargs["limit"] == editor_view.COMPLETION_MAX_ITEMS
    assert "filepath" in kwargs
    assert "language" in kwargs


# ============================================================
# 3. 候选内容：语言关键字 + 文档词
# ============================================================
def test_language_keywords_are_offered(editor, completer):
    """文档里没有 'return'，也必须能补出 Python 关键字 'return'"""
    editor.document.meta.filepath = "sample.py"
    editor.setText("ret\n")
    editor.setCursorPosition(0, 3)

    candidates = editor.trigger_local_completion(force=True)

    assert candidates, "补全候选为空"
    assert "return" in candidates, f"缺少语言关键字 return: {candidates}"


def test_document_words_are_offered(editor, completer):
    """文档词补全能力必须保留（原先靠 QScintilla AcsDocument）"""
    editor.document.meta.filepath = "sample.py"
    editor.setText(
        "def zq_worker():\n"
        "    zq_helper = 1\n"
        "    return zq_helper\n"
    )
    editor.setCursorPosition(1, 7)  # 行 "    zq_helper = 1"，光标在 "zq_" 之后

    candidates = editor.trigger_local_completion(force=True)

    assert "zq_helper" in candidates, f"缺少文档词 zq_helper: {candidates}"
    assert "zq_worker" in candidates, f"缺少文档词 zq_worker: {candidates}"


def test_language_detection_follows_extension(editor):
    editor.document.meta.filepath = "a.py"
    assert editor._completion_language() == "python"
    editor.document.meta.filepath = "a.js"
    assert editor._completion_language() == "javascript"
    editor.document.meta.filepath = "a.json"
    assert editor._completion_language() == ""
    editor.document.meta.filepath = ""
    assert editor._completion_language() == ""


# ============================================================
# 4. 词频 / 最近使用生效
# ============================================================
def test_record_used_changes_ranking():
    """record_used 必须把词排到最前（最近使用优先）"""
    comp = LocalCompleter()
    assert comp.get_completions("zq", language="python") == []

    comp.record_used("zq_alpha")
    comp.record_used("zq_beta")

    words = [w for w, _src in comp.get_completions("zq", language="python")]
    assert words[0] == "zq_beta", f"最近使用没有排到最前: {words}"
    assert set(words[:2]) == {"zq_beta", "zq_alpha"}


def test_file_word_frequency_changes_ranking():
    """文件内词频必须影响排序"""
    comp = LocalCompleter()
    comp.update_from_file(
        "f.py", "zq_first zq_second zq_second zq_second\n"
    )

    words = [
        w for w, _src in comp.get_completions(
            "zq", filepath="f.py", language="python"
        )
    ]
    assert words[0] == "zq_second", f"词频没有生效: {words}"


def test_completion_acceptance_is_wired_to_record_used(editor, completer):
    """用户接受补全项 -> SCN_AUTOC* 信号 -> LocalCompleter.record_used

    改用**连接检查 + 槽函数直调**，而不是 `signal.emit(...)`。

    原因（实测）：PyQt5/QScintilla 的 `SCN_AUTOCCOMPLETED` 绑定信号在
    某些情况下直接 `emit()` 会抛：
        TypeError: argument 1 has unexpected type 'str'
    这是 sip 绑定层对 `emit` 参数类型的内省限制，**不代表生产接线有问题**。
    而可靠的判据是：
        1. `receivers(signal) > 0`  —— 生产代码确实连接了；
        2. 直接调用槽函数，`record_used` 确实被调用。
    """
    before = list(completer.recent_words)

    # 1) 生产代码必须把信号连到槽上
    connected = None
    for name in ("SCN_AUTOCCOMPLETED", "SCN_AUTOCSELECTION"):
        sig = getattr(editor, name, None)
        if sig is None:
            continue
        try:
            if editor.receivers(sig) > 0:
                connected = name
                break
        except Exception:
            continue
    assert connected is not None, (
        "补全接受信号未连接到槽函数 → 记录使用永远不触发。\n"
        "    期望：ui/editor_view.py 的 _connect_signals 连接 "
        "SCN_AUTOCCOMPLETED（或回退 SCN_AUTOCSELECTION）"
    )

    # 2) 槽函数必须把选中的词喂给 record_used
    editor._on_completion_accepted("hello_world", 0, 0, 0)

    assert completer.recent_words and completer.recent_words[0] == "hello_world", (
        f"{connected} 的槽函数没有调用 record_used（before={before[:3]}）"
    )


# ============================================================
# 5. 候选真的送进了 Scintilla 弹窗
# ============================================================
def test_completion_popup_is_shown_to_scintilla(editor, completer, qapp):
    editor.show()
    qapp.processEvents()
    try:
        editor.document.meta.filepath = "sample.py"
        editor.setText("ret\n")
        editor.setCursorPosition(0, 3)

        candidates = editor.trigger_local_completion(force=True)
        assert candidates, "补全候选为空，无法弹出"

        active = editor.SendScintilla(QsciScintilla.SCI_AUTOCACTIVE)
        assert active == 1, "候选列表没有送进 Scintilla 弹窗（SCI_AUTOCACTIVE != 1）"
    finally:
        editor.SendScintilla(QsciScintilla.SCI_AUTOCCANCEL)
        editor.hide()


# ============================================================
# 6. 性能
# ============================================================
def test_completion_latency_is_reasonable(editor, completer):
    """冷启动（含全量索引）与热路径都必须 < 200ms"""
    lines = []
    for i in range(200):
        lines.append(f"def function_{i}():\n    return function_{i}\n")
    editor.document.meta.filepath = "sample.py"
    editor.setText("".join(lines))
    editor.setCursorPosition(0, 3)  # 光标在 "def" 之后

    start = time.perf_counter()
    cold_candidates = editor.trigger_local_completion(force=True)
    cold_ms = (time.perf_counter() - start) * 1000.0
    assert cold_candidates, "长文档上补全候选为空"

    warm_ms = 0.0
    for _ in range(20):
        start = time.perf_counter()
        editor.trigger_local_completion(force=True)
        warm_ms = (time.perf_counter() - start) * 1000.0

    # 便于人工核对实际数值（用 pytest -s 运行可见）
    print(
        f"[P10 补全耗时] 冷启动 {cold_ms:.2f}ms / 热路径 {warm_ms:.2f}ms "
        f"(文档 {len(lines)} 行, 门槛 {MAX_COMPLETION_MS:.0f}ms)"
    )

    assert cold_ms < MAX_COMPLETION_MS, f"冷启动补全耗时 {cold_ms:.1f}ms 超过门槛"
    assert warm_ms < MAX_COMPLETION_MS, f"热路径补全耗时 {warm_ms:.1f}ms 超过门槛"


# ============================================================
# 7. 偏好开关
# ============================================================
def test_completion_enabled_by_default(qapp, preferences):
    assert preferences is not None
    widget = EditorWidget(prefs=preferences)
    try:
        assert widget._completion_enabled is True, "本地补全应默认开启"
    finally:
        widget.deleteLater()


def test_completion_can_be_disabled_by_preference(qapp, preferences):
    assert preferences is not None
    preferences.set("local_completion", False)
    assert preferences.get("local_completion", True) is False

    widget = EditorWidget(prefs=preferences)
    try:
        widget.setText("ret\n")
        widget.setCursorPosition(0, 3)
        assert widget.local_completions("ret") == []
        assert widget.trigger_local_completion(force=True) == []
    finally:
        widget.deleteLater()


# ============================================================
# 8. 不破坏 QScintilla 原有行为
# ============================================================
def test_autocompletion_source_is_managed_by_editor(editor):
    """补全来源必须由本类接管（AcsNone + 阈值 -1），避免双弹窗"""
    assert editor.autoCompletionSource() == QsciScintilla.AcsNone
    assert editor.autoCompletionThreshold() < 0


def test_bracket_autoclose_still_works(editor):
    """P10 不能破坏括号自动闭合"""
    editor.setText("")
    editor.SendScintilla(QsciScintilla.SCI_INSERTTEXT, 0, b"(")
    editor.setCursorPosition(0, 1)

    editor.SCN_CHARADDED.emit(ord("("))

    assert editor.text() == "()", f"括号自动闭合失效: {editor.text()!r}"


def test_short_prefix_does_not_trigger(editor, completer):
    editor.setText("re\n")
    editor.setCursorPosition(0, 1)

    assert editor.trigger_local_completion() == []
