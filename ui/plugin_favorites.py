# -*- coding: utf-8 -*-
"""P4：插件收藏（QSettings 持久化）。"""
from PyQt5.QtCore import QSettings


def _settings():
    return QSettings("QingCao", "PluginMarket")


def load_favorites(settings=None):
    s = settings or _settings()
    raw = s.value("favorites", [], type=list) or []
    return {str(x) for x in raw if str(x)}


def is_favorite(name, settings=None):
    return str(name) in load_favorites(settings)


def toggle_favorite(name, settings=None):
    s = settings or _settings()
    names = load_favorites(s)
    key = str(name)
    if key in names:
        names.discard(key)
        state = False
    else:
        names.add(key)
        state = True
    s.setValue("favorites", sorted(names))
    s.sync()
    return state
