# -*- coding: utf-8 -*-
"""C-1 宿主接线：沙箱诊断发布到问题面板 + spell_check 沙箱试点"""
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


class _FakeSandbox:
    def __init__(self, issues):
        self._issues = issues
        self.closed = False

    def diagnostics(self, text):
        return list(self._issues)

    def close(self):
        self.closed = True


def test_run_sandboxed_diagnostics_publishes_to_problems(qapp, tmp_path):
    from core.problems import get_problem_manager
    from ui.main_window import MainWindow

    win = MainWindow()
    fp = ""
    try:
        f = tmp_path / "a.txt"
        f.write_text("hello\n", encoding="utf-8")
        win.tabs.open_file(str(f))
        fp = str(f)
        win._sandboxed_plugins = {
            "fake": _FakeSandbox([
                {"line": 0, "col": 0, "severity": "warning",
                 "message": "fake issue", "code": "D1"},
            ])
        }
        n = win.run_sandboxed_diagnostics()
        assert n == 1, n
        problems = get_problem_manager().get_for_file(fp) or []
        sandbox_problems = [p for p in problems
                            if getattr(p, "source", "") == "sandbox:fake"]
        assert len(sandbox_problems) == 1
        assert sandbox_problems[0].message == "fake issue"

        # 二次运行：覆盖而非重复
        win.run_sandboxed_diagnostics()
        problems = get_problem_manager().get_for_file(fp) or []
        sandbox_problems = [p for p in problems
                            if getattr(p, "source", "") == "sandbox:fake"]
        assert len(sandbox_problems) == 1
    finally:
        try:
            get_problem_manager().set_file_problems(fp, [])
        except Exception:
            pass
        _close(win)


def test_spell_check_back_in_process_with_sandbox_protocol():
    # 沙箱试点已由 plugins/sandbox_demo 完成；spell_check 为支持菜单/
    # 右键增强已恢复进程内运行，但仍保留沙箱协议入口以便再次迁移。
    manifest = json.load(open(os.path.join(
        ROOT, "plugins", "spell_check", "plugin.json"), encoding="utf-8"))
    assert "sandbox" not in manifest
    src = open(os.path.join(ROOT, "plugins", "spell_check", "__init__.py"),
               encoding="utf-8").read()
    assert "def diagnostics(self, text)" in src
    assert "def ignore_flagged_words(self)" in src