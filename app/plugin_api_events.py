# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""事件/命令/扩展点职责（v2.24 从 plugin_api.py 拆出）。"""

from app.plugin_api_common import *  # noqa: F401,F403,F405


class EventMixin:
    @staticmethod
    def _event_signal_map() -> dict:
        """事件名 → 事件总线信号 的**唯一**映射表

        修复（审计用例 test_unsubscribe_supports_every_subscribable_event）：
            `subscribe()` 与 `unsubscribe()` 各自维护了一份字面量映射，
            而 `unsubscribe` 的那份**只有 6 项**（subscribe 有 15 项）：
            缺少 file_modified、tab_changed、tab_added、tab_removed、
            project_opened、project_closed、macro_started、macro_stopped、
            theme_changed。

            于是这些事件的 `unsubscribe()` **静默失败** —— 插件的回调
            永远留在信号上。插件被禁用/重载后仍会被调用，访已释放的对象
            会崩溃，或造成重复响应。这是"订阅得上、退订不掉"的经典泄漏。

            现在两份共用一个映射表，从结构上杜绝不一致。
        """
        return {
            "file_opened": bus.file_opened,
            "file_saved": bus.file_saved,
            "file_closed": bus.file_closed,
            "file_modified": bus.file_modified,
            "editor_changed": bus.editor_changed,
            "cursor_moved": bus.cursor_moved,
            "selection_changed": bus.selection_changed,
            "tab_changed": bus.tab_changed,
            "tab_added": bus.tab_added,
            "tab_removed": bus.tab_removed,
            "project_opened": bus.project_opened,
            "project_closed": bus.project_closed,
            "macro_started": bus.macro_started,
            "macro_stopped": bus.macro_stopped,
            "theme_changed": bus.theme_changed,
        }

    def subscribe(self, event_name: str, callback: Callable):
        """
        订阅事件总线事件。

        参数:
            event_name: 事件名称，如 "file_opened", "cursor_moved"
            callback: 回调函数，接收事件对象

        支持的事件:
            file_opened, file_saved, file_closed, file_modified,
            editor_changed, cursor_moved, selection_changed,
            tab_changed, tab_added, tab_removed,
            project_opened, project_closed,
            macro_started, macro_stopped,
            theme_changed
        """
        signal_map = self._event_signal_map()

        signal = signal_map.get(event_name)
        if signal is None:
            self.show_status(f"未知事件: {event_name}", 3000, "warning")
            return

        try:
            signal.connect(callback)
            self._event_connections.append((signal, callback))
        except Exception as e:
            self.show_status(f"订阅事件失败: {e}", 3000, "error")

    def unsubscribe(self, event_name: str, callback: Callable):
        """取消订阅事件（映射与 `subscribe` 完全相同）

        ⚠️ 关键实现细节（实测踩坑）：
            PyQt 的 **bound signal 每次属性访问都会返回新的包装对象**：

                bus.file_opened is bus.file_opened   ->  False
                bus.file_opened == bus.file_opened   ->  True

            因此用 `is` 比较信号对象永远不成立 —— 这正是原实现
            `if not (s is signal and c is callback)` **静默失败**、
            退订后连接依然挂着的原因之一（另一个原因是映射表缺键）。

            现在用 `==` 比较（按底层信号身份），并同时逐个尝试
            `disconnect()`。
        """
        signal_map = self._event_signal_map()
        signal = signal_map.get(event_name)
        if signal is None:
            self.show_status(f"未知事件: {event_name}", 3000, "warning")
            return

        try:
            signal.disconnect(callback)
        except (TypeError, RuntimeError):
            # 未连接 / 已断开 —— 不是错误
            pass

        # 无论 disconnect 是否抛错都清理登记表（用 == 而非 is）
        self._event_connections = [
            (s, c)
            for s, c in self._event_connections
            if not (c == callback and (s == signal or s is signal))
        ]

    def emit_event(self, event: BaseEvent):
        """发射事件到事件总线"""
        bus.emit_event(event)

    def _cleanup_event_connections(self):
        """清理所有事件连接（插件卸载时调用）"""
        for signal, callback in self._event_connections:
            try:
                signal.disconnect(callback)
            except (TypeError, RuntimeError):
                pass
        self._event_connections.clear()

    # ========================================================
    # 状态栏消息
    # ========================================================

    def list_events(self) -> List[str]:
        """列出所有可订阅事件名（等价于 NPP 的 NPPN_* 通知清单）

        事件通过 ``api.subscribe(name, callback)`` 订阅，
        通过 ``api.unsubscribe(name, callback)`` 退订。
        """
        try:
            return sorted(self._event_signal_map().keys())
        except Exception:
            return []

    def register_command(self, name: str, callback: Callable, description: str = ""):
        """
        注册一个命令，可在命令面板中搜索。

        参数:
            name: 命令名称（唯一）
            callback: 执行函数
            description: 描述
        """
        self._registered_commands[name] = {"callback": callback, "description": description}
        # 添加到 ActionManager 以便命令面板可搜索
        try:
            if self.win is None:
                return
            action = QAction(description or name, self.win)
            action.triggered.connect(callback)
            # ⚠️ 必须是 `is not None` 判定，**不能**用真值判定！
            #
            # 实测缺陷：`ActionManager` 定义了 `__len__`（返回动作数），
            # 因此**空的 ActionManager 是 falsy**。而插件正是在**激活时**
            # 注册命令 —— 那一刻 `act_mgr` 里几乎还是空的（只有极少数
            # 早期动作），于是原来的
            #     `if hasattr(...) and self.win.act_mgr:`
            # 会直接短路，**命令一个都不会注册**：
            #   * 命令面板的「插件」分类永远是空的（它按
            #     `name.startswith("plugin.")` 从 `act_mgr.actions` 取）；
            #   * 「⭐ 特色功能」聚合入口只能显示"未注册命令"。
            # 缓过来之后再启动（actions 已被前一次运行填过）反而正常，
            # 所以这是**首次运行 100% 复现**的隐蔽缺陷。
            mgr = getattr(self.win, "act_mgr", None)
            if mgr is not None:
                mgr.register(
                    f"plugin.{self.plugin_name}.{name}",
                    action,
                    None,
                    category="插件",
                    description=description,
                )
            self._registered_actions.append(action)
        except Exception:
            pass

    def execute_command(self, name: str):
        """执行已注册的命令"""
        cmd = self._registered_commands.get(name)
        if cmd:
            try:
                cmd["callback"]()
            except Exception as e:
                self.show_status(f"命令执行失败: {e}", 3000, "error")

    def list_commands(self) -> List[str]:
        """列出所有已注册命令"""
        return list(self._registered_commands.keys())

    # ========================================================
    # 语法高亮注册
    # ========================================================

    def register_lexer(self, extension: str, lexer_factory: Callable):
        """
        注册自定义语法高亮器。

        参数:
            extension: 文件扩展名（如 ".abc"）
            lexer_factory: 创建 lexer 的函数
        """
        self._registered_lexers[extension] = lexer_factory
        if self.win is not None:
            if not hasattr(self.win, "_custom_lexers"):
                self.win._custom_lexers = {}
            self.win._custom_lexers[extension] = lexer_factory

    def get_lexer(self, extension: str) -> Optional[Any]:
        """获取指定扩展名的 lexer"""
        factory = self._registered_lexers.get(extension)
        if factory:
            try:
                return factory()
            except Exception:
                return None
        return None

    # ========================================================
    # 编辑器智能扩展点（v2.3）
    # ========================================================

    def register_completion_provider(self, provider, language_ids=None):
        """注册补全提供者 —— 让插件参与编辑器补全

        这是插件从"挂菜单/面板"升级为"参与编辑智能"的关键扩展点。

        参数:
            provider: 可调用对象，签名
                ``provider(prefix, language=..., filepath=...) -> list``
                返回候选词列表（str 列表，或 dict:
                ``{"label": "foo", "insert_text": "foo()", "detail": "..."}``）。
                在**主线程**调用，应快速返回（重活请用 run_background）。
            language_ids: 生效的语言/扩展名列表（如 ``["python", ".py"]``）；
                None 表示对所有语言生效。

        返回:
            是否注册成功

        权限: editor_read（需要读取当前编辑内容的能力）

        注意:
            * 提供者抛异常不会影响编辑器，异常被捕获并记日志；
            * 插件卸载（cleanup）时自动注销。
        """
        self._check_permission(PERMISSION_EDITOR_READ)
        win = self._host_window()
        if win is None:
            return False
        registrar = getattr(win, "register_plugin_completion_provider", None)
        if not callable(registrar):
            self.log("宿主不支持补全扩展点", "warning")
            return False
        ok = registrar(provider, language_ids=language_ids, plugin_name=self.plugin_name)
        if ok:
            self._registered_completion_providers.append((provider, language_ids))
        return bool(ok)

    def publish_diagnostics(self, problems, filepath=None):
        """发布诊断信息到「问题」面板

        参数:
            problems: 列表，元素为 dict 或 ``core.problems.Problem``：
                ``{"line": 3, "col": 0, "severity": "error"|"warning"|"info"|"hint",
                   "message": "...", "code": "E001"}``
                line/col 从 0 开始。
            filepath: 目标文件；None 表示当前编辑器文件。

        返回:
            实际发布的条目数

        权限: editor_read

        语义:
            * 只替换**本插件来源**的诊断，不会清掉 LSP / 其它插件的；
            * 重复调用 = 覆盖本插件上一批诊断（适合实时校验）；
            * 用 ``clear_diagnostics()`` 清空。
        """
        self._check_permission(PERMISSION_EDITOR_READ)
        fp = filepath or self.get_current_filepath() or ""
        try:
            from core.problems import Problem, get_problem_manager
        except Exception as e:
            self.log(f"问题管理器不可用: {e}", "error")
            return 0

        normalized = []
        for item in problems or []:
            try:
                if isinstance(item, Problem):
                    normalized.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                normalized.append(
                    Problem(
                        filepath=fp,
                        line=int(item.get("line", 0) or 0),
                        col=int(item.get("col", 0) or 0),
                        severity=str(item.get("severity", "info")),
                        message=str(item.get("message", "")),
                        source=str(item.get("source") or self.plugin_name),
                        code=str(item.get("code", "")),
                        end_line=int(item.get("end_line", 0) or 0),
                        end_col=int(item.get("end_col", 0) or 0),
                    )
                )
            except Exception:
                continue

        try:
            manager = get_problem_manager()
            existing = list(manager.get_for_file(fp) or [])
            # 只清掉"本插件发布过"的旧条目，保留其它来源
            keep = [p for p in existing if getattr(p, "source", "") != self.plugin_name]
            manager.set_file_problems(fp, keep + normalized)
            self._published_diagnostics[fp] = normalized
            return len(normalized)
        except Exception as e:
            self.log(f"发布诊断失败: {e}", "error")
            return 0

    def clear_diagnostics(self, filepath=None):
        """清除本插件发布的诊断（filepath=None 清全部）"""
        self._check_permission(PERMISSION_EDITOR_READ)
        try:
            from core.problems import get_problem_manager

            manager = get_problem_manager()
        except Exception:
            return 0
        targets = [filepath] if filepath else list(self._published_diagnostics.keys())
        removed = 0
        for fp in targets:
            try:
                existing = list(manager.get_for_file(fp) or [])
                keep = [p for p in existing if getattr(p, "source", "") != self.plugin_name]
                if len(keep) != len(existing):
                    manager.set_file_problems(fp, keep)
                    removed += len(existing) - len(keep)
                self._published_diagnostics.pop(fp, None)
            except Exception:
                continue
        return removed

    def run_background(self, func, on_done=None, on_error=None, name: str = ""):
        """在后台线程执行函数，回调回到**主线程**

        为什么需要（插件生态短板）：
            插件此前只能自己 ``threading.Thread`` + 手工往主线程
            投递，容易在窗口销毁后 emit 导致
            ``RuntimeError: wrapped C/C++ object has been deleted``。
            本方法用 QObject 信号桥把结果排队回主线程，并随插件
            卸载自动失效。

        参数:
            func: 无参可调用对象（在后台线程执行）
            on_done(result): 成功回调（主线程）
            on_error(message): 失败回调（主线程，收到异常文本）
            name: 任务名（仅用于日志/调试）

        返回:
            任务对象（可用 ``is_alive()`` 查询；插件卸载会自动取消）

        权限: 无（但 **func 内不要直接调用 PluginAPI** —— API 只在
        主线程安全；需要读写编辑器请在 on_done 里做）
        """
        import threading

        api = self
        bridge = _BackgroundBridge()

        def _on_done(result):
            if bridge.cancelled:
                return
            try:
                if on_done is not None:
                    on_done(result)
            except Exception as e:
                api.log(f"后台任务 {name} 的 on_done 失败: {e}", "error")

        def _on_error(message):
            if bridge.cancelled:
                return
            try:
                if on_error is not None:
                    on_error(message)
                else:
                    api.log(f"后台任务 {name} 失败: {message}", "error")
            except Exception:
                pass

        bridge.done.connect(_on_done)
        bridge.failed.connect(_on_error)

        def _work():
            try:
                result = func()
            except Exception as e:
                try:
                    bridge.failed.emit(str(e))
                except RuntimeError:
                    pass
                return
            try:
                bridge.done.emit(result)
            except RuntimeError:
                pass

        thread = threading.Thread(
            target=_work, daemon=True, name=f"plugin-bg:{name or self.plugin_name}"
        )
        self._background_bridges.append(bridge)
        self._background_threads.append(thread)
        thread.start()
        return thread

    # ========================================================
    # v2.4 扩展点：hover / 代码操作 / 右键菜单 / 状态栏 / 装饰 / 设置
    # ========================================================

    def register_hover_provider(self, provider, language_ids=None):
        """注册悬浮提示提供者

        provider 签名：``provider(line, col, filepath=..., language=...) -> str``
        返回文本作为工具提示（多个提供者用空行分隔）；主线程调用，应快速返回。

        权限：editor_read
        """
        self._check_permission(PERMISSION_EDITOR_READ)
        win = self._host_window()
        registrar = getattr(win, "register_plugin_hover_provider", None)
        if not callable(registrar):
            return False
        ok = registrar(provider, language_ids=language_ids, plugin_name=self.plugin_name)
        if ok:
            self._registered_hover_providers.append((provider, language_ids))
        return bool(ok)

    def register_code_action_provider(self, provider, language_ids=None):
        """注册代码操作提供者（"快速修复"类）

        provider 签名：``provider(line, col, filepath=..., language=...) -> list``
        每个元素：``{"title": "...", "kind": "quickfix", "callback": fn}``,
        callback 在用户选择该项时执行。

        权限：editor_write（代码操作通常会产生编辑）
        """
        self._check_permission(PERMISSION_EDITOR_WRITE)
        win = self._host_window()
        registrar = getattr(win, "register_plugin_code_action_provider", None)
        if not callable(registrar):
            return False
        ok = registrar(provider, language_ids=language_ids, plugin_name=self.plugin_name)
        if ok:
            self._registered_code_action_providers.append((provider, language_ids))
        return bool(ok)

    def register_symbol_provider(self, provider, language_ids=None):
        """注册符号提供者 → 合并进「大纲」面板

        等价 Notepad++ 的 `functionList.xml`（用户/插件贡献符号解析器）。

        provider 签名：
            ``provider(text, filepath=..., language=...) -> list``
        返回符号列表，每项::

            {"name": "foo", "type": "function", "line": 10, "col": 0,
             "signature": "(a, b)", "children": [...]}

        line/col 从 0 开始；type 取值见 `ui/outline_panel.SymbolType`
        （class/function/method/variable/... 或自定义字符串）。

        权限：editor_read
        """
        self._check_permission(PERMISSION_EDITOR_READ)
        win = self._host_window()
        registrar = getattr(win, "register_plugin_symbol_provider", None)
        if not callable(registrar) or not callable(provider):
            return False
        ok = registrar(provider, language_ids=language_ids, plugin_name=self.plugin_name)
        if ok:
            self._registered_symbol_providers.append((provider, language_ids))
        return bool(ok)

    # ========================================================
    # LSP 注册
    # ========================================================

    def register_lsp(
        self, language_id: str, server_command: List[str], extensions: Optional[List[str]] = None
    ):
        """
        注册 LSP 语言服务器。

        参数:
            language_id: 语言 ID（如 "python"）
            server_command: 启动命令列表
            extensions: 关联的文件扩展名列表
        """
        self._registered_lsp[language_id] = {
            "command": server_command,
            "extensions": extensions or [],
        }
        if self.win is not None:
            if not hasattr(self.win, "_lsp_servers"):
                self.win._lsp_servers = {}
            self.win._lsp_servers[language_id] = server_command

    def get_lsp_server(self, language_id: str) -> Optional[List[str]]:
        """获取指定语言的 LSP 启动命令"""
        info = self._registered_lsp.get(language_id)
        return info["command"] if info else None

    # ========================================================
    # 主题操作
    # ========================================================
