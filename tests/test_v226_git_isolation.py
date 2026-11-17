# -*- coding: utf-8 -*-
"""v2.26 B3：git_deep 隔离（宿主受控 Git API）"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _API:
    is_isolated = True

    def __init__(self):
        self.calls = []

    def get_current_filepath(self):
        return "/repo/a.py"

    def git_branch(self, filepath):
        self.calls.append(("branch", filepath))
        return "main"

    def git_status(self, filepath):
        return {"a.py": "M"}

    def git_diff(self, filepath, staged=False):
        return "diff"

    def git_log(self, filepath, limit=30):
        return [{"hash": "abc", "message": "m", "author": "a", "when": "now"}]

    def git_commit(self, filepath, message):
        return True, "ok"

    def git_push(self, filepath):
        return True, "ok"

    def git_pull(self, filepath):
        return False, "nope"

    def git_switch(self, filepath, name, create=False):
        return True, "ok"

    def git_hunks(self, filepath):
        return [{"index": 0, "preview": "@@ -1 +1 @@"}]

    def git_stage_hunks(self, filepath, indices):
        self.calls.append(("stage", indices))
        return True, "ok"

    def log(self, *a, **k):
        pass

    def show_status(self, *a, **k):
        pass

    def show_message(self, *a, **k):
        pass

    def ask_string(self, *a, **k):
        return ("0", True)


def test_isolated_adapter_uses_host_git():
    from plugins.git_deep import Plugin

    plugin = Plugin()
    plugin.api = _API()
    git = plugin._get_git()
    assert git.current_branch() == "main"
    assert git.status() == {"a.py": "M"}
    assert git.log(5)[0]["hash"] == "abc"
    assert git.commit("msg") == (True, "ok")
    assert git.switch_branch("dev", create=True) == (True, "ok")


def test_broker_has_git_permissions():
    from core.plugin_host import METHOD_PERMISSIONS

    for name in (
        "git_status",
        "git_branch",
        "git_diff",
        "git_commit",
        "git_push",
        "git_pull",
        "git_switch",
    ):
        assert name in METHOD_PERMISSIONS


def test_git_deep_in_isolatable_set():
    from app.plugin_isolation import ISOLATABLE_PLUGINS

    assert "git_deep" in ISOLATABLE_PLUGINS


def test_isolated_stage_hunks():
    from plugins.git_deep import Plugin

    plugin = Plugin()
    api = _API()
    plugin.api = api
    plugin.stage_hunks()
    assert ("stage", [0]) in api.calls
