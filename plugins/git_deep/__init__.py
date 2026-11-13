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
        self.api.add_menu("工具/Git/查看状态", self.show_status, shortcut="Ctrl+Alt+G")
        self.api.add_menu("工具/Git/查看差异", self.show_diff)
        self.api.add_menu("工具/Git/提交...", self.commit)
        self.api.add_menu("工具/Git/推送", self.push)
        self.api.add_menu("工具/Git/拉取", self.pull)
        self.api.add_menu("工具/Git/查看日志", self.show_log)
        self.api.add_menu("工具/Git/暂存选中 Hunk...", self.stage_hunks)
        self.api.add_menu("工具/Git/查看暂存差异", self.show_staged_diff)
        self.api.add_menu("工具/Git/切换分支...", self.switch_branch)
        self.api.add_menu("工具/Git/新建分支...", self.create_branch)

        # v2.4 扩展点：设置 schema + 状态栏项
        self.api.register_settings_schema(
            [
                {
                    "key": "max_log_lines",
                    "label": "日志最多行数",
                    "type": "int",
                    "default": 200,
                    "min": 10,
                    "max": 5000,
                },
                {"key": "confirm_push", "label": "推送前确认", "type": "bool", "default": True},
            ]
        )
        self._status = self.api.add_status_item("Git: -")

        # 状态栏定时刷新（隔离模式不启动 QTimer）
        self._status_timer = None
        if not getattr(self.api, "is_isolated", False):
            try:
                from PyQt5.QtCore import QTimer

                self._status_timer = QTimer()
                self._status_timer.setInterval(5000)
                self._status_timer.timeout.connect(self._refresh_status)
                self._status_timer.start()
                QTimer.singleShot(500, self._refresh_status)
            except Exception:
                self._status_timer = None

        # 命令
        self.api.register_command("git.status", self.show_status, "Git 状态")

    def on_deactivate(self):
        if self._status_timer is not None:
            try:
                self._status_timer.stop()
            except Exception:
                pass
        self.api.log("Git 插件已停用")

    def _refresh_status(self):
        git = self._get_git_silent()
        if git is None:
            return
        try:
            branch = git.current_branch() or "-"
            dirty = len(git.status() or {})
            text = "Git: %s%s" % (branch, (" ● %d" % dirty) if dirty else "")
            if hasattr(self._status, "setText"):
                self._status.setText(text)
        except Exception:
            pass

    def _get_git_silent(self):
        try:
            from core.git_client import GitClient

            filepath = self.api.get_current_filepath()
            if not filepath:
                return None
            git = GitClient()
            root = git.find_root(filepath)
            return GitClient(root) if root else None
        except Exception:
            return None

    def show_staged_diff(self):
        git = self._get_git()
        if not git:
            return
        try:
            filepath = self.api.get_current_filepath()
            diff = git.diff_staged(filepath)
            self.api.show_text_dialog("Git 暂存差异", diff or "(无暂存差异)", 900, 600)
        except Exception as e:
            self.api.show_message("Git 错误", str(e))

    def switch_branch(self):
        git = self._get_git()
        if not git:
            return
        name, ok = self.api.ask_string("切换分支", "分支名：", "")
        if not ok or not name.strip():
            return
        success, out = git.switch_branch(name.strip())
        self.api.show_status(
            "已切换分支" if success else "切换失败：%s" % out,
            3000,
            "success" if success else "error",
        )
        self._refresh_status()

    def create_branch(self):
        git = self._get_git()
        if not git:
            return
        name, ok = self.api.ask_string("新建分支", "分支名：", "")
        if not ok or not name.strip():
            return
        success, out = git.switch_branch(name.strip(), create=True)
        self.api.show_status(
            "已创建并切换" if success else "创建失败：%s" % out,
            3000,
            "success" if success else "error",
        )
        self._refresh_status()

    def stage_hunks(self):
        git = self._get_git()
        if not git:
            return
        try:
            from PyQt5.QtWidgets import (
                QDialog,
                QDialogButtonBox,
                QListWidget,
                QListWidgetItem,
                QVBoxLayout,
            )

            filepath = self.api.get_current_filepath()
            code, diff, err = git._run(["diff", "--", filepath])
            if code != 0:
                self.api.show_message("Git 错误", err or "diff 失败")
                return
            header, hunks = git.parse_hunks(diff)
            if not hunks:
                self.api.show_status("当前文件没有未暂存 hunk", 3000)
                return
            dlg = QDialog(self.api._host_window())
            dlg.setWindowTitle("暂存 Hunk - %s" % os.path.basename(filepath))
            dlg.resize(720, 480)
            layout = QVBoxLayout(dlg)
            lst = QListWidget()
            for i, h in enumerate(hunks):
                preview = "\n".join(h.splitlines()[:6])
                item = QListWidgetItem("[%d] %s" % (i, preview))
                item.setFlags(item.flags() | item.ItemIsUserCheckable)
                item.setCheckState(item.Unchecked)
                item.setData(256, i)
                lst.addItem(item)
            layout.addWidget(lst)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            layout.addWidget(buttons)
            if dlg.exec_() != QDialog.Accepted:
                return
            chosen = [
                lst.item(i).data(256)
                for i in range(lst.count())
                if lst.item(i).checkState() == lst.item(i).Checked
            ]
            if not chosen:
                self.api.show_status("未选择 hunk", 2000)
                return
            ok2, out = git.stage_hunks(filepath, chosen)
            self.api.show_status(
                "已暂存 %d 个 hunk" % len(chosen) if ok2 else "暂存失败：%s" % out,
                3000,
                "success" if ok2 else "error",
            )
            self._refresh_status()
        except Exception as e:
            self.api.show_message("Git 错误", str(e))

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
                self.api.show_message("Git", "当前文件不在 Git 仓库中")
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

            self.api.show_text_dialog("Git 状态", "\n".join(lines), 600, 500)
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
            self.api.show_text_dialog("Git 差异", diff or "(无差异)", 900, 600)
        except Exception as e:
            self.api.show_message("Git 错误", str(e))

    def commit(self):
        """提交"""
        git = self._get_git()
        if not git:
            return

        try:
            msg, ok = self.api.ask_string("提交", "提交信息:", "")
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
                lines.append(f"  {c['hash']}  {c['message']}")
                lines.append(f"      {c['author']} · {c['when']}")
            self.api.show_text_dialog("Git 日志", "\n".join(lines), 700, 500)
        except Exception as e:
            self.api.show_message("Git 错误", str(e))
