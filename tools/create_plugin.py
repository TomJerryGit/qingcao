#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""插件脚手架 - 一键生成插件骨架"""
import json
import os
import sys


TEMPLATE_MANIFEST = {
    "name": "{name}",
    "display_name": "{display_name}",
    "version": "1.0.0",
    "description": "{description}",
    "author": "{author}",
    "author_email": "{email}",
    "homepage": "",
    "repository": "",
    "license": "MIT",
    "type": "plugin",
    "category": "other",
    "tags": [],
    "permissions": [],
    "dependencies": [],
    "plugin_dependencies": [],
    "min_app_version": "1.0.0",
    "max_app_version": "",
    "api_version": "2.0.0",
    "enabled": True,
    "auto_load": True,
    "load_order": 100,
}


TEMPLATE_INIT = '''# -*- coding: utf-8 -*-
"""{display_name} - 青草编辑器插件"""
from app.plugins import PluginBase


class Plugin(PluginBase):
    NAME = "{name}"
    VERSION = "1.0.0"
    DESCRIPTION = "{description}"
    AUTHOR = "{author}"

    def on_activate(self):
        """插件激活时调用"""
        self.api.log("插件已激活: " + self.NAME)

        # 注册菜单
        self.api.add_menu(
            "工具/{display_name}/执行",
            self.run_action,
            shortcut="Ctrl+Alt+Shift+M"   # 避开 markdown_preview 的 Ctrl+Alt+M
        )

    def on_deactivate(self):
        """插件卸载时调用"""
        self.api.log("插件已卸载: " + self.NAME)

    def run_action(self):
        """示例动作"""
        self.api.show_status("Hello from {display_name}!")

        # 获取当前编辑器内容
        text = self.api.get_current_text()
        self.api.show_message(
            "当前文件信息",
            "字符数: %d" % len(text)
        )
'''


TEMPLATE_README = '''# {display_name}

{description}

## 安装

将本目录放入 `plugins/` 下，重启青草编辑器。

## 使用方法

在"工具"菜单中找到本插件。

## 权限说明

本插件暂时不需要特殊权限。

## 开发

- 修改 `__init__.py` 中的 `on_activate` 方法实现功能
- 修改 `plugin.json` 中的元数据
- 需要更多权限时，在 `plugin.json` 的 `permissions` 字段添加
'''


def create_plugin(name, target_dir="plugins"):
    """创建插件骨架"""
    display_name = name.replace('_', ' ').title()

    plugin_dir = os.path.join(target_dir, name)
    if os.path.exists(plugin_dir):
        print("[ERROR] 目录已存在: " + plugin_dir)
        return False

    os.makedirs(plugin_dir)

    # plugin.json
    manifest = dict(TEMPLATE_MANIFEST)
    for k, v in manifest.items():
        if isinstance(v, str) and '{' in v:
            manifest[k] = v.format(
                name=name,
                display_name=display_name,
                description="由脚手架生成的插件",
                author="your-name",
                email="your@email.com",
            )
    with open(os.path.join(plugin_dir, 'plugin.json'),
              'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # __init__.py
    with open(os.path.join(plugin_dir, '__init__.py'),
              'w', encoding='utf-8') as f:
        f.write(TEMPLATE_INIT.format(
            name=name,
            display_name=display_name,
            description="由脚手架生成的插件",
            author="your-name",
        ))

    # README.md
    with open(os.path.join(plugin_dir, 'README.md'),
              'w', encoding='utf-8') as f:
        f.write(TEMPLATE_README.format(
            display_name=display_name,
            description="由脚手架生成的插件",
        ))

    print("[OK] 插件已创建: " + plugin_dir)
    print()
    print("下一步：")
    print("  1. 编辑 " + os.path.join(plugin_dir, 'plugin.json'))
    print("  2. 编辑 " + os.path.join(plugin_dir, '__init__.py'))
    print("  3. 重启编辑器加载插件")
    return True


def main():
    if len(sys.argv) < 2:
        print("用法: python create_plugin.py <plugin_name>")
        print("示例: python create_plugin.py my_first_plugin")
        return 1

    name = sys.argv[1].strip()
    if not name:
        print("[ERROR] 插件名不能为空")
        return 1

    # 清理
    name = "".join(c if c.isalnum() or c == '_' else '_' for c in name)

    if create_plugin(name):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())