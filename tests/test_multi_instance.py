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