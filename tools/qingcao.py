#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - 开发工具 CLI
============================================================

用法：
    python tools/qingcao.py <command> [args...]

命令：
    check            依赖检查
    health           项目健康扫描
    diagnose-ai      AI 配置诊断
    diagnose-proxy   代理环境诊断
    quick-check      快速自检
    new-plugin NAME  创建插件骨架
    list             列出所有命令

示例：
    python tools/qingcao.py check
    python tools/qingcao.py health
    python tools/qingcao.py diagnose-ai
    python tools/qingcao.py new-plugin my_plugin
"""

import os
import subprocess
import sys


TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS_DIR)


# 命令 -> (脚本文件名, 说明)
COMMANDS = {
    'check':             ('check_deps.py',         '依赖检查'),
    'health':            ('health_check.py',       '项目健康扫描'),
    'diagnose-ai':       ('diagnose_ai.py',        'AI 配置诊断'),
    'diagnose-proxy':    ('diagnose_proxy.py',     '代理环境诊断'),
    'diagnose-shortcut': ('diagnose_shortcut.py',  '快捷键冲突诊断'),
    'quick-check':       ('quick_check.py',        '快速自检'),
    'new-plugin':        ('create_plugin.py',      '创建插件骨架'),
}


def print_usage():
    print(__doc__)


def print_commands():
    print('可用命令：')
    for cmd, (_, desc) in sorted(COMMANDS.items()):
        print('  {:16s} {}'.format(cmd, desc))


def run_script(script_name, extra_args):
    """通过 subprocess 调用 tools/ 下的脚本"""
    script_path = os.path.join(TOOLS_DIR, script_name)
    if not os.path.exists(script_path):
        print('[ERROR] 脚本不存在: {}'.format(script_path))
        return 1
    cmd = [sys.executable, script_path] + list(extra_args)
    try:
        return subprocess.run(cmd, cwd=ROOT).returncode
    except KeyboardInterrupt:
        print('\n用户中断')
        return 130


def main():
    if len(sys.argv) < 2:
        print_usage()
        return 1

    command = sys.argv[1]
    extra = sys.argv[2:]

    if command in ('-h', '--help', 'help'):
        print_usage()
        return 0

    if command == 'list':
        print_commands()
        return 0

    if command not in COMMANDS:
        print('[ERROR] 未知命令: {}'.format(command))
        print()
        print_commands()
        return 1

    script_name, _ = COMMANDS[command]
    return run_script(script_name, extra)


if __name__ == '__main__':
    sys.exit(main())
