# -*- coding: utf-8 -*-
"""Sprint 4：flaky 隔离清单工具"""

import importlib.util
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _tool():
    spec = importlib.util.spec_from_file_location(
        "qc_flaky", os.path.join(ROOT, "tools", "flaky_quarantine.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_add_list_remove(tmp_path, monkeypatch):
    mod = _tool()
    path = tmp_path / "q.json"
    monkeypatch.setattr(mod, "PATH", str(path))
    path.write_text('{"tests": []}', encoding="utf-8")
    mod.main(["--add", "tests/test_x.py::test_y"])
    assert "tests/test_x.py::test_y" in mod.load()
    mod.main(["--remove", "tests/test_x.py::test_y"])
    assert mod.load() == []
