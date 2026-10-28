# -*- coding: utf-8 -*-
"""多实例：--new-window 解析、设置目录与会话文件隔离"""
import importlib.util
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, rel):
    path = os.path.join(ROOT, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parse_new_window_flag():
    main = _load("qc_main_mi", "main.py")
    args = main.parse_arguments(["prog", "--new-window", "a.txt", "b.txt"])
    assert args["new_window"] is True
    assert args["files"] == ["a.txt", "b.txt"]
    plain = main.parse_arguments(["prog", "a.txt"])
    assert plain["new_window"] is False


def test_instance_settings_dir():
    main = _load("qc_main_mi2", "main.py")
    base = os.path.join("X", "data")
    assert main.instance_settings_dir(base, 123, False) == base
    assert main.instance_settings_dir(base, 123, True) == \
        os.path.join(base, "instances", "123")


def test_instance_session_file():
    session = _load("qc_session_mi", "app/session.py")
    assert session.instance_session_file("R", False, 1) == \
        os.path.join("R", "session.json")
    assert session.instance_session_file("R", True, 7) == \
        os.path.join("R", "session_w7.json")


def test_cleanup_stale_instance_dirs(tmp_path):
    import importlib.util
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "qc_main_cl", os.path.join(root, "main.py"))
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)
    inst = tmp_path / "instances"
    dead = inst / "999999"
    alive = inst / str(os.getpid())
    dead.mkdir(parents=True)
    alive.mkdir(parents=True)
    removed = main.cleanup_stale_instance_dirs(str(tmp_path))
    assert removed >= 1
    assert not dead.exists()
    assert alive.exists()


def test_remote_open_shows_status():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "ui", "main_window.py"),
               encoding="utf-8").read()
    assert "其它实例已打开" in src


def test_count_alive_instance_dirs(tmp_path):
    import importlib.util
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "qc_main_cap", os.path.join(root, "main.py"))
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)
    inst = tmp_path / "instances"
    (inst / "999999").mkdir(parents=True)
    (inst / str(os.getpid())).mkdir(parents=True)
    assert main.count_alive_instance_dirs(str(tmp_path)) == 1
    assert main.DEFAULT_MAX_NEW_WINDOW_INSTANCES == 3
    assert 1 <= main.get_max_new_window_instances() <= 10


def test_single_instance_focus_wired():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main_src = open(os.path.join(root, "main.py"),
                    encoding="utf-8").read()
    win_src = open(os.path.join(root, "ui", "main_window.py"),
                   encoding="utf-8").read()
    assert "try_focus_existing" in main_src
    assert "MAX_NEW_WINDOW_INSTANCES" in main_src
    assert "_on_focus_requested" in win_src
