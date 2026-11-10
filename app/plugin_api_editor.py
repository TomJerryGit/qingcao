# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""编辑器访问职责（v2.24 从 plugin_api.py 拆出）。"""

from app.plugin_api_common import *  # noqa: F401,F403,F405


class EditorAccessMixin:
    def current_editor(self):
        """
        获取当前活动编辑器代理。

        返回:
            EditorProxy 实例或 None
        """
        try:
            if self.win is None:
                return None
            return self.win.tabs.current_proxy()
        except Exception:
            return None

    def all_editors(self) -> List[Any]:
        """获取所有打开的编辑器代理"""
        editors = []
        try:
            if self.win is None:
                return editors
            for i in range(self.win.tabs.count()):
                w = self.win.tabs.widget(i)
                if hasattr(w, "proxy"):
                    editors.append(w.proxy)
        except Exception:
            pass
        return editors

    def get_editor_count(self) -> int:
        """获取当前打开的编辑器数量"""
        try:
            if self.win is None:
                return 0
            return self.win.tabs.count()
        except Exception:
            return 0

    def get_selected_text(self) -> str:
        """获取当前编辑器选中的文本"""
        editor = self.current_editor()
        if editor:
            return editor.sc.selectedText()
        return ""

    def get_current_text(self) -> str:
        """获取当前编辑器的全部文本"""
        editor = self.current_editor()
        if editor:
            return editor.sc.text()
        return ""

    def get_current_filepath(self) -> Optional[str]:
        """获取当前编辑器的文件路径（使用新 API）"""
        editor = self.current_editor()
        if not editor:
            return None

        # 优先使用新 API
        if hasattr(editor, "document") and editor.document:
            return editor.document.filepath or None

        # 兜底：走 EditorProxy 的属性别名
        return editor.filepath or None

    def get_cursor_position(self) -> Tuple[int, int]:
        """获取光标位置（行, 列），从 0 开始"""
        editor = self.current_editor()
        if editor:
            return editor.sc.getCursorPosition()
        return (0, 0)

    def insert_text(self, text: str, at_cursor: bool = True):
        """
        在当前编辑器插入文本。

        参数:
            text: 要插入的文本
            at_cursor: True 表示在光标处插入，False 表示追加到末尾
        """
        if not self.require_permission(PERMISSION_EDITOR_WRITE):
            return
        editor = self.current_editor()
        if not editor:
            return
        try:
            if at_cursor:
                editor.sc.insert(text)
            else:
                editor.sc.append(text)
        except Exception as e:
            self.show_status(f"插入文本失败: {e}", 3000, "error")

    def replace_selected_text(self, text: str):
        """替换当前选中的文本"""
        if not self.require_permission(PERMISSION_EDITOR_WRITE):
            return
        editor = self.current_editor()
        if editor:
            try:
                editor.sc.replaceSelectedText(text)
            except Exception as e:
                self.show_status(f"替换失败: {e}", 3000, "error")

    def set_editor_text(self, text: str):
        """设置当前编辑器的全部文本"""
        if not self.require_permission(PERMISSION_EDITOR_WRITE):
            return
        editor = self.current_editor()
        if editor:
            editor.sc.setText(text)

    def open_file(self, filepath: str) -> Optional[Any]:
        """
        在编辑器中打开文件。

        参数:
            filepath: 文件路径

        返回:
            EditorProxy 实例或 None
        """
        try:
            if not os.path.exists(filepath):
                self.show_status(f"文件不存在: {filepath}", 3000, "warning")
                return None
            if self.win is None:
                return None
            return self.win.tabs.open_file(filepath)
        except Exception as e:
            self.show_status(f"打开文件失败: {e}", 3000, "error")
            return None

    def save_current_file(self) -> bool:
        """保存当前文件"""
        if not self.require_permission(PERMISSION_EDITOR_WRITE):
            return False
        editor = self.current_editor()
        if editor:
            try:
                editor.save_file()
                return True
            except Exception as e:
                self.show_status(f"保存失败: {e}", 3000, "error")
        return False

    def new_tab(self, title: str = "未命名"):
        """新建标签页"""
        try:
            if self.win is None:
                return None
            return self.win.tabs.add_tab(title)
        except Exception as e:
            self.show_status(f"新建标签失败: {e}", 3000, "error")
            return None

    def close_current_tab(self):
        """关闭当前标签"""
        try:
            if self.win is None:
                return
            idx = self.win.tabs.currentIndex()
            if idx >= 0:
                self.win.tabs.close_tab(idx)
        except Exception:
            pass

    # ========================================================
    # 光标与选区操作
    # ========================================================

    def goto_line(self, line: int):
        """跳转到指定行（从 0 开始）"""
        editor = self.current_editor()
        if editor:
            try:
                editor.sc.setCursorPosition(line, 0)
                editor.sc.ensureLineVisible(line)
            except Exception:
                pass

    def goto_position(self, position: int):
        """跳转到指定字符位置"""
        editor = self.current_editor()
        if editor:
            try:
                editor.sc.SendScintilla(editor.sc.SCI_GOTOPOS, position)
            except Exception:
                pass

    def select_range(self, start: int, end: int):
        """选中指定范围"""
        editor = self.current_editor()
        if editor:
            try:
                editor.set_selection(start, end)
            except Exception:
                pass

    def highlight_text(self, pattern: str) -> int:
        """
        高亮所有匹配的文本。

        参数:
            pattern: 正则表达式

        返回:
            匹配数量
        """
        editor = self.current_editor()
        if editor:
            try:
                return editor.highlight_all(pattern)
            except Exception:
                pass
        return 0

    def clear_highlights(self):
        """清除所有高亮"""
        editor = self.current_editor()
        if editor:
            try:
                editor.clear_highlights()
            except Exception:
                pass

    # ========================================================
    # 菜单注册
    # ========================================================
