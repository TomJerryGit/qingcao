# -*- coding: utf-8 -*-
"""P1-2 回归测试：国际化、热重载、音效接线、惰性面板

修复前：
    * locale/ 下只有 1 个 .po（正文是 GBK 却声明 UTF-8），
      且全仓没有任何 .mo —— 4 种语言从未生效；
    * 插件热重载只打印"可能需要重启编辑器"；
    * sound_manager.py（1600+ 行）全仓零调用；
    * _build_docks 启动时同步构造全部 9 个面板。
"""
import gettext
import io
import json
import os
import re

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALE = os.path.join(ROOT, 'locale')
LANGS = ('zh_CN', 'en_US', 'ja_JP', 'ko_KR')


# ============================================================
# 国际化
# ============================================================
class TestLocaleFiles:
    @pytest.mark.parametrize("lang", LANGS)
    def test_po_exists_and_is_utf8(self, lang):
        po = os.path.join(LOCALE, lang, 'LC_MESSAGES', 'qingcao.po')
        assert os.path.exists(po), "缺少 %s" % po
        raw = open(po, 'rb').read()
        text = raw.decode('utf-8')          # 不抛异常即通过
        assert 'charset=UTF-8' in text.replace(' ', '')

    @pytest.mark.parametrize("lang", LANGS)
    def test_mo_exists(self, lang):
        mo = os.path.join(LOCALE, lang, 'LC_MESSAGES', 'qingcao.mo')
        assert os.path.exists(mo), (
            "缺少 %s —— gettext 只会加载 .mo，缺它则国际化不生效" % mo
        )

    @pytest.mark.parametrize("lang,expect", [
        ('zh_CN', '保存'),
        ('en_US', 'Save'),
        ('ja_JP', '保存'),
        ('ko_KR', '저장'),
    ])
    def test_gettext_returns_translation(self, lang, expect):
        tr = gettext.translation('qingcao', LOCALE, languages=[lang])
        got = tr.gettext('Save')
        assert isinstance(got, str)
        assert got == expect

    def test_all_mo_share_same_catalog_size(self):
        """4 种语言的词条数应一致"""
        sizes = set()
        for lang in LANGS:
            text = io.open(
                os.path.join(LOCALE, lang, 'LC_MESSAGES', 'qingcao.po'),
                encoding='utf-8',
            ).read()
            sizes.add(len(re.findall(r'^msgid ', text, re.M)))
        assert len(sizes) == 1, "各语言词条数不一致: %s" % sizes


class TestI18nManager:
    def test_load_all_languages(self, qapp):
        from core.i18n import get_i18n

        mgr = get_i18n()
        mgr.locale_dir = LOCALE
        for lang in LANGS:
            assert mgr.load(lang) is True
            assert mgr.current_language == lang

    def test_language_list_is_4(self):
        from core.i18n import get_i18n

        codes = [c for c, _ in get_i18n().list_languages()]
        assert codes == list(LANGS)

    def test_wizard_korean_label_not_broken(self):
        """修复前 first_run_wizard 的韩语标签是 '???'"""
        src = io.open(
            os.path.join(ROOT, 'ui', 'first_run_wizard.py'),
            encoding='utf-8',
        ).read()
        assert '("한국어", "ko_KR")' in src
        assert '("???", "ko_KR")' not in src


# ============================================================
# 插件热重载
# ============================================================
class TestHotReload:
    def test_no_longer_only_prints(self):
        """原先只有一句 print，现在必须真的重载"""
        src = io.open(
            os.path.join(ROOT, 'infrastructure', 'plugin_loader.py'),
            encoding='utf-8',
        ).read()
        assert 'def _detect_changed_plugins' in src
        assert 'self.reload_plugin(name)' in src

    def test_loader_accepts_hot_reload_flag(self, qapp):
        from infrastructure.plugin_loader import PluginLoader

        loader = PluginLoader(plugin_dir='plugins',
                              enable_watcher=True,
                              hot_reload_enabled=False)
        assert loader.enable_watcher is True
        assert loader.hot_reload_enabled is False

    def test_per_plugin_opt_out(self, qapp):
        from infrastructure.plugin_loader import PluginLoader

        loader = PluginLoader(plugin_dir='plugins')

        class _Meta:
            raw = {'hot_reload': False}

        class _Spec:
            meta = _Meta()

        assert loader._is_hot_reload_allowed(_Spec()) is False

        class _Meta2:
            raw = {}

        class _Spec2:
            meta = _Meta2()

        assert loader._is_hot_reload_allowed(_Spec2()) is True

    def test_watch_paths_cover_plugin_sources(self, qapp):
        """必须递归监控插件源码，否则改 __init__.py 不会触发"""
        from app.plugin_manager import PluginManager

        pm = PluginManager(main_window=None, plugin_dir='plugins',
                           auto_confirm_dangerous=True)
        pm.load_all(auto_activate=True)
        try:
            assert len(pm.loader._watch_paths) > 10
            assert any(
                p.endswith('__init__.py') or p.endswith('plugin.json')
                for p in pm.loader._watch_paths
            )
        finally:
            pm.loader.stop_watching()

    def test_manifest_raw_is_kept(self, qapp):
        from infrastructure.plugin_loader import PluginLoader

        loader = PluginLoader(plugin_dir='plugins')
        specs = loader.discover()
        assert specs
        for spec in specs:
            assert isinstance(spec.meta.raw, dict)
            # raw 里应包含清单的原始字段
            assert 'name' in spec.meta.raw


