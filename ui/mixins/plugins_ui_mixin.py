# -*- coding: utf-8 -*-
"""插件加载 UI（从 MainWindow 抽取，v2.18）"""

import hashlib
import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QDateTime, QSettings, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QFont, QIcon, QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QShortcut,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTextBrowser,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.mixins.capability_wiring_mixin import CapabilityWiringMixin
from ui.mixins.edit_ops_mixin import EditOpsMixin
from ui.mixins.file_ops_mixin import FileOpsMixin
from ui.mixins.project_mixin import ProjectMixin
from ui.mixins.status_bar_mixin import StatusBarMixin


logger = logging.getLogger("QingCao")


class PluginsUIMixin:
    """插件加载 UI（从 MainWindow 抽取，v2.18）"""

    def _show_plugin_store(self):
        """显示插件市场"""
        try:
            from ui.plugin_store import PluginStoreDialog

            dlg = PluginStoreDialog(self)
            dlg.exec_()
        except Exception as e:
            self._show_error("插件市场失败", str(e))

    def _load_plugins(self):
        """
        加载插件。

        修复说明:
            - 使用 api_factory 函数为每个插件创建独立的 PluginAPI 实例。
              之前直接把 PluginAPI 实例传给 load_all 会导致
              "PluginAPI object is not callable"。
            - P2-1: self.api 由 _create_main_api 创建（全权限），
              不再取第一个插件的 API，避免权限受限。
        """
        # 关闭守卫（测试/快速退出实测发现）：
        # `__init__` 里 QTimer.singleShot(100, self._load_plugins) 是延迟加载；
        # 窗口若在这 100ms 内被关闭，定时器仍会触发 —— 此时会去弹权限
        # 确认框、创建插件面板，进而在后续测试的事件循环里造成模态阻塞，
        # 甚至访问已销毁控件（实测全量测试偶发挂起/段错误）。
        if getattr(self, "_closing", False):
            print("[MainWindow] 窗口已关闭，跳过延迟插件加载")
            return

        # P2-1: 先创建独立的全权限主 API
        try:
            self.api = self._create_main_api()
            if self.api is not None:
                print("[MainWindow] 已创建主 API（全权限）")
        except Exception as e:
            print(f"[MainWindow] 创建主 API 异常: {e}")
            self.api = None

        try:
            from app.plugins import PluginAPI
            from infrastructure.plugin_loader import (
                PluginLoader,
                resolve_plugin_dir,
            )

            # 插件目录必须用**绝对路径**：相对路径取决于当前工作目录，
            # 从快捷方式/其他目录启动时会解析到错误位置 → 插件发现数为 0
            # → 菜单全部消失（实测：cwd=exe 目录 total=10，cwd=C:\ total=0）
            _plugin_dir = resolve_plugin_dir("plugins")

            # P0-3 修复：先创建 PluginManager（高层 API，包装
            # PluginLoader）。原实现在这里创建，但随后直接调用
            # 裸 loader.load_all()，导致 PluginManager 的
            # 权限确认逻辑永远不会执行。
            if self.plugin_manager is None:
                try:
                    from app.plugin_manager import PluginManager

                    self.plugin_manager = PluginManager(
                        main_window=self,
                        plugin_dir=_plugin_dir,
                    )
                except Exception as e:
                    print(f"[MainWindow] PluginManager 创建失败: {e}")
                    self.plugin_manager = None

            # P0-3 修复：优先通过 PluginManager.load_all() 加载，
            # 因为它会在激活前逐个弹出**权限确认对话框**，并遵守
            # 用户在插件管理里设置的禁用列表。
            #
            # 原实现直接调用裸 loader.load_all(auto_activate=True)，
            # 而 PluginManager.load_all / _check_and_confirm_permissions
            # 全仓无调用者 —— 结果是危险权限确认框在启动路径上
            # 永远不会弹出，plugin.json 的 permissions 形同虚设。
            result = None
            if self.plugin_manager is not None:
                try:
                    # defer_heavy=True：manifest 声明 defer_activation 的
                    # 重量级插件（如 ai_assistant 导入要 0.53s）延后到窗口
                    # 显示后再加载，避免"窗口刚出现就卡 0.6 秒"。
                    result = self.plugin_manager.load_all(auto_activate=True, defer_heavy=True)
                    loader = self.plugin_manager.loader
                except Exception as e:
                    print(f"[MainWindow] PluginManager 加载失败: {e}")
                    result = None
                    loader = None
            else:
                loader = None

            # 回退路径：PluginManager 不可用时仍用裸 loader，
            # 但必须显式打印警告（无权限确认）
            if result is None:
                print("[MainWindow] 警告：PluginManager 不可用，回退到无权限确认的加载路径")
                loader = PluginLoader(plugin_dir=_plugin_dir)

                # 关键：api_factory 是函数，接收 spec，返回 PluginAPI 实例
                def api_factory(spec):
                    try:
                        permissions = list(getattr(spec.meta, "permissions", []) or [])
                        # 每个插件得到自己权限范围内的 API
                        api = PluginAPI(
                            self,
                            permissions=permissions,
                            plugin_name=spec.name,
                        )
                        # P0-3: 插件不得自行提权，宿主需要显式放行
                        api.grant_permissions_by_host(permissions)
                        return api
                    except Exception as e:
                        print(f"[MainWindow] 创建 API 失败 ({spec.name}): {e}")
                        return None

                result = loader.load_all(
                    plugin_dir=_plugin_dir,
                    api_factory=api_factory,
                    auto_activate=True,
                )

            self.plugin_loader = loader

            # B1.5：flag 指定的插件由子进程承载，接线到窗口菜单/状态栏
            try:
                self._start_isolated_plugins()
            except Exception as e:
                print(f"[MainWindow] 隔离插件启动失败: {e}")

            # B7 修复：将 loader 的 specs 桥接给 PluginManager
            # 原实现只对独立 loader 调用 load_all()，PluginManager
            # 从未 load_all，其 specs 为空。后续 plugins_panel 绑定
            # 的是空 manager，插件管理面板永远空白。
            if self.plugin_manager is not None and loader is not None:
                try:
                    self.plugin_manager.loader = loader
                    self.plugin_manager.specs = dict(loader.specs)
                except Exception as e:
                    print(f"[MainWindow] 桥接 loader 到 manager 失败: {e}")

            # 收集已激活的插件实例
            activated_specs = []
            try:
                if loader is not None and hasattr(loader, "get_activated_plugins"):
                    activated_specs = loader.get_activated_plugins()
                elif loader is not None:
                    activated_specs = [
                        s for s in loader.specs.values() if getattr(s, "is_active", False)
                    ]
            except Exception:
                pass

            self.plugins = [
                getattr(s, "instance", None)
                for s in activated_specs
                if getattr(s, "instance", None) is not None
            ]

            # 将 plugin_manager 绑定到 plugins_panel
            if self.plugins_panel and self.plugin_manager:
                try:
                    self.plugins_panel.plugin_manager = self.plugin_manager
                    self.plugins_panel._connect_manager_signals()
                    self.plugins_panel.refresh()
                except Exception as e:
                    print(f"[MainWindow] 绑定 plugin_manager 失败: {e}")

            # 输出结果
            if result:
                print(f"[MainWindow] 已加载 {result.activated} 个插件 (共 {result.total} 个)")
            else:
                print("[MainWindow] 已加载 0 个插件")

            # P1-7：插件加载完成后，重建「特色功能」里的插件命令子菜单
            #
            # `_setup_feature_menu()` 在窗口构造时执行，那时 `act_mgr` 里
            # 还没有 `plugin.*` 条目（插件此刻才加载），因此必须在这里
            # 刷新一次 —— 否则用户看到的是"（该插件未注册命令）"的假象，
            # 等于 P1-7 没做。
            try:
                self.refresh_feature_menu()
            except Exception as e:
                print(f"[MainWindow] 刷新特色功能菜单失败: {e}")

            # 快捷键方案：应用用户上次选择的方案
            #
            # 为什么必须放在启动路径上：方案只写进 QSettings 而不在启动时
            # 重新应用的话，用户重启后快捷键会**悄悄回到默认** ——
            # 这个功能就等于没做（用户的抱怨会是"我设了但没用"）。
            #
            # 时序：必须在所有动作注册完之后（动作在 `_build_menus` 里注册，
            # 早于这里），否则 `set_shortcut()` 找不到目标动作而静默失败。
            try:
                from ui.keymap_editor import apply_saved_scheme

                if apply_saved_scheme(self.act_mgr):
                    from ui.keymap_editor import load_saved_scheme

                    print(f"[MainWindow] 已应用快捷键方案: {load_saved_scheme()}")
            except Exception as e:
                print(f"[MainWindow] 应用快捷键方案失败: {e}")

        except Exception as e:
            import traceback

            traceback.print_exc()
            print(f"[MainWindow] 加载插件失败: {e}")

    def load_plugins(self):
        """公开接口：重新加载插件"""
        self._load_plugins()

    def reload_plugins(self):
        """重新加载插件"""
        try:
            for plugin in self.plugins:
                try:
                    if hasattr(plugin, "deactivate"):
                        plugin.deactivate()
                except Exception:
                    pass

            self.plugins = []
            self._load_plugins()
            self.status_bar.showMessage("插件已重新加载", 2000)
        except Exception as e:
            print(f"[MainWindow] 重载插件失败: {e}")

    def _start_isolated_plugins(self):
        """按 QINGCAO_PLUGIN_ISOLATION 启动隔离插件（B1.5）。"""
        from app.plugin_isolation import isolated_plugin_names

        names = isolated_plugin_names()
        if not names:
            return None
        from ui.isolated_plugins import IsolatedPluginHost

        host = IsolatedPluginHost(self).start(names)
        self._isolated_host = host
        return host
