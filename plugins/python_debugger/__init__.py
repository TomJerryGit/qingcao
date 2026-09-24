# -*- coding: utf-8 -*-
"""Python 调试器插件"""
import os
import sys
import subprocess
from app.plugins import PluginBase


class Plugin(PluginBase):
    NAME = "python_debugger"
    VERSION = "1.0.0"
    DESCRIPTION = "Python 调试器"
    AUTHOR = "hedongwei"

    def on_activate(self):
        self.api.log("Python 调试器插件已激活")

        self.api.add_menu(
            "工具/Python 调试/运行当前文件",
            self.run_current,
            shortcut="F5"
        )
        self.api.add_menu(
            "工具/Python 调试/调试当前文件 (pdb)",
            self.debug_current,
            shortcut="F6"
        )
        self.api.add_menu(
            "工具/Python 调试/带参数运行...",
            self.run_with_args
        )

    def on_deactivate(self):
        self.api.log("Python 调试器插件已停用")

    def _get_python_file(self):
        """获取当前 Python 文件"""
        filepath = self.api.get_current_filepath()
        if not filepath:
            self.api.show_status("没有打开的文件", 2000)
            return None
        if not filepath.lower().endswith(('.py', '.pyw')):
            self.api.show_message(
                "提示", "只有 Python 文件可以运行"
            )
            return None

        # 提示保存
        editor = self.api.current_editor()
        if editor and hasattr(editor, 'proxy'):
            if editor.proxy and editor.proxy.is_modified:
                self.api.show_message(
                    "提示",
                    "文件已修改，请先保存后再运行"
                )
                return None

        return filepath

    def run_current(self):
        """运行当前文件"""
        filepath = self._get_python_file()
        if not filepath:
            return

        try:
            cwd = os.path.dirname(filepath) or os.getcwd()
            cmd = [sys.executable, filepath]

            # Windows 下用新控制台
            if sys.platform == 'win32':
                subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                subprocess.Popen(
                    ['gnome-terminal', '--', *cmd] if
                    subprocess.run(['which', 'gnome-terminal'],
                                    capture_output=True
                                    ).returncode == 0
                    else cmd,
                    cwd=cwd
                )

            self.api.show_status(
                f"运行: {os.path.basename(filepath)}", 2000, "success"
            )
        except Exception as e:
            self.api.show_message("运行失败", str(e))

    def debug_current(self):
        """用 pdb 调试"""
        filepath = self._get_python_file()
        if not filepath:
            return

        try:
            cwd = os.path.dirname(filepath) or os.getcwd()
            cmd = [sys.executable, '-m', 'pdb', filepath]

            if sys.platform == 'win32':
                subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                subprocess.Popen(cmd, cwd=cwd)

            self.api.show_status(
                f"调试: {os.path.basename(filepath)}", 2000
            )
        except Exception as e:
            self.api.show_message("调试失败", str(e))

    def run_with_args(self):
        """带参数运行"""
        filepath = self._get_python_file()
        if not filepath:
            return

        args, ok = self.api.ask_string(
            "运行参数",
            "命令行参数（空格分隔）:",
            ""
        )
        if not ok:
            return

        try:
            cwd = os.path.dirname(filepath) or os.getcwd()
            cmd = [sys.executable, filepath] + args.split()

            if sys.platform == 'win32':
                subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                subprocess.Popen(cmd, cwd=cwd)

            self.api.show_status("运行中...", 2000, "success")
        except Exception as e:
            self.api.show_message("运行失败", str(e))