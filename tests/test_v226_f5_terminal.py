# -*- coding: utf-8 -*-
"""F5 智能运行：input() 分支使用新控制台"""

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
        return "name = input('name?')\nprint(name)\n"


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


def test_input_script_uses_console(qapp, monkeypatch):
    import subprocess

    from ui.mixins.window_theme_mixin import WindowThemeMixin

    calls = []

    class _Popen:
        def __init__(self, *a, **k):
            calls.append((a, k))

    monkeypatch.setattr(subprocess, "Popen", _Popen)
    fake = _Fake()
    fake._run_in_terminal = WindowThemeMixin._run_in_terminal.__get__(fake)
    WindowThemeMixin._run_current_file(fake)
    assert calls, "未启动新控制台"
    assert calls[0][1].get("creationflags") & subprocess.CREATE_NEW_CONSOLE
