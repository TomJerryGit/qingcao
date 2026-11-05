# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""MainWindow session 职责（v2.23 D2 拆分）。"""

from ui.main_window_common import *  # noqa: F401,F403
from ui.main_window_common import _TopLevelThemeFilter  # noqa: F401


class WindowSessionMixin:
    # ========================================================
    # 状态栏更新
    # ========================================================
    def _on_status_message(self, event):
        """状态消息事件"""
        try:
            msg = getattr(event, "message", str(event))
            timeout = getattr(event, "timeout", 3000)
            self.status_bar.showMessage(msg, timeout)
        except Exception:
            pass

    def _on_cursor_moved(self, event):
        """光标移动"""
        try:
            line = getattr(event, "line", 1)
            col = getattr(event, "col", 0)
            self.cursor_label.setText(f"行 {line}, 列 {col}")
        except Exception:
            pass

    def _on_tab_changed(self, index: int):
        """
        标签切换。

        P2-5: 同步 column_mode_action 状态，避免 UI 与实际不一致。
        """
        try:
            if index < 0:
                return

            editor = self.tabs.widget(index)
            if not editor:
                return

            # 大纲（基础版）
            if self.outline:
                try:
                    if hasattr(self.outline, "update_symbols"):
                        self.outline.update_symbols(editor)
                    elif hasattr(self.outline, "schedule_update"):
                        self.outline.schedule_update()
                except Exception as e:
                    print(f"[MainWindow] 大纲更新失败: {e}")

            # 大纲（增强版）
            if self.outline_enhanced:
                try:
                    if hasattr(self.outline_enhanced, "update_symbols"):
                        self.outline_enhanced.update_symbols(editor)
                    elif hasattr(self.outline_enhanced, "schedule_update"):
                        self.outline_enhanced.schedule_update()
                except Exception as e:
                    print(f"[MainWindow] 增强大纲更新失败: {e}")

            # Minimap（安全调用）
            if self.minimap:
                try:
                    if hasattr(self.minimap, "set_editor"):
                        self.minimap.set_editor(editor)
                except Exception as e:
                    print(f"[MainWindow] Minimap 更新失败: {e}")

            # 状态栏
            self._update_status_for_editor()

            # Git 分支
            self._update_git_branch()

            # P2-5: 同步列模式状态
            self._sync_column_mode_state()

            # P6: LSP 总开关打开时，为新标签补上 LSP（幂等）
            self._sync_lsp_for_current_tab()

            # P0-1: 录制中切换标签 → 录制钩子必须跟着切到新标签的
            # undo_manager（proxy 是每标签一个）。否则用户在录制过程中
            # 切了标签，之后的编辑一条也录不到，而 UI 仍显示"● REC"。
            try:
                macro = getattr(self, "macro", None)
                if (
                    macro is not None
                    and getattr(macro, "recording", False)
                    and hasattr(macro, "bind_current_undo_manager")
                ):
                    macro.bind_current_undo_manager()
            except Exception as e:
                print(f"[MainWindow] 切换标签后重绑宏录制失败: {e}")

        except Exception as e:
            print(f"[MainWindow] 标签切换失败: {e}")

    def _sync_column_mode_state(self):
        """同步工具栏列模式按钮状态（P2-5）"""
        try:
            if not hasattr(self, "column_mode_action"):
                return

            proxy = self.tabs.current_proxy()
            if not proxy or not hasattr(proxy, "is_column_mode"):
                return

            is_col = bool(proxy.is_column_mode())
            if self.column_mode_action.isChecked() != is_col:
                # 阻断信号避免触发 _toggle_column_mode 再次调用
                self.column_mode_action.blockSignals(True)
                self.column_mode_action.setChecked(is_col)
                self.column_mode_action.blockSignals(False)
        except Exception as e:
            print(f"[MainWindow] 同步列模式状态失败: {e}")

    def _sync_lsp_for_current_tab(self):
        """P6: LSP 总开关打开时，切标签后为新编辑器补上 LSP（幂等）。

        只对 `LSP_LANGUAGE_BY_EXT` 里认得出的文件类型自动启用，避免
        每次切到 .txt / .log 都弹一次"不支持"的提示。
        """
        try:
            if not hasattr(self, "lsp_action") or not self.lsp_action.isChecked():
                return
            proxy = self.tabs.current_proxy()
            if proxy is None or not hasattr(proxy, "toggle_lsp"):
                return
            if getattr(proxy, "lsp_client", None) is not None:
                return

            filepath = ""
            if getattr(proxy, "document", None) is not None:
                filepath = proxy.document.filepath or ""
            try:
                from core.editor import lsp_language_for_file

                if not filepath or not lsp_language_for_file(filepath):
                    return
            except Exception:
                return

            self._connect_lsp_signals(proxy)
            if proxy.toggle_lsp(True) and filepath:
                self._lsp_clients[filepath] = proxy
        except Exception as e:
            logger.debug("切换标签后同步 LSP 失败: %s", e)

    def _on_all_tabs_closed(self):
        """所有标签关闭"""
        try:
            self.central_stack.setCurrentIndex(1)

            if self.minimap and hasattr(self.minimap, "set_editor"):
                try:
                    self.minimap.set_editor(None)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_symbol_clicked(self, line: int):
        """大纲符号点击"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.sc:
                proxy.sc.setCursorPosition(line, 0)
                proxy.sc.ensureLineVisible(line)
                proxy.sc.setFocus()
        except Exception:
            pass

    def _on_file_from_tree(self, filepath: str):
        """从目录树打开文件"""
        try:
            self.central_stack.setCurrentIndex(0)
            self.tabs.open_file(filepath)
        except Exception as e:
            print(f"[MainWindow] 打开文件失败: {e}")

    def _on_search_match_activated(self, filepath: str, start: int, end: int, line: int, col: int):
        """全局搜索匹配激活"""
        try:
            proxy = self.tabs.open_file(filepath)
            if proxy and proxy.sc:
                try:
                    proxy.sc.SendScintilla(proxy.sc.SCI_SETSEL, start, end)
                except Exception:
                    pass
                proxy.sc.setCursorPosition(line - 1, col)
                proxy.sc.ensureLineVisible(line - 1)
        except Exception as e:
            print(f"[MainWindow] 搜索跳转失败: {e}")

    def _current_search_options(self, pattern: str):
        """取"当前搜索选项"：优先全局搜索面板的勾选（P0-3）

        缺陷背景（P0-3，实测确认）:
            `_on_global_replace` 原先自己 new 了一份
            `SearchOptions(pattern=pattern)` —— 即
            `is_regex=False / case_sensitive=False / whole_word=False`
            的**默认值**，完全无视面板上的勾选。后果是"正则搜索 + 全部替换"
            按字面量替换：例如用 `\\d+` 搜到 12 个匹配，替换阶段却去找
            字面量 `\\d+`，一处也匹配不上（静默 0 处替换）。

        修复策略：面板的 `build_options()` 是选项的**唯一构造点**，
        并把选项对象随 `replace_requested` 信号一起传进来（见
        `ui/global_search_panel.py`）。本方法只是"面板不可用"时的兜底，
        行为与修复前一致，不会更差。
        """
        gsearch = getattr(self, "gsearch", None)
        if gsearch is not None and hasattr(gsearch, "build_options"):
            try:
                options = gsearch.build_options()
                if options is not None:
                    if pattern and not options.pattern:
                        options.pattern = pattern
                    return options
            except Exception as e:
                print(f"[MainWindow] 读取搜索选项失败: {e}")

        from core.search import SearchOptions

        return SearchOptions.from_preferences(pattern=pattern)

    def _on_global_replace(self, pattern: str, replace_text: str, file_results: dict, options=None):
        """P2-C5: 全局搜索 → 全部替换。

        参数:
            pattern: 搜索模式
            replace_text: 替换文本
            file_results: {filepath: [SearchMatch, ...]}
            options: 搜索选项（P0-3；由面板随信号传入）

        缺陷背景（P0-3，已实测）:
            本方法原先用 `SearchOptions(pattern=pattern)` 重建选项 ——
            面板上勾选的"正则 / 大小写 / 全词 / 转义 / 多行"被**静默丢弃**。
            更隐蔽的是：这里对每个文件**重新搜索**一遍来确定匹配位置，
            用默认选项重搜，得到的匹配集与用户看到的搜索结果根本不是同一批
            （正则表达式在字面量模式下往往匹配到 0 处），替换位置随之错乱。

            修复后：搜索与替换共用同一个 `SearchOptions` 对象
            （`GlobalSearchPanel.build_options()` 构造、
            `replace_requested` 信号携带），语义上保证"所见即所替"。
        """
        if not pattern or not file_results:
            return

        if options is None:
            options = self._current_search_options(pattern)

        try:
            from core.content_provider import LocalFileProvider
            from core.search import ReplaceEngine, SearchEngine

            total = 0
            abs_paths = set()

            for filepath in file_results:
                abs_paths.add(os.path.abspath(filepath))
                try:
                    provider = LocalFileProvider()
                    provider.open(filepath)
                    try:
                        # P0-3: 复用同一套选项（正则/大小写/全词/转义/多行），
                        # 而不是 SearchOptions 的默认值
                        engine = SearchEngine(provider, options)
                        result = engine.search()
                        if result.is_empty:
                            continue

                        replace_engine = ReplaceEngine(provider)
                        n = replace_engine.replace_all(
                            result,
                            replace_text,
                            is_regex=options.is_regex,
                            pattern=options.pattern,
                        )
                        provider.save(filepath)
                        total += n
                    finally:
                        provider.close()
                except Exception as e:
                    print(f"[MainWindow] 替换 {filepath} 失败: {e}")

            # 刷新已打开的受影响文件
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if not hasattr(w, "proxy") or not w.proxy:
                    continue
                fp = None
                try:
                    if w.proxy.document:
                        fp = w.proxy.document.filepath
                except Exception:
                    pass
                if fp and os.path.abspath(fp) in abs_paths:
                    try:
                        if w.proxy.document:
                            w.proxy.document.reload()
                        if w.proxy.sc and w.proxy.document:
                            w.proxy.sc.setText(w.proxy.document.get_text())
                    except Exception:
                        pass

            self.status_bar.showMessage(f"已替换 {total} 处", 3000)

        except Exception as e:
            print(f"[MainWindow] 全局替换失败: {e}")

    # ========================================================
    # 标签切换辅助
    # ========================================================
    def _next_tab(self):
        """下一个标签"""
        try:
            count = self.tabs.count()
            if count > 1:
                idx = (self.tabs.currentIndex() + 1) % count
                self.tabs.setCurrentIndex(idx)
        except Exception:
            pass

    def _prev_tab(self):
        """上一个标签"""
        try:
            count = self.tabs.count()
            if count > 1:
                idx = (self.tabs.currentIndex() - 1) % count
                self.tabs.setCurrentIndex(idx)
        except Exception:
            pass

    # ========================================================
    # 会话
    # ========================================================
    def _restore_session(self):
        """恢复会话"""
        try:
            if not self.session:
                return

            if self.prefs and not self.prefs.get("restore_session", True):
                return

            count = self.session.restore(self.tabs, self, confirm_recovery=False)

            if count and count > 0:
                self.central_stack.setCurrentIndex(0)
                self.status_bar.showMessage(f"已恢复 {count} 个文件", 3000)
                self.session_restored.emit(count)
        except Exception as e:
            print(f"[MainWindow] 恢复会话失败: {e}")

    def restore_session(self):
        """公开接口：恢复会话（供 main.py 调用）"""
        self._restore_session()

    def _autosave_session(self):
        """
        自动保存会话。

        P2-3: 无打开文件时跳过，避免每 2 分钟无谓写盘。
        """
        try:
            if not self.session:
                return

            if self.prefs and not self.prefs.get("restore_session", True):
                return

            # 无打开文件则跳过
            if self.tabs.count() == 0:
                return

            self.session.save(self.tabs, self)
        except Exception:
            pass

    def save_session(self):
        """手动保存会话"""
        try:
            if self.session:
                self.session.save(self.tabs, self)
        except Exception as e:
            print(f"[MainWindow] 保存会话失败: {e}")

    # ========================================================
    # 插件
    # ========================================================
    def _create_main_api(self):
        """
        创建主窗口的独立 API（P2-1）。

        与插件的 API 不同，主 API 拥有全部权限，
        不受任何插件 manifest 中 permissions 的限制。
        用于 Python 控制台、插件管理等场景。
        """
        try:
            from app.plugins import PluginAPI
        except Exception as e:
            print(f"[MainWindow] 无法导入 PluginAPI: {e}")
            return None

        # 尝试获取完整的权限列表
        perms = []
        try:
            from app.plugins import ALL_PERMISSIONS

            if ALL_PERMISSIONS:
                perms = list(ALL_PERMISSIONS)
        except Exception:
            pass

        # 若无法获取，使用内置的回退列表
        if not perms:
            perms = list(_MAIN_API_FALLBACK_PERMISSIONS)

        try:
            return PluginAPI(
                self,
                permissions=perms,
                plugin_name="__main__",
            )
        except Exception as e:
            print(f"[MainWindow] 创建主 API 失败: {e}")
            return None

    # ========================================================
    # 错误处理
    # ========================================================
    def _show_error(self, title: str, message: str):
        """显示错误"""
        # P1-2: 音效接线（默认关闭）
        try:
            from infrastructure.sound_manager import SoundEvent, play_sound

            play_sound(SoundEvent.NOTIFY_ERROR)
        except Exception:
            pass
        QMessageBox.critical(self, title, message)

    def _show_info(self, title: str, message: str):
        """显示信息"""
        QMessageBox.information(self, title, message)

    # ========================================================
    # 关闭事件
    # ========================================================
    def closeEvent(self, event):
        try:
            checker = getattr(self, "_update_checker", None)
            if checker is not None:
                checker.cancel()
        except Exception:
            pass

        # 主题事件过滤器挂在 QApplication 上：窗口销毁前必须显式移除，
        # 否则多窗口/多测试连续创建时可能访问已销毁对象（崩溃）。
        try:
            from PyQt5.QtWidgets import QApplication

            filt = getattr(self, "_toplevel_theme_filter", None)
            if filt is not None:
                QApplication.instance().removeEventFilter(filt)
                self._toplevel_theme_filter = None
        except Exception:
            pass
        self._closeEvent_impl(event)

    def _closeEvent_impl(self, event):
        self._close_sandboxed_plugins()
        """
        关闭事件。

        修复说明（P0）：
            - 原实现仅调用 event.accept()，依赖 main.py 中的
              setQuitOnLastWindowClosed(True) 退出事件循环。
            - 这里额外显式调用 QApplication.quit()（双保险），
              以覆盖"关闭主窗口时仍有其他 QDialog/子窗口存活"的
              边缘场景，确保事件循环一定能退出。
        """
        if getattr(self, "_closing", False):
            event.accept()
            return

        self._closing = True

        # 卸载多键序列的应用级按键过滤器
        #
        # ★ 修复（实测访问违例 0xC0000005）：
        #   QApplication 上的事件过滤器若在窗口销毁后仍挂着，
        #   Qt 会在下一次事件派发时调用已析构对象 → 崩溃。
        #   必须在 `_closing` 置位后**立即**卸载（此时过滤器已能安全跳过）。
        try:
            self._teardown_key_sequences()
        except Exception as e:
            logger.debug("卸载按键序列过滤器失败: %s", e)

        # 先停止文件监听并释放 provider 句柄
        #
        # 修复（实测段错误 0xC0000005 / 句柄泄漏）：
        #   `QFileSystemWatcher` 的回调可能在窗口销毁过程中被事件循环触发，
        #   此时弹模态对话框会访问正在析构的 Qt 对象 → 崩溃。
        #   同时每个标签的 provider 持有文件句柄，不释放会在 Windows 上
        #   阻止文件被外部程序修改。见 `TabManager.dispose` 的说明。
        try:
            if hasattr(self.tabs, "dispose"):
                self.tabs.dispose()
        except Exception as e:
            logger.debug("释放 TabManager 资源失败: %s", e)

        try:
            # 检查未保存文件
            modified = []
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if not hasattr(w, "proxy"):
                    continue
                proxy = w.proxy
                if proxy and hasattr(proxy, "is_modified") and proxy.is_modified:
                    fp = None
                    if proxy.document:
                        fp = proxy.document.filepath
                    modified.append(fp or "(未命名)")

            if modified:
                msg = "以下文件有未保存的修改：\n\n" + "\n".join(
                    f"• {os.path.basename(f)}" for f in modified[:10]
                )
                if len(modified) > 10:
                    msg += f"\n... 及其他 {len(modified) - 10} 个文件"
                msg += "\n\n是否放弃所有修改并退出？"

                reply = QMessageBox.question(
                    self,
                    "未保存的修改",
                    msg,
                    QMessageBox.Discard | QMessageBox.Cancel,
                    QMessageBox.Cancel,
                )

                if reply == QMessageBox.Cancel:
                    event.ignore()
                    return

            # 保存会话
            try:
                if self.session and (not self.prefs or self.prefs.get("restore_session", True)):
                    self.session.save(self.tabs, self)
            except Exception:
                pass

            # 停止定时器
            if hasattr(self, "_status_timer"):
                self._status_timer.stop()
            if hasattr(self, "_session_timer"):
                self._session_timer.stop()

            # 停止自动备份定时器（P1 收尾）
            #
            # 与构造处的 `start_autosave()` 配对。虽然定时器停不停都不影响
            # 进程退出，但显式停止能让"最后一次保存"发生在可预期的时刻，
            # 也避免对象析构后回调仍被触发。
            try:
                if self.session is not None:
                    self.session.stop_autosave()
            except Exception as e:
                logging.debug("停止自动备份定时器失败: %s", e)

            # 阶段 2.1（关闭路径收尾）：停止插件后台线程与文件监听。
            #
            # 背景：closeEvent 原先只停两个主窗口定时器就 app.quit()，
            # 而插件可能持有 QThread（如 AI 助手的 Ollama 刷新/拉取线程）
            # 与 QFileSystemWatcher（插件热重载）。Windows 上父进程退出
            # 不会连带清理子进程，且 QThread 在**运行中**被析构时 Qt 会
            # 打印 "QThread: Destroyed while thread is still running"
            # 并可能 qFatal() 导致异常退出。
            #
            # 这里逐个显式收尾，任何一步失败都不影响退出流程。
            self._shutdown_background_work()

            event.accept()

            # 显式退出事件循环（双保险，不依赖 setQuitOnLastWindowClosed）
            try:
                app = QApplication.instance()
                if app is not None:
                    app.quit()
            except Exception as quit_err:
                print(f"[MainWindow] quit() 失败: {quit_err}")

        except Exception as e:
            print(f"[MainWindow] 关闭失败: {e}")
            event.accept()
            # 即使异常也尽力退出事件循环
            try:
                app = QApplication.instance()
                if app is not None:
                    app.quit()
            except Exception:
                pass

    # ========================================================
    # 关闭时的后台资源收尾（阶段 2.1）
    # ========================================================
    def _shutdown_background_work(self, timeout_ms: int = 2000):
        """在退出前显式停止后台线程、插件监听与语言服务器。

        这是对审计报告 F-2 的修复：原先 `closeEvent` 只停两个主窗口
        定时器就 `app.quit()`，导致：

          * 插件持有的 `QThread`（AI 助手 Ollama 刷新/拉取）在运行中被
            析构 → Qt 打印 "QThread: Destroyed while thread is still
            running"，可能 `qFatal()`；
          * 插件热重载的 `QFileSystemWatcher` 未停止；
          * 每份文档的语言服务器子进程未被 kill（Windows 上会变孤儿）。

        所有步骤各自 try/except，任何失败都不阻断退出。
        """
        import time as _time

        # 1. 插件线程 + 面板线程
        try:
            pm = getattr(self, "plugin_manager", None)
            loader = getattr(pm, "loader", None) if pm is not None else None
            specs = getattr(loader, "specs", None) or {}
            for spec in specs.values():
                inst = getattr(spec, "instance", None)
                if inst is None:
                    continue
                # 面板的线程收尾
                panel = getattr(inst, "ollama_panel", None)
                if panel is not None:
                    try:
                        panel._stop_threads(timeout_ms)
                    except Exception:
                        pass
                # 插件自定义的线程收尾钩子（若实现）
                hook = getattr(inst, "shutdown_background", None)
                if callable(hook):
                    try:
                        hook()
                    except Exception:
                        pass
        except Exception:
            pass

        # 2. 插件热重载目录监控
        try:
            pm = getattr(self, "plugin_manager", None)
            loader = getattr(pm, "loader", None) if pm is not None else None
            if loader is not None and hasattr(loader, "stop_watching"):
                loader.stop_watching()
        except Exception:
            pass

        # 3. 各标签的编辑器资源（停 LSP 子进程、停草稿定时器、摘文件监听）
        #    注意：这里不弹"未保存"对话框 —— closeEvent 已经在前面问过了。
        try:
            tabs = getattr(self, "tabs", None)
            if tabs is not None and hasattr(tabs, "count"):
                for i in range(tabs.count()):
                    try:
                        widget = tabs.widget(i)
                        proxy = getattr(widget, "proxy", None)
                        if proxy is not None and hasattr(proxy, "close"):
                            proxy.close()
                    except Exception:
                        pass
        except Exception:
            pass

        # 4. 给事件循环一点时间处理 deleteLater（避免悬空对象告警）
        try:
            app = QApplication.instance()
            if app is not None:
                deadline = _time.time() + (timeout_ms / 1000.0)
                while _time.time() < deadline:
                    app.processEvents()
                    _time.sleep(0.01)
                    break
        except Exception:
            pass
