# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为插件管理器模块，包含：
- PluginManager：插件管理器（高层 API，封装 PluginLoader）
- PluginConfig：插件配置持久化
- PermissionConfirmer：危险权限确认对话框
- DependencyResolver：插件依赖解析与拓扑排序
- PluginInfo：插件展示信息数据类
- PluginState：插件状态枚举
- 权限系统（检查、确认、记录）
- 启用/禁用管理（持久化）
- 插件热重载与崩溃恢复
- 插件分类与搜索
- 插件配置读写
- 生命周期回调
- 事件总线集成
- 批量操作（全部启用/禁用）
- 统计信息与调试输出

职责:
- 集成 infrastructure.plugin_loader.PluginLoader
- 提供 UI 友好的高层接口
- 处理权限确认
- 处理依赖检查
- 处理配置持久化
"""

import datetime
import json
import os
import shutil
import time
import traceback
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import QObject, QSettings, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)


# ============================================================
# 常量定义
# ============================================================
PLUGIN_CONFIG_FILE = "plugin_config.json"
PLUGIN_DIR = "plugins"
PLUGIN_MANIFEST = "plugin.json"

# 危险权限（加载时需要用户确认）
DANGEROUS_PERMISSIONS = {
    "network",       # 访问网络
    "process",       # 执行系统命令
    "terminal",      # 使用终端
    "debugger",      # 调试器
}

# 权限的中文描述（用于 UI 展示）
PERMISSION_NAMES = {
    "filesystem": "读写本地文件",
    "network": "访问网络",
    "process": "执行系统命令",
    "clipboard": "读写剪贴板",
    "dialog": "显示对话框",
    "editor_write": "修改编辑器内容",
    "editor_read": "读取编辑器内容",
    "terminal": "使用终端",
    "lsp": "注册 LSP 服务",
    "debugger": "调试功能",
    "settings": "读写配置",
    "themes": "读写主题",
    "plugins": "管理其他插件",
}

# 加载超时（秒）
LOAD_TIMEOUT = 30

# 崩溃重启上限
MAX_RESTART_COUNT = 3


# ============================================================
# 插件状态枚举
# ============================================================
class PluginState(Enum):
    """插件状态"""
    DISCOVERED = "discovered"       # 已发现
    LOADING = "loading"             # 加载中
    LOADED = "loaded"               # 已加载
    ACTIVATED = "activated"         # 已激活
    ERROR = "error"                 # 错误
    DISABLED = "disabled"           # 已禁用
    UNLOADED = "unloaded"           # 已卸载


# ============================================================
# 插件展示信息（用于 UI 列表）
# ============================================================
@dataclass
class PluginInfo:
    """插件展示信息（供 UI 使用）"""

    # 基本
    name: str = ""
    display_name: str = ""
    version: str = "0.0.0"
    description: str = ""
    author: str = ""
    author_email: str = ""

    # 分类
    category: str = "other"
    tags: List[str] = field(default_factory=list)
    type: str = "plugin"

    # 状态
    state: str = "discovered"
    is_active: bool = False
    is_enabled: bool = False

    # 权限
    permissions: List[str] = field(default_factory=list)

    # 依赖
    dependencies: List[str] = field(default_factory=list)
    plugin_dependencies: List[str] = field(default_factory=list)

    # 路径
    directory: str = ""

    # 时间
    loaded_at: float = 0.0
    activated_at: float = 0.0

    # 错误
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================
# 插件配置持久化
# ============================================================
class PluginConfig:
    """插件配置（持久化到 QSettings）"""

    def __init__(self, org: str = "QingCao"):
        self.settings = QSettings(org, "Plugins")

        # 禁用列表
        self.disabled_plugins: Set[str] = set()

        # 显式启用列表（记录用户明确启用的）
        self.explicitly_enabled: Set[str] = set()

        # 已确认权限的插件
        self.permission_confirmed: Set[str] = set()

        # 插件级配置
        self.plugin_settings: Dict[str, Dict[str, Any]] = {}

        # 加载
        self._load()

    # --------------------------------------------------------
    def _load(self):
        """加载配置"""
        try:
            disabled = self.settings.value("disabled", [], type=list)
            if isinstance(disabled, str):
                disabled = [disabled] if disabled else []
            self.disabled_plugins = set(disabled)
        except Exception:
            self.disabled_plugins = set()

        try:
            enabled = self.settings.value("enabled", [], type=list)
            if isinstance(enabled, str):
                enabled = [enabled] if enabled else []
            self.explicitly_enabled = set(enabled)
        except Exception:
            self.explicitly_enabled = set()

        try:
            confirmed = self.settings.value(
                "permission_confirmed", [], type=list
            )
            if isinstance(confirmed, str):
                confirmed = [confirmed] if confirmed else []
            self.permission_confirmed = set(confirmed)
        except Exception:
            self.permission_confirmed = set()

        try:
            raw = self.settings.value("plugin_settings", "{}", type=str)
            self.plugin_settings = json.loads(raw) if raw else {}
        except Exception:
            self.plugin_settings = {}

    def save(self):
        """保存配置"""
        try:
            self.settings.setValue(
                "disabled", list(self.disabled_plugins)
            )
            self.settings.setValue(
                "enabled", list(self.explicitly_enabled)
            )
            self.settings.setValue(
                "permission_confirmed",
                list(self.permission_confirmed)
            )
            self.settings.setValue(
                "plugin_settings",
                json.dumps(self.plugin_settings, ensure_ascii=False)
            )
            self.settings.sync()
        except Exception as e:
            print(f"[PluginConfig] 保存失败: {e}")

    # --------------------------------------------------------
    def is_disabled(self, name: str) -> bool:
        return name in self.disabled_plugins

    def set_disabled(self, name: str, disabled: bool):
        if disabled:
            self.disabled_plugins.add(name)
            self.explicitly_enabled.discard(name)
        else:
            self.disabled_plugins.discard(name)
            self.explicitly_enabled.add(name)
        self.save()

    def is_permission_confirmed(self, name: str) -> bool:
        return name in self.permission_confirmed

    def set_permission_confirmed(self, name: str, confirmed: bool):
        if confirmed:
            self.permission_confirmed.add(name)
        else:
            self.permission_confirmed.discard(name)
        self.save()

    def get_plugin_setting(self, plugin_name: str,
                            key: str, default=None):
        return self.plugin_settings.get(plugin_name, {}).get(key, default)

    def set_plugin_setting(self, plugin_name: str, key: str, value):
        if plugin_name not in self.plugin_settings:
            self.plugin_settings[plugin_name] = {}
        self.plugin_settings[plugin_name][key] = value
        self.save()

    def clear(self):
        """清空所有配置"""
        self.disabled_plugins.clear()
        self.explicitly_enabled.clear()
        self.permission_confirmed.clear()
        self.plugin_settings.clear()
        self.save()


# ============================================================
# 权限确认对话框
# ============================================================
class PermissionConfirmDialog(QDialog):
    """危险权限确认对话框"""

    def __init__(self, plugin_name: str, display_name: str,
                 permissions: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("插件权限请求")
        self.resize(500, 400)

        self.plugin_name = plugin_name
        self.approved = False
        self.remember = True

        self._build_ui(display_name, permissions)
        self._apply_style()

    def _build_ui(self, display_name, permissions):
        layout = QVBoxLayout(self)

        # 标题
        title = QLabel(
            f"<h3>插件 <b>{display_name}</b> 请求以下权限:</h3>"
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        # 权限列表
        browser = QTextBrowser()
        html = "<ul>"
        for perm in permissions:
            name = PERMISSION_NAMES.get(perm, perm)
            is_dangerous = perm in DANGEROUS_PERMISSIONS
            color = "#f14c4c" if is_dangerous else "#7ec850"
            marker = "⚠ " if is_dangerous else "• "
            html += (
                f'<li style="color:{color}; padding:4px;">'
                f'{marker}<b>{name}</b> '
                f'<span style="color:#888;">({perm})</span>'
                f'</li>'
            )
        html += "</ul>"
        browser.setHtml(html)
        layout.addWidget(browser)

        # 提示
        if any(p in DANGEROUS_PERMISSIONS for p in permissions):
            warn = QLabel(
                "<p style='color:#f0ad4e;'>"
                "⚠ 该插件请求了危险权限，请确认来源可信。"
                "</p>"
            )
            warn.setWordWrap(True)
            layout.addWidget(warn)

        # 记住选择
        self.remember_cb = QCheckBox("记住我的选择")
        self.remember_cb.setChecked(True)
        layout.addWidget(self.remember_cb)

        # 按钮
        buttons = QDialogButtonBox()
        allow_btn = buttons.addButton(
            "允许", QDialogButtonBox.AcceptRole
        )
        deny_btn = buttons.addButton(
            "拒绝", QDialogButtonBox.RejectRole
        )
        allow_btn.setStyleSheet(
            "background-color: #7ec850; color: white; "
            "padding: 6px 16px; border-radius: 3px;"
        )
        deny_btn.setStyleSheet(
            "background-color: #5a5a5a; color: white; "
            "padding: 6px 16px; border-radius: 3px;"
        )

        buttons.accepted.connect(self._on_allow)
        buttons.rejected.connect(self._on_deny)
        layout.addWidget(buttons)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; }
            QTextBrowser {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 8px;
            }
            QCheckBox { color: #d4d4d4; padding: 8px 0; }
            QPushButton {
                min-width: 80px;
                border: none;
                border-radius: 3px;
            }
        """)

    def _on_allow(self):
        self.approved = True
        self.remember = self.remember_cb.isChecked()
        self.accept()

    def _on_deny(self):
        self.approved = False
        self.remember = self.remember_cb.isChecked()
        self.reject()


