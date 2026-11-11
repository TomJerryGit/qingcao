# -*- coding: utf-8 -*-
"""菜单默认快捷键兜底（v2.24.x UX）：为常用动作补齐缺失快捷键。"""

import re

from PyQt5.QtGui import QKeySequence


# 文本关键字 → 快捷键（按顺序匹配，越靠前越优先）
DEFAULTS = (
    ("新建文件", "Ctrl+N"),
    ("新建", "Ctrl+N"),
    ("打开文件", "Ctrl+O"),
    ("打开文件夹", "Ctrl+Shift+O"),
    ("打开", "Ctrl+O"),
    ("保存全部", "Ctrl+Shift+S"),
    ("保存", "Ctrl+S"),
    ("关闭项目", "Ctrl+Shift+W"),
    ("关闭标签", "Ctrl+W"),
    ("关闭", "Ctrl+W"),
    ("退出", "Ctrl+Q"),
    ("撤销", "Ctrl+Z"),
    ("重做", "Ctrl+Y"),
    ("剪切", "Ctrl+X"),
    ("复制", "Ctrl+C"),
    ("粘贴", "Ctrl+V"),
    ("全选", "Ctrl+A"),
    ("查找", "Ctrl+F"),
    ("替换", "Ctrl+H"),
    ("转到行", "Ctrl+G"),
    ("转到定义", "F12"),
    ("命令面板", "Ctrl+Shift+P"),
    ("插件市场", "Ctrl+Shift+M"),
    ("首选项", "Ctrl+,"),
    ("设置", "Ctrl+,"),
    ("终端", "Ctrl+`"),
    ("全局搜索", "Ctrl+Shift+F"),
    ("切换注释", "Ctrl+/"),
    ("格式化", "Ctrl+Alt+F"),
    ("放大", "Ctrl+="),
    ("缩小", "Ctrl+-"),
    ("全部展开", "Ctrl+Shift+]"),
    ("全部折叠", "Ctrl+Shift+["),
    ("会话快照", "Ctrl+Alt+S"),
    ("快照", "Ctrl+Alt+S"),
    ("导出为 PDF", "Ctrl+Alt+E"),
    ("导出为 HTML", "Ctrl+Alt+H"),
    ("导出为 Markdown", "Ctrl+Alt+M"),
    ("导出", "Ctrl+Shift+E"),
    ("打印预览", "Ctrl+Alt+P"),
    ("打印", "Ctrl+P"),
    ("转为大写", "Ctrl+Shift+U"),
    ("转为小写", "Ctrl+Shift+L"),
    ("书签", "Ctrl+F2"),
    ("下一书签", "F2"),
    ("上一书签", "Shift+F2"),
    ("问题", "Ctrl+Shift+J"),
    ("大纲", "Ctrl+Shift+O"),
    ("任务", "Ctrl+Shift+T"),
    ("资源管理器", "Ctrl+Shift+E"),
    ("文件树", "Ctrl+Shift+E"),
    ("宏", "Ctrl+Shift+R"),
    ("录制", "Ctrl+Shift+R"),
    ("编码", "Ctrl+Shift+U"),
    ("行尾", "Ctrl+Shift+L"),
    ("自动换行", "Alt+Z"),
    ("专注", "F11"),
    ("全屏", "F11"),
    ("分屏", "Ctrl+\\"),
    ("列编辑", "Alt+Shift+I"),
    ("代码片段", "Ctrl+Shift+K"),
    ("拼写", "F7"),
    ("主题市场", "Ctrl+Shift+M"),
    ("反馈", "Ctrl+Shift+F1"),
    ("帮助", "F1"),
    ("关于", "Shift+F1"),
)


def _normalize(text):
    text = re.sub(r"&[A-Za-z]", "", text or "")
    text = re.sub(r"[\u2000-\u2BFF\uE000-\uF8FF]", " ", text)
    return " ".join(text.split())


def shortcut_for_text(text):
    """按动作文本返回默认快捷键（供工具栏 tooltip 使用）。"""
    label = _normalize(text)
    for key, seq in DEFAULTS:
        if key in label:
            return seq
    return ""


def apply_toolbar_tooltips(toolbar):
    """为工具栏按钮补 tooltip（含默认快捷键提示）。"""
    count = 0
    for action in toolbar.actions():
        if action.isSeparator():
            continue
        label = _normalize(action.text())
        if not label:
            continue
        seq = shortcut_for_text(label)
        tip = f"{action.text()}" + (f"  ({seq})" if seq else "")
        action.setToolTip(tip)
        action.setStatusTip(tip)
        count += 1
    return count


def apply_default_shortcuts(window):
    """为菜单栏/工具栏中缺快捷键的动作补齐默认值，返回设置数量。"""
    try:
        menubar = window.menuBar()
    except Exception:
        return 0
    count = 0
    seen = set()
    for menu_action in menubar.actions():
        menu = menu_action.menu()
        if menu is None:
            continue
        for action in menu.actions():
            if action.isSeparator() or action in seen:
                continue
            seen.add(action)
            if not action.shortcut().isEmpty():
                continue
            label = _normalize(action.text())
            for key, seq in DEFAULTS:
                if key in label:
                    action.setShortcut(QKeySequence(seq))
                    count += 1
                    break
    return count