# ============================================================
# 音效接线
# ============================================================
class TestSoundWiring:
    def test_preference_defaults_off(self, qapp):
        from app.preferences import Preferences

        assert Preferences().get('sound_effects') is False

    def test_off_by_default_blocks_play(self, qapp):
        from infrastructure.sound_manager import SoundEvent, play_sound

        assert play_sound(SoundEvent.FILE_SAVE, force=True) is False

    def test_on_allows_play(self, qapp, monkeypatch):
        from app.preferences import Preferences
        from infrastructure import sound_manager as sm

        prefs = Preferences()
        old = prefs.get('sound_effects')
        prefs.set('sound_effects', True)
        try:
            # QtMultimedia 在 CI/offscreen 下可能不可用，回退到
            # 系统提示音后仍应返回 True
            assert sm.play_sound(sm.SoundEvent.FILE_SAVE, force=True) is True
        finally:
            prefs.set('sound_effects', old)

    def test_sound_manager_is_singleton(self, qapp):
        from infrastructure.sound_manager import get_sound_manager

        assert get_sound_manager() is get_sound_manager()

    def test_main_window_calls_sound(self):
        """主窗口/文件操作里必须真的调用 play_sound"""
        for rel in ('ui/mixins/file_ops_mixin.py', 'ui/main_window.py'):
            src = io.open(os.path.join(ROOT, rel), encoding='utf-8').read()
            assert 'play_sound' in src, "%s 未接入音效" % rel


# ============================================================
# 惰性面板
# ============================================================
class TestLazyPanels:
    def test_only_default_panels_built_at_startup(self, qapp):
        """启动时只构造 _DEFAULT_PANELS，其余仍为延迟构造

        历史：曾要求"启动时构造 0 个面板"，但那会导致
          ① 界面开箱为空（用户观感"功能没了"）
          ② 会话保存采集到空 docks → 覆盖用户布局
        因此改为：构造一组常用默认面板，其余保持延迟。
        """
        import ui.main_window as mw

        win = mw.MainWindow()
        try:
            assert win._panels_built == set(win._DEFAULT_PANELS), (
                "启动时应恰好构造默认面板，实际: %s" % win._panels_built
            )
            # 未列入默认的仍不应被构造
            for name in ('outline', 'outline_enhanced',
                         'minimap', 'console', 'search_bar'):
                if name in win._DEFAULT_PANELS:
                    continue
                assert name not in win._panels_built, (
                    "%s 不应在启动时构造" % name
                )
        finally:
            win.close()

    def test_default_panels_visible(self, qapp):
        """默认面板不仅要构造，还要**可见**（否则界面依旧空白）"""
        from PyQt5.QtWidgets import QDockWidget

        import ui.main_window as mw

        win = mw.MainWindow()
        win.show()
        try:
            qapp.processEvents()
            names = {d.objectName() for d in win.findChildren(QDockWidget)
                     if d.isVisible()}
            assert "DirectoryTreeDock" in names, (
                "项目目录树应默认可见，实际可见: %s" % names
            )
            assert "GlobalSearchPanel" in names
            assert "PluginsPanel" in names
            assert "PerfMonitor" in names
        finally:
            win.close()

    def test_panel_built_on_demand(self, qapp):
        import ui.main_window as mw

        win = mw.MainWindow()
        try:
            assert win._ensure_panel('outline') is True
            assert win.outline is not None
            assert 'outline' in win._panels_built

            assert win._ensure_panel('perf_monitor') is True
            assert win.perf_monitor is not None
        finally:
            win.close()

    def test_all_panels_have_object_name(self, qapp):
        """每个面板都要有稳定 objectName —— 会话采集/恢复依赖它"""
        import ui.main_window as mw

        win = mw.MainWindow()
        try:
            expected = {
                'outline': 'OutlinePanel',
                'outline_enhanced': 'OutlineEnhancedDock',
                'dir_tree': 'DirectoryTreeDock',
                'minimap': 'MinimapDock',
                'gsearch': 'GlobalSearchPanel',
                'console': 'PythonConsole',
                'plugins_panel': 'PluginsPanel',
                'perf_monitor': 'PerfMonitor',
                'search_bar': 'SearchBar',
            }
            for name, oname in expected.items():
                assert win._ensure_panel(name) is True, name
                obj = getattr(win, name, None)
                if name in ('dir_tree', 'minimap'):
                    obj = getattr(win, f"{name}_dock", None)
                assert obj is not None, name
                assert obj.objectName() == oname, (
                    "%s 的 objectName 应为 %s，实际 %r"
                    % (name, oname, obj.objectName())
                )
        finally:
            win.close()

    def test_all_panels_can_be_built(self, qapp):
        import ui.main_window as mw

        win = mw.MainWindow()
        try:
            for name in win._LAZY_PANELS:
                assert win._ensure_panel(name) is True, (
                    "面板 %s 构造失败" % name
                )
        finally:
            win.close()

    def test_unknown_panel_rejected(self, qapp):
        import ui.main_window as mw

        win = mw.MainWindow()
        try:
            assert win._ensure_panel('not_a_panel') is False
        finally:
            win.close()
