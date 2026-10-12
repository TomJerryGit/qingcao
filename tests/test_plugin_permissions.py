# -*- coding: utf-8 -*-
"""P0-3 回归测试：插件权限门控与确认接线

修复前：
    * PluginManager.load_all / _check_and_confirm_permissions
      全仓无调用者 —— 权限确认框永远不会弹出；
    * PluginAPI.grant_permission() 允许插件自我提权；
    * api.win 是公开属性，可直达全权限主 API；
    * get_plugin_data_dir()/save_plugin_config() 是免权限写盘后门。
"""
import pytest


class TestSelfEscalationBlocked:
    """插件不得自我提权"""

    def test_plugin_cannot_grant_itself_permission(self, qapp):
        from app.plugins import PERMISSION_PROCESS, PluginAPI

        api = PluginAPI(None, permissions=[], plugin_name="evil")
        assert api.grant_permission(PERMISSION_PROCESS) is False
        assert api.has_permission(PERMISSION_PROCESS) is False

    def test_host_can_grant(self, qapp):
        from app.plugins import PERMISSION_PROCESS, PluginAPI

        api = PluginAPI(None, permissions=[], plugin_name="good")
        granted = api.grant_permissions_by_host([PERMISSION_PROCESS])
        assert granted == 1
        assert api.has_permission(PERMISSION_PROCESS) is True


class TestHostWindowGated:
    """主窗口访问需要 dialog 权限"""

    def test_without_dialog_permission(self, qapp):
        from app.plugins import PluginAPI

        api = PluginAPI(None, permissions=[], plugin_name="p")
        assert api.get_main_window() is None

    def test_with_dialog_permission(self, qapp):
        from app.plugins import PERMISSION_DIALOG, PluginAPI

        sentinel = object()
        api = PluginAPI(sentinel, permissions=[PERMISSION_DIALOG],
                        plugin_name="p")
        assert api.get_main_window() is sentinel

    def test_win_attribute_is_deprecated_but_works(self, qapp):
        """兼容：api.win 仍可用，但会打印弃用告警"""
        from app.plugins import PluginAPI

        sentinel = object()
        api = PluginAPI(sentinel, permissions=[], plugin_name="p")
        assert api.win is sentinel


class TestFilesystemGateOnDataDir:
    """插件私有数据目录需要 filesystem 权限"""

    def test_data_dir_requires_filesystem(self, qapp):
        from app.plugins import PluginAPI

        api = PluginAPI(None, permissions=[], plugin_name="p")
        assert api.get_plugin_data_dir() == ""

    def test_save_config_requires_filesystem(self, qapp):
        from app.plugins import PluginAPI

        api = PluginAPI(None, permissions=[], plugin_name="p")
        assert api.save_plugin_config({"a": 1}) is False


class TestDocumentedPermissionsExist:
    """README 列出的权限都必须在代码里存在"""

    def test_lsp_and_debugger_defined(self):
        from app.plugins import (
            ALL_PERMISSIONS,
            PERMISSION_DEBUGGER,
            PERMISSION_LSP,
        )
        assert PERMISSION_LSP in ALL_PERMISSIONS
        assert PERMISSION_DEBUGGER in ALL_PERMISSIONS

    def test_allowed_permissions_superset(self):
        from app.plugins import ALL_PERMISSIONS
        from infrastructure.plugin_loader import ALLOWED_PERMISSIONS

        # plugin.json 里能声明的权限必须都能被 API 识别
        missing = set(ALLOWED_PERMISSIONS) - set(ALL_PERMISSIONS) - {
            "settings", "themes", "plugins",
        }
        assert missing == set(), "未在 PluginAPI 中定义的权限: %s" % missing


class TestPermissionConfirmationWired:
    """启动路径必须经过权限确认逻辑"""

    def test_load_all_invokes_permission_check(self, qapp, monkeypatch):
        from app.plugin_manager import PluginManager

        pm = PluginManager(main_window=None, plugin_dir="plugins",
                           auto_confirm_dangerous=True)
        checked = []
        original = pm._check_and_confirm_permissions

        def spy(name, display_name, permissions):
            checked.append(name)
            return original(name, display_name, permissions)

        monkeypatch.setattr(pm, '_check_and_confirm_permissions', spy)
        pm.load_all(auto_activate=True)

        assert checked, "PluginManager.load_all 没有调用权限确认"
        assert len(checked) >= 5
        pm.loader.stop_watching()

    def test_loader_watcher_enabled_by_manager(self, qapp):
        """P1-2: manager 创建的 loader 必须开监控"""
        from app.plugin_manager import PluginManager

        pm = PluginManager(main_window=None, plugin_dir="plugins",
                           auto_confirm_dangerous=True)
        assert pm.loader.enable_watcher is True
        assert pm.loader.hot_reload_enabled is True


class TestBuiltinPluginsDeclareDialog:
    """内置面板类插件必须声明它们用到的 dialog 权限"""

    @pytest.mark.parametrize("plugin", [
        "logtail", "markdown_preview", "todo_panel", "wordcount",
    ])
    def test_dialog_declared(self, plugin):
        import json
        import os

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        manifest = os.path.join(root, "plugins", plugin, "plugin.json")
        with open(manifest, encoding="utf-8") as f:
            data = json.load(f)
        assert "dialog" in data.get("permissions", []), (
            "%s 使用了主窗口却没有声明 dialog 权限" % plugin
        )

    def test_plugins_do_not_use_deprecated_win(self):
        """内置插件不应再直接读 api.win"""
        import glob
        import os

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        for path in glob.glob(os.path.join(root, "plugins", "*", "*.py")):
            with open(path, encoding="utf-8", errors="replace") as f:
                if "self.api.win" in f.read():
                    offenders.append(os.path.relpath(path, root))
        assert offenders == [], "仍在使用弃用 api.win: %s" % offenders
