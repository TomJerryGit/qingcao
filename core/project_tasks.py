# -*- coding: utf-8 -*-
"""项目任务系统"""
import json
import os
import subprocess
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QObject, pyqtSignal


class ProjectTask:
    """单个任务"""

    def __init__(self, data):
        self.label = data.get('label', 'Unnamed')
        self.command = data.get('command', '')
        self.args = data.get('args', [])
        self.cwd = data.get('cwd', '')
        self.env = data.get('env', {})
        self.group = data.get('group', 'default')
        self.problem_matcher = data.get('problemMatcher', '')

    def to_dict(self):
        return {
            'label': self.label,
            'command': self.command,
            'args': self.args,
            'cwd': self.cwd,
            'env': self.env,
            'group': self.group,
        }


class TaskRunner(QObject):
    """任务运行器"""

    task_started = pyqtSignal(str)
    task_output = pyqtSignal(str)
    task_finished = pyqtSignal(str, int)  # label, exit_code
    task_error = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None

    def run(self, task, project_root=""):
        """执行任务"""
        self.task_started.emit(task.label)

        cwd = task.cwd or project_root or os.getcwd()

        # 构建环境变量
        env = os.environ.copy()
        env.update(task.env)

        try:
            self.process = subprocess.Popen(
                [task.command] + task.args,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
            )

            # 读取输出
            import threading
            def reader():
                try:
                    for line in self.process.stdout:
                        self.task_output.emit(line.rstrip())
                except Exception:
                    pass
                self.process.wait()
                self.task_finished.emit(task.label, self.process.returncode)

            t = threading.Thread(target=reader, daemon=True)
            t.start()
        except Exception as e:
            self.task_error.emit(task.label, str(e))

    def cancel(self):
        """取消任务"""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except Exception:
                self.process.kill()


class ProjectTaskManager:
    """项目任务管理器"""

    def __init__(self, project_root=""):
        self.project_root = project_root
        self.tasks = []

    def load_tasks(self):
        """加载项目任务文件

        ★ 两个位置都支持（接线时发现的不一致）：

            `core/project_config.py` 约定项目配置在 `.qingcao/` 目录下
            （`settings.json` / `tasks.json`），而本模块原先只读
            根目录的 `.qingcao-tasks.json`。用户按项目配置的约定
            把任务写进 `.qingcao/tasks.json` 时**任务列表为空**，
            且没有任何提示。

            现在优先读 `.qingcao/tasks.json`（新约定），
            回退到 `.qingcao-tasks.json`（旧约定），两者都兼容。
        """
        candidates = [
            os.path.join(self.project_root, '.qingcao', 'tasks.json'),
            os.path.join(self.project_root, '.qingcao-tasks.json'),
        ]
        task_file = next((p for p in candidates if os.path.exists(p)), None)
        if task_file is None:
            return

        try:
            with open(task_file, encoding='utf-8') as f:
                data = json.load(f)
            self.tasks = [
                ProjectTask(t) for t in data.get('tasks', [])
            ]
        except Exception as e:
            print("[TaskManager] 加载失败: %s" % e)

    def get_tasks_by_group(self):
        """按组返回任务"""
        groups = {}
        for task in self.tasks:
            groups.setdefault(task.group, []).append(task)
        return groups

    def find_task(self, label):
        """按名称查找任务"""
        for task in self.tasks:
            if task.label == label:
                return task
        return None