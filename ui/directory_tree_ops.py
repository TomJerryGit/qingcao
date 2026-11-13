# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""目录树右键菜单与文件操作（v2.25 从 directory_tree 拆出）。"""

from ui.directory_tree_common import *  # noqa: F401,F403


class DirectoryTreeOpsMixin:
    def _show_context_menu(self, pos):
        """显示右键菜单"""
        item = self.tree.itemAt(pos)
        if item is None:
            # 点击空白区域
            self._show_blank_context_menu(pos)
            return

        path = item.data(0, Qt.UserRole)
        node_type = item.data(0, Qt.UserRole + 1)

        if not path:
            return

        menu = QMenu(self)

        # 针对文件的菜单
        if node_type == NODE_TYPE_FILE:
            open_act = menu.addAction("📂 打开")
            open_act.triggered.connect(lambda: self._open_file(path))

            open_system_act = menu.addAction("🌐 用系统默认程序打开")
            open_system_act.triggered.connect(lambda: self._open_with_system(path))

            menu.addSeparator()

            reveal_act = menu.addAction("📁 在文件管理器中显示")
            reveal_act.triggered.connect(lambda: self._reveal_in_explorer(path))

            copy_path_act = menu.addAction("📋 复制完整路径")
            copy_path_act.triggered.connect(lambda: self._copy_to_clipboard(path))

            copy_rel_act = menu.addAction("📋 复制相对路径")
            copy_rel_act.triggered.connect(lambda: self._copy_relative_path(path))

            copy_name_act = menu.addAction("📋 复制文件名")
            copy_name_act.triggered.connect(lambda: self._copy_to_clipboard(os.path.basename(path)))

            menu.addSeparator()

        # 针对目录的菜单
        if node_type in (NODE_TYPE_DIR, NODE_TYPE_ROOT):
            new_file_act = menu.addAction("📄 新建文件")
            new_file_act.triggered.connect(lambda: self._create_file(path))

            new_folder_act = menu.addAction("📁 新建文件夹")
            new_folder_act.triggered.connect(lambda: self._create_folder(path))

            menu.addSeparator()

            refresh_act = menu.addAction("🔄 刷新")
            refresh_act.triggered.connect(self._do_refresh)

            # 仅对根目录提供关闭项目
            if node_type == NODE_TYPE_ROOT:
                menu.addSeparator()
                close_act = menu.addAction("❌ 关闭项目")
                close_act.triggered.connect(self.clear)

            menu.addSeparator()

        # 重命名和删除（仅对非根节点）
        if node_type != NODE_TYPE_ROOT:
            rename_act = menu.addAction("✏ 重命名")
            rename_act.triggered.connect(lambda: self._rename_item(item))

            delete_act = menu.addAction("🗑 删除")
            delete_act.triggered.connect(lambda: self._delete_item(item))

            menu.addSeparator()

        # 多选时批量操作
        selected = self.tree.selectedItems()
        if len(selected) > 1:
            batch_delete_act = menu.addAction(f"🗑 批量删除 ({len(selected)} 项)")
            batch_delete_act.triggered.connect(lambda: self._batch_delete(selected))

            menu.addSeparator()

        # 属性
        properties_act = menu.addAction("ℹ 属性")
        properties_act.triggered.connect(lambda: self._show_properties(path))

        # 显示菜单
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _show_blank_context_menu(self, pos):
        """点击空白区域的上下文菜单"""
        menu = QMenu(self)

        refresh_act = menu.addAction("🔄 刷新")
        refresh_act.triggered.connect(self._do_refresh)

        if self._root_item:
            expand_act = menu.addAction("⊞ 展开全部")
            expand_act.triggered.connect(lambda: self.expand_all(3))

            collapse_act = menu.addAction("⊟ 折叠全部")
            collapse_act.triggered.connect(self.collapse_all)

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    # ========================================================
    # 文件操作
    # ========================================================
    def _create_file(self, parent_dir: str):
        """新建文件"""
        name, ok = QInputDialog.getText(self, "新建文件", "文件名:", text="new_file.txt")

        if not ok or not name:
            return

        # 清理文件名
        name = name.strip()
        if not name:
            return

        full_path = os.path.join(parent_dir, name)

        if os.path.exists(full_path):
            QMessageBox.warning(self, "文件已存在", f"文件已存在: {name}")
            return

        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            # 创建空文件
            with open(full_path, "w", encoding="utf-8") as f:
                pass

            # 刷新目录
            self._do_refresh()

            # 定位到新文件
            self._select_path(full_path)

            # 发射信号
            self.file_created.emit(full_path)

            # 可选：自动打开新文件
            self.file_opened.emit(full_path)

        except Exception as e:
            QMessageBox.critical(self, "创建失败", str(e))

    def _create_folder(self, parent_dir: str):
        """新建文件夹"""
        name, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名:", text="new_folder")

        if not ok or not name:
            return

        name = name.strip()
        if not name:
            return

        full_path = os.path.join(parent_dir, name)

        if os.path.exists(full_path):
            QMessageBox.warning(self, "文件夹已存在", f"文件夹已存在: {name}")
            return

        try:
            os.makedirs(full_path)
            self._do_refresh()
            self._select_path(full_path)
        except Exception as e:
            QMessageBox.critical(self, "创建失败", str(e))

    def _rename_item(self, item: QTreeWidgetItem):
        """重命名节点"""
        old_path = item.data(0, Qt.UserRole)
        if not old_path:
            return

        old_name = os.path.basename(old_path)

        new_name, ok = QInputDialog.getText(self, "重命名", "新名称:", text=old_name)

        if not ok or not new_name:
            return

        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return

        new_path = os.path.join(os.path.dirname(old_path), new_name)

        if os.path.exists(new_path):
            QMessageBox.warning(self, "名称冲突", f"目标已存在: {new_name}")
            return

        try:
            os.rename(old_path, new_path)

            # 更新模型缓存
            self.model.clear_cache()

            # 刷新
            self._do_refresh()

            # 定位到新文件
            self._select_path(new_path)

            # 发射信号
            self.file_renamed.emit(old_path, new_path)

        except Exception as e:
            QMessageBox.critical(self, "重命名失败", str(e))

    def _delete_item(self, item: QTreeWidgetItem):
        """删除节点"""
        path = item.data(0, Qt.UserRole)
        if not path:
            return

        name = os.path.basename(path)
        is_dir = os.path.isdir(path)

        # 确认对话框
        type_name = "文件夹" if is_dir else "文件"
        msg = f"确定要删除{type_name}吗？\n\n{name}"

        if is_dir:
            # 检查是否为空
            try:
                children = os.listdir(path)
                if children:
                    msg += f"\n\n⚠ 该文件夹包含 {len(children)} 项内容，将一并删除！"
            except Exception:
                pass

        reply = QMessageBox.question(
            self, "确认删除", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            if is_dir:
                shutil.rmtree(path)
            else:
                os.remove(path)

            # 刷新
            self._do_refresh()

            # 发射信号
            self.file_deleted.emit(path)

        except Exception as e:
            QMessageBox.critical(self, "删除失败", str(e))

    def _batch_delete(self, items: List[QTreeWidgetItem]):
        """批量删除"""
        paths = []
        for item in items:
            path = item.data(0, Qt.UserRole)
            if path and path not in paths:
                paths.append(path)

        if not paths:
            return

        # 检查是否有子路径被包含
        filtered_paths = []
        for path in paths:
            is_child = False
            for other in paths:
                if path != other and path.startswith(other + os.sep):
                    is_child = True
                    break
            if not is_child:
                filtered_paths.append(path)

        paths = filtered_paths

        # 确认
        msg = f"确定要删除以下 {len(paths)} 项吗？\n\n"
        msg += "\n".join(f"• {os.path.basename(p)}" for p in paths[:10])
        if len(paths) > 10:
            msg += f"\n... 及其他 {len(paths) - 10} 项"
        msg += "\n\n此操作不可撤销！"

        reply = QMessageBox.question(
            self, "批量删除", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # 执行删除
        deleted = 0
        errors = []
        for path in paths:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                deleted += 1
                self.file_deleted.emit(path)
            except Exception as e:
                errors.append(f"{os.path.basename(path)}: {e}")

        # 刷新
        self._do_refresh()

        # 提示结果
        if errors:
            QMessageBox.warning(
                self,
                "部分删除失败",
                f"成功删除 {deleted} 项，{len(errors)} 项失败:\n\n" + "\n".join(errors[:5]),
            )

    # ========================================================
    # 辅助操作
    # ========================================================
    def _open_file(self, path: str):
        """打开文件"""
        self.file_opened.emit(path)

    def _open_with_system(self, path: str):
        """用系统默认程序打开"""
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))

    def _reveal_in_explorer(self, path: str):
        """在文件管理器中显示"""
        try:
            if sys.platform == "win32":
                # P1-B1: /select, 必须作为单个参数
                # 原写法 ['explorer', '/select,', path] 会打开目录
                # 但不定位文件，因为 explorer 要求 /select,<path>
                # 是同一个参数。
                subprocess.Popen(["explorer", f"/select,{path.replace('/', chr(92))}"])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                folder = os.path.dirname(path) if os.path.isfile(path) else path
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            QMessageBox.warning(self, "无法打开", str(e))

    def _copy_to_clipboard(self, text: str):
        """复制到剪贴板"""
        try:
            QApplication.clipboard().setText(text)
            self._show_status(f"已复制: {text[:50]}", 2000)
        except Exception:
            pass

    def _copy_relative_path(self, path: str):
        """复制相对路径"""
        rel = self.model.get_relative_path(path)
        self._copy_to_clipboard(rel)

    def _show_properties(self, path: str):
        """显示文件属性"""
        info = self.model.get_file_info(path)
        if not info:
            return

        size = info.get("size", 0)
        size_str = self._format_size(size)

        mtime = info.get("mtime", 0)
        mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))

        is_dir = info.get("is_dir", False)
        type_str = "文件夹" if is_dir else "文件"

        msg = f"""<h3>{os.path.basename(path)}</h3>
<p><b>类型:</b> {type_str}</p>
<p><b>路径:</b> {path}</p>
<p><b>大小:</b> {size_str}</p>
<p><b>修改时间:</b> {mtime_str}</p>
<p><b>可读:</b> {"是" if info.get("readable") else "否"}</p>
<p><b>可写:</b> {"是" if info.get("writable") else "否"}</p>
<p><b>可执行:</b> {"是" if info.get("executable") else "否"}</p>
"""

        QMessageBox.information(self, "属性", msg)

    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小"""
        if size < 1024:
            return f"{size} 字节"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / 1024 / 1024:.1f} MB"
        else:
            return f"{size / 1024 / 1024 / 1024:.2f} GB"

    # ========================================================
    # 定位与选择
    # ========================================================
