# -*- coding: utf-8 -*-
"""插件兼容性门控（NPP npp-compatible-version 等价）测试"""
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def test_compatible_ranges():
    from infrastructure.plugin_updater import is_app_version_compatible

    assert is_app_version_compatible("", "", "2.2.0") == (True, "")
    assert is_app_version_compatible("2.0.0", "", "2.2.0")[0] is True
    assert is_app_version_compatible("2.3.0", "", "2.2.0")[0] is False
    ok, reason = is_app_version_compatible("2.3.0", "", "2.2.0")
    assert "需要应用" in reason
    assert is_app_version_compatible("", "2.2.0", "2.2.0")[0] is True
    assert is_app_version_compatible("", "2.1.0", "2.2.0")[0] is False
    assert is_app_version_compatible("2.0.0", "2.9.9", "2.2.0")[0] is True


def test_invalid_payload_rejected():
    from infrastructure.plugin_updater import is_app_version_compatible

    ok, reason = is_app_version_compatible("not-a-version", "", "2.2.0")
    assert ok is False and "不可解析" in reason
    ok, reason = is_app_version_compatible("2.0.0", "", "bad-current")
    assert ok is False


def test_updater_check_compatibility_wraps_info():
    from PyQt5.QtWidgets import QApplication

    from infrastructure.plugin_updater import PluginUpdater, UpdateInfo

    app = QApplication.instance() or QApplication([])
    updater = PluginUpdater()
    info = UpdateInfo(name="x", min_app_version="99.0.0")
    ok, reason = updater.check_compatibility(info)
    assert ok is False and "需要应用" in reason
    info2 = UpdateInfo(name="x")
    assert updater.check_compatibility(info2)[0] is True
    app.processEvents()
