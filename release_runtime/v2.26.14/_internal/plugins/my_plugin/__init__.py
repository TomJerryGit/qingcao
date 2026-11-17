# -*- coding: utf-8 -*-
"""My Plugin - 青草编辑器插件"""
from app.plugins import PluginBase


class Plugin(PluginBase):
    NAME = "my_plugin"
    VERSION = "1.0.0"
    DESCRIPTION = "由脚手架生成的插件"
    AUTHOR = "your-name"

    def on_activate(self):
        # v2.4 扩展点：设置 schema（无权限需求，仅插件自有配置）
        self.api.register_settings_schema([
            {"key": "hello_text", "label": "问候文本", "type": "str",
             "default": "Hello from my_plugin"},
        ])

        """插件激活时调用"""
        self.api.log("插件已激活: " + self.NAME)

        # 注册菜单
        self.api.add_menu(
            "工具/My Plugin/执行",
            self.run_action,
            shortcut="Ctrl+Alt+Shift+M"   # 避开 markdown_preview 的 Ctrl+Alt+M
        )

    def on_deactivate(self):
        """插件卸载时调用"""
        self.api.log("插件已卸载: " + self.NAME)

    def run_action(self):
        """示例动作"""
        self.api.show_status("Hello from My Plugin!")

        # 获取当前编辑器内容
        text = self.api.get_current_text()
        self.api.show_message(
            "当前文件信息",
            "字符数: %d" % len(text)
        )
