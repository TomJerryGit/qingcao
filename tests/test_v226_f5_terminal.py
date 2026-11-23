# -*- coding: utf-8 -*-
"""F5 智能终端运行：input() 分支"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _Input:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = text


class _Tab:
    def __init__(self):
        self.input = _Input()
        self.sent = []

    def send_raw(self, data):
        self.sent.append(data)

    def run_command(self):
        self.sent.append(self.input.text)


class _Terminal:
    def __init__(self):
        self._tab = _Tab()
        self.input = self._tab.input
        self.tabs = self

    def currentWidget(self):
        return self._tab

    def show(self):
        pass

    def raise_(self):
        pass

    def run_command(self):
        self._tab.run_command()


class _Doc:
    filepath = "D:/tmp/demo.py"


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
        self.terminal = _Terminal()
        self.status_bar = _Status()
        self.plugins = []


def test_input_script_uses_terminal(qapp):
    from ui.mixins.window_theme_mixin import WindowThemeMixin

    fake = _Fake()
    fake._run_in_terminal = WindowThemeMixin._run_in_terminal.__get__(fake)
    WindowThemeMixin._run_current_file(fake)
    assert fake.terminal._tab.sent
    assert "demo.py" in fake.terminal._tab.sent[-1]
