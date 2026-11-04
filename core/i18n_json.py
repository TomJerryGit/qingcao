# -*- coding: utf-8 -*-
"""轻量 i18n（v2.18.x 脚手架 / v2.19 首批落地）

中文原文 → 目标语言 JSON 映射（locale/<lang>/strings.json）。
语言优先级：环境变量 QINGCAO_LANG > QSettings("QingCao","Editor").ui_language > zh_CN。

    from core.i18n_json import tr, tr_menu, set_language
"""

import io
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LANG = "zh_CN"
AVAILABLE = {"zh_CN": "简体中文", "zh_TW": "繁體中文", "en_US": "English"}
_cache = {}


def _settings():
    try:
        from PyQt5.QtCore import QSettings

        return QSettings("QingCao", "Editor")
    except Exception:
        return None


def current_language() -> str:
    env = os.environ.get("QINGCAO_LANG")
    if env:
        return env
    try:
        s = _settings()
        if s is not None:
            return str(s.value("ui_language", DEFAULT_LANG, type=str) or DEFAULT_LANG)
    except Exception:
        pass
    return DEFAULT_LANG


def set_language(lang: str) -> bool:
    if lang not in AVAILABLE:
        return False
    try:
        s = _settings()
        if s is not None:
            s.setValue("ui_language", lang)
            s.sync()
    except Exception:
        return False
    clear_cache()
    return True


def locale_dir(lang, root=None):
    return os.path.join(root or ROOT, "locale", lang)


def load_strings(lang=None, root=None):
    lang = lang or current_language()
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
    lang = current_language()
    if lang == DEFAULT_LANG:
        return text
    return load_strings(lang).get(text, text)


def _split_prefix(text):
    """拆分前缀（emoji/符号 + 空格）与正文；用于翻译「📄 新建」这类文本"""
    import re

    m = re.match(r"^([^\w\u4e00-\u9fff]{1,6}\s+)(.+)$", text)
    if m:
        return m.group(1), m.group(2)
    return "", text


def _split_accel(text):
    """拆分菜单加速键（如 文件(&F) -> (文件, F)）"""
    import re

    m = re.match(r"^(.*?)\s*\(&([A-Za-z0-9])\)\s*$", text)
    if m:
        return m.group(1), m.group(2)
    return None, None


def tr_menu(text):
    """菜单文本翻译：支持 emoji 前缀与 (&X) 加速键回退匹配"""
    if not text:
        return text
    lang = current_language()
    if lang == DEFAULT_LANG:
        return text
    strings = load_strings(lang)
    if text in strings:
        return strings[text]
    base, accel = _split_accel(text)
    if base is not None:
        translated = strings.get(base)
        if translated:
            return "%s(&%s)" % (translated, accel)
    prefix, rest = _split_prefix(text)
    translated = strings.get(rest)
    if translated:
        return prefix + translated
    return text


def clear_cache():
    _cache.clear()
