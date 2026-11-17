# -*- coding: utf-8 -*-
"""v2.26：隔离插件 UI 级 e2e（git_deep 菜单 → 宿主 Git API → 对话框）"""

import os
import sys

from PyQt5.QtWidgets import QMainWindow, QMessageBox, QTabWidget, QWidget


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _pump(app, predicate, timeout_ms=5000):
    import time

    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


class _Proxy:
    def __init__(self):
        self.inserted = []
        self.replaced = []

    def insert_text(self, text):
        self.inserted.append(text)

    def replace_selected_text(self, text):
        self.replaced.append(text)

    def text(self):
        return "b\na\n"

    def get_filepath(self):
        return os.path.join(ROOT, "README.md")


class _Editor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.proxy = _Proxy()


class _Win(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tabs = QTabWidget(self)
        self.tabs.addTab(_Editor(), "README")
        self.setCentralWidget(self.tabs)


def test_isolated_git_deep_menu_e2e(qapp, monkeypatch):
    from ui.isolated_plugins import IsolatedPluginHost

    captured = {}
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: captured.setdefault("msg", a[2] if len(a) > 2 else a),
    )
    win = _Win()
    host = IsolatedPluginHost(win)
    try:
        host.start({"git_deep"})
        assert _pump(qapp, lambda: bool(host.api.menus)), "隔离菜单未注册"
        action = next((a for a in host.api.menus.values() if a.text() == "查看状态"), None)
        assert action is not None, [a.text() for a in host.api.menus.values()]
        action.trigger()
        assert _pump(qapp, lambda: bool(captured.get("msg"))), "未弹出 Git 状态"
        assert "分支" in str(captured["msg"]) or "无变更" in str(captured["msg"])
    finally:
        host.stop_all()
        win.close()


def test_isolated_python_debugger_e2e(qapp, tmp_path, monkeypatch):
    import time

    from core.debug_service import get_debug_service
    from ui.isolated_plugins import IsolatedPluginHost

    script = tmp_path / "target.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    win = _Win()
    win.tabs.currentWidget().proxy = _DebugProxy(str(script))
    monkeypatch.setenv("QINGCAO_TRUSTED_PLUGINS", "python_debugger")
    host = IsolatedPluginHost(win)
    service = get_debug_service()
    try:
        host.start({"python_debugger"})
        assert _pump(qapp, lambda: bool(host.api.menus)), "调试器菜单未注册"
        start = next((a for a in host.api.menus.values() if a.text() == "调试当前文件"), None)
        assert start is not None, [a.text() for a in host.api.menus.values()]
        start.trigger()
        deadline = time.time() + 15
        while time.time() < deadline and service.session is None:
            qapp.processEvents()
            time.sleep(0.02)
        assert service.session is not None, "宿主调试会话未启动"
        stop = next((a for a in host.api.menus.values() if a.text() == "终止调试"), None)
        assert stop is not None
        stop.trigger()
        deadline = time.time() + 10
        while time.time() < deadline and service.session is not None:
            qapp.processEvents()
            time.sleep(0.02)
        assert service.session is None, "调试会话未停止"
    finally:
        service.shutdown()
        host.stop_all()
        win.close()


class _DebugProxy(_Proxy):
    def __init__(self, path):
        self._path = path

    def get_filepath(self):
        return self._path


class _AIClient:
    def chat(self, prompt, system="", use_history=False, **kwargs):
        return "AI-REPLY:" + prompt[:20]

    def chat_stream(self, prompt, system="", callback=None, use_history=False, **kwargs):
        text = "STREAM:"
        for part in ("a", "b", "c"):
            text += part
            if callback:
                callback(part)
        return text


