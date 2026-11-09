# -*- coding: utf-8 -*-
"""v2.23 D3：ui/plugin_store.py 拆分结构回归"""

import dataclasses
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_plugin_store_split_structure():
    lines = len(open(os.path.join(ROOT, "ui", "plugin_store.py"), encoding="utf-8").readlines())
    assert lines < 1500, "plugin_store.py 拆分后应 < 1500 行，当前 %d" % lines
    for name in ("plugin_client.py", "plugin_detail.py"):
        assert os.path.isfile(os.path.join(ROOT, "ui", name))


def test_plugin_reexports_and_dataclass():
    import ui.plugin_client as client
    from ui.plugin_detail import InstallProgressDialog, PluginDetailDialog
    from ui.plugin_store import (
        SORT_OPTIONS,
        PluginCard,
        PluginInfo,
        PluginStoreClient,
        PluginStoreDialog,
        build_market_catalog,
        check_plugin_compatibility,
    )

    assert PluginInfo is client.PluginInfo
    assert PluginStoreClient is client.PluginStoreClient
    assert callable(build_market_catalog)
    assert callable(check_plugin_compatibility)
    fields = {f.name for f in dataclasses.fields(PluginInfo)}
    assert {"name", "version", "file_hash", "signature"} <= fields
    assert any(key == "local_rating" for key, _ in SORT_OPTIONS)
    for cls in (PluginCard, PluginStoreDialog, PluginDetailDialog, InstallProgressDialog):
        assert cls is not None
