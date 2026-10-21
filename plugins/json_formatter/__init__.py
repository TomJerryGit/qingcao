# -*- coding: utf-8 -*-
"""JSON 格式化插件（已迁移到 v2.3/v2.4 扩展点）"""
import json
import re

from app.plugins import PluginBase


class Plugin(PluginBase):
    NAME = "json_formatter"
    VERSION = "1.0.0"
    DESCRIPTION = "格式化 JSON"
    AUTHOR = "hedongwei"

    def on_activate(self):
        self.api.log("JSON 格式化插件已激活")

        # ---- v2.4 扩展点：真实使用（不只是 API 存在）----
        # 1) hover：悬停显示 JSON 键/值或语法错误
        self.api.register_hover_provider(
            self._hover, language_ids=["json", ".json"])
        # 2) 代码操作（右键菜单「代码操作…」）：格式化/压缩/排序
        self.api.register_code_action_provider(
            self._code_actions, language_ids=["json", ".json"])
        # 3) 编辑器右键菜单直达"按设置格式化"
        self.api.add_editor_context_menu(
            "🧩 JSON 格式化（按设置）", self.format_by_settings)
        # 4) 设置界面 schema（自动生成「工具 → 插件设置」对话框）
        self.api.register_settings_schema([
            {"key": "indent", "label": "缩进空格数", "type": "choice",
             "default": 2, "choices": [("2 空格", 2), ("4 空格", 4)]},
            {"key": "sort_keys", "label": "格式化时排序键",
             "type": "bool", "default": False},
        ])

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
        self.api.add_menu(
            "工具/JSON/检查并报告到问题面板", self.check_and_report
        )

    def on_deactivate(self):
        try:
            self.api.clear_diagnostics()
        except Exception:
            pass
        self.api.log("JSON 格式化插件已停用")

    # ========================================================
    # v2.4 扩展点实现
    # ========================================================
    def _settings_indent(self) -> int:
        try:
            value = self.api.get_config("indent", 2)
            return 4 if int(value) == 4 else 2
        except Exception:
            return 2

    def _settings_sort_keys(self) -> bool:
        try:
            return bool(self.api.get_config("sort_keys", False))
        except Exception:
            return False

    def _count_nodes(self, obj) -> int:
        if isinstance(obj, dict):
            return 1 + sum(self._count_nodes(v) for v in obj.values())
        if isinstance(obj, list):
            return 1 + sum(self._count_nodes(v) for v in obj)
        return 1

    def _current_text(self) -> str:
        try:
            return self.api.get_current_text() or ""
        except Exception:
            return ""

    def _hover(self, line, col, filepath="", language=""):
        """悬停提示：JSON 键/值；若该行有语法错误则显示错误"""
        text = self._current_text()
        if not text.strip():
            return ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            if int(line) + 1 == e.lineno:
                return "JSON 语法错误：第 %d 行第 %d 列\n%s" % (
                    e.lineno, e.colno, e.msg)
            return ""
        lines = text.splitlines()
        if 0 <= int(line) < len(lines):
            stripped = lines[int(line)].strip().rstrip(",")
            m = re.match(r'"([^"]+)"\s*:\s*(.*)$', stripped)
            if m:
                value = m.group(2)
                if len(value) > 120:
                    value = value[:117] + "..."
                return "JSON 键：%s\n值：%s" % (m.group(1), value)
        return "JSON 有效（%d 个节点）" % self._count_nodes(data)

    def _code_actions(self, line, col, filepath="", language=""):
        """代码操作：格式化 / 压缩 / 排序（右键菜单「代码操作…」）"""
        text = self._current_text()
        if not text.strip():
            return []
        actions = [{
            "title": "格式化 JSON（按设置：%d 空格%s）" % (
                self._settings_indent(),
                "，排序键" if self._settings_sort_keys() else ""),
            "kind": "quickfix",
            "callback": self.format_by_settings,
        }]
        try:
            json.loads(text)
        except json.JSONDecodeError:
            return actions   # 语法错误时只提供"格式化"（会报错说明原因）
        actions.append({"title": "压缩 JSON", "kind": "refactor",
                        "callback": self.compress})
        actions.append({"title": "排序键并格式化", "kind": "refactor",
                        "callback": self.sort_keys})
        return actions

    def format_by_settings(self):
        """按插件设置格式化当前文档/选区"""
        indent = self._settings_indent()
        sort_keys = self._settings_sort_keys()
        text, is_selection = self._get_json_text()
        if not text.strip():
            self.api.show_status("没有内容", 2000)
            return
        try:
            data = json.loads(text)
            result = json.dumps(data, indent=indent,
                                ensure_ascii=False, sort_keys=sort_keys)
            self._apply(result, is_selection)
            self.api.show_status("格式化成功（%d 空格）" % indent, 2000,
                                 "success")
        except json.JSONDecodeError as e:
            self.api.show_message(
                "JSON 错误",
                "第 %d 行 第 %d 列: %s" % (e.lineno, e.colno, e.msg))

    def check_and_report(self):
        """校验并把错误发布到「问题」面板（v2.3 诊断 API）"""
        text = self._current_text()
        if not text.strip():
            self.api.show_status("没有内容", 2000)
            return
        try:
            data = json.loads(text)
            self.api.clear_diagnostics()
            self.api.show_status(
                "✓ JSON 有效（%d 个节点）" % self._count_nodes(data),
                3000, "success")
        except json.JSONDecodeError as e:
            n = self.api.publish_diagnostics([{
                "line": max(0, e.lineno - 1),
                "col": max(0, e.colno - 1),
                "severity": "error",
                "message": e.msg,
                "code": "JSON001",
            }])
            self.api.show_status("JSON 错误已报告到问题面板", 3000, "warning")
            return n
        return 0

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