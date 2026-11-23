# -*- coding: utf-8 -*-
"""F5 交互脚本：使用真实 Python 解释器"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _Doc:
    filepath = r"D:\tmp\demo.py"


class _Proxy:
    document = _Doc()

    def get_text(self):
        return "name = input('name?')\n"


class _Tabs:
    def current_proxy(self):
        return _Proxy()


class _Status:
    def __init__(self):
        self.messages = []

    def showMessage(self, msg, *a):
        self.messages.append(msg)


class _Fake:
    def __init__(self):
        self.tabs = _Tabs()
        self.status_bar = _Status()
        self.plugins = []


def test_uses_python_not_editor(qapp, monkeypatch):
    import subprocess

    from ui.mixins.window_theme_mixin import WindowThemeMixin

    calls = []

    class _Popen:
        def __init__(self, args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.setattr(subprocess, "Popen", _Popen)
    fake = _Fake()
    fake._run_in_terminal = WindowThemeMixin._run_in_terminal.__get__(fake)
    fake._python_executable = lambda: "python-test"
    WindowThemeMixin._run_current_file(fake)
    assert calls, "未启动控制台"
    assert calls[0][0][0].lower() == "cmd.exe"
    assert "demo.py" in " ".join(calls[0][0])
