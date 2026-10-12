#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""每日技巧数据"""
import random


TIPS = [
    "按 Ctrl+Shift+P 打开命令面板，模糊搜索所有功能。",
    "按 Ctrl+P 快速切换已打开的文件。",
    "按 Ctrl+R 跳转到当前文件的函数或类。",
    "按 Alt+C 进入列模式，可同时编辑多行文本。",
    "按 Ctrl+D 选中当前单词，再按一次选中下一个相同单词。",
    "按 Ctrl+Shift+R 开始录制宏，Ctrl+Shift+M 回放宏。",
    "选中文本后输入括号或引号可自动包裹。",
    "按 Ctrl+/ 快速注释或取消注释当前行。",
    "按 F11 进入无干扰全屏模式，专心编辑。",
    "按 Ctrl+` 打开 Python 控制台，可执行交互式脚本。",
    "按 Ctrl+Shift+F 进行项目级别的全局搜索。",
    "按 F5 在光标处插入当前日期时间。",
    "拖拽文件到编辑器窗口可直接打开。",
    "双击标签可将标签分离为独立窗口。",
    "中键点击标签可快速关闭标签。",
    "在编辑器中按住 Ctrl+点击可添加多光标。",
    "按 Ctrl+Shift+Up/Down 可以上下移动整行代码。",
    "按 Ctrl+Shift+D 可以复制当前行到下一行。",
    "通过插件市场可安装 Markdown 预览、AI 助手等扩展。",
    "按 Ctrl+G 快速跳转到指定行。",
    "在状态栏可查看编码、行尾符、Git 分支等信息。",
    "在查找框中输入正则表达式可进行复杂搜索。",
    "在全局搜索中可指定文件类型过滤，如 *.py;*.md。",
    "按 Ctrl+Alt+S 可保存所有未保存的文件。",
    "在目录树中按 Alt+点击可快速切换书签。",
]


def get_tip():
    """获取随机技巧"""
    return random.choice(TIPS)


def get_tips_by_level(level="beginner"):
    """根据用户等级返回技巧"""
    if level == "beginner":
        return TIPS[:8]
    elif level == "intermediate":
        return TIPS[8:16]
    else:
        return TIPS[16:]