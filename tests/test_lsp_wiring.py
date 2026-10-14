# -*- coding: utf-8 -*-
"""P6 回归测试：LSP 真正接线（此前是"实现了但从未接线"）

本文件针对 task-3 第 2 步（P6）。修复前的三个已核实缺陷：

1. ``core/editor.py`` 调用 ``self.lsp_client.start()``（零参数），而
   :meth:`LspClient.start` 的 ``command`` 是必填位置参数 → 必然
   ``TypeError``，且被外层 ``except Exception`` 吞掉 → **LSP 从未启动**。
2. ``toggle_lsp`` 硬编码 ``ext not in ('.py', '.pyw') → return False``，
   与本文件的 ``LSP_LANGUAGE_BY_EXT``（20+ 种语言）自相矛盾。
3. ``toggle_lsp`` 全仓零生产调用点；``request_definition`` 等 8 个请求
   方法全仓零调用方。

这里的断言刻意分成两类：
- **AST 静态断言**：直接检查源码里真实存在的调用形态（不是 grep 注释），
  顺带让 pytest 成为 core/editor.py、ui/main_window.py 的语法哨兵。
- **运行时断言**：用 stub 的 LspClient / 假的 EditorProxy 真的把
  ``toggle_lsp`` 跑一遍，验证参数、返回值与用户可见提示。
"""
import ast
import os

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ============================================================
# 源码工具（AST，不看注释与字符串）
# ============================================================
def read_source(relpath):
    with open(os.path.join(ROOT, relpath), encoding="utf-8") as f:
        return f.read()


def calls_to(source, attr):
    """返回源码中所有 ``<x>.<attr>(...)`` 调用节点。"""
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == attr:
                found.append(node)
    return found


def parse_ok(relpath):
    """源码必须能被 ast 解析（语法哨兵）。"""
    return ast.parse(read_source(relpath))


def get_function_node(source, name):
    """按名字取函数/方法定义节点（找不到返回 None）。"""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                return node
    return None


def string_literals(node):
    """收集节点内所有字符串字面量（docstring 整体算一个，不会误匹配）。"""
    out = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.add(sub.value)
    return out


def called_names(node):
    """收集节点内以裸名字调用的函数名，例如 f(x) → {"f"}。"""
    out = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
            out.add(sub.func.id)
    return out


# ============================================================
# 测试替身
# ============================================================
def _make_recording_client_class():
    """构造一个 LspClient 子类：记录参数、不真正 spawn 子进程。"""
    from core.lsp_client import LspClient

    class RecordingLspClient(LspClient):
        instances = []

        def __init__(self, parent=None):
            super().__init__(parent)
            self.calls = []
            RecordingLspClient.instances.append(self)

        def start(self, command, working_dir=None, env=None):
            self.calls.append(("start", list(command), working_dir, env))

        def initialize(self, root_uri, *args, **kwargs):
            self.calls.append(("initialize", root_uri))

        def did_open(self, uri, language_id, text, version=1):
            self.calls.append(("did_open", uri, language_id))

    return RecordingLspClient


@pytest.fixture
def make_proxy(qapp):
    """构造真实的 EditorProxy（裸 QsciScintilla + （可选的）文件路径）。"""
    created = []

    def _make(path=None):
        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy

        sc = QsciScintilla()
        doc = Document()
        if path is not None:
            doc.meta.filepath = os.path.abspath(str(path))
        proxy = EditorProxy(sc, doc)
        created.append((proxy, sc, doc))
        return proxy, sc, doc

    yield _make

    for proxy, sc, doc in created:
        try:
            doc.close()
        except Exception:
            pass


@pytest.fixture
def window(qapp):
    """真实的 MainWindow（并确保 LSP 开关处于默认关闭状态）。"""
    try:
        from app.preferences import get_preferences
        get_preferences().set("lsp_enabled", False, notify=False)
    except Exception:
        pass

    import ui.main_window as mw

    win = mw.MainWindow()
    try:
        yield win
    finally:
        try:
            win.close()
        except Exception:
            pass