def test_isolated_ai_assistant_headless(qapp, monkeypatch):
    from core.ai_service import AIService, set_ai_service
    from ui.isolated_plugins import IsolatedPluginHost

    set_ai_service(AIService(client=_AIClient()))
    captured = {}
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *a, **k: captured.setdefault("msg", a[2] if len(a) > 2 else a),
    )
    win = _Win()
    host = IsolatedPluginHost(win)
    # 关闭自动弹窗，避免模态事件与 diff 断言竞态（弹窗逻辑另有覆盖）
    host.api.settings.setValue("plugins/ai_assistant/auto_result_dialog", False)
    try:
        host.start({"ai_assistant"})
        assert _pump(qapp, lambda: bool(host.api.menus), 12000), "AI 隔离菜单未注册"
        action = next((a for a in host.api.menus.values() if a.text() == "解释代码"), None)
        assert action is not None, [a.text() for a in host.api.menus.values()]
        action.trigger()

        def _panel_text():
            panel = getattr(host.api, "_ai_panel", None)
            return panel.view.toPlainText() if panel is not None else ""

        assert _pump(qapp, lambda: "abc" in _panel_text(), 12000), "流式输出未显示"
        assert "abc" in _panel_text()
        assert "ai_output" in host.api.remote_panels
        combo = host.api._ai_panel.session_combo
        assert combo.count() >= 1
        editor = win.tabs.currentWidget()
        insert = next((a for a in host.api.menus.values() if a.text() == "插入结果到光标"), None)
        assert insert is not None
        insert.trigger()
        assert _pump(qapp, lambda: bool(editor.proxy.inserted), 8000)
        assert "abc" in editor.proxy.inserted[-1]
        captured.clear()
        diff_action = next((a for a in host.api.menus.values() if a.text() == "预览差异"), None)
        assert diff_action is not None
        diff_action.trigger()
        assert _pump(
            qapp,
            lambda: "AI 建议" in str(captured.get("msg", "")),
            12000,
        ), "未打开差异预览"
        msg = str(captured["msg"])
        assert "+abc" in msg or "abc" in msg
    finally:
        set_ai_service(None)
        host.stop_all()
        win.close()


def test_isolated_debugger_breakpoint(qapp, tmp_path, monkeypatch):
    import time

    from core.debug_service import get_debug_service
    from ui.isolated_plugins import IsolatedPluginHost

    script = tmp_path / "loop.py"
    script.write_text(
        "import time\nx = 0\nfor i in range(30):\n    x = i\n    time.sleep(0.05)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("QINGCAO_TRUSTED_PLUGINS", "python_debugger")
    win = _Win()
    win.tabs.currentWidget().proxy = _DebugProxy(str(script))
    host = IsolatedPluginHost(win)
    service = get_debug_service()
    try:
        host.start({"python_debugger"})
        assert _pump(qapp, lambda: bool(host.api.menus)), "调试器菜单未注册"
        start = next((a for a in host.api.menus.values() if a.text() == "调试当前文件"), None)
        assert start is not None
        start.trigger()
        deadline = time.time() + 15
        while time.time() < deadline and service.session is None:
            qapp.processEvents()
            time.sleep(0.02)
        assert service.session is not None, "宿主调试会话未启动"
        service.handle("debug.set_breakpoints", {"files": {str(script): [3]}})
        service.handle("debug.continue")
        deadline = time.time() + 10
        while time.time() < deadline and service.last_break is None:
            qapp.processEvents()
            time.sleep(0.02)
        assert service.last_break is not None, "未命中隔离调试断点"
        panel_action = next(
            (a for a in host.api.menus.values() if a.text() == "显示调试面板"), None
        )
        assert panel_action is not None
        panel_action.trigger()
        assert _pump(qapp, lambda: getattr(host.api, "_debug_panel", None) is not None, 8000), (
            "宿主调试面板未创建"
        )
        for label, attr in (("查看局部变量", "last_locals"), ("查看调用栈", "last_stack")):
            action = next((a for a in host.api.menus.values() if a.text() == label), None)
            assert action is not None, label + " 菜单缺失"
            action.trigger()
            deadline = time.time() + 8
            while time.time() < deadline and getattr(service, attr) is None:
                qapp.processEvents()
                time.sleep(0.02)
            assert getattr(service, attr) is not None, label + " 未返回"
    finally:
        service.shutdown()
        host.stop_all()
        win.close()
