# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""插件命令/调试/主题（v2.25 从 capability_wiring 拆出）。"""

from ui.mixins.capability_wiring_common import *  # noqa: F401,F403


class CommandsThemeMixin:
    def _find_action_with_text(self, text: str):
        """在整个菜单栏里按文本找已存在的 QAction（用于跨菜单复用同一动作）

        **优先返回带快捷键的那个**：实测菜单栏里可能存在**同名**动作
        （一个是真正的命令、带快捷键；另一个是无快捷键的展示项）。
        随便取第一个可能取到无快捷键的那个，导致复用失败。

        实现要点（实测坑）：不能用 `menuBar().findChildren(QAction)` ——
        菜单里的 QAction 的 parent 是**主窗口**，而不是 QMenuBar，
        因此 `findChildren` 一个都找不到（会静默返回 None，
        于是又新建一个动作，F5 就变成两个）。必须**遍历 QMenu 树**。

        为什么要复用：同一动作出现在多个菜单是正常的（VSCode 也如此），
        但**不能新建第二个带相同快捷键的 QAction** —— 那会让 Qt 报
        ambiguous shortcut，按键直接失效（实测 F5 就是这样失效的）。
        """
        try:
            from PyQt5.QtWidgets import QMenu

            found = []
            menus = list(self.findChildren(QMenu))
            # 递归展开子菜单（QMenu 的菜单项本身也是 QAction/QMenu）
            seen = set()
            stack = list(menus) + [self.menuBar()]
            while stack:
                menu = stack.pop()
                if id(menu) in seen:
                    continue
                seen.add(id(menu))
                try:
                    actions = menu.actions()
                except Exception:
                    continue
                for act in actions:
                    if act.text() == text:
                        found.append(act)
                    sub = act.menu()
                    if sub is not None:
                        stack.append(sub)
            for act in found:
                if not act.shortcut().isEmpty():
                    return act  # 带快捷键的优先
            return found[0] if found else None
        except Exception as e:
            if logger:
                logger.debug("按文本查找动作失败(%s): %s", text, e)
        return None

    def _plugin_commands(self, plugin_name: str):
        """取出某插件**已注册**的命令（键形如 `plugin.<插件>.<命令>`）

        真实链路（已核实 `app/plugins.py:1426-1433`）：
            `PluginAPI.register_command()` 会创建 QAction 并以
            `plugin.{plugin_name}.{name}` 注册到 `win.act_mgr`
            （`ActionManager.register`）。命令面板 `_load_plugin_commands()`
            正是按 `name.startswith("plugin.")` 从同一个 `act_mgr.actions`
            里取的 —— 因此本菜单与命令面板**同源**，不会出现
            "菜单里有、命令面板里没有"的偏差。

        返回: [(完整命令名, QAction), ...]，按名称排序
        """
        out = []
        try:
            mgr = getattr(self, "act_mgr", None)
            actions = getattr(mgr, "actions", None) if mgr else None
            if not actions:
                return out
            prefix = "plugin.%s." % plugin_name
            for key, action in actions.items():
                if isinstance(key, str) and key.startswith(prefix):
                    out.append((key, action))
        except Exception as e:
            if logger:
                logger.debug("枚举插件命令失败: %s", e)
        return sorted(out, key=lambda kv: kv[0])

    def _add_plugin_commands_submenu(self, title: str, plugin_name: str, icon_key: str = ""):
        """把某插件注册的命令加成一个子菜单

        **找不到命令时如实说明**，而不是放一个点了没反应的菜单项 ——
        这正是 P1-7 想解决的问题（用户找不到 ≠ 没有；但也不能假装有）。
        """
        try:
            sub = self.feature_menu.addMenu(title)
        except Exception:
            return
        # v2.19 P2：记录子菜单，供「插件未启用时隐藏」与延后刷新使用
        if not hasattr(self, "_feature_plugin_menus"):
            self._feature_plugin_menus = {}
        self._feature_plugin_menus[title] = sub
        cmds = self._plugin_commands(plugin_name)
        if not cmds:
            # 插件未启用/未注册命令：直接隐藏子菜单，不再显示禁用占位项
            try:
                sub.menuAction().setVisible(False)
            except Exception:
                pass
            return
        for name, action in cmds:
            short = name.rsplit(".", 1)[-1]
            label = action.text() or short
            sc = ""
            try:
                sc = action.shortcut().toString() if action.shortcut() else ""
            except Exception:
                sc = ""
            # 直接复用插件原来的 QAction（trigger 即执行其 callback），
            # 不新建包装 —— 避免出现"两个动作、两条冲突快捷键"。
            self._add_action(sub, label, sc or None, action.trigger)

    def _make_menu(self, title):
        """创建一个 QMenu（抽出来便于异常处理）"""
        from PyQt5.QtWidgets import QMenu

        return QMenu(title, self)

    def _invoke_plugin_command(self, plugin_name: str):
        """触发某插件注册的**第一个**命令（找不到时给出明确提示）

        保留此方法供聚合入口使用；实现改为走 `_plugin_commands()`
        （此前用的 `act_mgr.list_plugin_commands()` **不存在**，
        导致这条聚合入口一点就报"未找到"）。
        """
        try:
            cmds = self._plugin_commands(plugin_name)
            if cmds:
                cmds[0][1].trigger()
                return True
            self.status_bar.showMessage(
                f"插件「{plugin_name}」未注册命令或未启用：请到「工具 → 插件管理」确认", 8000
            )
        except Exception as e:
            print(f"[MainWindow] 调用插件命令失败: {e}")
        return False

    def _toggle_ai_inline(self):
        """开关 AI 行内补全（`ui/ai_inline_completer.py`）"""
        try:
            completer = getattr(self, "ai_inline_completer", None)
            if completer is None:
                self.status_bar.showMessage(
                    "AI 行内补全不可用：请先在插件中配置 AI 服务商（工具 → 插件管理 → AI 助手）",
                    8000,
                )
                return
            enabled = getattr(completer, "enabled", False)
            if hasattr(completer, "set_enabled"):
                completer.set_enabled(not enabled)
                self.status_bar.showMessage(f"AI 行内补全已{'关闭' if enabled else '开启'}", 3000)
        except Exception as e:
            print(f"[MainWindow] 切换 AI 行内补全失败: {e}")

    def _debug_run(self):
        """启动调试（复用已有能力，找不到就明确提示）"""
        try:
            if hasattr(self, "_run_current_file"):
                self._run_current_file()
            else:
                self.status_bar.showMessage("调试不可用", 3000)
        except Exception as e:
            print(f"[MainWindow] 启动调试失败: {e}")

    def _debug_breakpoint(self):
        """切换当前行断点"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy is None:
                return
            if hasattr(proxy, "toggle_breakpoint"):
                proxy.toggle_breakpoint()
                n = len(proxy.get_breakpoints()) if hasattr(proxy, "get_breakpoints") else 0
                self.status_bar.showMessage(f"当前断点数: {n}", 3000)
            else:
                self.status_bar.showMessage("该编辑器不支持断点", 3000)
        except Exception as e:
            print(f"[MainWindow] 切换断点失败: {e}")

    def _show_panel_lsp(self):
        """打开 LSP 面板"""
        try:
            if self._ensure_panel("lsp") and getattr(self, "lsp", None):
                self.lsp.setVisible(True)
                self.lsp.raise_()
        except Exception as e:
            print(f"[MainWindow] 打开 LSP 面板失败: {e}")

    # ========================================================
    # 启动主题（修复"面板永远深色"）
    # ========================================================
    def apply_startup_theme(self):
        """启动时把**已保存的主题**应用到所有面板

        ## 真实桌面验证发现的缺陷

        打包版在真实桌面截图里，编辑器是浅色护眼主题，而所有停靠面板
        （目录树、全局搜索、性能监控……）却是**纯黑/深色**——
        左侧目录树甚至只是"一块黑矩形"，看起来像面板坏了。

        根因：
          * `main.load_theme()` 启动时只对 `QApplication` 设了 QSS；
          * 各面板在构造函数的 `_apply_style()` 里写死深色 QSS，
            **会覆盖 app 级 QSS**；
          * 真正能把面板 QSS 按主题换算的函数是
            `ThemeLoader.notify_widgets()`（它调用各面板的
            `refresh_theme()` → `adapt_qss_colors()`），
            但此前**只在用户手动切换主题时**调用，启动时从不调用。

        修复：主窗口构造完成后调用本方法 —— 读 `theme_name` 设置，
        应用 QSS 并 `notify_widgets(self, theme)`，让面板与编辑器一致。
        """
        try:
            from PyQt5.QtCore import QSettings
            from PyQt5.QtWidgets import QApplication

            from infrastructure.theme_loader import ThemeLoader

            settings = QSettings("QingCao", "Editor")
            name = settings.value("theme_name", "", type=str)
            # 幂等：同一主题已应用过则直接返回（避免重复 apply_qss/notify_widgets）
            _key = name or "__builtin__"
            if (
                getattr(self, "_startup_theme_key", None) == _key
                and getattr(self, "_startup_theme", None) is not None
            ):
                return self._startup_theme
            loader = ThemeLoader()
            theme = None
            if name:
                try:
                    theme = loader.load_by_name(name)
                except Exception as e:
                    print(f"[Theme] 启动加载主题失败 {name}: {e}")
            if theme is None:
                # 没有保存过主题 → 用内置暗夜（与 main.load_theme 的回退一致）
                try:
                    from infrastructure.theme_loader import BuiltinThemes

                    theme = BuiltinThemes.dark_night()
                except Exception:
                    theme = None
            if theme is None:
                return None

            app = QApplication.instance()
            if app is not None:
                try:
                    # lazy=True：只 polish 可见控件；隐藏面板的 QSS
                    # 在它们首次显示时再套（见 theme_loader 的
                    # `_LazyThemeApplier`），避免启动时对几十个隐藏面板
                    # 逐个 setStyleSheet + unpolish/polish（实测 0.4~0.6s）。
                    loader.apply_qss(app, theme, lazy=True)
                except Exception as e:
                    print(f"[Theme] 启动 apply_qss 失败: {e}")

            # 关键：通知所有面板按主题换算 QSS
            # v2.25 QSS 专项：批量期间关闭重绘，减少首帧 polish/paint 次数
            try:
                self.setUpdatesEnabled(False)
            except Exception:
                pass
            try:
                loader.notify_widgets(self, theme)
            except Exception as e:
                print(f"[Theme] 启动 notify_widgets 失败: {e}")

            # 插件/第三方面板若无 refresh_theme，统一递归适配其硬编码 QSS
            try:
                adapt = getattr(self, "adapt_widget_styles", None)
                if callable(adapt):
                    adapt(self, theme)
            except Exception as e:
                print(f"[Theme] 启动子控件样式适配失败: {e}")
            finally:
                try:
                    self.setUpdatesEnabled(True)
                except Exception:
                    pass

            self._startup_theme = theme
            self._startup_theme_key = _key
            return theme
        except Exception as e:
            print(f"[MainWindow] 启动主题应用失败: {e}")
            return None