# ============================================================
# 1. 静态接线断言
# ============================================================
class TestStaticWiring:
    def test_sources_are_syntactically_valid(self):
        """pytest 兼作语法哨兵（不需要 import 就能发现语法错误）。"""
        for rel in ("core/editor.py", "ui/main_window.py", "core/lsp_client.py"):
            parse_ok(rel)

    def test_lsp_start_always_passes_command(self):
        """核心缺陷 1：lsp_client.start() 必须传 command。"""
        source = read_source("core/editor.py")
        starts = [
            node for node in calls_to(source, "start")
            if isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "lsp_client"
        ]
        assert starts, "core/editor.py 里找不到 lsp_client.start(...) 调用"

        for call in starts:
            assert call.args, (
                "core/editor.py 第 %d 行：lsp_client.start() 没有传 "
                "command —— LspClient.start(command) 是必填位置参数，"
                "这会 TypeError 并被 except 吞掉，LSP 永远起不来"
                % call.lineno
            )

        assert any(
            kw.arg == "working_dir"
            for call in starts for kw in call.keywords
        ), "lsp_client.start() 必须传 working_dir"

    def test_py_only_restriction_removed(self):
        """核心缺陷 2：toggle_lsp 里不得再硬编码只支持 .py/.pyw。

        刻意用 AST 而不是字符串搜索：源码的**注释与 docstring** 里会
        描述历史缺陷（本身就包含 ``'.py', '.pyw'``），字符串搜索会
        把自己的说明文字当成违规。
        """
        source = read_source("core/editor.py")
        func = get_function_node(source, "toggle_lsp")
        assert func is not None, "core/editor.py 里找不到 toggle_lsp"

        literals = string_literals(func)
        assert ".py" not in literals, (
            "toggle_lsp 里仍然硬编码了 Python 扩展名（应为 "
            "LSP_LANGUAGE_BY_EXT 派生的判断）"
        )
        assert ".pyw" not in literals

        names = called_names(func)
        assert "lsp_language_for_file" in names, (
            "toggle_lsp 必须改用 LSP_LANGUAGE_BY_EXT 派生的判断函数，"
            "实际调用了: %s" % sorted(names)
        )

    def test_request_definition_has_production_call_site(self):
        """核心缺陷 3：request_definition 必须被生产代码调用。"""
        source = read_source("core/editor.py")
        calls = calls_to(source, "request_definition")
        assert calls, (
            "core/editor.py 里没有 request_definition 的调用点 "
            "（此前是零调用方的死方法）"
        )

    def test_toggle_lsp_has_production_call_site(self):
        """核心缺陷 3：toggle_lsp 必须被主窗口调用（且带参数）。"""
        source = read_source("ui/main_window.py")
        calls = calls_to(source, "toggle_lsp")
        assert calls, "ui/main_window.py 里没有 toggle_lsp 的生产调用点"
        assert all(call.args for call in calls), (
            "toggle_lsp(...) 必须显式传 enable"
        )

    def test_lsp_menu_action_wired(self):
        """可勾选菜单项必须真的连到 _toggle_lsp。"""
        source = read_source("ui/main_window.py")
        assert "self.lsp_action" in source
        assert "self.lsp_action.setCheckable(True)" in source
        assert "self.lsp_action.toggled.connect(self._toggle_lsp)" in source

    def test_definition_shortcut_is_f12(self):
        source = read_source("ui/main_window.py")
        assert '"🔎 转到定义", "F12"' in source, (
            "转到定义必须绑定 F12（或 Ctrl+Click，由 ui/editor_view.py 负责）"
        )


