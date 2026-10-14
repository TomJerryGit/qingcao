# -*- coding: utf-8 -*-
"""欢迎页主题跟随回归测试

锁死一个真实缺陷：`WelcomeWidget` 及相关面板把 20+ 处颜色**硬编码**为
暗色（#1e1e1e / #2d2d2d / #094771 …），导致浅色主题（如护眼）下出现
"深色欢迎页 + 浅色工具栏"的割裂观感。

原因：内联样式（setStyleSheet）不会随全局 QSS 变化自动更新，
`unpolish/polish` 也无法重算 —— 必须显式重放。

修复方式：各面板新增 `refresh_theme`，`WelcomeWidget.refresh_theme`
重新绑定主题色并让各面板重放样式。

运行::

    python -m pytest tests/test_welcome_theme.py -v
"""
import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DARK_SURFACE_MARKERS = ("#1e1e1e", "#2d2d2d", "#094771")


def _theme_color_set(theme):
    """该主题定义的全部颜色值（小写）"""
    import dataclasses

    from infrastructure.theme_loader import ThemeColors
    return {str(getattr(theme.colors, f.name, "")).lower()
            for f in dataclasses.fields(ThemeColors)}


def _style_colors(text):
    """样式文本里出现的颜色字面量"""
    import re
    return {m.lower() for m in re.findall(r"#[0-9a-fA-F]{6}\b", text)}


def _loader():
    from infrastructure.theme_loader import ThemeLoader
    return ThemeLoader()


def _welcome():
    from ui.welcome_widget import WelcomeWidget
    return WelcomeWidget()


def _all_styles(w):
    """收集欢迎页所有内联样式文本"""
    parts = [w.styleSheet()]
    for attr in ("_content_widget", "_scroll_area"):
        child = getattr(w, attr, None)
        if child is not None:
            parts.append(child.styleSheet())
    from PyQt5.QtWidgets import QWidget
    for child in w.findChildren(QWidget):
        parts.append(child.styleSheet())
    return "\n".join(p for p in parts if p)


def test_has_refresh_theme(qapp):
    w = _welcome()
    assert callable(getattr(w, "refresh_theme", None))


def test_panels_have_refresh_theme(qapp):
    """每个持有内联样式的面板都必须能重放样式"""
    w = _welcome()
    for attr in ("header", "quick_actions", "recent_files",
                 "tips_panel", "stats_panel", "footer"):
        panel = getattr(w, attr, None)
        assert panel is not None, "缺少 %s" % attr
        assert callable(getattr(panel, "refresh_theme", None)), (
            "%s 没有 refresh_theme —— 主题切换时其内联样式不会更新" % attr)


@pytest.mark.parametrize("theme_name,bg", [
    ("eye_protect", "#c7edcc"),
    ("light_clean", "#ffffff"),
    ("high_contrast", "#000000"),
    ("dark_night", "#1e1e1e"),
])
def test_welcome_follows_theme(qapp, theme_name, bg):
    """切换主题后，欢迎页背景应等于该主题的 window_bg"""
    w = _welcome()
    theme = _loader().load_by_name(theme_name)
    assert theme is not None, "主题加载失败: %s" % theme_name

    w.refresh_theme(theme)
    qapp.processEvents()

    own = w.styleSheet().lower()
    content = getattr(w, "_content_widget", None)
    content_ss = content.styleSheet().lower() if content else ""
    assert bg in own, "%s: 欢迎页背景未使用 window_bg=%s" % (theme_name, bg)
    assert bg in content_ss, "%s: content 未使用 window_bg=%s" % (
        theme_name, bg)


@pytest.mark.parametrize("theme_name", ["eye_protect", "light_clean"])
def test_styles_only_use_theme_colors(qapp, theme_name):
    """浅色主题下，欢迎页样式里出现的颜色**必须来自该主题**

    这次缺陷的本质是"内联样式硬编码暗色、不随主题重放"。因此最准确的
    判据不是"没有某个颜色"，而是"所用的颜色都属于当前主题" ——
    这样即使某个颜色恰好与主题值相同（如 light_clean 的 button_pressed
    #0a4d7a），也不会误报。
    """
    w = _welcome()
    theme = _loader().load_by_name(theme_name)
    w.refresh_theme(theme)
    qapp.processEvents()

    used = _style_colors(_all_styles(w))
    allowed = _theme_color_set(theme)
    unknown = sorted(c for c in used if c not in allowed)
    assert not unknown, (
        "%s：欢迎页样式里出现不属于该主题的颜色 %s —— "
        "说明有内联样式仍硬编码、未随主题重放" % (theme_name, unknown))


@pytest.mark.parametrize("theme_name", ["eye_protect", "light_clean"])
def test_no_dark_surface_in_light_themes(qapp, theme_name):
    """浅色主题下不应出现暗色**背景**值（本次缺陷的直观防线）"""
    w = _welcome()
    theme = _loader().load_by_name(theme_name)
    w.refresh_theme(theme)
    qapp.processEvents()

    styles = _all_styles(w).lower()
    leaked = [c for c in DARK_SURFACE_MARKERS if c in styles]
    assert not leaked, (
        "%s 是浅色主题，但欢迎页样式中仍残留暗色 %s" % (theme_name, leaked))



def test_dark_theme_still_dark(qapp):
    """暗色主题本身不受影响"""
    w = _welcome()
    theme = _loader().load_by_name("dark_night")
    w.refresh_theme(theme)
    qapp.processEvents()
    styles = _all_styles(w).lower()
    assert "#1e1e1e" in styles, "暗色主题下欢迎页应仍是深色"


def test_refresh_theme_without_arg_does_not_crash(qapp):
    """theme=None 时不应抛异常（ThemeLoader 可能传 None）"""
    w = _welcome()
    w.refresh_theme(None)
    w.refresh_theme()


def test_theme_proxy_fallback(qapp):
    """_ThemeProxy 在任何情况下都应返回可用颜色，不抛异常"""
    from ui.welcome_widget import C
    for attr in ("window_bg", "panel_fg", "success", "border"):
        val = getattr(C, attr)
        assert isinstance(val, str) and val.startswith("#"), attr
