# -*- coding: utf-8 -*-
"""v2.26 P2：Git hunk 暂存/分支"""

import subprocess
import types


ROOT_DIFF = """diff --git a/a.py b/a.py
index 111..222 100644
--- a/a.py
+++ b/a.py
@@ -1,3 +1,3 @@
 line1
-old1
+new1
 line3
@@ -10,3 +10,3 @@
 line10
-old2
+new2
 line12
"""


def test_parse_and_build_hunk_patch():
    from core.git_client import GitClient

    header, hunks = GitClient.parse_hunks(ROOT_DIFF)
    assert "diff --git" in header and len(hunks) == 2
    patch = GitClient.build_hunk_patch(ROOT_DIFF, [1])
    assert "new2" in patch and "new1" not in patch


def test_stage_hunks_applies_selected(monkeypatch):
    from core.git_client import GitClient

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = GitClient(".")
    monkeypatch.setattr(client, "_run", lambda args, cwd=None: (0, ROOT_DIFF, ""))
    ok, out = client.stage_hunks("a.py", [0])
    assert ok
    assert "apply" in captured["cmd"] and "--cached" in captured["cmd"]
    assert "new1" in captured["input"] and "new2" not in captured["input"]


def test_switch_branch_args(monkeypatch):
    from core.git_client import GitClient

    seen = {}

    def fake_run(args, cwd=None):
        seen["args"] = args
        return 0, "", ""

    client = GitClient(".")
    monkeypatch.setattr(client, "_run", fake_run)
    ok, out = client.switch_branch("feature/x", create=True)
    assert ok and seen["args"] == ["switch", "-c", "feature/x"]


def test_plugin_has_status_and_hunk_ui():
    src = open("plugins/git_deep/__init__.py", encoding="utf-8").read()
    for text in ("暂存选中 Hunk", "切换分支", "查看暂存差异", "_refresh_status"):
        assert text in src