# ============================================================
# 2. toggle_lsp 的参数与失败可见性
# ============================================================
class TestToggleLsp:
    def test_start_receives_registry_command_and_working_dir(
        self, tmp_path, monkeypatch, make_proxy
    ):
        import core.editor as editor_mod
        from core.lsp_client import LspServerRegistry

        target = tmp_path / "demo.py"
        target.write_text("print('hi')\n", encoding="utf-8")

        proxy, _sc, _doc = make_proxy(target)

        recorder = _make_recording_client_class()
        monkeypatch.setattr(editor_mod, "LspClient", recorder)
        # pylsp 未必装在测试机上；只验证"取到命令并传进去"
        monkeypatch.setattr(
            editor_mod, "lsp_command_available", lambda cmd: True
        )

        assert proxy.toggle_lsp(True) is True

        client = recorder.instances[-1]
        starts = [c for c in client.calls if c[0] == "start"]
        assert starts, "start() 根本没有被调用（P6 的核心缺陷）"

        _, command, working_dir, _env = starts[0]
        assert command == LspServerRegistry.get_command("python"), (
            "start() 收到的 command 不是注册表按语言取出的值: %r" % (command,)
        )
        assert command, "command 不得为空"
        assert working_dir == str(tmp_path), (
            "start() 必须传文件所在目录作为 working_dir，实际 %r"
            % (working_dir,)
        )

        opens = [c for c in client.calls if c[0] == "did_open"]
        assert opens, "did_open 没有被调用"
        assert opens[0][2] == "python", (
            "did_open 的 languageId 应为 python，实际 %r" % (opens[0][2],)
        )

        assert proxy.lsp_active is True
        assert proxy.lsp_client is client

    def test_non_python_file_now_supported(
        self, tmp_path, monkeypatch, make_proxy
    ):
        """核心缺陷 2 的运行时证明：.js 也能走通启动路径。"""
        import core.editor as editor_mod
        from core.lsp_client import LspServerRegistry

        target = tmp_path / "app.js"
        target.write_text("const a = 1;\n", encoding="utf-8")
        proxy, _sc, _doc = make_proxy(target)

        recorder = _make_recording_client_class()
        monkeypatch.setattr(editor_mod, "LspClient", recorder)
        monkeypatch.setattr(
            editor_mod, "lsp_command_available", lambda cmd: True
        )

        assert proxy.toggle_lsp(True) is True
        command = recorder.instances[-1].calls[0][1]
        assert command == LspServerRegistry.get_command("javascript")

    def test_unknown_extension_does_not_crash(self, tmp_path, make_proxy):
        """未知扩展名必须安全返回 False 并给出用户可见提示。"""
        target = tmp_path / "data.xyz"
        target.write_text("nothing\n", encoding="utf-8")
        proxy, _sc, _doc = make_proxy(target)

        messages = []
        proxy.lsp_error.connect(messages.append)
        statuses = []
        proxy.lsp_status_changed.connect(statuses.append)

        assert proxy.toggle_lsp(True) is False
        assert proxy.lsp_client is None, "不支持的扩展名不应创建 LspClient"
        assert messages, "失败必须通过 lsp_error 让用户看见"
        assert "不支持" in messages[0]
        assert statuses == ["unsupported"]

    def test_unsaved_file_does_not_crash(self, make_proxy):
        proxy, _sc, _doc = make_proxy(None)
        messages = []
        proxy.lsp_error.connect(messages.append)

        assert proxy.toggle_lsp(True) is False
        assert messages and "保存" in messages[0]

    def test_supported_ext_without_server_reports_reason(
        self, tmp_path, make_proxy
    ):
        """.json 在 LSP_LANGUAGE_BY_EXT 里有，但注册表没有对应服务器。"""
        target = tmp_path / "data.json"
        target.write_text("{}\n", encoding="utf-8")
        proxy, _sc, _doc = make_proxy(target)

        messages = []
        proxy.lsp_error.connect(messages.append)
        statuses = []
        proxy.lsp_status_changed.connect(statuses.append)

        assert proxy.toggle_lsp(True) is False
        assert proxy.lsp_client is None
        assert messages and "语言服务器" in messages[0]
        assert statuses == ["no_server"]

    def test_missing_server_message_is_actionable(
        self, tmp_path, monkeypatch, make_proxy
    ):
        """失败提示必须具体到"装什么"（P6 要求 ④）。"""
        import core.editor as editor_mod

        target = tmp_path / "demo.py"
        target.write_text("x = 1\n", encoding="utf-8")
        proxy, _sc, _doc = make_proxy(target)

        recorder = _make_recording_client_class()
        monkeypatch.setattr(editor_mod, "LspClient", recorder)
        monkeypatch.setattr(
            editor_mod, "lsp_command_available", lambda cmd: False
        )

        messages = []
        proxy.lsp_error.connect(messages.append)
        statuses = []
        proxy.lsp_status_changed.connect(statuses.append)

        assert proxy.toggle_lsp(True) is False
        text = " ".join(messages)
        assert "pylsp" in text, "提示里必须点名缺失的可执行文件: %r" % text
        assert "pip install python-lsp-server" in text, (
            "提示里必须给出可复制的安装命令: %r" % text
        )
        assert statuses == ["not_found"]
        assert recorder.instances == [], "服务器不可用时不应创建 LspClient"

    def test_toggle_off_cleans_up(self, tmp_path, monkeypatch, make_proxy):
        import core.editor as editor_mod

        target = tmp_path / "demo.py"
        target.write_text("x = 1\n", encoding="utf-8")
        proxy, _sc, _doc = make_proxy(target)

        recorder = _make_recording_client_class()
        monkeypatch.setattr(editor_mod, "LspClient", recorder)
        monkeypatch.setattr(
            editor_mod, "lsp_command_available", lambda cmd: True
        )

        assert proxy.toggle_lsp(True) is True
        assert proxy.toggle_lsp(False) is True
        assert proxy.lsp_client is None
        assert proxy.lsp_active is False


