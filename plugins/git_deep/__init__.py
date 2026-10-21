# -*- coding: utf-8 -*-
"""Git 深度集成插件"""
import os

from app.plugins import PluginBase


class Plugin(PluginBase):
    NAME = "git_deep"
    VERSION = "1.0.0"
    DESCRIPTION = "Git 集成"

    def on_activate(self):
        self.api.log("Git 插件已激活")

        # 菜单
        self.api.add_menu(
            "工具/Git/查看状态", self.show_status,
            shortcut="Ctrl+Alt+G"
        )
        self.api.add_menu(
            "工具/Git/查看差异", self.show_diff
        )
        self.api.add_menu(
            "工具/Git/提交...", self.commit
        )
        self.api.add_menu(
            "工具/Git/推送", self.push
        )
        self.api.add_menu(
            "工具/Git/拉取", self.pull
        )
        self.api.add_menu(
            "工具/Git/查看日志", self.show_log
        )

        # v2.4 扩展点：设置 schema + 状态栏项
        self.api.register_settings_schema([
            {"key": "max_log_lines", "label": "日志最多行数", "type": "int",
             "default": 200, "min": 10, "max": 5000},
            {"key": "confirm_push", "label": "推送前确认", "type": "bool",
             "default": True},
        ])
        self._status = self.api.add_status_item("Git: -")

        # 命令
        self.api.register_command(
            "git.status", self.show_status, "Git 状态"
        )

    def on_deactivate(self):
        self.api.log("Git 插件已停用")

    # --------------------------------------------------------
    def _get_git(self):
        """获取 Git 客户端"""
        try:
            from core.git_client import GitClient

            filepath = self.api.get_current_filepath()
            if not filepath:
                self.api.show_status("没有打开的文件", 2000)
                return None

            git = GitClient()
            root = git.find_root(filepath)
            if not root:
                self.api.show_message(
                    "Git", "当前文件不在 Git 仓库中"
                )
                return None

            return GitClient(root)
        except Exception as e:
            self.api.log(f"获取 Git 失败: {e}", "error")
            return None

    def show_status(self):
        """显示 Git 状态"""
        git = self._get_git()
        if not git:
            return

        try:
            branch = git.current_branch()
            status = git.status()

            lines = [f"分支: {branch}", "=" * 50, ""]
            if not status:
                lines.append("(无变更)")
            else:
                for fp, code in status.items():
                    lines.append(f"  [{code}] {fp}")

            self.api.show_text_dialog(
                "Git 状态", "\n".join(lines), 600, 500
            )
        except Exception as e:
            self.api.show_message("Git 错误", str(e))

    def show_diff(self):
        """显示当前文件差异"""
        git = self._get_git()
        if not git:
            return

        try:
            filepath = self.api.get_current_filepath()
            diff = git.diff(filepath) or git.diff_staged(filepath)
            self.api.show_text_dialog(
                "Git 差异", diff or "(无差异)", 900, 600
            )
        except Exception as e:
            self.api.show_message("Git 错误", str(e))

    def commit(self):
        """提交"""
        git = self._get_git()
        if not git:
            return

        try:
            msg, ok = self.api.ask_string(
                "提交", "提交信息:", ""
            )
            if not ok or not msg.strip():
                return

            # 暂存所有变更
            status = git.status()
            for fp in status.keys():
                git.add(fp)

            success, output = git.commit(msg)
            if success:
                self.api.show_status("提交成功", 2000, "success")
            else:
                self.api.show_message("提交失败", output)
        except Exception as e:
            self.api.show_message("Git 错误", str(e))

    def push(self):
        git = self._get_git()
        if not git:
            return
        try:
            success, output = git.push()
            if success:
                self.api.show_status("推送成功", 2000, "success")
            else:
                self.api.show_message("推送失败", output)
        except Exception as e:
            self.api.show_message("Git 错误", str(e))

    def pull(self):
        git = self._get_git()
        if not git:
            return
        try:
            success, output = git.pull()
            if success:
                self.api.show_status("拉取成功", 2000, "success")
            else:
                self.api.show_message("拉取失败", output)
        except Exception as e:
            self.api.show_message("Git 错误", str(e))

    def show_log(self):
        """查看日志"""
        git = self._get_git()
        if not git:
            return
        try:
            commits = git.log(30)
            lines = [f"最近 {len(commits)} 次提交", "=" * 50, ""]
            for c in commits:
                lines.append(
                    f"  {c['hash']}  {c['message']}"
                )
                lines.append(
                    f"      {c['author']} · {c['when']}"
                )
            self.api.show_text_dialog(
                "Git 日志", "\n".join(lines), 700, 500
            )
        except Exception as e:
            self.api.show_message("Git 错误", str(e))