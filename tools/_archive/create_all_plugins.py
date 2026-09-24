#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一键创建所有插件骨架"""
import os
import json


ROOT = os.path.dirname(os.path.abspath(__file__))
PLUGINS_DIR = os.path.join(ROOT, 'plugins')


PLUGINS = {
    'ai_assistant': {
        'manifest': {
            'name': 'ai_assistant',
            'display_name': 'AI 助手',
            'version': '1.0.0',
            'description': '在编辑器内使用 AI 进行代码解释、重构、生成测试',
            'author': 'hedongwei',
            'author_email': '1265338136@qq.com',
            'license': 'MIT',
            'type': 'plugin',
            'category': 'editor',
            'tags': ['ai', 'code'],
            'permissions': ['network', 'editor_read',
                             'editor_write', 'dialog'],
            'dependencies': ['requests'],
            'api_version': '2.0.0',
            'enabled': True,
            'auto_load': True,
            'load_order': 50,
        },
    },
    'git_deep': {
        'manifest': {
            'name': 'git_deep',
            'display_name': 'Git 深度集成',
            'version': '1.0.0',
            'description': 'Git 状态、差异、提交、推送、拉取',
            'author': 'hedongwei',
            'license': 'MIT',
            'type': 'plugin',
            'category': 'integration',
            'tags': ['git', 'vcs'],
            'permissions': ['process', 'filesystem', 'dialog'],
            'dependencies': [],
            'api_version': '2.0.0',
            'enabled': True,
            'auto_load': True,
            'load_order': 60,
        },
    },
    'json_formatter': {
        'manifest': {
            'name': 'json_formatter',
            'display_name': 'JSON 格式化',
            'version': '1.0.0',
            'description': '格式化、压缩、验证 JSON',
            'author': 'hedongwei',
            'license': 'MIT',
            'type': 'plugin',
            'category': 'tool',
            'tags': ['json', 'format'],
            'permissions': ['editor_read', 'editor_write'],
            'dependencies': [],
            'api_version': '2.0.0',
            'enabled': True,
            'auto_load': True,
            'load_order': 70,
        },
    },
    'logtail': {
        'manifest': {
            'name': 'logtail',
            'display_name': '日志实时监视',
            'version': '1.0.0',
            'description': '监视日志文件的变化并自动滚动',
            'author': 'hedongwei',
            'license': 'MIT',
            'type': 'plugin',
            'category': 'tool',
            'tags': ['log', 'tail'],
            'permissions': ['filesystem'],
            'dependencies': [],
            'api_version': '2.0.0',
            'enabled': True,
            'auto_load': True,
            'load_order': 80,
        },
    },
    'markdown_preview': {
        'manifest': {
            'name': 'markdown_preview',
            'display_name': 'Markdown 预览',
            'version': '1.0.0',
            'description': 'Markdown 实时预览（分屏）',
            'author': 'hedongwei',
            'license': 'MIT',
            'type': 'plugin',
            'category': 'editor',
            'tags': ['markdown', 'preview'],
            'permissions': ['editor_read'],
            'dependencies': [],
            'api_version': '2.0.0',
            'enabled': True,
            'auto_load': True,
            'load_order': 90,
        },
    },
    'python_debugger': {
        'manifest': {
            'name': 'python_debugger',
            'display_name': 'Python 调试器',
            'version': '1.0.0',
            'description': '基于 pdb 的简单 Python 调试器',
            'author': 'hedongwei',
            'license': 'MIT',
            'type': 'plugin',
            'category': 'integration',
            'tags': ['python', 'debug'],
            'permissions': ['process', 'editor_read', 'dialog'],
            'dependencies': [],
            'api_version': '2.0.0',
            'enabled': True,
            'auto_load': True,
            'load_order': 100,
        },
    },
    'todo_panel': {
        'manifest': {
            'name': 'todo_panel',
            'display_name': 'TODO 面板',
            'version': '1.0.0',
            'description': '收集并显示所有 TODO/FIXME 注释',
            'author': 'hedongwei',
            'license': 'MIT',
            'type': 'plugin',
            'category': 'tool',
            'tags': ['todo', 'task'],
            'permissions': ['filesystem', 'editor_read'],
            'dependencies': [],
            'api_version': '2.0.0',
            'enabled': True,
            'auto_load': True,
            'load_order': 110,
        },
    },
    'wordcount': {
        'manifest': {
            'name': 'wordcount',
            'display_name': '字数统计',
            'version': '1.0.0',
            'description': '实时统计字符数、词数、行数',
            'author': 'hedongwei',
            'license': 'MIT',
            'type': 'plugin',
            'category': 'tool',
            'tags': ['word', 'count'],
            'permissions': ['editor_read'],
            'dependencies': [],
            'api_version': '2.0.0',
            'enabled': True,
            'auto_load': True,
            'load_order': 120,
        },
    },
}


def create_plugin(name, manifest):
    """创建插件目录"""
    plugin_dir = os.path.join(PLUGINS_DIR, name)
    os.makedirs(plugin_dir, exist_ok=True)

    # plugin.json
    manifest_path = os.path.join(plugin_dir, 'plugin.json')
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # __init__.py（占位，如果不存在）
    init_path = os.path.join(plugin_dir, '__init__.py')
    if not os.path.exists(init_path):
        with open(init_path, 'w', encoding='utf-8') as f:
            f.write(
                '# -*- coding: utf-8 -*-\n'
                '# 请从对话中粘贴实际代码\n'
            )

    print(f"[OK] {plugin_dir}")


def main():
    print("=" * 60)
    print("创建插件骨架")
    print("=" * 60)

    os.makedirs(PLUGINS_DIR, exist_ok=True)

    for name, data in PLUGINS.items():
        create_plugin(name, data['manifest'])

    print()
    print(f"共创建 {len(PLUGINS)} 个插件")


if __name__ == '__main__':
    main()