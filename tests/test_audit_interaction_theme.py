# -*- coding: utf-8 -*-
"""
交互审计：主题 × 组件 / 偏好设置
==============================

覆盖的交互：
    1. 主题 × 面板自定义 QSS —— adapt_qss_colors 的替换表存在
       "链式二次替换"，把已经换好的文字色又换成了面板背景色。
    2. 主题 × 编辑器偏好       —— loader.apply 无条件打开
       "高亮当前行"，覆盖用户的 show_current_line 设置。

断言不变式：
    INV-T1  adapt_qss_colors(qss, theme) 的输出中，原本是
            "文字色" 的位置必须是该主题的 foreground/tab_fg，
            不能被换成背景色（否则文字与背景同色 = 不可见）。
    INV-T2  应用主题不应修改与主题无关的编辑器显示偏好。

运行方式：
    python -m pytest tests/test_audit_interaction_theme.py -v
"""

import pytest


# ============================================================
# 1. adapt_qss_colors 的链式二次替换
# ============================================================
class TestAdaptQssColorsChaining:
    """
    静态定位：
        infrastructure/theme_loader.py:650-701 的 replacements 列表
        是"顺序执行"的一串 str.replace()。前面的替换会产生新的
        hex 字符串，而这些新字符串又命中列表中后面的条目：

            #d4d4d4 --(行 656)--> c.foreground --(行 678)--> c.panel_bg
            #cccccc --(行 657)--> c.tab_fg     --(行 659)--> c.line_number_fg

        对 light_clean（晨曦）主题：foreground="#333333"、
        panel_bg="#f5f5f5"，于是文字色变成了面板背景色。
    """

    @pytest.mark.audit_expected_fail
    def test_light_theme_foreground_not_clobbered_by_panel_bg(self, qapp):
        from infrastructure.theme_loader import BuiltinThemes, adapt_qss_colors

        theme = BuiltinThemes.light_clean()
        out = adapt_qss_colors("color: #d4d4d4;", theme)

        assert theme.colors.foreground in out, (
            "INV-T1 违反：原文字色 #d4d4d4 未被换成主题前景色。"
            f" 期望包含 {theme.colors.foreground}，实际输出 {out!r}"
        )
        assert theme.colors.panel_bg not in out, (
            "INV-T1 违反：#d4d4d4 先被换成 foreground("
            f"{theme.colors.foreground})，随后又被后面的条目 "
            f"('#333333', c.panel_bg) 换成了面板背景色 "
            f"{theme.colors.panel_bg}，文字与背景同色 -> 不可见。"
            f" 实际输出 {out!r}"
        )

    @pytest.mark.audit_expected_fail
    def test_light_theme_tab_fg_not_clobbered_by_line_number_fg(self, qapp):
        from infrastructure.theme_loader import BuiltinThemes, adapt_qss_colors

        theme = BuiltinThemes.light_clean()
        out = adapt_qss_colors("color: #cccccc;", theme)

        assert out == f"color: {theme.colors.tab_fg};", (
            "INV-T1 违反：#cccccc 应映射到 tab_fg("
            f"{theme.colors.tab_fg})，但被后面的 "
            "('#666666', c.line_number_fg) 二次替换成了 "
            f"{theme.colors.line_number_fg}。实际输出 {out!r}"
        )

    @pytest.mark.audit_expected_fail
    def test_foreground_mapping_is_final_for_all_builtin_themes(self, qapp):
        """对 4 套内置主题逐一验证 #d4d4d4 的最终归宿。

        只有 light_clean 会因为链式替换把前景色换成背景色；
        其余 3 套主题因 `old == new` 被 `if old != new` 保护而正确。
        这条测试失败即说明"晨曦主题下文字与背景同色"。
        """
        from infrastructure.theme_loader import BuiltinThemes, adapt_qss_colors

        wrong = []
        for theme in BuiltinThemes.all_themes():
            out = adapt_qss_colors("color: #d4d4d4;", theme)
            expected = f"color: {theme.colors.foreground};"
            if out != expected:
                wrong.append((theme.name, out, expected,
                              theme.colors.panel_bg))

        assert not wrong, (
            "以下主题的 #d4d4d4 未落到 foreground："
            + "; ".join(
                f"{n}: 实际={o!r} 期望={e!r} (panel_bg={pb})"
                for n, o, e, pb in wrong
            )
        )


# ============================================================
# 2. 主题应用覆盖编辑器偏好
# ============================================================
class TestThemeApplyVsPreferences:

    @pytest.mark.audit_expected_fail
    def test_apply_theme_does_not_force_caret_line_visible(self, qapp):
        """ThemeLoader.apply 里 `editor.setCaretLineVisible(True)`
        （infrastructure/theme_loader.py:927）无视
        prefs['show_current_line']（ui/editor_view.py:269-271）。
        """
        from PyQt5.Qsci import QsciScintilla

        from infrastructure.theme_loader import BuiltinThemes, ThemeLoader

        sc = QsciScintilla()
        sc.setCaretLineVisible(False)     # 用户在首选项里关闭了"高亮当前行"

        loader = ThemeLoader()
        loader.apply(sc, BuiltinThemes.light_clean())

        assert not sc.caretLineVisible(), (
            "INV-T2 违反：切换主题把'高亮当前行'强制打开了，"
            "用户的 show_current_line=False 被静默覆盖。"
        )

    @pytest.mark.audit_expected_fail
    def test_theme_switch_keeps_editor_editable(self, qapp, tmp_path):
        """主题切换后再编辑仍应正常（编辑/撤销链路不被打断）。"""
        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy
        from infrastructure.theme_loader import BuiltinThemes, ThemeLoader

        p = tmp_path / "t.py"
        p.write_text("a = 1\n", encoding="utf-8")

        sc = QsciScintilla()
        sc.setUtf8(True)
        proxy = EditorProxy(sc, Document())
        assert proxy.open_file(str(p)) is True

        loader = ThemeLoader()
        for theme in BuiltinThemes.all_themes():
            loader.apply(sc, theme)
            assert sc.text() == "a = 1\n", (
                f"应用主题 {theme.name} 后编辑器内容被改变"
            )

        sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"# x\n")
        assert sc.text().startswith("# x\n")
        assert len(proxy.undo_manager.undo_stack) >= 1, (
            "切换 4 套主题后编辑不再被撤销栈记录"
        )


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-v"]))
