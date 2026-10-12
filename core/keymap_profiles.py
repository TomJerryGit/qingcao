# -*- coding: utf-8 -*-
"""快捷键方案预设"""
from typing import Dict


KEYMAP_SCHEMES = {
    "default": {
        "name": "青草默认",
        "description": "默认的快捷键布局",
        "overrides": {},  # 使用 ActionManager 里的默认值
    },

    "vscode": {
        "name": "VSCode 兼容",
        "description": "使用 VSCode 风格的快捷键",
        "overrides": {
            "file.new": "Ctrl+N",
            "file.open": "Ctrl+O",
            "file.save": "Ctrl+S",
            "file.save_as": "Ctrl+Shift+S",
            "edit.find": "Ctrl+F",
            "edit.replace": "Ctrl+H",
            "edit.goto_line": "Ctrl+G",
            "tools.command_palette": "Ctrl+Shift+P",
            "tools.quick_open": "Ctrl+P",
            "edit.toggle_comment": "Ctrl+/",
            "edit.duplicate_line": "Shift+Alt+Down",
            "edit.move_line_up": "Alt+Up",
            "edit.move_line_down": "Alt+Down",
            "edit.select_next": "Ctrl+D",
            "view.column_mode": "Shift+Alt+Down",  # VSCode 中是列选
        },
    },

    "sublime": {
        "name": "Sublime Text 兼容",
        "description": "使用 Sublime 风格的快捷键",
        "overrides": {
            "file.new": "Ctrl+N",
            "file.open": "Ctrl+O",
            "file.save": "Ctrl+S",
            "edit.find": "Ctrl+F",
            "edit.replace": "Ctrl+H",
            "edit.goto_line": "Ctrl+G",
            "tools.command_palette": "Ctrl+Shift+P",
            "tools.quick_open": "Ctrl+P",
            "edit.toggle_comment": "Ctrl+/",
            "edit.select_next": "Ctrl+D",
            "edit.move_line_up": "Ctrl+Shift+Up",
            "edit.move_line_down": "Ctrl+Shift+Down",
        },
    },

    "vim": {
        "name": "Vim 模式",
        "description": "使用 Vim 风格的操作",
        "overrides": {
            "file.save": "Ctrl+S",
            "edit.find": "Ctrl+F",
            "edit.undo": "Ctrl+Z",
            "edit.redo": "Ctrl+Shift+Z",
            "edit.goto_line": "Ctrl+G",
            "tools.command_palette": "Ctrl+Shift+P",
        },
    },
}


def get_scheme_names():
    """获取所有方案名"""
    return [(k, v["name"]) for k, v in KEYMAP_SCHEMES.items()]


def get_scheme(key):
    """获取方案详情"""
    return KEYMAP_SCHEMES.get(key, KEYMAP_SCHEMES["default"])


def apply_scheme(action_manager, scheme_key):
    """应用快捷键方案

    参数:
        action_manager: ActionManager 实例
        scheme_key: 方案 key
    """
    scheme = get_scheme(scheme_key)

    if scheme_key == "default":
        # 恢复默认
        action_manager.reset_to_defaults()
        return

    # 先恢复默认
    action_manager.reset_to_defaults()

    # 再应用覆盖
    overrides = scheme.get("overrides", {})
    for action_name, shortcut in overrides.items():
        try:
            action_manager.set_shortcut(action_name, shortcut)
        except Exception as e:
            print("[KeymapScheme] 应用 %s 失败: %s" % (action_name, e))