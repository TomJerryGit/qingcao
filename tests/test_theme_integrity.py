# -*- coding: utf-8 -*-
"""主题完整性回归测试

锁死两个曾经导致真实缺陷的不变量：

  1. **JSON 优先于内置定义**
     `load_by_name()` 原先优先返回内置定义，而内置 `eye_protect()` 只
     显式设置 32/70 个键，缺失键回退到暗色默认值 → 护眼主题（浅绿底）
     上菜单栏/工具栏文字变成浅灰 #d4d4d4，**几乎不可见**。

  2. **所有主题键集合一致 + 对比度达标**
     避免某个主题缺键静默回退，或配色对比度过低不可读。

运行::

    python -m pytest tests/test_theme_integrity.py -v
"""
import io
import json
import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

THEMES_DIR = os.path.join(ROOT, "themes")

# 正文类最低对比度（WCAG AA）
MIN_CONTRAST_TEXT = 4.5
# 非正文（行号、边距、光标等）最低对比度
MIN_CONTRAST_UI = 3.0


def _rgb(s):
    s = (s or "").lstrip("#")
    if len(s) == 8:
        s = s[2:]
    if len(s) != 6:
        return None
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _lum(rgb):
    def ch(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg, bg):
    l1, l2 = _lum(fg), _lum(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def _theme_files():
    if not os.path.isdir(THEMES_DIR):
        return []
    return sorted(f for f in os.listdir(THEMES_DIR) if f.endswith(".json"))


def _load(name):
    with io.open(os.path.join(THEMES_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def test_theme_files_exist():
    files = _theme_files()
    assert files, "themes/ 下应有主题 JSON"
    names = {_load(f).get("name") for f in files}
    for expected in ("dark_night", "light_clean", "eye_protect",
                     "high_contrast"):
        assert expected in names, "缺少内置主题 %s" % expected


def test_all_themes_share_same_keys():
    """键集合必须一致，否则缺失键会静默回退到默认色"""
    files = _theme_files()
    keysets = {f: set(_load(f).get("colors", {})) for f in files}
    union = set()
    for s in keysets.values():
        union |= s
    for f, s in keysets.items():
        missing = sorted(union - s)
        assert not missing, "%s 缺少颜色键: %s" % (f, missing)


def test_color_values_are_valid_hex():
    for f in _theme_files():
        for k, v in _load(f).get("colors", {}).items():
            assert _rgb(v) is not None, "%s: %s=%r 不是合法颜色" % (f, k, v)


@pytest.mark.parametrize("fname", _theme_files())
def test_editor_text_contrast(fname):
    """编辑器正文必须达到 WCAG AA 4.5:1"""
    c = _load(fname)["colors"]
    ratio = _contrast(_rgb(c["foreground"]), _rgb(c["background"]))
    assert ratio >= MIN_CONTRAST_TEXT - 0.01, (
        "%s 正文对比度 %.2f:1 低于 %.1f" % (fname, ratio, MIN_CONTRAST_TEXT))


@pytest.mark.parametrize("fname", _theme_files())
def test_menubar_and_menu_contrast(fname):
    """菜单栏/下拉菜单文字必须可读（护眼主题曾在此失效）"""
    c = _load(fname)["colors"]
    for fg_k, bg_k in (("menubar_fg", "menubar_bg"),
                       ("menu_fg", "menu_bg"),
                       ("statusbar_fg", "statusbar_bg"),
                       ("button_fg", "button_bg"),
                       ("panel_fg", "panel_bg")):
        fg, bg = _rgb(c.get(fg_k)), _rgb(c.get(bg_k))
        if fg is None or bg is None:
            continue
        ratio = _contrast(fg, bg)
        assert ratio >= MIN_CONTRAST_TEXT - 0.01, (
            "%s %s/%s 对比度 %.2f:1 低于 %.1f"
            % (fname, fg_k, bg_k, ratio, MIN_CONTRAST_TEXT))


@pytest.mark.parametrize("fname", _theme_files())
def test_ui_element_contrast(fname):
    """行号/边距/光标等非正文元素至少 3:1"""
    c = _load(fname)["colors"]
    pairs = (("line_number_fg", "line_number_bg"),
             ("margin_fg", "margin_bg"),
             ("fold_margin_fg", "fold_margin_bg"),
             ("caret", "background"))
    for fg_k, bg_k in pairs:
        fg, bg = _rgb(c.get(fg_k)), _rgb(c.get(bg_k))
        if fg is None or bg is None:
            continue
        ratio = _contrast(fg, bg)
        assert ratio >= MIN_CONTRAST_UI - 0.01, (
            "%s %s/%s 对比度 %.2f:1 低于 %.1f"
            % (fname, fg_k, bg_k, ratio, MIN_CONTRAST_UI))


def test_eye_protect_is_light_type():
    """护眼主题必须是浅色类型（内置定义曾错标成 dark）"""
    d = _load("eye_protect.json")
    assert d["type"] == "light", "护眼主题 type 应为 light，实际 %r" % d["type"]
    bg = _rgb(d["colors"]["background"])
    assert _lum(bg) > 0.5, "护眼主题背景应为浅色"


def test_json_takes_priority_over_builtin(qapp):
    """回归防线：load_by_name 必须返回**完整 JSON** 而非残缺内置定义

    这是"护眼主题文字不可见"的直接原因：内置 eye_protect() 缺 38/70 个键，
    缺失键回退暗色默认值。
    """
    from infrastructure.theme_loader import ThemeLoader
    loader = ThemeLoader()
    theme = loader.load_by_name("eye_protect")
    assert theme is not None

    with io.open(os.path.join(THEMES_DIR, "eye_protect.json"),
                 encoding="utf-8") as f:
        json_colors = json.load(f)["colors"]

    # 关键键必须与 JSON 一致（而不是暗色默认值 #d4d4d4）
    for k in ("window_fg", "menubar_fg", "menu_fg", "button_bg"):
        got = getattr(theme.colors, k)
        assert got == json_colors[k], (
            "主题 %s=%s 与 JSON %s=%s 不一致 —— JSON 未生效，"
            "可能又回退到残缺的内置定义"
            % (k, got, k, json_colors[k]))


def test_no_duplicate_theme_names(qapp):
    """load_all 不应出现同名重复项（内置 + JSON 同时返回）"""
    from infrastructure.theme_loader import ThemeLoader
    names = [t.name for t in ThemeLoader().load_all()]
    dups = {n for n in names if names.count(n) > 1}
    assert not dups, "主题列表存在重复名称: %s" % dups


def test_theme_dirs_resolve_for_frozen(monkeypatch):
    """打包运行时必须能解析到 _internal/themes"""
    import infrastructure.theme_loader as tl
    fake_internal = os.path.join(ROOT, "_fake_internal")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", os.path.join(ROOT, "_fake_meipass"),
                        raising=False)
    dirs = tl.resolve_theme_dirs("themes")
    assert any("themes" in d for d in dirs), dirs
    assert any(os.path.join("_internal", "themes") in d for d in dirs), (
        "冻结运行时应包含 _internal/themes，实际: %s" % dirs)
    del fake_internal
