# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""标签打开/关闭职责（v2.24 拆出）。"""
from app.tabs_common import *  # noqa: F401,F403,F405


class TabOpenCloseMixin:
    def add_tab(self, title: str = "未命名") -> Optional[Any]:
        """
        新增一个空白标签。

        参数:
            title: 标签标题

        返回:
            EditorWidget 实例（或 None 表示失败）
        """
        try:
            from ui.editor_view import EditorWidget

            editor = EditorWidget()
            index = self.addTab(editor, title)
            self.setCurrentIndex(index)
            self._editors.append(editor)

            # 连接脏状态信号（兼容 modified_changed 和 mod_state）
            try:
                if hasattr(editor.proxy, 'modified_changed'):
                    editor.proxy.modified_changed.connect(
                        lambda modified, w=editor: self._update_tab_title(w)
                    )
                elif hasattr(editor.proxy, 'mod_state'):
                    editor.proxy.mod_state.connect(
                        lambda modified, w=editor: self._update_tab_title(w)
                    )
            except Exception:
                pass

            # 记录活动时间
            self._last_active[editor] = QDateTime.currentDateTime()

            # 发射事件
            self.tab_opened.emit(index)
            try:
                bus.emit_event(TabAddedEvent(index=index, title=title))
            except Exception:
                pass

            return editor
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[TabManager] add_tab 失败: {e}")
            return None

    # ========================================================
    # 打开文件
    # ========================================================

    def open_file(self, filepath: str, line: int = 0) -> Optional[Any]:
        """
        打开一个文件到新标签。

        如果文件已打开，则激活现有标签。

        参数:
            filepath: 文件路径
            line: 跳转到的行号（从 0 开始，可选）

        返回:
            EditorProxy 实例或 None
        """
        try:
            filepath = os.path.abspath(filepath)

            # 检查是否已打开
            existing = self.find_tab_by_path(filepath)
            if existing is not None:
                self.setCurrentIndex(existing)
                if line > 0:
                    editor = self.widget(existing)
                    try:
                        editor.SendScintilla(editor.SCI_GOTOLINE, line)
                        editor.setFocus()
                    except Exception:
                        pass
                return self.widget(existing).proxy

            # 检查文件是否存在
            if not os.path.exists(filepath):
                QMessageBox.warning(
                    self, "文件不存在",
                    f"文件不存在：\n{filepath}"
                )
                return None

            if not os.path.isfile(filepath):
                QMessageBox.warning(
                    self, "无法打开",
                    f"路径不是文件：\n{filepath}"
                )
                return None

            # 检查是否二进制文件
            #
            # ★ 修复（混合场景压测实测发现）：
            #   原实现是 `if b'\x00' in chunk` → 判定二进制并弹
            #   「文件可能包含二进制内容，确定要打开吗？」。
            #   但 **UTF-16/UTF-32 文本必然含 NUL 字节**
            #   （ASCII 字符在 UTF-16 里是 `61 00`，换行是 `0A 00`）。
            #   实测：一个正常的 UTF-16 文本被拦下来询问，
            #   用户选「否」后**根本无法打开**。
            #
            #   现在改用 `is_binary_sample()`：有文本 BOM / 可严格 UTF-8 解码 /
            #   像无 BOM 的 UTF-16（NUL 集中在单侧且可打印比例高）都判为文本；
            #   只有 NUL 比例 > 5% 这类才判二进制。
            try:
                with open(filepath, 'rb') as f:
                    chunk = f.read(1024)
                if is_binary_sample(chunk) and not filepath.lower().endswith(
                    ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico',
                     '.pdf', '.zip', '.tar', '.gz', '.exe', '.dll',
                     '.so', '.dylib')
                ):
                    ret = QMessageBox.question(
                        self, "二进制文件",
                        f"文件可能包含二进制内容，确定要打开吗？\n"
                        f"{os.path.basename(filepath)}",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if ret != QMessageBox.Yes:
                        return None
            except PermissionError:
                QMessageBox.warning(
                    self, "权限不足",
                    f"没有权限读取文件：\n{filepath}"
                )
                return None
            except Exception as e:
                QMessageBox.warning(self, "打开失败", str(e))
                return None

            # 创建 EditorWidget
            try:
                from ui.editor_view import EditorWidget

                provider = LocalFileProvider()
                provider.open(filepath)

                editor = EditorWidget(provider=provider)

                # 大文件模式：加载前关闭折叠/彩虹缩进等高开销特性（v2.17）
                try:
                    from core.large_file import apply_large_file_mode, is_huge_file, is_large_file
                    if is_large_file(filepath):
                        apply_large_file_mode(
                            editor, huge=is_huge_file(filepath))
                except Exception:
                    pass

                # 打开文件（加载内容）
                try:
                    editor.proxy.open_file(filepath)
                except Exception as e:
                    print(f"[TabManager] open_file 加载内容失败: {e}")

                # 释放该文件的映射/句柄
                #
                # 为什么（Windows 文件锁定，实测确认）：
                #   即使**只读** mmap 也会阻止另一进程覆盖写该文件
                #   （`open(path,'w')` 报 `OSError: [Errno 22]`）。
                #   于是"编辑器打开着文件"就足以让 git / 构建工具 / 其它
                #   编辑器无法修改它 —— 外部变更检测与三方合并永远不会
                #   触发，而这正是本模块要支持的核心场景。
                #
                #   只释放**这个标签自己的** provider（不做全堆扫描，
                #   原因见 `_release_provider_handles` 的说明）。
                #   内容已加载进编辑器，后续需要时会由 `_ensure_handle()`
                #   按需重建句柄，因此释放不影响功能。
                try:
                    self._dispose_provider(
                        getattr(editor.proxy.document, 'provider', None)
                    )
                except Exception:
                    pass

                # 设置语法高亮
                if hasattr(editor, 'set_lexer_by_filename'):
                    try:
                        editor.set_lexer_by_filename(filepath)
                    except Exception as e:
                        print(f"[TabManager] 设置语法高亮失败: {e}")

                title = os.path.basename(filepath)
                index = self.addTab(editor, title)
                self.setCurrentIndex(index)
                self._editors.append(editor)

                # 连接脏状态信号
                try:
                    if hasattr(editor.proxy, 'modified_changed'):
                        editor.proxy.modified_changed.connect(
                            lambda modified, w=editor:
                            self._update_tab_title(w)
                        )
                    elif hasattr(editor.proxy, 'mod_state'):
                        editor.proxy.mod_state.connect(
                            lambda modified, w=editor:
                            self._update_tab_title(w)
                        )
                except Exception:
                    pass

                # 记录活动时间
                self._last_active[editor] = QDateTime.currentDateTime()

                # 跳转到指定行
                if line > 0:
                    try:
                        editor.SendScintilla(editor.SCI_GOTOLINE, line)
                    except Exception:
                        pass

                # 应用文件类型颜色
                self._apply_file_type_color(index, filepath)

                # 应用 Git 状态颜色
                try:
                    self._update_git_status(index, filepath)
                except Exception:
                    pass

                # 设置文件监听
                self._setup_file_watcher(filepath, editor)

                # 检查只读
                try:
                    if not os.access(filepath, os.W_OK):
                        editor.setReadOnly(True)
                except Exception:
                    pass

                # 更新标签标题（处理只读锁图标）
                self._update_tab_title(editor)

                # 发射事件
                self.tab_opened.emit(index)
                try:
                    size = os.path.getsize(filepath)
                    bus.emit_event(FileOpenedEvent(
                        path=filepath,
                        size=size,
                        encoding=provider.encoding,
                        is_readonly=not os.access(filepath, os.W_OK)
                    ))
                    bus.emit_event(TabAddedEvent(
                        index=index, title=title, filepath=filepath
                    ))
                except Exception:
                    pass

                return editor.proxy

            except Exception as e:
                import traceback
                traceback.print_exc()
                QMessageBox.critical(
                    self, "打开文件失败",
                    f"无法打开文件：\n{filepath}\n\n错误：{e}"
                )
                return None

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[TabManager] open_file 异常: {e}")
            return None

    def open_files(self, filepaths: List[str]) -> int:
        """
        批量打开多个文件。

        返回:
            成功打开的数量
        """
        count = 0
        for path in filepaths:
            if self.open_file(path):
                count += 1
        return count

    # ========================================================
    # 关闭标签
    # ========================================================

    def close_tab(self, index: int) -> bool:
        """
        关闭指定标签。

        参数:
            index: 标签索引

        返回:
            是否真正关闭（用户可能取消）
        """
        if index < 0 or index >= self.count():
            return False

        widget = self.widget(index)
        if not widget:
            return False

        # 检查是否有 proxy
        if not hasattr(widget, 'proxy'):
            # 无 proxy，直接移除
            self.removeTab(index)
            if widget in self._editors:
                self._editors.remove(widget)
            widget.deleteLater()
            return True

        proxy = widget.proxy

        # 检查是否有未保存的修改
        try:
            is_modified = getattr(proxy, 'is_modified', False)
            if is_modified:
                title = self.tabText(index)
                ret = QMessageBox.question(
                    self, "未保存的修改",
                    f"文件 {title} 已修改，是否保存？",
                    QMessageBox.Save | QMessageBox.Discard |
                    QMessageBox.Cancel,
                    QMessageBox.Save
                )

                if ret == QMessageBox.Save:
                    try:
                        proxy.save_file()
                        if proxy.is_modified:
                            # 保存失败或用户取消
                            return False
                    except Exception as e:
                        QMessageBox.critical(
                            self, "保存失败", str(e)
                        )
                        return False
                elif ret == QMessageBox.Cancel:
                    return False
        except Exception as e:
            print(f"[TabManager] 检查修改状态失败: {e}")

        # 收集关闭信息
        # 使用辅助方法统一提取（兼容新旧 API）
        filepath = self._get_proxy_filepath(proxy)
        encoding = self._get_proxy_encoding(proxy)
        cursor_pos = 0
        first_line = 0

        try:
            if hasattr(proxy, 'get_current_pos'):
                cursor_pos = proxy.get_current_pos()
            if hasattr(widget, 'SendScintilla'):
                first_line = widget.SendScintilla(
                    widget.SCI_GETFIRSTVISIBLELINE
                )
        except Exception as e:
            print(f"[TabManager] 收集关闭信息失败: {e}")

        # 收集书签与折叠状态（P1-4 修复：之前遗漏，导致恢复时丢失）
        bookmarks: List[int] = []
        folded_lines: List[int] = []
        try:
            if hasattr(proxy, 'document') and proxy.document:
                if hasattr(proxy.document, 'get_bookmarks'):
                    bookmarks = list(proxy.document.get_bookmarks())
                if hasattr(proxy.document, 'get_folded_lines'):
                    folded_lines = list(proxy.document.get_folded_lines())
        except Exception as e:
            print(f"[TabManager] 收集书签/折叠失败: {e}")

        info = {
            'filepath': filepath,
            'cursor_pos': cursor_pos,
            'first_line': first_line,
            'title': self.tabText(index),
            'encoding': encoding,
            'bookmarks': bookmarks,
            'folded_lines': folded_lines,
        }

        self._closed_tabs.append(info)
        if len(self._closed_tabs) > MAX_CLOSED_TABS:
            self._closed_tabs.pop(0)

        # 移除文件监听
        if filepath:
            self._remove_file_watcher(filepath)

        # 先中止大文件延迟分块加载（必须在 deleteLater 之前）
        #
        # ★ 修复（真实 UI 压测复现的段错误 0xC0000005）：
        #   大文件（>10MB）靠 `QTimer.singleShot(0, proxy._load_chunk_slice)`
        #   续跑。若用户在加载完成前关掉**单个标签**，Qt 销毁 QScintilla
        #   控件后，已排队的回调仍会执行 `self.sc.append(...)`
        #   → 作用在已销毁的 C++ 对象上 → 段错误。
        #   与 `dispose()` 里的处理同源，这里覆盖"只关一个标签"的路径。
        try:
            abort = getattr(proxy, 'abort_loading', None)
            if callable(abort):
                abort()
        except Exception:
            pass

        # 清理资源
        try:
            if hasattr(proxy, 'close'):
                proxy.close()
        except Exception:
            pass

        # 移除标签
        self.removeTab(index)
        if widget in self._editors:
            self._editors.remove(widget)
        self._last_active.pop(widget, None)
        self._released_content.pop(widget, None)

        try:
            widget.deleteLater()
        except Exception:
            pass

        # 发射事件
        self.tab_closed.emit(index)
        try:
            bus.emit_event(FileClosedEvent(path=filepath or ""))
            bus.emit_event(TabRemovedEvent(index=index))
        except Exception:
            pass

        # 检查是否所有标签都关闭
        if self.count() == 0:
            self.all_tabs_closed.emit()

        return True

    def close_all_tabs(self) -> bool:
        """
        关闭所有标签。

        返回:
            是否全部关闭（用户可能取消）
        """
        for i in range(self.count() - 1, -1, -1):
            if not self.close_tab(i):
                return False
        return True

    def close_other_tabs(self, keep_index: int):
        """关闭除指定索引外的所有标签"""
        for i in range(self.count() - 1, -1, -1):
            if i != keep_index:
                self.close_tab(i)

    def close_tabs_to_right(self, from_index: int):
        """关闭指定索引右侧的所有标签"""
        for i in range(self.count() - 1, from_index, -1):
            self.close_tab(i)

    def close_tabs_to_left(self, from_index: int):
        """关闭指定索引左侧的所有标签"""
        for i in range(from_index - 1, -1, -1):
            self.close_tab(i)

    # ========================================================
    # 恢复关闭的标签
    # ========================================================

    def restore_closed_tab(self) -> bool:
        """
        恢复最近关闭的标签。

        修复说明（P1-4）:
            - 增加书签和折叠状态的恢复。
            - 之前在 close_tab 中未收集，导致恢复时丢失。

        返回:
            是否成功恢复
        """
        if not self._closed_tabs:
            return False

        info = self._closed_tabs.pop()
        filepath = info.get('filepath')

        if not filepath or not os.path.exists(filepath):
            # 文件不存在，跳过
            if self._closed_tabs:
                return self.restore_closed_tab()
            return False

        proxy = self.open_file(filepath)
        if proxy is None:
            return False

        # 恢复光标和滚动
        try:
            cursor_pos = info.get('cursor_pos', 0)
            if cursor_pos > 0:
                max_pos = proxy.sc.SendScintilla(
                    proxy.sc.SCI_GETLENGTH
                )
                proxy.sc.SendScintilla(
                    proxy.sc.SCI_GOTOPOS, min(cursor_pos, max_pos)
                )
        except Exception:
            pass

        try:
            first_line = info.get('first_line', 0)
            if first_line > 0:
                proxy.sc.SendScintilla(
                    proxy.sc.SCI_SETFIRSTVISIBLELINE, first_line
                )
        except Exception:
            pass

        # 恢复书签（P1-4 修复）
        try:
            bookmarks = info.get('bookmarks', []) or []
            for line in bookmarks:
                try:
                    # Scintilla 标记号 0 为书签（与 EditorWidget 中定义一致）
                    proxy.sc.markerAdd(line, 0)
                    # 同步到 document
                    if hasattr(proxy, 'document') and proxy.document:
                        if hasattr(proxy.document, 'add_bookmark'):
                            proxy.document.add_bookmark(line)
                except Exception:
                    continue
        except Exception as e:
            print(f"[TabManager] 恢复书签失败: {e}")

        # 恢复折叠状态（P1-4 修复）
        try:
            folded_lines = info.get('folded_lines', []) or []
            for line in folded_lines:
                try:
                    proxy.sc.SendScintilla(
                        proxy.sc.SCI_TOGGLEFOLD, line
                    )
                    # 同步到 document
                    if hasattr(proxy, 'document') and proxy.document:
                        if hasattr(proxy.document, 'add_fold'):
                            proxy.document.add_fold(line)
                except Exception:
                    continue
        except Exception as e:
            print(f"[TabManager] 恢复折叠失败: {e}")

        return True

    def has_closed_tabs(self) -> bool:
        """检查是否有可恢复的已关闭标签"""
        return len(self._closed_tabs) > 0

    # ========================================================
    # 查找标签
    # ========================================================

    def find_tab_by_path(self, filepath: str) -> Optional[int]:
        """
        根据文件路径查找标签索引。

        参数:
            filepath: 文件路径

        返回:
            标签索引或 None
        """
        if not filepath:
            return None

        target = os.path.abspath(filepath)

        for i in range(self.count()):
            widget = self.widget(i)
            if not hasattr(widget, 'proxy'):
                continue
            proxy = widget.proxy
            if not proxy:
                continue

            # 使用辅助方法统一提取（兼容新旧 API）
            fp = self._get_proxy_filepath(proxy)
            if fp:
                try:
                    if os.path.abspath(fp) == target:
                        return i
                except Exception:
                    pass

        return None

    def find_tab_by_title(self, title: str) -> Optional[int]:
        """根据标题查找标签索引"""
        for i in range(self.count()):
            if self.tabText(i) == title:
                return i
        return None

    def get_open_files(self) -> List[str]:
        """获取所有打开的文件路径列表"""
        files = []
        for i in range(self.count()):
            widget = self.widget(i)
            if not hasattr(widget, 'proxy'):
                continue
            proxy = widget.proxy
            if not proxy:
                continue

            # 使用辅助方法
            fp = self._get_proxy_filepath(proxy)
            if fp:
                files.append(fp)

        return files

    # ========================================================
    # 当前编辑器访问
    # ========================================================
