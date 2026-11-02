# -*- coding: utf-8 -*-
"""轻量 i18n 脚手架（v2.18.x P3）

设计：不要求一次性改造全部 tr()，先支持**中文原文 → 目标语言**的
JSON 映射（locale/<lang>/strings.json），逐步替换 UI 字符串调用。

    from core.i18n_json import tr
    label = tr("保存")
"""
import io
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LANG = os.environ.get("QINGCAO_LANG", "zh_CN")
_cache = {}


def locale_dir(lang, root=None):
    return os.path.join(root or ROOT, "locale", lang)


def load_strings(lang=None, root=None):
    lang = lang or DEFAULT_LANG
    if lang in _cache:
        return _cache[lang]
    path = os.path.join(locale_dir(lang, root), "strings.json")
    data = {}
    try:
        data = json.load(io.open(path, encoding="utf-8"))
    except Exception:
        data = {}
    _cache[lang] = data
    return data


def tr(text):
    """翻译：命中映射则返回译文，否则返回原文（安全回退）"""
    if not text:
        return text
    return load_strings().get(text, text)


def clear_cache():
    _cache.clear()
