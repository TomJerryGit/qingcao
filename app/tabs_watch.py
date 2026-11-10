# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""文件监视/内存回收职责（v2.24 拆出）。"""
from app.tabs_common import *  # noqa: F401,F403,F405


class TabFileWatchMixin:
    def _setup_file_watcher(self, filepath: str, editor):
        """为文件设置外部修改监听"""
        if filepath in self._file_watchers:
            return

        try:
            watcher = QFileSystemWatcher(self)
            watcher.addPath(filepath)
            watcher.fileChanged.connect(
                lambda path, w=editor: self._on_file_changed(path, w)
            )
            self._file_watchers[filepath] = watcher
            self._watcher_paths[filepath] = editor
        except Exception as e:
            print(f"[TabManager] 设置文件监听失败: {e}")

    def _remove_file_watcher(self, filepath: str):
        """移除文件监听"""
        if filepath in self._file_watchers:
            try:
                watcher = self._file_watchers.pop(filepath)
                watcher.deleteLater()
            except Exception:
                pass
        self._watcher_paths.pop(filepath, None)

    def _on_file_changed(self, filepath: str, editor):
        """文件外部修改回调"""
        try:
            # 关闭/销毁过程中不再弹任何对话框
            #
            # 缺陷背景（实测段错误 0xC0000005）：
            #   `QFileSystemWatcher` 的回调可能在**窗口销毁过程中**被事件
            #   循环触发。此时弹出模态 `QMessageBox` 会访问正在析构的
            #   Qt 对象 → 段错误。
            #
            #   实测：pytest teardown 阶段 `_process_events()` 触发本回调，
            #   faulthandler 明确指向下面的 `QMessageBox.question`。
            #   真实场景同理（关闭主窗口时外部程序恰好改了文件）。
            if self._shutting_down:
                return

            # 防止**重入**：本回调会弹出模态对话框（`QMessageBox.question`），
            # 而模态对话框自己会跑事件循环 —— 期间文件监听可能**再次**触发
            # 本回调，形成递归重入（每个嵌套层都新建对话框/重载文件）。
            # 实测这会在窗口销毁阶段演变成段错误（0xC0000005）。
            if self._handling_file_change:
                return
            self._handling_file_change = True
            try:
                self._handle_file_change(filepath, editor)
            finally:
                self._handling_file_change = False

        except Exception as e:
            print(f"[TabManager] 文件修改处理失败: {e}")

    def _handle_file_change(self, filepath: str, editor):
        """`_on_file_changed` 的实际处理（已由外层做好守卫）"""
        try:
            # 文件可能被删除
            if not os.path.exists(filepath):
                self._show_status(
                    f"文件已被删除: {os.path.basename(filepath)}",
                    5000, "warning"
                )
                return

            # 文件可能被重命名，重新添加监听
            if filepath not in self._file_watchers:
                return
            watcher = self._file_watchers[filepath]
            if filepath not in watcher.files():
                try:
                    watcher.addPath(filepath)
                except Exception:
                    pass

            # 检查编辑器是否已修改（避免覆盖用户修改）
            is_modified = False
            try:
                if hasattr(editor, 'proxy') and editor.proxy:
                    is_modified = getattr(
                        editor.proxy, 'is_modified', False
                    )
            except Exception:
                pass

            if is_modified:
                # 用户有未保存修改，提示
                self._show_status(
                    f"文件已被外部修改，但你有未保存的修改: "
                    f"{os.path.basename(filepath)}",
                    5000, "warning"
                )
                return

            # 请求重新加载 —— 通过**信号**交给主窗口，而不是在这里直接弹
            # 模态对话框。
            #
            # 修复（实测段错误 0xC0000005）：
            #   本方法是 `QFileSystemWatcher` 的回调。在回调里执行
            #   `QMessageBox.question`（模态，自己跑事件循环）是明确的
            #   反模式：它会重入事件循环，可能在窗口销毁过程中再次触发
            #   文件回调，并访问正在析构的 Qt 对象。
            #
            #   faulthandler 已明确指向这里的 `QMessageBox.question`
            #   （pytest teardown 的 `_process_events()` 恰好触发了 watcher）。
            #   交给主窗口后，对话框在正常的事件循环层级弹出，不再重入。
            self.file_changed_externally.emit(filepath)

        except Exception as e:
            print(f"[TabManager] 文件修改处理失败: {e}")

    def _reload_file(self, filepath: str, editor):
        """重新加载文件内容

        修复（两条审计用例）：
          * **INV-D 撤销栈失效**：重载后内容被整体替换，但 `undo_manager`
            仍保留针对**旧内容位置**的撤销命令 —— 用户按 Ctrl+Z 会把命令
            施加到新内容上，产生错乱的编辑甚至破坏文件。现在必须清空
            撤销栈（与 `_on_document_reloaded` 的做法一致）。
          * **句柄/mmap 泄漏**：原来直接用新 provider 覆盖
            `document.provider`，**从不 close 旧的** —— 旧的 mmap 与文件
            句柄一直持有，在 Windows 上会锁住文件导致外部程序写入失败
            （这正是"外部变更"场景本身）。现在先关闭旧 provider。
          * 顺带：`editor.clear()` / `append()` 是程序行为，需用
            `_restoring` 抑制，避免被当成用户编辑记进撤销栈并置脏。
        """
        try:
            cursor_pos = 0
            first_line = 0

            proxy = None
            try:
                if hasattr(editor, 'proxy') and editor.proxy:
                    proxy = editor.proxy
                    cursor_pos = proxy.get_current_pos()
                first_line = editor.SendScintilla(
                    editor.SCI_GETFIRSTVISIBLELINE
                )
            except Exception:
                pass

            # 重新打开文件
            provider = LocalFileProvider()
            provider.open(filepath)

            # 替换 provider，并**释放旧的**（否则 mmap/句柄泄漏）
            try:
                if proxy is not None and proxy.document:
                    old_provider = proxy.document.provider
                    proxy.document.provider = provider
                    if old_provider is not None and old_provider is not provider:
                        try:
                            old_provider.close()
                        except Exception as e:
                            logger.debug("关闭旧 provider 失败: %s", e)
            except Exception as e:
                logger.debug("替换 provider 失败: %s", e)

            # 程序性替换内容：抑制 SCN_MODIFIED 回调
            suppress = proxy is not None and hasattr(proxy, '_restoring')
            if suppress:
                proxy._restoring = True
            try:
                editor.clear()
                for i in range(provider.total_blocks):
                    data = provider.read_block(i)
                    editor.append(data.decode(provider.encoding,
                                              errors='replace'))

                # 恢复位置
                try:
                    max_pos = editor.SendScintilla(editor.SCI_GETLENGTH)
                    editor.SendScintilla(
                        editor.SCI_GOTOPOS, min(cursor_pos, max_pos)
                    )
                    editor.SendScintilla(
                        editor.SCI_SETFIRSTVISIBLELINE, first_line
                    )
                except Exception:
                    pass
            finally:
                if suppress:
                    proxy._restoring = False

            # 释放映射/句柄：Windows 上映射会阻止外部程序覆盖该文件，
            # 而本模块的职责正是"外部变更检测"。内容已读入编辑器，
            # 后续需要时会由 `_ensure_handle()` 按需重建。
            self._dispose_provider(provider)

            # 重置修改状态，并清空撤销栈
            #
            # 重载等于"文件被整体替换"，旧的撤销命令位置对新内容全部失效。
            try:
                editor.setModified(False)
                if proxy is not None:
                    proxy._modified = False
                    try:
                        if getattr(proxy, 'undo_manager', None) is not None:
                            proxy.undo_manager.clear()
                    except Exception:
                        pass
                    try:
                        editor.SendScintilla(
                            editor.SCI_EMPTYUNDOBUFFER
                        )
                    except Exception:
                        pass
                    try:
                        proxy.modified_changed.emit(False)
                    except Exception:
                        pass
            except Exception:
                pass

            self._update_tab_title(editor)

            self._show_status(
                f"已重新加载: {os.path.basename(filepath)}"
            )

        except Exception as e:
            self._show_status(f"重新加载失败: {e}", 3000, "error")

    # ========================================================
    # 后台标签资源释放
    # ========================================================

    def _check_idle_tabs(self):
        """检查并释放长时间闲置的后台标签内容"""
        now = QDateTime.currentDateTime()
        current_index = self.currentIndex()

        for i in range(self.count()):
            if i == current_index:
                continue

            widget = self.widget(i)
            if not widget:
                continue

            # 检查是否已释放
            if widget in self._released_content:
                continue

            # 检查最后活动时间
            last_active = self._last_active.get(widget)
            if last_active is None:
                self._last_active[widget] = now
                continue

            elapsed = last_active.secsTo(now)
            if elapsed > IDLE_RELEASE_MINUTES * 60:
                self._release_tab_content(widget)

    def _release_provider_handles(self, filepath: str):
        """释放指向该文件的 provider 映射/句柄（允许外部程序写入）

        为什么需要（Windows 文件锁定，已实测）：
            即使**只读**的内存映射也会阻止另一进程覆盖写该文件 ——
            `open(path, 'w')` 抛 `OSError: [Errno 22] Invalid argument`。
            于是编辑器一打开文件，git / 构建工具 / 其它编辑器就再也改不了
            它，而"外部变更检测 / 三方合并"因此永远不会触发。

        ⚠️ 为什么**不**用 `gc.get_objects()` 扫描（重要教训）：
            最初的实现靠遍历全堆对象来找出指向该文件的 provider。
            在 Qt 进程里这会导致**段错误**（退出码 0xC0000005）：
            遍历数十万个对象并与 Qt 的对象生命周期/GC 交织，是明确不安全
            的行为（实测：命令行单独跑可通过，pytest 中必崩，且与
            `release_mmap` 内部逻辑无关 —— 把它改成 no-op 仍然崩）。

            现在只处理调用方**明确持有**的目标 provider，不做任何堆扫描。
        """
        return

    def _dispose_provider(self, provider):
        """安全释放一个 provider 的映射与句柄（只影响这一个对象）"""
        if provider is None:
            return
        try:
            if hasattr(provider, 'release_mmap'):
                provider.release_mmap()
        except Exception as e:
            logger.debug("释放 provider 句柄失败: %s", e)

    def _restore_released_content(self, widget) -> bool:
        """恢复被内存回收释放的标签内容（返回是否发生了恢复）

        与 `_release_tab_content` 对称。设为独立方法的原因：
          * 切回标签（`_on_current_changed`）与"保存前需要内容"等场景
            都要用它，避免逻辑分叉；
          * 可被测试直接调用，测到的是**生产代码**而不是照抄一遍。

        关键点：`setText()` 会触发 SCN_MODIFIED，必须用 `_restoring`
        抑制 `_on_scintilla_modified` —— 否则恢复动作本身被当成用户编辑，
        标签会显示 '*'（内容其实与磁盘一致），退出时还会被问"是否保存"。
        """
        if widget is None or widget not in self._released_content:
            return False
        try:
            proxy = getattr(widget, 'proxy', None)
            suppress = proxy is not None and hasattr(proxy, '_restoring')
            if suppress:
                proxy._restoring = True
            try:
                widget.setText(self._released_content.pop(widget))
                if proxy is not None:
                    try:
                        proxy._modified = False
                        proxy.sc.setModified(False)
                    except Exception:
                        pass
            finally:
                if suppress:
                    proxy._restoring = False
            return True
        except Exception as e:
            print(f"[TabManager] 恢复标签内容失败: {e}")
            return False

    def _release_tab_content(self, widget):
        """释放标签的文本内容（保留元数据）"""
        try:
            # 检查是否已修改
            is_modified = False
            try:
                if hasattr(widget, 'proxy') and widget.proxy:
                    is_modified = getattr(
                        widget.proxy, 'is_modified', False
                    )
            except Exception:
                pass

            if is_modified:
                return

            # 内容太短不释放
            text = widget.text()
            if len(text) < 1000:
                return

            # 缓存内容的**权威版本**
            #
            # 修复（审计用例 test_save_all_after_release...）：
            #   `widget.text()` 是 Scintilla 归一化后的文本 —— 它会把 CRLF
            #   也报告为 `\n`（或按 eolMode 归一），与磁盘上的原始字节**不
            #   完全一致**。若直接把 `widget.text()` 当作缓存并在切回时
            #   `setText` 回去，就会**改写文件的行尾**（实测：原文 `\n`
            #   变成 `\r\n`）。
            #
            #   这里在释放前先把 provider（其内容来自磁盘）同步为当前
            #   缓冲区，再以 provider 的文本作为缓存 —— 保证"释放→恢复"
            #   是**无损**的。
            proxy = getattr(widget, 'proxy', None)
            cached = text
            try:
                if proxy is not None:
                    proxy._sync_content_to_provider(text)
                    provider = getattr(proxy.document, 'provider', None)
                    if provider is not None:
                        pt = provider.read_text()
                        if pt:
                            cached = pt
            except Exception:
                cached = text

            # 缓存内容
            self._released_content[widget] = cached

            # 清空编辑器
            #
            # 修复（审计用例 TestIdleReleaseVsSave，两条）：
            #   `widget.clear()` 会触发 SCN_MODIFIED，而
            #   `_on_scintilla_modified` 把它当成**用户编辑** —— 于是：
            #     1) 记入撤销栈（用户按 Ctrl+Z 会看到莫名其妙的"清空"）
            #     2) `proxy._modified` 被置 True → 标签页显示 '*'
            #     3) 自动保存为这个"已修改"的空内容生成备份
            #     4) 关窗时弹出"是否保存"的假警告
            #
            #   这是程序自身发起的变更，必须用 `_restoring` 抑制回调
            #   （与 `_on_document_reloaded` 等处的做法一致），
            #   并在之后把"是否有未保存修改"的语义恢复为清空前的值。
            suppress = proxy is not None and hasattr(proxy, '_restoring')
            if suppress:
                proxy._restoring = True
            try:
                widget.clear()
                if proxy is not None:
                    try:
                        proxy._modified = False
                        proxy.sc.setModified(False)
                    except Exception:
                        pass
            finally:
                if suppress:
                    proxy._restoring = False

            # 记录日志
            fp = "未命名"
            try:
                if hasattr(widget, 'proxy') and widget.proxy:
                    fp = self._get_proxy_filepath(widget.proxy) or "未命名"
            except Exception:
                pass

            print(f"[TabManager] 已释放后台标签内容: "
                  f"{os.path.basename(fp)} ({len(text)} 字符)")
        except Exception as e:
            print(f"[TabManager] 释放标签内容失败: {e}")

    def force_release_idle(self):
        """强制释放所有符合条件的闲置标签"""
        self._check_idle_tabs()

    def get_memory_usage(self) -> Dict[str, Any]:
        """获取标签内存使用情况"""
        total_chars = 0
        released_count = 0

        for i in range(self.count()):
            widget = self.widget(i)
            if not widget:
                continue
            if widget in self._released_content:
                released_count += 1
            else:
                try:
                    total_chars += len(widget.text())
                except Exception:
                    pass

        return {
            'tab_count': self.count(),
            'total_chars': total_chars,
            'released_count': released_count,
            'closed_history': len(self._closed_tabs),
        }

    # ========================================================
    # 状态提示
    # ========================================================
