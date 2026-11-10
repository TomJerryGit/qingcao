# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""标签 UI/标题/菜单职责（v2.24 拆出）。"""
from app.tabs_common import *  # noqa: F401,F403,F405


class TabUiMixin:
    def _update_tab_title(self, widget):
        """更新标签标题（脏标志、只读锁、文件名）"""
        if not widget:
            return

        try:
            index = self.indexOf(widget)
            if index < 0:
                return

            title = self.tabText(index)

            # 去掉已有的标记
            for prefix in ('🔒 ', '● '):
                if title.startswith(prefix):
                    title = title[len(prefix):]
            title = title.rstrip(' *').rstrip()

            # 只读标记
            is_readonly = False
            try:
                if hasattr(widget, 'proxy') and widget.proxy:
                    fp = self._get_proxy_filepath(widget.proxy)
                    if fp and os.path.exists(fp):
                        is_readonly = not os.access(fp, os.W_OK)
            except Exception:
                pass

            if is_readonly:
                title = '🔒 ' + title

            # 脏标志
            try:
                if hasattr(widget, 'proxy') and widget.proxy:
                    if getattr(widget.proxy, 'is_modified', False):
                        title = title + ' *'
            except Exception:
                pass

            self.setTabText(index, title)
        except Exception as e:
            print(f"[TabManager] 更新标题失败: {e}")

    def update_all_titles(self):
        """更新所有标签的标题"""
        for i in range(self.count()):
            widget = self.widget(i)
            if widget:
                self._update_tab_title(widget)

    # ========================================================
    # 文件类型颜色
    # ========================================================

    def _apply_file_type_color(self, index: int, filepath: str):
        """根据文件类型设置标签文本颜色"""
        if not filepath:
            return
        try:
            ext = os.path.splitext(filepath)[1].lower()
            color = FILE_TYPE_COLORS.get(ext)
            if color:
                self.tabBar().setTabTextColor(index, color)
        except Exception:
            pass

    def _apply_git_status_color(self, index: int, status: str):
        """根据 Git 状态设置标签颜色"""
        color_map = {
            'M': GIT_MODIFIED_COLOR,
            'A': GIT_ADDED_COLOR,
            'D': GIT_DELETED_COLOR,
            '?': GIT_UNTRACKED_COLOR,
            'R': GIT_MODIFIED_COLOR,
        }
        color = color_map.get(status)
        if color:
            try:
                self.tabBar().setTabTextColor(index, color)
            except Exception:
                pass

    def _update_git_status(self, index: int, filepath: str):
        """更新指定文件的 Git 状态颜色"""
        if not filepath or not os.path.exists(filepath):
            return

        try:
            # 查找 .git 目录
            dirpath = os.path.dirname(filepath)
            git_root = None
            check_path = dirpath

            while check_path != os.path.dirname(check_path):
                if os.path.isdir(os.path.join(check_path, '.git')):
                    git_root = check_path
                    break
                check_path = os.path.dirname(check_path)

            if not git_root:
                return

            # 执行 git status
            result = subprocess.run(
                ['git', '-C', git_root, 'status', '--porcelain',
                 '--', filepath],
                capture_output=True, text=True, timeout=2,
                encoding='utf-8', errors='replace'
            )

            if result.returncode == 0 and result.stdout.strip():
                status = result.stdout.strip()[0]
                self._apply_git_status_color(index, status)

        except Exception:
            pass

    def refresh_git_status(self):
        """刷新所有标签的 Git 状态"""
        for i in range(self.count()):
            widget = self.widget(i)
            if not hasattr(widget, 'proxy'):
                continue
            proxy = widget.proxy
            if not proxy:
                continue

            fp = self._get_proxy_filepath(proxy)
            if fp:
                self._update_git_status(i, fp)

    # ========================================================
    # 标签栏拖动/切换
    # ========================================================

    def _on_tab_moved(self, from_index: int, to_index: int):
        """标签顺序变更时同步 _editors 列表"""
        try:
            if 0 <= from_index < len(self._editors):
                editor = self._editors.pop(from_index)
                self._editors.insert(to_index, editor)
        except (IndexError, ValueError):
            pass

    def _on_current_changed(self, index: int):
        """
        当前标签变更。

        修复说明:
            - 使用 _get_proxy_filepath 辅助方法，避免
              proxy.prov / proxy.document.enc 属性访问崩溃
        """
        old_index = self._last_index
        self._last_index = index

        widget = self.widget(index) if index >= 0 else None
        if widget:
            self._last_active[widget] = QDateTime.currentDateTime()

            # 恢复被释放的内容
            #
            # 修复（审计用例 test_restore_after_release_keeps_clean_state）：
            #   `setText()` 会触发 SCN_MODIFIED，被 `_on_scintilla_modified`
            #   当成**用户编辑** → 标签立刻显示 '*'，即使内容与磁盘一致。
            #   恢复是程序行为，必须抑制回调。逻辑抽到
            #   `_restore_released_content`，与"释放"对称、可单独测试。
            self._restore_released_content(widget)

        # 发射信号
        self.tab_switched.emit(old_index, index)
        try:
            title = self.tabText(index) if index >= 0 else ""
            bus.emit_event(TabChangedEvent(
                index=index, old_index=old_index, title=title
            ))
        except Exception:
            pass

        # 刷新 Git 状态
        if index >= 0 and widget:
            try:
                if hasattr(widget, 'proxy') and widget.proxy:
                    fp = self._get_proxy_filepath(widget.proxy)
                    if fp:
                        self._update_git_status(index, fp)
            except Exception:
                pass

    # ========================================================
    # 右键菜单
    # ========================================================

    def _show_tab_context_menu(self, pos):
        """显示标签右键菜单"""
        try:
            index = self.tabBar().tabAt(pos)
            if index < 0:
                return

            menu = QMenu(self)

            # 关闭当前
            close_act = menu.addAction("❌ 关闭")
            close_act.triggered.connect(lambda: self.close_tab(index))

            # 关闭其他
            if self.count() > 1:
                close_others_act = menu.addAction("关闭其他标签")
                close_others_act.triggered.connect(
                    lambda: self.close_other_tabs(index)
                )

            # 关闭右侧
            if index < self.count() - 1:
                close_right_act = menu.addAction("关闭右侧标签")
                close_right_act.triggered.connect(
                    lambda: self.close_tabs_to_right(index)
                )

            # 关闭左侧
            if index > 0:
                close_left_act = menu.addAction("关闭左侧标签")
                close_left_act.triggered.connect(
                    lambda: self.close_tabs_to_left(index)
                )

            menu.addSeparator()

            # 文件相关操作
            widget = self.widget(index)
            filepath = None

            if widget and hasattr(widget, 'proxy') and widget.proxy:
                filepath = self._get_proxy_filepath(widget.proxy)

            if filepath:
                copy_path_act = menu.addAction("📋 复制文件路径")
                copy_path_act.triggered.connect(
                    lambda: self._copy_file_path(filepath)
                )

                copy_name_act = menu.addAction("📋 复制文件名")
                copy_name_act.triggered.connect(
                    lambda: self._copy_file_name(filepath)
                )

                menu.addSeparator()

                open_folder_act = menu.addAction("📂 打开文件所在位置")
                open_folder_act.triggered.connect(
                    lambda: self._open_file_location(filepath)
                )

                open_system_act = menu.addAction("🌐 用系统默认程序打开")
                open_system_act.triggered.connect(
                    lambda: self._open_with_system(filepath)
                )

                menu.addSeparator()

            # 复制标签标题
            copy_title_act = menu.addAction("📋 复制标签标题")
            copy_title_act.triggered.connect(
                lambda: QApplication.clipboard().setText(
                    self.tabText(index)
                )
            )

            # 重命名标签（仅未命名文件）
            if widget and hasattr(widget, 'proxy') and widget.proxy:
                fp = self._get_proxy_filepath(widget.proxy)

                if not fp:
                    rename_act = menu.addAction("✏ 重命名标签")
                    rename_act.triggered.connect(
                        lambda: self._rename_tab(index)
                    )

            menu.addSeparator()

            # 恢复关闭的标签
            if self.has_closed_tabs():
                restore_act = menu.addAction("↩ 恢复关闭的标签")
                restore_act.triggered.connect(self.restore_closed_tab)

            menu.addSeparator()

            # 在新窗口打开
            split_act = menu.addAction("⬌ 在新窗口打开")
            split_act.triggered.connect(lambda: self._detach_tab(index))

            # 显示菜单
            menu.exec_(self.tabBar().mapToGlobal(pos))
        except Exception as e:
            print(f"[TabManager] 右键菜单失败: {e}")

    def _copy_file_path(self, filepath: str):
        """复制文件路径到剪贴板"""
        QApplication.clipboard().setText(filepath)
        self._show_status("路径已复制到剪贴板")

    def _copy_file_name(self, filepath: str):
        """复制文件名到剪贴板"""
        QApplication.clipboard().setText(os.path.basename(filepath))
        self._show_status("文件名已复制到剪贴板")

    def _open_file_location(self, filepath: str):
        """打开文件所在目录"""
        try:
            folder = os.path.dirname(filepath)
            if sys.platform == 'win32':
                # P1-B1: /select, 必须作为单个参数
                subprocess.Popen(
                    ['explorer',
                     f'/select,{filepath.replace("/", chr(92))}']
                )
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', '-R', filepath])
            else:
                subprocess.Popen(['xdg-open', folder])
        except Exception as e:
            self._show_status(f"打开目录失败: {e}")

    def _open_with_system(self, filepath: str):
        """用系统默认程序打开文件"""
        try:
            if sys.platform == 'win32':
                os.startfile(filepath)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', filepath])
            else:
                subprocess.Popen(['xdg-open', filepath])
        except Exception as e:
            self._show_status(f"打开失败: {e}")

    def _rename_tab(self, index: int):
        """重命名标签（仅未命名文件可重命名）"""
        current = self.tabText(index)
        title, ok = QInputDialog.getText(
            self, "重命名标签", "新名称:", text=current
        )
        if ok and title:
            self.setTabText(index, title)

    def _detach_tab(self, index: int):
        """将标签分离为独立窗口"""
        widget = self.widget(index)
        if not widget:
            return

        # 检查是否有未保存的修改
        has_modified = False
        try:
            if hasattr(widget, 'proxy') and widget.proxy:
                has_modified = getattr(
                    widget.proxy, 'is_modified', False
                )
        except Exception:
            pass

        if has_modified:
            ret = QMessageBox.question(
                self, "分离标签",
                "分离标签前建议先保存文件。是否继续？",
                QMessageBox.Yes | QMessageBox.No
            )
            if ret != QMessageBox.Yes:
                return

        try:
            # 从当前标签移除
            title = self.tabText(index)
            self.removeTab(index)
            if widget in self._editors:
                self._editors.remove(widget)

            # 创建独立窗口
            from ui.detached_window import DetachedWindow
            detached = DetachedWindow(widget, title)
            detached.show()

        except ImportError:
            self._show_status("独立窗口功能不可用")
        except Exception as e:
            self._show_status(f"分离标签失败: {e}")

    # ========================================================
    # 文件外部修改监听
    # ========================================================

    def _show_status(self, message: str, timeout: int = 3000,
                     level: str = "info"):
        """显示状态栏消息"""
        try:
            from app.event_bus import StatusMessageEvent
            bus.emit_event(StatusMessageEvent(
                message=message, timeout=timeout, level=level
            ))
        except Exception:
            # 回退到主窗口状态栏
            try:
                win = self.window()
                if hasattr(win, 'statusBar') and callable(win.statusBar):
                    win.statusBar().showMessage(message, timeout)
            except Exception:
                pass

    # ========================================================
    # 批量操作
    # ========================================================
