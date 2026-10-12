# -*- coding: utf-8 -*-
"""项目级配置"""
import json
import os
from typing import Any, Dict, Optional


PROJECT_DIR = ".qingcao"


class ProjectConfig:
    """项目配置"""

    def __init__(self, project_root=""):
        self.project_root = project_root
        self.config_dir = os.path.join(project_root, PROJECT_DIR)
        self.settings: Dict[str, Any] = {}
        self.keybindings: Dict[str, str] = {}
        self.tasks: Dict[str, Any] = {}
        self.snippets: Dict[str, Any] = {}

    def load(self) -> bool:
        """加载项目配置"""
        if not os.path.isdir(self.config_dir):
            return False

        # settings
        self.settings = self._load_json('settings.json') or {}

        # keybindings
        self.keybindings = self._load_json('keybindings.json') or {}

        # tasks
        self.tasks = self._load_json('tasks.json') or {}

        # snippets
        self.snippets = self._load_json('snippets.json') or {}

        return True

    def _load_json(self, filename: str) -> Optional[Dict]:
        """读取 JSON 文件"""
        filepath = os.path.join(self.config_dir, filename)
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print("[ProjectConfig] 加载 %s 失败: %s" % (filename, e))
            return None

    def save_settings(self):
        """保存 settings"""
        self._save_json('settings.json', self.settings)

    def _save_json(self, filename: str, data: Any):
        """保存 JSON"""
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            filepath = os.path.join(self.config_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("[ProjectConfig] 保存 %s 失败: %s" % (filename, e))

    def get_setting(self, key: str, default: Any = None) -> Any:
        """获取设置"""
        return self.settings.get(key, default)

    def set_setting(self, key: str, value: Any):
        """设置"""
        self.settings[key] = value
        self.save_settings()

    def has_config(self) -> bool:
        """是否有项目配置"""
        return os.path.isdir(self.config_dir)

    def init_project_dir(self):
        """初始化项目目录"""
        os.makedirs(self.config_dir, exist_ok=True)

        # 示例 settings.json
        example_settings = {
            "font_size": 13,
            "tab_width": 4,
            "word_wrap": False,
            "trim_trailing_whitespace": True,
        }
        settings_file = os.path.join(self.config_dir, 'settings.json')
        if not os.path.exists(settings_file):
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(example_settings, f, indent=2,
                          ensure_ascii=False)

        # .gitignore
        gitignore = os.path.join(self.config_dir, '.gitignore')
        if not os.path.exists(gitignore):
            with open(gitignore, 'w', encoding='utf-8') as f:
                f.write("# 青草项目配置\n")
                f.write("*.local.json\n")


# 全局单例
_current_project_config: Optional[ProjectConfig] = None


def get_project_config() -> Optional[ProjectConfig]:
    return _current_project_config


def set_project_root(root: str):
    """设置当前项目根目录"""
    global _current_project_config
    if not root or not os.path.isdir(root):
        _current_project_config = None
        return

    # 检查是否已有 .qingcao 目录
    config_dir = os.path.join(root, PROJECT_DIR)
    if not os.path.isdir(config_dir):
        # 向上查找
        current = os.path.abspath(root)
        while current != os.path.dirname(current):
            cfg = os.path.join(current, PROJECT_DIR)
            if os.path.isdir(cfg):
                root = current
                break
            current = os.path.dirname(current)

    _current_project_config = ProjectConfig(root)
    _current_project_config.load()