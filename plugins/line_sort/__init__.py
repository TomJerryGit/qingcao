# -*- coding: utf-8 -*-
"""行排序 — 由 tools/new_plugin.py 生成后实现（P4 模板采用）。"""

from app.plugins import PluginBase


class Plugin(PluginBase):
    NAME = "line_sort"
    VERSION = "1.0.0"
    DESCRIPTION = "选中行/整文件排序（升序、降序、去重）"
    AUTHOR = "QingCao"

    def on_activate(self):
        self.api.log("行排序已激活")
        self.api.add_menu("工具/行排序/升序", lambda: self._sort(False))
        self.api.add_menu("工具/行排序/降序", lambda: self._sort(True))
        self.api.add_menu("工具/行排序/去重升序", lambda: self._sort(False, True))
        self.api.register_settings_schema(
            [
                {"key": "case_sensitive", "label": "区分大小写", "type": "bool", "default": False},
            ]
        )
        self._status = self.api.add_status_item("行排序: 就绪")

    def on_deactivate(self):
        self.api.log("行排序已停用")

    def _case_sensitive(self):
        try:
            return bool(self.api.get_config("case_sensitive", False))
        except Exception:
            return False

    def _sort(self, reverse=False, dedupe=False):
        try:
            selected = self.api.get_selected_text() or ""
        except Exception:
            selected = ""
        is_selection = bool(selected.strip())
        if not is_selection:
            try:
                selected = self.api.get_current_text() or ""
            except Exception:
                selected = ""
        if not selected.strip():
            self.api.show_status("没有可排序的文本", 2000)
            return 0

        lines = selected.splitlines()
        key = (lambda s: s) if self._case_sensitive() else (lambda s: s.lower())
        lines.sort(key=key, reverse=bool(reverse))
        if dedupe:
            seen = set()
            unique = []
            for line in lines:
                k = key(line)
                if k in seen:
                    continue
                seen.add(k)
                unique.append(line)
            lines = unique
        result = "\n".join(lines)
        try:
            if is_selection:
                self.api.replace_selected_text(result)
            else:
                self.api.set_editor_text(result)
        except Exception as e:
            self.api.show_message("行排序失败", str(e))
            return 0
        self.api.show_status("已排序 %d 行" % len(lines), 2000, "success")
        return len(lines)
