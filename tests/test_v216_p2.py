# -*- coding: utf-8 -*-
"""v2.16 P2：分片自适应 / 诊断来源列 / 广播 ACK 重试"""
import importlib.util
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(path, name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pick_shards_by_cpu():
    mod = _load(os.path.join("tools", "run_tests_sharded.py"), "qc_shards")
    assert mod.pick_shards(2) == 2
    assert mod.pick_shards(4) == 2
    assert mod.pick_shards(6) == 3
    assert mod.pick_shards(16) == 4
    assert mod.pick_shards(16, cap=3) == 3


def test_ci_uses_auto_shards():
    yml = open(os.path.join(ROOT, ".github", "workflows", "test.yml"),
               encoding="utf-8").read()
    assert "run_tests_sharded.py --auto-shards" in yml


def test_problems_panel_source_column(qapp):
    from core.problems import Problem, get_problem_manager
    from ui.main_window import MainWindow
    from ui.problems_panel import ProblemsPanel
    manager = get_problem_manager()
    manager.clear()
    fp = os.path.join(ROOT, "tests", "fixture_p2.py")
    manager.set_file_problems(fp, [
        Problem(filepath=fp, line=0, col=0, severity="info",
                message="m", source="sandbox:dummy"),
    ])
    win = MainWindow()
    panel = ProblemsPanel(main_window=win)
    try:
        panel.refresh()
        top = panel.tree.topLevelItem(0)
        assert top is not None
        assert top.child(0).text(4) == "sandbox:dummy"
    finally:
        manager.clear()
        panel.close()
        try:
            sess = getattr(win, "session", None)
            if sess is not None and hasattr(sess, "save"):
                sess.save = lambda *a, **k: None
        except Exception:
            pass
        win.close()


def test_broadcast_ack_retry(qapp):
    from infrastructure.instance_broadcast import InstanceBroadcaster
    b = InstanceBroadcaster()
    try:
        b.announce("C:/tmp/x.txt", 1.0)
        assert b._pending_acks, "announce 应登记待确认"
        msg_id = next(iter(b._pending_acks))
        b._dispatch(json.dumps({"v": 1, "type": "ack",
                                "msg_id": msg_id, "pid": 999}))
        assert not b._pending_acks, "收到 ack 后应清除待确认"
        # 带 msg_id 的远端保存也应回复 ack（无 socket 时不报错）
        b._dispatch(json.dumps({"v": 1, "type": "file_saved",
                                "path": "C:/tmp/y.txt", "mtime": 1.0,
                                "pid": 999, "msg_id": "x-1"}))
    finally:
        b.stop()