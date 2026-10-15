# -*- coding: utf-8 -*-
"""
青草编辑器 - 文件操作 Mixin
============================
从 ui/main_window.py 拆分出来的文件操作相关方法。
"""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QFileDialog,
    QInputDialog,
    QMessageBox,
)


class FileOpsMixin:
    """文件操作 Mixin —— 由 MainWindow 继承"""

    # 依赖属性: self.tabs, self.central_stack, self.status_bar
    #          self.api, self.prefs, self.session

    # ========================================================
    # 文件操作
    # ========================================================
    def _new_file(self):
        """新建文件（弹出格式选择对话框）"""
        try:
            formats = [
                "纯文本 (*.txt)",
                "Python (*.py)",
                "Markdown (*.md)",
                "JSON (*.json)",
                "HTML (*.html)",
                "CSS (*.css)",
                "JavaScript (*.js)",
                "日志文件 (*.log)",
                "无扩展名",
            ]
            choice, ok = QInputDialog.getItem(
                self, "新建文件", "选择文件类型:",
                formats, 0, False
            )
            if not ok:
                return

            # 解析扩展名
            ext = ""
            if "(*." in choice:
                ext = "." + choice.split("*.")[1].rstrip(")")
            elif "无扩展名" in choice:
                ext = ""

            # 切到编辑区
            if self.central_stack:
                self.central_stack.setCurrentIndex(0)

            # 新建标签
            proxy = self.tabs.add_tab()
            if proxy is None:
                print("[MainWindow] 新建文件失败: proxy 为 None")
                return

            # 设置词法器和初始模板
            try:
                editor = self.tabs.widget(self.tabs.currentIndex())
                if editor and hasattr(editor, "set_lexer_by_filename") and ext:
                    editor.set_lexer_by_filename("untitled" + ext)
                template = self._get_template_for_ext(ext)
                if template and editor:
                    editor.setText(template)
                    editor.setModified(True)
            except Exception as e:
                print("[MainWindow] 词法器/模板设置失败: %s" % e)

            self._update_status_for_editor()
            if not self.isVisible():
                self.show()
            print("[MainWindow] 新建文件成功: ext=%r" % ext)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("[MainWindow] 新建文件异常: %s" % e)



    def _get_template_for_ext(self, ext):
        """根据扩展名返回初始模板"""
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        templates = {
            ".py": (
                "#!/usr/bin/env python\n"
                "# -*- coding: utf-8 -*-\n"
                "\n\n"
                "def main():\n"
                "    pass\n"
                "\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
            ".md": "# 标题\n\n## 二级标题\n\n正文内容\n",
            ".json": '{\n  "key": "value"\n}\n',
            ".html": (
                "<!DOCTYPE html>\n"
                "<html lang=\"zh-CN\">\n"
                "<head>\n"
                "    <meta charset=\"UTF-8\">\n"
                "    <title>Document</title>\n"
                "</head>\n"
                "<body>\n"
                "    \n"
                "</body>\n"
                "</html>\n"
            ),
            ".css": "/* CSS */\nbody {\n    margin: 0;\n}\n",
            ".js": "// JavaScript\n\n",
            ".txt": "",
            ".log": "# Log created at " + now + "\n",
        }
        return templates.get(ext, "")


    def _open_file(self):
        """打开文件"""
        try:
            paths, _ = QFileDialog.getOpenFileNames(
                self, "打开文件", "",
                "所有文件 (*.*);;文本文件 (*.txt);;Python (*.py);;"
                "Markdown (*.md);;JSON (*.json);;日志 (*.log)"
            )

            if not paths:
                return

            self.central_stack.setCurrentIndex(0)

            for path in paths:
                self.tabs.open_file(path)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error("打开文件失败", str(e))


    def _open_folder(self, folder: str = ""):
        """打开文件夹到目录树"""
        try:
            if not folder:
                folder = QFileDialog.getExistingDirectory(self, "打开文件夹")
            if folder and self.dir_tree:
                self.dir_tree.set_root(folder)
                if self.dir_tree_dock:
                    self.dir_tree_dock.show()
        except Exception as e:
            self._show_error("打开文件夹失败", str(e))


    def _open_recent_file(self, filepath: str):
        """打开最近文件"""
        try:
            if filepath and os.path.exists(filepath):
                self.central_stack.setCurrentIndex(0)
                self.tabs.open_file(filepath)
        except Exception as e:
            self._show_error("打开文件失败", str(e))


    def _open_recent_project(self, project_path: str):
        """打开最近项目"""
        try:
            if project_path and os.path.exists(project_path):
                self.open_project(project_path)
        except Exception as e:
            self._show_error("打开项目失败", str(e))


    def _save_file(self):
        """保存当前文件"""
        try:
            proxy = self.tabs.current_proxy()
            if not proxy:
                return

            filepath = ""
            if proxy.document:
                filepath = proxy.document.filepath or ""

            if not filepath:
                self._save_file_as()
            else:
                # 必须检查返回值（真实缺陷修复）：
                #   原实现丢弃 `save_file()` 的 bool 返回值，无条件提示
                #   "已保存"。于是磁盘满、权限不足、只读介质等情况下，
                #   用户会**以为文件已经存好**，实际修改全部丢失。
                ok = proxy.save_file()
                if ok:
                    self.status_bar.showMessage("已保存", 2000)
                else:
                    self._show_error(
                        "保存失败",
                        "文件未能写入磁盘：\n%s\n\n"
                        "请检查磁盘空间、文件权限，或用「另存为」保存到其它位置。"
                        % filepath
                    )

        except Exception as e:
            self._show_error("保存失败", str(e))


    def _save_file_as(self):
        """另存为"""
        try:
            proxy = self.tabs.current_proxy()
            if not proxy:
                return

            filepath = ""
            if proxy.document:
                filepath = proxy.document.filepath or ""

            filters = (
                "所有文件 (*.*);;"
                "文本文件 (*.txt);;"
                "Python (*.py);;"
                "Markdown (*.md);;"
                "JSON (*.json);;"
                "HTML (*.html);;"
                "CSS (*.css);;"
                "JavaScript (*.js);;"
                "日志文件 (*.log)"
            )
            path, _selected = QFileDialog.getSaveFileName(
                self, "另存为", filepath, filters
            )

            if path:
                # 必须走 EditorProxy.save_file(path)，**不能**直接调
                # proxy.document.save(path)。
                #
                # 缺陷背景（P0-B，已实测复现的数据丢失）：
                #   `Document.save()` 只把 provider 里**已有的字节**写盘，
                #   而编辑器当前内容要到 `EditorProxy._sync_content_to_provider()`
                #   才会同步进 provider。原实现绕过同步点，于是"另存为"
                #   写下的是**打开文件时**的旧内容：
                #       打开 = 'OLD LINE 1\nOLD LINE 2\n'
                #       编辑 = 'NEW CONTENT A\n...'
                #       另存为返回 True，磁盘上却仍是 OLD 内容
                #   而 Document.save 还返回 True、清 modified、删草稿，
                #   用户看到"成功"，编辑全部丢失且连草稿都救不回来。
                #
                #   save_file(path) 会依次做：同步内容 → 保存 → 清脏标记
                #   → 通知 LSP → 删草稿，是唯一正确的入口。
                if not proxy.save_file(path):
                    self._show_error(
                        "另存为失败",
                        "文件未能写入磁盘：\n%s\n\n"
                        "请检查目标路径的权限与磁盘空间。" % path
                    )
                    return

                # 更新标签标题
                idx = self.tabs.currentIndex()
                if idx >= 0:
                    self.tabs.setTabText(idx, os.path.basename(path))

                self.status_bar.showMessage(
                    "已另存为: %s" % os.path.basename(path), 3000
                )

        except Exception as e:
            self._show_error("另存为失败", str(e))


    def _save_all(self):
        """保存所有文件

        修复（真实缺陷）：原实现丢弃 `save_file()` 的返回值并把"调用了"
        当成"成功了"，`saved += 1` 无条件累加；异常还被 `pass` 吞掉。
        结果磁盘满时也报"已保存 N 个文件"，失败的文件用户完全不知道。
        现在按**真实返回值**统计，并把失败清单报给用户。
        """
        try:
            saved = 0
            failed = []
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if not hasattr(w, 'proxy'):
                    continue
                proxy = w.proxy
                if proxy and hasattr(proxy, 'is_modified') and proxy.is_modified:
                    name = self.tabs.tabText(i)
                    try:
                        if proxy.save_file():
                            saved += 1
                        else:
                            failed.append(name)
                    except Exception as e:
                        failed.append("%s (%s)" % (name, e))

            if failed:
                self._show_error(
                    "部分文件保存失败",
                    "以下文件未能写入磁盘：\n\n  · %s\n\n"
                    "已成功保存 %d 个。请检查磁盘空间与文件权限。"
                    % ("\n  · ".join(failed), saved)
                )
            elif saved:
                self.status_bar.showMessage(f"已保存 {saved} 个文件", 2000)
            else:
                self.status_bar.showMessage("没有需要保存的文件", 2000)

        except Exception as e:
            self._show_error("保存全部失败", str(e))


    def _close_current_tab(self):
        """关闭当前标签"""
        try:
            idx = self.tabs.currentIndex()
            if idx >= 0:
                self.tabs.close_tab(idx)
        except Exception as e:
            print(f"[MainWindow] 关闭标签失败: {e}")


    def _close_all_tabs(self):
        """关闭所有标签"""
        try:
            for i in range(self.tabs.count() - 1, -1, -1):
                self.tabs.close_tab(i)
        except Exception as e:
            print(f"[MainWindow] 关闭所有标签失败: {e}")


    def _restore_closed_tab(self):
        """恢复最近关闭的标签"""
        try:
            if hasattr(self.tabs, 'restore_closed_tab'):
                self.tabs.restore_closed_tab()
        except Exception as e:
            print(f"[MainWindow] 恢复标签失败: {e}")


    def _open_startup_files(self):
        """打开启动文件"""
        try:
            for filepath in self.startup_files:
                if os.path.exists(filepath):
                    self.tabs.open_file(filepath)

            if self.tabs.count() > 0:
                self.central_stack.setCurrentIndex(0)

        except Exception as e:
            print(f"[MainWindow] 打开启动文件失败: {e}")


    def _on_file_opened(self, event):
        """文件打开"""
        try:
            path = getattr(event, 'path', '')
            if path:
                self.central_stack.setCurrentIndex(0)
                # P1-2: 音效接线（默认关闭，需在首选项开启）
                try:
                    from infrastructure.sound_manager import SoundEvent, play_sound
                    play_sound(SoundEvent.FILE_OPEN)
                except Exception:
                    pass
        except Exception:
            pass


    def _on_file_saved(self, event):
        """文件保存"""
        try:
            path = getattr(event, 'path', '')
            if path:
                self.status_bar.showMessage(
                    f"已保存: {os.path.basename(path)}", 2000
                )
                # P1-2: 音效接线
                try:
                    from infrastructure.sound_manager import SoundEvent, play_sound
                    play_sound(SoundEvent.FILE_SAVE)
                except Exception:
                    pass
        except Exception:
            pass


    # ========================================================
    # 项目
    # ========================================================
    def open_project(self, project_file: str):
        """打开项目"""
        try:
            from core.project import Project
            self._current_project = Project.load(project_file)

            if self._current_project:
                if self.dir_tree:
                    self.dir_tree.set_root(self._current_project.root_path)

                for filepath in getattr(self._current_project, 'files', []):
                    if os.path.exists(filepath):
                        self.tabs.open_file(filepath)

                self.status_bar.showMessage(
                    f"已打开项目: {self._current_project.name}", 3000
                )
        except Exception as e:
            self._show_error("打开项目失败", str(e))


    def save_project(self):
        """保存项目"""
        if not self._current_project:
            return

        try:
            filepath, _ = QFileDialog.getSaveFileName(
                self, "保存项目", "", "青草项目 (*.qingcao-project)"
            )
            if filepath:
                files = []
                for i in range(self.tabs.count()):
                    w = self.tabs.widget(i)
                    if hasattr(w, 'proxy') and w.proxy and w.proxy.document:
                        fp = w.proxy.document.filepath
                        if fp:
                            files.append(fp)

                self._current_project.files = files
                self._current_project.save(filepath)
                self.status_bar.showMessage("项目已保存", 2000)
        except Exception as e:
            self._show_error("保存项目失败", str(e))


    def close_project(self):
        """关闭项目"""
        self._current_project = None
        if self.dir_tree and hasattr(self.dir_tree, 'clear'):
            self.dir_tree.clear()
        self.status_bar.showMessage("项目已关闭", 2000)


    # ========================================================
    # 新窗口
    # ========================================================
    def _new_window(self):
        """打开新窗口"""
        try:
            # 修复 P0-C3: 延迟导入 MainWindow
            # 原实现直接 MainWindow() 会 NameError，
            # 异常被 except 吞掉，用户无感知。
            from ui.main_window import MainWindow
            new_window = MainWindow()
            new_window.show()
        except Exception as e:
            print(f"[MainWindow] 新窗口失败: {e}")
