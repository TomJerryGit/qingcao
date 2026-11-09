# -*- coding: utf-8 -*-
"""v2.23 P1-2：ratings.json 发布接线 + 客户端拉取/展示"""

import importlib.util
import json
import os


def _load(name, rel):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(name, os.path.join(root, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, root


def test_publish_builds_ratings(tmp_path):
    mod, root = _load("qc_pub_rat", "tools/publish_registry_release.py")
    path, data = mod.build_ratings(str(tmp_path))
    assert path.endswith("ratings.json")
    assert os.path.isfile(path)
    assert data["version"] == 1
    src = open(os.path.join(root, "tools", "publish_registry_release.py"), encoding="utf-8").read()
    assert "ratings_path" in src


def test_client_fetch_and_cache(monkeypatch):
    from ui import plugin_client as pc

    class Resp:
        status_code = 200

        def json(self):
            return {"plugins": {"demo": {"average": 4.5, "count": 2}}}

    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp())
    monkeypatch.delenv("QINGCAO_NO_COMMUNITY_RATINGS", raising=False)
    client = pc.PluginStoreClient("https://example/reg/registry.json")
    data = client.fetch_ratings()
    assert data["plugins"]["demo"]["average"] == 4.5
    pc.set_community_ratings(data["plugins"])
    assert pc.get_community_rating("demo") == (4.5, 2)


def test_ui_renders_community(monkeypatch):
    from ui import plugin_client as pc

    monkeypatch.setattr(pc, "COMMUNITY_RATINGS", {"demo": {"average": 4.5, "count": 2}})
    store = open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "plugin_store.py"
        ),
        encoding="utf-8",
    ).read()
    detail = open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "plugin_detail.py"
        ),
        encoding="utf-8",
    ).read()
    assert "get_community_rating" in store and "get_community_rating" in detail
    assert os.path.isfile(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "docs",
            "plugin_ratings_aggregate.md",
        )
    )
