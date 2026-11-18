# -*- coding: utf-8 -*-
def test_plugin_i18n():
    from core import plugin_i18n as i18n

    i18n.set_locale("zh_CN")
    assert i18n.tr("plugin.market", "插件市场") == "插件市场"
    i18n.set_locale("en_US")
    assert i18n.tr("plugin.market") == "Plugin Market"
    assert i18n.tr("missing.key", "回退") == "回退"
    assert i18n.tr("hi {name}", "hi {name}", name="x") == "hi x"