# ============================================================
# 3. request_definition 真正接上（F12）
# ============================================================
class TestGotoDefinition:
    def test_goto_definition_without_lsp_is_user_visible(self, make_proxy):
        proxy, _sc, _doc = make_proxy(None)
        messages = []
        proxy.lsp_error.connect(messages.append)

        assert proxy.goto_definition() is False
        assert messages and "LSP" in messages[0], (
            "未启用 LSP 时必须给出可操作的提示，而不是静默失败"
        )

    def test_goto_definition_calls_request_definition(self, make_proxy):
        proxy, _sc, _doc = make_proxy(None)

        calls = []

        class FakeClient:
            def request_definition(self, uri, line, character):
                calls.append((uri, line, character))

        proxy.lsp_client = FakeClient()
        proxy.lsp_active = True
        proxy._lsp_uri = "file:///d:/demo.py"

        assert proxy.goto_definition() is True
        assert calls and calls[0][0] == "file:///d:/demo.py"

    def test_definition_result_jumps_in_same_file(self, make_proxy):
        target_text = "def foo():\n    pass\n\nfoo()\n"
        proxy, sc, doc = make_proxy(None)
        sc.setText(target_text)
        doc.meta.filepath = os.path.abspath("demo.py")

        proxy._on_lsp_definition([{
            "uri": "file:///" + os.path.abspath("demo.py").replace("\\", "/"),
            "range": {"start": {"line": 3, "character": 0}},
        }])

        assert sc.getCursorPosition()[0] == 3, (
            "同文件内的定义没有跳转（期望第 3 行，实际第 %d 行）"
            % sc.getCursorPosition()[0]
        )

    def test_definition_in_other_file_emits_request(self, make_proxy):
        proxy, _sc, doc = make_proxy(None)
        doc.meta.filepath = os.path.abspath("a.py")

        requests = []
        proxy.definition_requested.connect(
            lambda path, line, ch: requests.append((path, line, ch))
        )

        proxy._on_lsp_definition([{
            "uri": "file:///" + os.path.abspath("b.py").replace("\\", "/"),
            "range": {"start": {"line": 7, "character": 2}},
        }])

        assert len(requests) == 1
        assert requests[0][0].endswith("b.py")
        assert requests[0][1] == 7

    def test_empty_definition_result_is_reported(self, make_proxy):
        proxy, _sc, _doc = make_proxy(None)
        messages = []
        proxy.lsp_error.connect(messages.append)

        proxy._on_lsp_definition([])
        assert messages and "未找到定义" in messages[0]


