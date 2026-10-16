# -*- coding: utf-8 -*-
"""
青草编辑器 - 编辑操作 Mixin
============================
从 ui/main_window.py 拆分出来的编辑相关方法。
"""

import datetime


class EditOpsMixin:
    """编辑操作 Mixin —— 由 MainWindow 继承"""

    # 依赖属性: self.tabs

    # ========================================================
    # 编辑操作
    # ========================================================
    def _undo(self):
        """撤销"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy:
                proxy.undo()
        except Exception as e:
            print(f"[MainWindow] 撤销失败: {e}")


    def _redo(self):
        """重做"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy:
                proxy.redo()
        except Exception as e:
            print(f"[MainWindow] 重做失败: {e}")


    def _cut(self):
        """剪切"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.sc:
                proxy.sc.cut()
        except Exception:
            pass


    def _copy(self):
        """复制"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.sc:
                proxy.sc.copy()
        except Exception:
            pass


    def _paste(self):
        """粘贴"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.sc:
                proxy.sc.paste()
        except Exception:
            pass


    def _select_all(self):
        """全选"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.sc:
                proxy.sc.selectAll()
        except Exception:
            pass


    def _duplicate_line(self):
        """复制整行"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and hasattr(proxy, 'duplicate_line'):
                proxy.duplicate_line()
        except Exception as e:
            print(f"[MainWindow] 复制行失败: {e}")


    def _move_line_up(self):
        """上移行"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and hasattr(proxy, 'move_line_up'):
                proxy.move_line_up()
        except Exception as e:
            print(f"[MainWindow] 上移行失败: {e}")


    def _move_line_down(self):
        """下移行"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and hasattr(proxy, 'move_line_down'):
                proxy.move_line_down()
        except Exception as e:
            print(f"[MainWindow] 下移行失败: {e}")


    def _select_next_occurrence(self):
        """选择下一个相同项"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and hasattr(proxy, 'select_next_occurrence'):
                proxy.select_next_occurrence()
        except Exception as e:
            print(f"[MainWindow] 选择下一项失败: {e}")


    def _toggle_comment(self):
        """注释切换"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and hasattr(proxy, 'toggle_line_comment'):
                proxy.toggle_line_comment()
        except Exception as e:
            print(f"[MainWindow] 注释切换失败: {e}")


    def _eval_expression(self):
        """计算表达式"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and hasattr(proxy, 'eval_expression'):
                proxy.eval_expression()
        except Exception as e:
            print(f"[MainWindow] 计算失败: {e}")


    def _insert_datetime(self):
        """插入日期时间"""
        try:
            import datetime
            proxy = self.tabs.current_proxy()
            if proxy and proxy.sc:
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                proxy.sc.insert(ts)
        except Exception as e:
            print(f"[MainWindow] 插入日期失败: {e}")


    def _to_upper(self):
        """转为大写"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.sc:
                text = proxy.sc.selectedText()
                if text:
                    proxy.sc.replaceSelectedText(text.upper())
        except Exception:
            pass


    def _to_lower(self):
        """转为小写"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.sc:
                text = proxy.sc.selectedText()
                if text:
                    proxy.sc.replaceSelectedText(text.lower())
        except Exception:
            pass


    def _auto_complete(self):
        """自动补全"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and hasattr(proxy, 'request_completion'):
                proxy.request_completion()
        except Exception as e:
            print(f"[MainWindow] 自动补全失败: {e}")

    # ========================================================
    # 列编辑器（P0 核心功能）
    # ========================================================
    def _column_editor(self):
        """列编辑器：在矩形选区/多光标/多行上逐行插入文本或递增数字

        对标 Notepad++ 的 `Edit → Column Editor…`。此前该能力
        （`ui/column_editor_dialog.py`）只能从编辑器右键菜单进入，
        这里补上「编辑」菜单入口。
        """
        try:
            proxy = self.tabs.current_proxy()
            if proxy is None:
                self.status_bar.showMessage("没有活动的编辑器", 3000)
                return
            from ui.column_editor_dialog import show_column_editor
            show_column_editor(proxy, self)
        except Exception as e:
            print(f"[MainWindow] 列编辑器失败: {e}")
            try:
                self.status_bar.showMessage(f"列编辑器失败: {e}", 6000)
            except Exception:
                pass

    # ========================================================
    # 书签导航（引擎早已实现、会话已持久化，此前无菜单无快捷键）
    # ========================================================
    def _bookmark_proxy(self):
        """取当前 proxy（书签相关方法的统一前置检查）"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy is None:
                self.status_bar.showMessage("没有活动的编辑器", 3000)
            return proxy
        except Exception:
            return None

    def _toggle_bookmark(self):
        """切换当前行书签"""
        proxy = self._bookmark_proxy()
        if proxy is None:
            return
        try:
            if hasattr(proxy, 'toggle_bookmark'):
                proxy.toggle_bookmark()
            elif hasattr(proxy, 'toggle_breakpoint'):
                # 有些版本把书签/断点合并为一个装订线切换
                proxy.toggle_breakpoint()
            self._update_status_for_editor()
        except Exception as e:
            print(f"[MainWindow] 切换书签失败: {e}")

    def _bookmark_next(self):
        """跳到下一个书签（`core/editor.py` 的引擎此前零入口）"""
        proxy = self._bookmark_proxy()
        if proxy is None:
            return
        try:
            if hasattr(proxy, 'next_bookmark'):
                moved = proxy.next_bookmark()
                if moved is False:
                    self.status_bar.showMessage("没有更多书签", 3000)
        except Exception as e:
            print(f"[MainWindow] 下一个书签失败: {e}")

    def _bookmark_prev(self):
        """跳到上一个书签"""
        proxy = self._bookmark_proxy()
        if proxy is None:
            return
        try:
            if hasattr(proxy, 'prev_bookmark'):
                moved = proxy.prev_bookmark()
                if moved is False:
                    self.status_bar.showMessage("没有更多书签", 3000)
        except Exception as e:
            print(f"[MainWindow] 上一个书签失败: {e}")

    def _bookmark_clear(self):
        """清除所有书签"""
        proxy = self._bookmark_proxy()
        if proxy is None:
            return
        try:
            if hasattr(proxy, 'clear_bookmarks'):
                proxy.clear_bookmarks()
                self.status_bar.showMessage("已清除所有书签", 3000)
        except Exception as e:
            print(f"[MainWindow] 清除书签失败: {e}")

    # ========================================================
    # 对比合并（P0 核心功能）
    # ========================================================
    def _show_file_diff(self):
        """对比两个文件（工具菜单）

        先让用户选 A/B 两个文件（`FileDiffDialog.pick_files` 内部完成），
        再打开并排双栏 diff 对话框。

        注意：**不绑快捷键** —— `Ctrl+Alt+D` 已被"插入日期时间"占用，
        且有 `tests/test_shortcuts.py` 的重复扫描保护。
        """
        try:
            from ui.file_merge_dialog import FileDiffDialog
            dlg = FileDiffDialog.pick_files(parent=self)
            if dlg is None:
                return
            result = dlg.exec_()
            try:
                if result == dlg.Accepted and getattr(dlg, 'action', '') \
                        == 'save':
                    self.status_bar.showMessage("对比结果已保存", 3000)
            except Exception:
                pass
        except Exception as e:
            print(f"[MainWindow] 对比文件失败: {e}")
            try:
                self._show_error("对比文件失败", str(e))
            except Exception:
                pass

    # ========================================================
    # 代码格式化（P0-4：接线此前零引用的 core/formatter.py）
    # ========================================================
    def _format_document(self, formatter_name: str = ""):
        """格式化当前文件

        为什么需要（P0-4）：
            `core/formatter.py` 早已实现 Black / Autopep8 / Clang-Format
            三个**真实**格式化器（会真的调用对应子进程），并带注册表
            （按语言挑可用者），但**全仓零生产引用** —— 用户完全用不到。

            而现有的"LSP 格式化"依赖用户自己装好语言服务器（LSP 默认
            关闭），离线/未装服务器的场景**完全没有兜底**。本地格式化器
            正好补上这个缺口。

        实现要点：
            1. 语言从 `document.meta.language` 推断（formatter 注册表按
               language 匹配）；
            2. 格式化在**当前文本**上进行，结果写回编辑器；
            3. 写回后必须能**一次撤销回退**（见下）；
            4. 失败/无可用格式化器时给出**明确原因**，不静默失败。

        撤销说明（重要）：
            写回用 `EditorProxy.set_text()`，它会触发 SCN_MODIFIED，
            由自研 `UndoManager` 记录成可撤销命令 —— 因此格式化后
            Ctrl+Z 即可回到格式化前的全文。
        """
        try:
            proxy = self.tabs.current_proxy()
            if proxy is None:
                self.status_bar.showMessage("没有活动的编辑器", 3000)
                return False

            from core.formatter import get_formatter_registry

            registry = get_formatter_registry()
            available = registry.list_available()
            if not available:
                self.status_bar.showMessage(
                    "没有可用的本地格式化器：请先安装 black / autopep8 "
                    "或 clang-format（pip install black 等）", 8000
                )
                return False

            text = proxy.get_text()
            if not text.strip():
                self.status_bar.showMessage("文件为空，无需格式化", 3000)
                return False

            language = "python"
            filepath = ""
            try:
                doc = proxy.document
                language = getattr(doc.meta, "language", "python") or "python"
                filepath = doc.filepath or ""
            except Exception:
                pass

            ok, result = registry.format(
                text, language=language,
                filepath=filepath, formatter_name=formatter_name,
            )
            if not ok:
                self.status_bar.showMessage(
                    f"格式化失败: {result}", 8000
                )
                return False

            if result == text:
                self.status_bar.showMessage("已经是格式化后的状态", 4000)
                return True

            # 写回 —— 必须是**一条**原子撤销命令。
            #
            # 为什么不用 `proxy.set_text()`（实测教训）：
            #   `set_text()` 内部是 `sc.setText()`，它触发的 SCN_MODIFIED 会被
            #   自研 `UndoManager` 记成**多条**命令（实测撤销栈深度 2）。
            #   于是用户按一次 Ctrl+Z 只回退了其中一条 —— 实测直接把内容
            #   清空（原始 'x=1\ny = 2\n' 变成 ''），**比不格式化更糟**。
            #
            #   改用 `CompoundCmd`（带显式逆操作），把"整段替换"表达为
            #   单个命令：undo 恢复格式化前的全文，redo 恢复格式化后的全文。
            #   （与宏回放的整体回滚命令同一机制。）
            self._replace_all_text_atomic(proxy, result)

            try:
                proxy.sc.setModified(True)
            except Exception:
                pass

            self._update_status_for_editor()
            self.status_bar.showMessage("已格式化当前文件", 4000)
            return True
        except Exception as e:
            print(f"[MainWindow] 格式化失败: {e}")
            try:
                self.status_bar.showMessage(f"格式化失败: {e}", 8000)
            except Exception:
                pass
            return False

    @staticmethod
    def _replace_all_text_atomic(proxy, new_text: str):
        """把编辑器全文替换为 `new_text`，并记为**一条**可撤销命令

        见 `_format_document` 里"为什么不用 set_text"的说明。
        """
        from core.commands import CompoundCmd

        sc = proxy.sc
        old_text = sc.text()

        def _set(text):
            def _fn(target):
                try:
                    target.setText(text)
                except Exception:
                    try:
                        target.SendScintilla(
                            target.SCI_SETTEXT, 0, text.encode("utf-8")
                        )
                    except Exception:
                        pass
            return _fn

        cmd = CompoundCmd(
            forward_fn=_set(new_text),
            backward_fn=_set(old_text),
            pos=0,
            description="格式化文档",
        )
        # 直接写入缓冲区，并用 _restoring 抑制 SCN_MODIFIED，
        # 避免这次替换被记成多条命令（否则一次 Ctrl+Z 只能回退一半）。
        try:
            proxy._restoring = True
            try:
                sc.SendScintilla(sc.SCI_BEGINUNDOACTION)
                cmd.execute(sc)
                sc.SendScintilla(sc.SCI_ENDUNDOACTION)
            finally:
                proxy._restoring = False
        except Exception:
            cmd.execute(sc)
        try:
            proxy.undo_manager.record(cmd)
        except Exception:
            pass

    def _format_document_with(self):
        """让用户选择用哪个格式化器（列出本机可用的）"""
        try:
            from PyQt5.QtWidgets import QInputDialog

            from core.formatter import get_formatter_registry

            registry = get_formatter_registry()
            available = registry.list_available()
            if not available:
                self.status_bar.showMessage(
                    "没有可用的本地格式化器：请先安装 black / autopep8 "
                    "或 clang-format", 8000
                )
                return
            names = [f.name for f in available]
            if len(names) == 1:
                self._format_document(names[0])
                return
            name, ok = QInputDialog.getItem(
                self, "选择格式化器", "使用:", names, 0, False
            )
            if ok and name:
                self._format_document(name)
        except Exception as e:
            print(f"[MainWindow] 选择格式化器失败: {e}")
