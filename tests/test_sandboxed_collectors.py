# -*- coding: utf-8 -*-
"""B-3b：宿主沙箱注册表 + 符号收集合并测试"""


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


class _FakeSandbox:
    def __init__(self):
        self.closed = False
        self.symbols_calls = 0

    def symbols(self, text, filepath="", language=""):
        self.symbols_calls += 1
        return [{"name": "sandbox_sym", "type": "function", "line": 0}]

    def close(self):
        self.closed = True


def test_sandboxed_symbols_merged_into_collector(qapp):
    from ui.main_window import MainWindow
    win = MainWindow()
    try:
        fake = _FakeSandbox()
        win._sandboxed_plugins = {"fake": fake}
        items = win.collect_plugin_symbols("x", "a.md", "markdown")
        names = [i["name"] for i in items]
        assert "sandbox_sym" in names, names
        assert fake.symbols_calls >= 1
    finally:
        _close(win)


def test_close_sandboxed_plugins_closes_all(qapp):
    from ui.main_window import MainWindow
    win = MainWindow()
    try:
        a, b = _FakeSandbox(), _FakeSandbox()
        win._sandboxed_plugins = {"a": a, "b": b}
        win._close_sandboxed_plugins()
        assert a.closed and b.closed
        assert win._sandboxed_plugins == {}
    finally:
        _close(win)


def test_discovery_defaults_empty_without_manifest_flag(qapp):
    from ui.main_window import MainWindow
    win = MainWindow()
    try:
        # 仓库内置插件当前都没有声明 sandbox: true
        result = win._get_sandboxed_plugins()
        assert isinstance(result, dict)
        assert result == {}
    finally:
        _close(win)