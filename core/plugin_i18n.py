# -*- coding: utf-8 -*-
"""插件 i18n 基础：中文回退 + 英文字典（后续扩展到 ja/ko）。"""

import os


_LOCALE = os.environ.get("QINGCAO_LOCALE", "zh_CN")
_EN = {
    "plugin.market": "Plugin Market",
    "plugin.install": "Install",
    "plugin.uninstall": "Uninstall",
    "plugin.enable": "Enable",
    "plugin.disable": "Disable",
    "plugin.settings": "Settings",
    "plugin.usage": "Usage",
    "plugin.rating": "Rating",
    "common.close": "Close",
    "common.cancel": "Cancel",
    "common.save": "Save",
    "common.search": "Search",
}
_ZH = {}


def set_locale(locale):
    global _LOCALE
    _LOCALE = str(locale or "zh_CN")


def get_locale():
    return _LOCALE


def tr(key, default=None, **kwargs):
    table = _EN if _LOCALE.lower().startswith("en") else _ZH
    text = table.get(key)
    if text is None:
        text = default if default is not None else key
    try:
        return text.format(**kwargs) if kwargs else text
    except Exception:
        return text
