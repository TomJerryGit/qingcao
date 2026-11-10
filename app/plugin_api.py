# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405,F811
"""插件 API（v2.24 拆分：公共/编辑器/UI/数据/事件）。"""

from app.plugin_api_common import *  # noqa: F401,F403,F405
from app.plugin_api_common import _BackgroundBridge  # noqa: F401
from app.plugin_api_data import DataMixin
from app.plugin_api_editor import EditorAccessMixin
from app.plugin_api_events import EventMixin
from app.plugin_api_ui import UiMixin


class PluginAPI(EditorAccessMixin, UiMixin, DataMixin, EventMixin, QObject):
    """
    暴露给插件的 API 接口。

    插件通过此对象与编辑器交互，所有操作均受权限校验。
    使用方式：

        class Plugin:
            def activate(self, api):
                self.api = api
                api.add_menu("工具/我的功能", self.run)
                api.subscribe('file_opened', self.on_file_opened)

            def deactivate(self):
                pass

    插件需在 plugin.json 中声明所需权限：
        {
            "name": "my_plugin",
            "permissions": ["filesystem", "network"]
        }
    """

    # 说明（P3-1）:
    #   原有两个信号 plugin_loaded / plugin_unloaded 从未在
    #   PluginAPI 内部 emit，属于死代码。PluginLoader /
    #   PluginManager 有各自的 plugin_loaded 信号负责通知，
    #   PluginAPI 层不需要重复。
    #
    #   如果第三方插件引用了 api.plugin_loaded，请在插件里
    #   改用 from app.event_bus import bus 或直接监听
    #   PluginLoader 的信号。

    def __init__(
        self, main_window, permissions: Optional[List[str]] = None, plugin_name: str = "unknown"
    ):
        """
        参数:
            main_window: 主窗口实例
            permissions: 权限列表
            plugin_name: 插件名称（用于日志和错误提示）
        """
        # 防御性处理：即使 main_window 为 None 也不崩溃
        super().__init__(main_window if isinstance(main_window, QObject) else None)

        # P0-3: 主窗口引用不放在实例字典里，改为受控属性，
        # 使 __getattr__ 能对直读给出弃用警告。
        # （api.win 旧写法仍可用，但会提示迁移到
        #   get_main_window()；内部代码请统一用 _host_window()。）
        self.__dict__["_win_compat"] = main_window
        self.permissions = set(permissions or [])
        self.plugin_name = plugin_name

        # P0-3: 只有宿主可以动态授权
        self._host_authorized: bool = False
        # P0-3: 兼容旧插件的 api.win 直读，但给出明确警告，
        # 引导改用 get_main_window()（受 dialog 权限门控）
        self._win_warned: bool = False

        # 插件注册的资源（用于卸载时清理）
        self._registered_actions: List[QAction] = []
        self._registered_menus: List[QMenu] = []
        self._registered_panels: List[QDockWidget] = []
        self._registered_shortcuts: List[QAction] = []
        self._event_connections: List[Tuple[Any, Callable]] = []
        self._registered_commands: Dict[str, Callable] = {}
        self._registered_lexers: Dict[str, Any] = {}
        self._registered_lsp: Dict[str, List[str]] = {}

        # v2.3 扩展点：编辑器智能（补全 / 诊断 / 后台任务）
        self._registered_completion_providers: List[Any] = []
        self._published_diagnostics: Dict[str, List[Any]] = {}
        self._background_bridges: List[Any] = []
        self._background_threads: List[Any] = []

        # v2.4 扩展点：hover / 代码操作 / 右键菜单 / 状态栏 / 装饰 / 设置
        self._registered_hover_providers: List[Any] = []
        self._registered_context_actions: List[Any] = []
        self._registered_code_action_providers: List[Any] = []
        self._registered_status_items: List[Any] = []
        self._registered_decorations: List[Any] = []
        self._registered_symbol_providers: List[Any] = []
        self._settings_schema: List[Any] = []
        self._settings_action = None

        # 插件私有数据目录
        try:
            self._data_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "data", "plugins", plugin_name
            )
        except Exception:
            # 基于应用根目录，避免相对路径随工作目录变化
            try:
                from infrastructure.plugin_loader import (
                    app_root_dir as _app_root,
                )

                _base = _app_root()
            except Exception:
                _base = "."
            self._data_dir = os.path.join(_base, "data", "plugins", plugin_name)

    # ========================================================
    # 权限校验
    # ========================================================

    @property
    def win(self):
        """兼容属性：主窗口（已弃用）

        P0-3: 本编辑器目前**没有进程级沙箱**，插件与编辑器同
        进程运行，权限只在 API 边界上做门控，因此 `api.win`
        这种直通宿主的属性是绕过权限的主要通道。

        该属性为兼容既有插件而保留（会打印一次弃用警告），
        新代码请改用 get_main_window()（受 dialog 权限门控）。
        """
        if not self.__dict__.get("_win_warned", False):
            self.__dict__["_win_warned"] = True
            try:
                print(
                    "[PluginAPI] 警告：api.win 已弃用（绕过权限门控），"
                    "请改用 api.get_main_window()（需要 dialog 权限）"
                )
            except Exception:
                pass
        return self.__dict__.get("_win_compat")

    def _host_window(self):
        """内部/内置插件专用：取主窗口，不打印弃用警告

        P0-3: 内置插件的面板注册需要主窗口。这里提供一个不触发
        api.win 弃用告警的内部通道。第三方插件请使用
        get_main_window()（受 dialog 权限门控）。
        """
        return self.__dict__.get("_win_compat")

    def _check_permission(self, perm: str):
        """检查是否有指定权限"""
        if perm not in self.permissions:
            raise PermissionError(
                f"插件 '{self.plugin_name}' 缺少 '{perm}' 权限。"
                f"请在 plugin.json 的 permissions 字段中声明。"
            )

    def has_permission(self, perm: str) -> bool:
        """查询是否有指定权限"""
        return perm in self.permissions

    def require_permission(self, perm: str) -> bool:
        """要求权限，无权限时显示提示而非抛异常"""
        if not self.has_permission(perm):
            self.show_status(f"插件 {self.plugin_name} 缺少 '{perm}' 权限", 3000, "warning")
            return False
        return True

    def grant_permission(self, perm: str):
        """动态授予权限（仅宿主可调用）

        P0-3 修复：原实现是 `self.permissions.add(perm)`，
        插件可以一行代码自我提权：
            self.api.grant_permission('process')
            self.api.run_command('...')
        现在必须由宿主（主窗口/插件管理器）显式授权，
        否则拒绝并提示。
        """
        if not self._host_authorized:
            self.show_status(
                f"插件 {self.plugin_name} 不允许自行授予权限 '{perm}'", 3000, "warning"
            )
            return False
        self.permissions.add(perm)
        return True

    def grant_permissions_by_host(self, perms) -> int:
        """宿主授予权限（不受 _host_authorized 限制）

        供主窗口/插件管理器在用户确认权限后调用。
        """
        count = 0
        for p in perms or []:
            if p not in self.permissions:
                self.permissions.add(p)
                count += 1
        return count

    def revoke_permission(self, perm: str):
        """撤销权限"""
        self.permissions.discard(perm)

    # ========================================================
    # 宿主窗口访问（P0-3）
    # ========================================================

    def get_main_window(self):
        """获取主窗口（需要 dialog 权限）

        P0-3 修复：原先 `api.win` 是公开属性，插件可由此拿到
        主窗口，进而取到全权限的主 API（widget.api）从而绕过
        所有权限检查。现改为受权限门控的方法访问。
        """
        if not self.win:
            return None
        if PERMISSION_DIALOG not in self.permissions:
            self.show_status(
                f"插件 {self.plugin_name} 缺少 'dialog' 权限，无法访问主窗口", 3000, "warning"
            )
            return None
        return self.win

    # ========================================================
    # 编辑器访问
    # ========================================================

    def send_message(self, target_plugin: str, message: Any):
        """
        向其他插件发送消息（通过事件总线）。

        参数:
            target_plugin: 目标插件名称
            message: 任意可序列化对象
        """
        try:
            event = NotificationEvent(
                title=f"plugin_message:{target_plugin}",
                message=(json.dumps(message) if not isinstance(message, str) else message),
                level="info",
            )
            bus.emit_event(event)
        except Exception:
            pass

    # ========================================================
    # 卸载清理
    # ========================================================

    def cleanup(self):
        """
        清理所有注册的资源（插件卸载时由 PluginLoader 调用）。
        """
        # 清理 v2.3 扩展点（补全提供者 / 诊断 / 后台任务）
        try:
            win = self._host_window()
            unregister = getattr(win, "unregister_plugin_completion_provider", None)
            if callable(unregister):
                unregister(self.plugin_name)
        except Exception:
            pass
        # 清理 v2.4 扩展点（hover / 右键菜单 / 代码操作 / 设置 / 状态栏）
        try:
            win = self._host_window()
            extras = getattr(win, "unregister_plugin_extras", None)
            if callable(extras):
                extras(self.plugin_name)
        except Exception:
            pass
        for widget in self._registered_status_items:
            try:
                bar = widget.parentWidget()
                if bar is not None and hasattr(bar, "removeWidget"):
                    bar.removeWidget(widget)
                widget.deleteLater()
            except Exception:
                pass
        self._registered_status_items.clear()
        self._registered_hover_providers.clear()
        self._registered_context_actions.clear()
        self._registered_code_action_providers.clear()
        self._registered_decorations.clear()
        self._registered_symbol_providers.clear()
        self._settings_schema = []
        self._registered_completion_providers.clear()
        try:
            self.clear_diagnostics()
        except Exception:
            pass
        # ★ 不要 deleteLater()：后台线程可能正持有桥并 emit，
        #   析构 QObject 后从工作线程 emit → Qt 访问违例（实测段错误）。
        #   正确做法：置 cancelled + 断开信号；桥对象交给 GC，
        #   即使线程稍后 emit 也没有接收者，不会崩。
        for bridge in self._background_bridges:
            try:
                bridge.cancelled = True
            except Exception:
                pass
            for sig in ("done", "failed"):
                try:
                    getattr(bridge, sig).disconnect()
                except Exception:
                    pass
        self._background_bridges.clear()
        self._background_threads.clear()

        # 清理事件连接
        try:
            self._cleanup_event_connections()
        except Exception:
            pass

        # 清理菜单动作
        for action in self._registered_actions:
            try:
                if action.parent():
                    action.parent().removeAction(action)
                action.setParent(None)
                action.deleteLater()
            except Exception:
                pass
        self._registered_actions.clear()

        # 清理子菜单
        #
        # 修复（审计用例 test_menu_item_survives_one_hot_reload）：
        #   原先只调 `menu.deleteLater()` —— **延迟删除**，子菜单仍挂在
        #   父菜单上。热重载时 `add_menu` 的"复用已存在子菜单"分支按文本
        #   找到的正是这个**待销毁的旧子菜单**，新动作被加进即将被销毁的
        #   容器；处理 DeferredDelete 后整项**凭空消失**（实测 0，期望 1）。
        #
        #   正确做法：先找到"承载该子菜单的那个 QAction"并从父菜单摘除，
        #   再 deleteLater。
        #
        #    ⚠️ 实测教训：`menu.menuAction().parent()` 返回的是**子菜单自己**
        #    （不是父菜单），所以不能直接用它 removeAction；
        #    必须遍历候选父菜单的 actions，找 `act.menu() is menu` 的那一个。
        for menu in self._registered_menus:
            try:
                holder = None
                holder_parent = None

                def _scan(parent_menu):
                    if parent_menu is None:
                        return None
                    try:
                        for act in parent_menu.actions():
                            if act.menu() is menu:
                                return act
                    except Exception:
                        pass
                    return None

                # 候选父：菜单自身的 parent()（通常是 QMenu）
                p = menu.parent()
                if p is not None and hasattr(p, "actions"):
                    holder = _scan(p)
                    holder_parent = p
                # 再兜底扫描菜单栏
                if holder is None and self.win is not None:
                    try:
                        for act in self.win.menuBar().actions():
                            if act.menu():
                                h = _scan(act.menu())
                                if h is not None:
                                    holder, holder_parent = h, act.menu()
                                    break
                    except Exception:
                        pass

                menu.clear()
                if holder is not None and holder_parent is not None:
                    holder_parent.removeAction(holder)
                menu.setParent(None)
                menu.deleteLater()
            except Exception:
                pass
        self._registered_menus.clear()

        # 清理面板
        for dock in self._registered_panels:
            try:
                if self.win is not None:
                    self.win.removeDockWidget(dock)
                dock.setParent(None)
                dock.deleteLater()
            except Exception:
                pass
        self._registered_panels.clear()

        # 清理快捷键
        for action in self._registered_shortcuts:
            try:
                if self.win is not None:
                    self.win.removeAction(action)
                action.setParent(None)
                action.deleteLater()
            except Exception:
                pass
        self._registered_shortcuts.clear()

        # 清理命令
        self._registered_commands.clear()

    # ========================================================
    # 信息查询
    # ========================================================

    def get_api_version(self) -> str:
        """获取 API 版本"""
        return API_VERSION

    # ========================================================
    # 能力探测（借鉴 Notepad++ 插件 API 的"函数表"思路）
    # ========================================================
    # NPP 的做法：插件 DLL 拿到 NppData 后，通过函数指针表判断宿主
    # 提供哪些消息（NPPM_*），再决定注册哪些菜单/面板 —— 插件不会在
    # 旧版宿主上调用不存在的接口而崩溃。
    #
    # 本软件用 Python API 版本代替函数表，但同样需要一个**可探测的
    # 能力清单**：插件（尤其第三方插件）可以先查询宿主支持哪些扩展点、
    # 哪些事件，再决定注册策略，而不是 try/except 盲试。
    _CAPABILITY_EXTENSION_POINTS = (
        "completion",
        "diagnostics",
        "background",
        "hover",
        "code_action",
        "editor_context_menu",
        "status_item",
        "decoration",
        "settings_schema",
        "symbol_provider",
    )

    def get_api_capabilities(self) -> Dict[str, Any]:
        """返回宿主能力清单（供插件做能力探测）

        返回结构::

            {
              "api_version": "2.0.0",
              "app_version": "2.23.0",
              "extension_points": {"completion": True, ...},
              "events": ["file_opened", ...],
              "permissions": ["editor_read", ...],
            }

        推荐用法（新插件在 on_activate 开头）::

            caps = api.get_api_capabilities()
            if caps["extension_points"].get("completion"):
                api.register_completion_provider(self.suggest)
        """
        try:
            events = self.list_events()
        except Exception:
            events = []
        return {
            "api_version": API_VERSION,
            "app_version": self.get_app_version(),
            "extension_points": {name: True for name in self._CAPABILITY_EXTENSION_POINTS},
            "events": events,
            "permissions": sorted(self.permissions),
        }

    def get_plugin_name(self) -> str:
        """获取当前插件名称"""
        return self.plugin_name

    def get_app_version(self) -> str:
        """获取应用版本"""
        try:
            from main import __version__

            return __version__
        except Exception:
            return "unknown"

    def get_permissions(self) -> List[str]:
        """获取当前插件的权限列表"""
        return sorted(self.permissions)

    # ========================================================
    # 调试辅助
    # ========================================================

    def log(self, message: str, level: str = "info"):
        """
        记录日志（输出到控制台和运行日志）。

        参数:
            message: 日志内容
            level: 级别
        """
        prefix = f"[Plugin:{self.plugin_name}]"
        print(f"{prefix} [{level.upper()}] {message}")

    def __repr__(self) -> str:
        return (
            f"<PluginAPI plugin={self.plugin_name!r} "
            f"permissions={sorted(self.permissions)} "
            f"api_version={API_VERSION}>"
        )