# ============================================================
# 依赖解析器
# ============================================================
class DependencyResolver:
    """插件依赖解析与拓扑排序"""

    @staticmethod
    def resolve(specs: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """
        拓扑排序。

        参数:
            specs: {name: spec} 字典

        返回:
            (排序后的名字列表, 循环依赖的名字列表)
        """
        visited: Set[str] = set()
        visiting: Set[str] = set()
        result: List[str] = []
        cycles: List[str] = []

        def visit(name: str):
            if name in visited:
                return
            if name in visiting:
                cycles.append(name)
                return

            visiting.add(name)
            spec = specs.get(name)
            if spec:
                deps = getattr(spec.meta, 'plugin_dependencies', []) or []
                for dep in deps:
                    if dep in specs:
                        visit(dep)

            visiting.discard(name)
            visited.add(name)
            result.append(name)

        for name in specs.keys():
            visit(name)

        return result, cycles

    @staticmethod
    def check_missing(spec, specs: Dict[str, Any]) -> List[str]:
        """
        检查缺失的依赖。

        返回:
            缺失的依赖列表
        """
        missing = []
        deps = getattr(spec.meta, 'plugin_dependencies', []) or []
        for dep in deps:
            if dep not in specs:
                missing.append(dep)
        return missing


# ============================================================
# 插件管理器
# ============================================================
class PluginManager(QObject):
    """
    插件管理器（高层 API）。

    职责:
    - 集成 PluginLoader，提供 UI 友好接口
    - 权限确认
    - 依赖检查
    - 启用/禁用持久化
    - 热重载
    - 事件总线集成
    - 批量操作

    信号:
        plugin_loaded(str): 插件加载成功
        plugin_activated(str): 插件激活成功
        plugin_enabled(str): 插件启用
        plugin_disabled(str): 插件禁用
        plugin_unloaded(str): 插件卸载
        plugin_error(str, str): 插件错误
        plugins_changed(): 插件列表变化
        load_progress(int, int): 加载进度（当前, 总数）
    """

    # --------------------------------------------------------
    # 信号
    # --------------------------------------------------------
    plugin_loaded = pyqtSignal(str)
    plugin_activated = pyqtSignal(str)
    plugin_enabled = pyqtSignal(str)
    plugin_disabled = pyqtSignal(str)
    plugin_unloaded = pyqtSignal(str)
    plugin_error = pyqtSignal(str, str)
    plugins_changed = pyqtSignal()
    load_progress = pyqtSignal(int, int)

    # --------------------------------------------------------
    def __init__(self, main_window=None,
                 plugin_dir: str = PLUGIN_DIR,
                 auto_confirm_dangerous: bool = False,
                 parent: Optional[QObject] = None):
        """
        参数:
            main_window: 主窗口（用于弹对话框）
            plugin_dir: 插件目录
            auto_confirm_dangerous: 是否自动确认危险权限（跳过对话框）
            parent: 父 QObject
        """
        super().__init__(parent)

        self.main_window = main_window
        self.plugin_dir = plugin_dir
        self.auto_confirm_dangerous = auto_confirm_dangerous

        # 配置
        self.config = PluginConfig()

        # 插件规格字典 {name: PluginSpec}
        self.specs: Dict[str, Any] = {}

        # 加载的 loader
        self.loader: Optional[Any] = None

        # 加载结果
        self.last_load_result: Optional[Any] = None

        # 已确认权限的缓存（本次会话）
        self._session_confirmed: Set[str] = set()

        # 初始化 loader
        self._init_loader()

        # 连接事件总线
        self._connect_event_bus()

    # --------------------------------------------------------
    # 初始化
    # --------------------------------------------------------
    def _init_loader(self):
        """初始化 PluginLoader"""
        try:
            from infrastructure.plugin_loader import PluginLoader

            # P1-2: 读取热重载偏好（默认开启）
            hot_reload = True
            try:
                prefs = getattr(self.main_window, 'prefs', None)
                if prefs is not None:
                    hot_reload = bool(prefs.get(
                        "plugin_hot_reload", True
                    ))
            except Exception:
                pass

            self.loader = PluginLoader(
                plugin_dir=self.plugin_dir,
                enable_watcher=True,
                hot_reload_enabled=hot_reload,
            )

            # 连接 loader 信号
            self.loader.plugin_loaded.connect(self._on_loaded)
            self.loader.plugin_activated.connect(self._on_activated)
            self.loader.plugin_error.connect(self._on_error)
            self.loader.plugin_unloaded.connect(self._on_unloaded)

        except ImportError as e:
            print(f"[PluginManager] PluginLoader 未找到: {e}")
            self.loader = None
        except Exception as e:
            print(f"[PluginManager] 初始化失败: {e}")
            traceback.print_exc()
            self.loader = None

    def _connect_event_bus(self):
        """连接到全局事件总线"""
        try:
            from app.event_bus import PluginErrorEvent, PluginLoadedEvent, PluginUnloadedEvent, bus
            # 将 plugin_manager 的信号转发到事件总线
            self.plugin_loaded.connect(
                lambda name: bus.emit_event(PluginLoadedEvent(
                    plugin_name=name
                ))
            )
            self.plugin_unloaded.connect(
                lambda name: bus.emit_event(PluginUnloadedEvent(
                    plugin_name=name
                ))
            )
        except Exception:
            pass

    # ========================================================
    # 加载与卸载
    # ========================================================
    def load_all(self, auto_activate: bool = True) -> Optional[Any]:
        """
        加载所有插件。

        参数:
            auto_activate: 是否自动激活

        返回:
            LoadResult 对象
        """
        if not self.loader:
            print("[PluginManager] loader 未就绪")
            return None

        try:
            # API 工厂
            def api_factory(spec):
                return self._create_api(spec)

            result = self.loader.load_all(
                plugin_dir=self.plugin_dir,
                api_factory=api_factory,
                auto_activate=False,  # 我们自己控制激活
            )

            self.last_load_result = result
            self.specs = dict(self.loader.specs)

            # 逐个激活（带权限确认）
            if auto_activate:
                self._activate_all_with_permission()

            # 应用禁用配置
            self._apply_disabled_config()

            # P1-2: 启动目录监控（热重载）
            try:
                if getattr(self.loader, 'enable_watcher', False):
                    self.loader.start_watching()
            except Exception as e:
                print(f"[PluginManager] 启动热重载监控失败: {e}")

            self.plugins_changed.emit()
            return result

        except Exception as e:
            print(f"[PluginManager] 加载失败: {e}")
            traceback.print_exc()
            return None

    def _create_api(self, spec):
        """为插件创建 API"""
        try:
            from app.plugins import PluginAPI
            return PluginAPI(
                self.main_window,
                permissions=getattr(spec.meta, 'permissions', []),
                plugin_name=spec.name,
            )
        except ImportError:
            return None
        except Exception as e:
            print(f"[PluginManager] 创建 API 失败 ({spec.name}): {e}")
            return None

    def _activate_all_with_permission(self):
        """逐个激活（带权限确认）"""
        if not self.loader:
            return

        # 拓扑排序
        ordered_names, cycles = DependencyResolver.resolve(self.specs)

        if cycles:
            print(f"[PluginManager] 循环依赖: {cycles}")

        total = len(ordered_names)
        for i, name in enumerate(ordered_names):
            spec = self.specs.get(name)
            if not spec:
                continue

            self.load_progress.emit(i + 1, total)

            # 检查是否禁用
            if self.config.is_disabled(name):
                continue

            # 检查缺失依赖
            missing = DependencyResolver.check_missing(spec, self.specs)
            if missing:
                spec.state = type(spec.state).ERROR
                spec.error = f"缺少依赖: {', '.join(missing)}"
                self.plugin_error.emit(name, spec.error)
                continue

            # 检查权限
            permissions = getattr(spec.meta, 'permissions', []) or []
            if not self._check_and_confirm_permissions(
                spec.name, spec.meta.display_name or spec.name,
                permissions
            ):
                # 用户拒绝
                self.config.set_disabled(name, True)
                continue

            # 激活
            try:
                if hasattr(self.loader, '_activate_plugin'):
                    self.loader._activate_plugin(spec)
            except Exception as e:
                print(f"[PluginManager] 激活失败 ({name}): {e}")

    def _check_and_confirm_permissions(self, name: str,
                                        display_name: str,
                                        permissions: List[str]) -> bool:
        """
        检查并确认权限。

        返回:
            True 表示允许
        """
        if not permissions:
            return True

        # 会话内已确认
        if name in self._session_confirmed:
            return True

        # 持久化已确认
        if self.config.is_permission_confirmed(name):
            self._session_confirmed.add(name)
            return True

        # 无需确认（无危险权限）
        dangerous = [p for p in permissions
                     if p in DANGEROUS_PERMISSIONS]
        if not dangerous:
            self.config.set_permission_confirmed(name, True)
            self._session_confirmed.add(name)
            return True

        # 自动确认模式
        if self.auto_confirm_dangerous:
            self.config.set_permission_confirmed(name, True)
            self._session_confirmed.add(name)
            return True

        # 内置插件：自动授权（不弹模态框）
        #
        # 为什么必须这样做（真实缺陷）：
        #   内置插件与插件市场下载的第三方插件位于**同一目录**，
        #   而危险权限确认框是**模态阻塞**的 —— 它卡在启动时的插件
        #   加载循环里。用户漏点其中任何一个、或对话框被主窗口遮挡，
        #   对应插件就永久不激活，界面上也没有任何提示。
        #   症状正是"AI 助手 / Git / Python 调试 菜单根本没有"
        #   （这三个恰好分别声明 network / process / process 危险权限）。
        #
        # 安全性：内置插件随主程序一同安装，来源可信；且清单是
        #   代码内的冻结集合（core/builtin_plugins.py），第三方插件
        #   即使把目录放进 plugins/ 也不会命中，因此仍需用户确认。
        try:
            from core.builtin_plugins import is_built_in
            if is_built_in(name):
                self.config.set_permission_confirmed(name, True)
                self._session_confirmed.add(name)
                print("[PluginManager] 内置插件 %s 自动授权: %s"
                      % (name, sorted(dangerous)))
                return True
        except Exception as e:
            print("[PluginManager] 判断内置插件失败: %s" % e)

        # 弹对话框
        try:
            dlg = PermissionConfirmDialog(
                name, display_name, permissions,
                self.main_window
            )
            if dlg.exec_() == QDialog.Accepted and dlg.approved:
                if dlg.remember:
                    self.config.set_permission_confirmed(name, True)
                self._session_confirmed.add(name)
                return True
            return False
        except Exception as e:
            print(f"[PluginManager] 权限对话框失败: {e}")
            return False

    def _apply_disabled_config(self):
        """应用禁用配置"""
        for name in list(self.specs.keys()):
            if self.config.is_disabled(name):
                spec = self.specs.get(name)
                if spec and getattr(spec, 'is_active', False):
                    try:
                        if self.loader:
                            self.loader.unload_plugin(name)
                    except Exception:
                        pass

    def unload_plugin(self, name: str) -> bool:
        """卸载插件"""
        if not self.loader:
            return False
        try:
            success = self.loader.unload_plugin(name)
            if success:
                self.plugin_unloaded.emit(name)
            return success
        except Exception as e:
            print(f"[PluginManager] 卸载失败 ({name}): {e}")
            return False

    def reload_plugin(self, name: str) -> bool:
        """重载插件"""
        if not self.loader:
            return False
        try:
            # 先卸载
            self.loader.unload_plugin(name)

            # 重新发现
            spec = self.specs.get(name)
            if not spec:
                return False

            directory = spec.directory
            dir_name = os.path.basename(directory)

            if hasattr(self.loader, '_parse_plugin'):
                new_spec = self.loader._parse_plugin(directory, dir_name)
                if new_spec and hasattr(self.loader, '_load_plugin'):
                    if self.loader._load_plugin(new_spec):
                        if hasattr(self.loader, '_activate_plugin'):
                            self.loader._activate_plugin(new_spec)
                        self.specs[name] = new_spec
                        return True
            return False
        except Exception as e:
            print(f"[PluginManager] 重载失败 ({name}): {e}")
            return False

    def unload_all(self) -> int:
        """卸载所有插件"""
        if not self.loader:
            return 0
        count = 0
        for name in list(self.specs.keys()):
            if self.unload_plugin(name):
                count += 1
        return count

    # ========================================================
    # 启用/禁用
    # ========================================================
    def enable_plugin(self, name: str, ask: bool = False) -> bool:
        """启用插件"""
        spec = self.specs.get(name)
        if not spec:
            return False

        if ask:
            display_name = getattr(spec.meta, 'display_name', name)
            permissions = getattr(spec.meta, 'permissions', []) or []
            if not self._check_and_confirm_permissions(
                name, display_name, permissions
            ):
                return False

        # 更新配置
        self.config.set_disabled(name, False)

        # 已激活
        if getattr(spec, 'is_active', False):
            return True

        # 重新加载并激活
        if self.reload_plugin(name):
            self.plugin_enabled.emit(name)
            self.plugins_changed.emit()
            return True

        return False

    def disable_plugin(self, name: str, ask: bool = True) -> bool:
        """禁用插件"""
        if ask and self.main_window:
            reply = QMessageBox.question(
                self.main_window,
                "禁用插件",
                f"确定要禁用插件 '{name}' 吗？\n\n"
                f"部分功能可能立即失效。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return False

        # 更新配置
        self.config.set_disabled(name, True)

        # 卸载
        try:
            if self.loader:
                self.loader.unload_plugin(name)
        except Exception:
            pass

        self.plugin_disabled.emit(name)
        self.plugins_changed.emit()
        return True

    def toggle_plugin(self, name: str) -> bool:
        """切换插件启用状态"""
        if self.is_enabled(name):
            return self.disable_plugin(name, ask=False)
        else:
            return self.enable_plugin(name)

    def is_enabled(self, name: str) -> bool:
        """插件是否启用"""
        if self.config.is_disabled(name):
            return False
        spec = self.specs.get(name)
        if spec:
            return getattr(spec, 'is_active', False)
        return False

    def enable_all(self):
        """启用所有插件"""
        for name in self.specs.keys():
            self.config.set_disabled(name, False)
        self.plugins_changed.emit()

    def disable_all(self):
        """禁用所有插件"""
        for name in self.specs.keys():
            self.disable_plugin(name, ask=False)

    # ========================================================
    # 查询
    # ========================================================
    def get_plugin(self, name: str):
        """获取插件规格"""
        return self.specs.get(name)

    def has_plugin(self, name: str) -> bool:
        """插件是否存在"""
        return name in self.specs

    def count(self) -> int:
        """插件数量"""
        return len(self.specs)

    def names(self) -> List[str]:
        """所有插件名"""
        return list(self.specs.keys())

    def get_active_plugins(self) -> List[Any]:
        """获取所有已激活的插件"""
        return [
            spec for spec in self.specs.values()
            if getattr(spec, 'is_active', False)
        ]

    def list_plugins(self) -> List[PluginInfo]:
        """列出所有插件（简化信息）"""
        result = []
        for name, spec in self.specs.items():
            info = PluginInfo(
                name=name,
                display_name=getattr(spec.meta, 'display_name', name),
                version=getattr(spec, 'version', '0.0.0'),
                description=getattr(spec.meta, 'description', ''),
                author=getattr(spec.meta, 'author', ''),
                author_email=getattr(spec.meta, 'author_email', ''),
                category=getattr(spec.meta, 'category', 'other'),
                tags=list(getattr(spec.meta, 'tags', [])),
                type=getattr(spec.meta, 'type', 'plugin'),
                state=spec.state.name if hasattr(spec, 'state')
                else 'UNKNOWN',
                is_active=getattr(spec, 'is_active', False),
                is_enabled=self.is_enabled(name),
                permissions=list(
                    getattr(spec.meta, 'permissions', [])
                ),
                dependencies=list(
                    getattr(spec.meta, 'dependencies', [])
                ),
                plugin_dependencies=list(
                    getattr(spec.meta, 'plugin_dependencies', [])
                ),
                directory=getattr(spec, 'directory', ''),
                loaded_at=getattr(spec, 'load_time_ms', 0.0) / 1000.0
                if getattr(spec, 'load_time_ms', 0) else 0.0,
                activated_at=getattr(spec, 'activated_at', 0.0),
                error=getattr(spec, 'error', ''),
            )
            result.append(info)

        return sorted(result, key=lambda x: x.display_name.lower())

    def get_by_category(self) -> Dict[str, List[PluginInfo]]:
        """按分类分组"""
        result: Dict[str, List[PluginInfo]] = {}
        for info in self.list_plugins():
            result.setdefault(info.category, []).append(info)
        return result

    def search(self, keyword: str) -> List[PluginInfo]:
        """搜索插件"""
        if not keyword:
            return self.list_plugins()

        keyword = keyword.lower()
        result = []
        for info in self.list_plugins():
            text = (
                info.name + info.display_name +
                info.description + info.author +
                ' '.join(info.tags)
            ).lower()
            if keyword in text:
                result.append(info)
        return result

    def get_statistics(self) -> Dict[str, int]:
        """获取插件统计"""
        total = len(self.specs)
        active = 0
        error = 0
        disabled = 0
        for spec in self.specs.values():
            if getattr(spec, 'is_active', False):
                active += 1
            if hasattr(spec, 'state'):
                if spec.state.name == 'ERROR':
                    error += 1
            if self.config.is_disabled(spec.name):
                disabled += 1

        return {
            'total': total,
            'active': active,
            'error': error,
            'disabled': disabled,
        }

    def get_plugin_config(self, plugin_name: str, key: str,
                            default=None):
        """获取插件配置"""
        return self.config.get_plugin_setting(
            plugin_name, key, default
        )

    def set_plugin_config(self, plugin_name: str, key: str, value):
        """设置插件配置"""
        self.config.set_plugin_setting(plugin_name, key, value)

    # ========================================================
    # 信号处理
    # ========================================================
    def _on_loaded(self, name: str):
        print(f"[PluginManager] 已加载: {name}")
        self.plugin_loaded.emit(name)

    def _on_activated(self, name: str):
        print(f"[PluginManager] 已激活: {name}")
        self.plugin_activated.emit(name)
        self.plugins_changed.emit()

    def _on_error(self, name: str, error: str):
        print(f"[PluginManager] 错误 ({name}): {error}")
        self.plugin_error.emit(name, error)

    def _on_unloaded(self, name: str):
        print(f"[PluginManager] 已卸载: {name}")
        self.plugin_unloaded.emit(name)
        self.plugins_changed.emit()

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出管理器信息"""
        lines = ["PluginManager", "=" * 60]
        stats = self.get_statistics()
        lines.append(f"总数:   {stats['total']}")
        lines.append(f"激活:   {stats['active']}")
        lines.append(f"错误:   {stats['error']}")
        lines.append(f"禁用:   {stats['disabled']}")
        lines.append(f"目录:   {self.plugin_dir}")
        lines.append("")

        if self.specs:
            lines.append("插件列表:")
            for info in self.list_plugins():
                status_icon = {
                    'ACTIVATED': '✓',
                    'LOADED': '◐',
                    'ERROR': '✗',
                    'DISABLED': '⊘',
                    'UNLOADED': '−',
                }.get(info.state, '?')

                lines.append(
                    f"  {status_icon} {info.name:25s} "
                    f"v{info.version:10s} "
                    f"[{info.category}]"
                )
                if info.error:
                    lines.append(f"      错误: {info.error}")

        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self.specs)

    def __contains__(self, name: str) -> bool:
        return name in self.specs

    def __iter__(self):
        return iter(self.specs.values())

    def __repr__(self) -> str:
        stats = self.get_statistics()
        return (f"<PluginManager total={stats['total']} "
                f"active={stats['active']}>")