# ============================================================
# 4. LspClient.start 的健壮性
# ============================================================
class TestLspClientStartGuard:
    def test_empty_command_does_not_raise(self, qapp):
        from core.lsp_client import LspClient, LspState

        client = LspClient()
        errors = []
        client.error_occurred.connect(errors.append)

        client.start([])   # 修复前 command[0] 会 IndexError

        assert client.state == LspState.ERROR
        assert errors, "空命令必须通过 error_occurred 报告"

    def test_none_command_does_not_raise(self, qapp):
        from core.lsp_client import LspClient

        client = LspClient()
        client.start(None)  # type: ignore[arg-type]


# ============================================================
# 5. 主窗口开关真的能驱动 LSP
# ============================================================
class TestMainWindowLspSwitch:
    def test_lsp_action_defaults_off_and_has_no_shortcut(self, window):
        action = getattr(window, "lsp_action", None)
        assert action is not None, "工具菜单缺少 LSP 开关"
        assert action.isCheckable()
        assert not action.isChecked(), "LSP 默认必须关闭"
        assert action.shortcut().isEmpty(), (
            "LSP 开关不应占用快捷键，避免与用户/插件冲突"
        )

    def test_checking_menu_item_reaches_proxy(self, window, monkeypatch):
        """勾选菜单项必须真的调到 EditorProxy.toggle_lsp。"""
        calls = []

        class FakeProxy:
            document = None

            def toggle_lsp(self, enable):
                calls.append(enable)
                return True

        monkeypatch.setattr(
            window.tabs, "current_proxy", lambda: FakeProxy()
        )

        window.lsp_action.setChecked(True)
        assert calls == [True], "勾选 LSP 菜单没有调用 toggle_lsp"

        window.lsp_action.setChecked(False)
        assert calls == [True, False]

    def test_failed_enable_rolls_back_checkbox(self, window, monkeypatch):
        class FailingProxy:
            document = None

            def toggle_lsp(self, enable):
                return False

        monkeypatch.setattr(
            window.tabs, "current_proxy", lambda: FailingProxy()
        )

        window.lsp_action.setChecked(True)
        assert not window.lsp_action.isChecked(), (
            "启用失败后菜单必须回滚为未勾选，否则 UI 与实际状态不一致"
        )

    def test_no_editor_reports_status(self, window, monkeypatch):
        monkeypatch.setattr(window.tabs, "current_proxy", lambda: None)
        window.lsp_action.setChecked(True)
        assert not window.lsp_action.isChecked()

    def test_lsp_pref_round_trip(self, window):
        """开关状态会写进 Preferences（lsp_enabled）。"""
        window.lsp_action.setChecked(False)
        assert window.prefs is not None
        assert not window.prefs.get("lsp_enabled", False)

    def test_install_hint_helper(self):
        from core.editor import lsp_install_hint

        hint = lsp_install_hint("python")
        assert hint == "pip install python-lsp-server"

        # 没有 install 命令的（clangd / jdtls）也要给出可读提示
        assert lsp_install_hint("cpp")
        assert "clangd" in lsp_install_hint("cpp")

        assert lsp_install_hint(None) == ""

    def test_language_helpers(self):
        from core.editor import (
            lsp_language_for_file,
            lsp_server_language_for_file,
        )

        assert lsp_language_for_file("a.py") == "python"
        assert lsp_language_for_file("a.rs") == "rust"
        assert lsp_language_for_file("a.xyz") is None
        assert lsp_language_for_file(None) is None

        assert lsp_server_language_for_file("a.py") == "python"
        # .ts 的 languageId 是 typescript，但注册表键是 javascript
        assert lsp_server_language_for_file("a.ts") == "javascript"
        assert lsp_server_language_for_file("a.md") is None

    def test_resolve_datetime_format(self):
        from core.editor import resolve_datetime_format

        # 默认 date_format 自带时间 → 不得重复追加
        assert resolve_datetime_format(
            "%Y-%m-%d %H:%M:%S", "%H:%M:%S"
        ) == "%Y-%m-%d %H:%M:%S"
        # 纯日期 → 追加 time_format
        assert resolve_datetime_format(
            "%Y-%m-%d", "%H:%M:%S"
        ) == "%Y-%m-%d %H:%M:%S"
        # 兜底
        assert resolve_datetime_format(None, None) == "%Y-%m-%d %H:%M:%S"
