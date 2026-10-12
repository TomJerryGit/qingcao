# -*- coding: utf-8 -*-
"""JSON 格式化插件"""
import json

from app.plugins import PluginBase


class Plugin(PluginBase):
    NAME = "json_formatter"
    VERSION = "1.0.0"
    DESCRIPTION = "格式化 JSON"
    AUTHOR = "hedongwei"

    def on_activate(self):
        self.api.log("JSON 格式化插件已激活")

        self.api.add_menu(
            "工具/JSON/格式化 (2 空格)", self.format_2,
            shortcut="Ctrl+Alt+J"
        )
        self.api.add_menu(
            "工具/JSON/格式化 (4 空格)", self.format_4
        )
        self.api.add_menu(
            "工具/JSON/压缩", self.compress
        )
        self.api.add_menu(
            "工具/JSON/验证", self.validate
        )
        self.api.add_menu(
            "工具/JSON/排序键", self.sort_keys
        )

    def on_deactivate(self):
        self.api.log("JSON 格式化插件已停用")

    # --------------------------------------------------------
    def _get_json_text(self):
        """获取 JSON 文本"""
        selected = self.api.get_selected_text()
        if selected:
            return selected, True

        text = self.api.get_current_text()
        return text, False

    def _apply(self, new_text, replace_selection):
        """应用结果"""
        if replace_selection:
            self.api.replace_selected_text(new_text)
        else:
            editor = self.api.current_editor()
            if editor and editor.sc:
                editor.sc.setText(new_text)

    def format_2(self):
        self._format(2)

    def format_4(self):
        self._format(4)

    def _format(self, indent):
        """格式化"""
        text, is_selection = self._get_json_text()
        if not text.strip():
            self.api.show_status("没有内容", 2000)
            return

        try:
            data = json.loads(text)
            result = json.dumps(
                data, indent=indent, ensure_ascii=False
            )
            self._apply(result, is_selection)
            self.api.show_status("格式化成功", 2000, "success")
        except json.JSONDecodeError as e:
            self.api.show_message(
                "JSON 错误",
                f"第 {e.lineno} 行 第 {e.colno} 列: {e.msg}"
            )

    def compress(self):
        """压缩"""
        text, is_selection = self._get_json_text()
        if not text.strip():
            return

        try:
            data = json.loads(text)
            result = json.dumps(
                data, separators=(',', ':'), ensure_ascii=False
            )
            self._apply(result, is_selection)
            self.api.show_status("已压缩", 2000, "success")
        except json.JSONDecodeError as e:
            self.api.show_message(
                "JSON 错误",
                f"第 {e.lineno} 行: {e.msg}"
            )

    def validate(self):
        """验证"""
        text, _ = self._get_json_text()
        try:
            data = json.loads(text)
            # 统计
            def count(obj):
                if isinstance(obj, dict):
                    return 1 + sum(count(v) for v in obj.values())
                elif isinstance(obj, list):
                    return 1 + sum(count(v) for v in obj)
                return 1

            total = count(data)
            self.api.show_status(
                f"✓ 有效 JSON ({total} 个节点)", 3000, "success"
            )
        except json.JSONDecodeError as e:
            self.api.show_message(
                "JSON 错误",
                f"第 {e.lineno} 行 第 {e.colno} 列:\n{e.msg}"
            )

    def sort_keys(self):
        """排序键"""
        text, is_selection = self._get_json_text()
        try:
            data = json.loads(text)
            result = json.dumps(
                data, indent=2, ensure_ascii=False, sort_keys=True
            )
            self._apply(result, is_selection)
            self.api.show_status("已排序", 2000, "success")
        except json.JSONDecodeError as e:
            self.api.show_message("JSON 错误", str(e))