# -*- coding: utf-8 -*-
"""Demo 插件 —— 青草编辑器最小示例"""
from app.plugins import PluginBase


class Plugin(PluginBase):
    NAME = "demo"
    VERSION = "1.0.0"
    DESCRIPTION = "青草编辑器最小示例插件"
    AUTHOR = "hedongwei"
    PERMISSIONS = ["editor_read", "dialog"]

    def on_activate(self):
        # v2.4 扩展点：设置 schema + 状态栏项
        self.api.register_settings_schema([
            {"key": "greeting", "label": "状态栏问候语", "type": "str",
             "default": "Demo 插件就绪"},
        ])
        self._status = self.api.add_status_item(
            str(self.api.get_config("greeting", "Demo 插件就绪")))

        self.api.log("Demo 插件已激活")
        self.api.add_menu(
            "工具/Demo/显示当前文件字符数",
            self.show_stats,
        )

    def on_deactivate(self):
        self.api.log("Demo 插件已停用")

    def show_stats(self):
        text = self.api.get_current_text()
        self.api.show_message(
            "Demo", f"当前文件字符数: {len(text)}"
        )
