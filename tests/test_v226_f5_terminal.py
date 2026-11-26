# -*- coding: utf-8 -*-
"""F5 智能运行：input() 分支进入内嵌控制台"""

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


class _Panel:
    def __init__(self):
        self.calls = []

    def show(self):
        pass

    def raise_(self):
        pass

    def run_file(self, path, interpreter="python"):
        self.calls.append((path, interpreter))


class _Fake:
    def __init__(self):
        self.tabs = _Tabs()
        self.status_bar = _Status()
        self.plugins = []
        self.run_console = _Panel()


def test_input_script_uses_embedded_console(qapp):
    from ui.mixins.window_theme_mixin import WindowThemeMixin

    fake = _Fake()
    fake._run_in_terminal = WindowThemeMixin._run_in_terminal.__get__(fake)
    fake._python_executable = lambda: "python-test"
    fake._show_run_console = lambda: fake.run_console
    WindowThemeMixin._run_current_file(fake)
    assert fake.run_console.calls
    assert "demo.py" in fake.run_console.calls[0][0]
