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
