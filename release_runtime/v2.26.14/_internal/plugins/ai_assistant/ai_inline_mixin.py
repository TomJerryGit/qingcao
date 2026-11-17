# -*- coding: utf-8 -*-
"""AI 助手内联补全逻辑（v2.26 从 __init__ 拆出）。"""

from PyQt5.QtCore import QSettings  # noqa: F401

from .ai_common import *  # noqa: F401,F403,F405


class InlineCompleterMixin:
    def _setup_inline_completer(self):
        """创建内联补全器并注册菜单。

        设计取舍：
          * **默认关闭**。每次补全都是一次真实的 AI 请求，有延迟也有
            费用；自动启用会打扰输入并可能产生大量请求。
          * **显式触发**：用户按 Ctrl+Alt+Space 才请求，Ctrl+Alt+Return
            接受建议。不做"输入即请求"。
        """
        try:
            from ui.ai_inline_completer import AIInlineCompleter
        except Exception as e:
            self.api.log("内联补全不可用: %s" % e, "warning")
            self.inline_completer = None
            return

        # 注意：`PluginBase` 继承自 `object`，**不是 QObject**，
        # 因此不能把 `self` 当 parent 传给接受 QObject 的构造器
        # （会抛 "argument 1 has unexpected type 'Plugin'"，
        #  且会让整个插件激活失败 → 所有菜单消失）。
        # 这里用无 parent + 插件实例持强引用的方式保证生命周期。
        try:
            self.inline_completer = AIInlineCompleter(None, None, parent=None)
        except Exception as e:
            self.api.log("创建内联补全器失败: %s" % e, "error")
            self.inline_completer = None
            return
        # 默认关闭，并写入首选项以便持久化
        enabled = False
        try:
            settings = QSettings("QingCao", "AI")
            enabled = settings.value("inline_completion", False, type=bool)
        except Exception:
            pass
        self.inline_completer.set_enabled(enabled)

        # 菜单：开关 + 触发 + 接受
        items = [
            ("工具/AI 助手/⌨ 切换行内补全 (Ghost Text)", self._toggle_inline_completer, None),
            ("工具/AI 助手/⌨ 请求行内补全", self._on_inline_request, "Ctrl+Alt+Space"),
            ("工具/AI 助手/⌨ 接受行内补全", self._on_inline_accept, "Ctrl+Alt+Return"),
        ]
        for path, cb, sc in items:
            try:
                action = self.api.add_menu(path, cb, sc)
                if action:
                    self._menus.append(action)
            except Exception as e:
                self.api.log("注册内联补全菜单失败: %s" % e, "error")

    def _sync_inline_editor(self):
        """让补全器绑定到当前编辑器（切换标签/首次使用时调用）"""
        comp = getattr(self, "inline_completer", None)
        if comp is None:
            return None
        try:
            editor = self.api.current_editor()
            if editor is None:
                return None
            comp.set_client(self._client)
            # 编辑器变了才重新绑定
            if comp.editor is not getattr(editor, "sc", None):
                comp.editor = comp._resolve_scintilla(editor)
                comp._apply_annotation_style()
            return comp
        except Exception:
            return None

    def _toggle_inline_completer(self):
        """开关行内补全"""
        comp = getattr(self, "inline_completer", None)
        if comp is None:
            self.api.show_status("行内补全不可用", 3000, "warning")
            return
        now = not comp.enabled
        comp.set_enabled(now)
        try:
            QSettings("QingCao", "AI").setValue("inline_completion", now)
        except Exception:
            pass
        if now and not self._ensure_client():
            comp.set_enabled(False)
            return
        self.api.show_status(
            "AI 行内补全已%s。按 Ctrl+Alt+Space 请求建议，"
            "Ctrl+Alt+Return 接受。" % ("开启" if now else "关闭"),
            5000,
            "info",
        )

    def _on_inline_request(self):
        """快捷键：请求行内补全"""
        comp = getattr(self, "inline_completer", None)
        if comp is None:
            return
        if not comp.enabled:
            self.api.show_status("AI 行内补全未开启：工具 → AI 助手 → ⌨ 切换行内补全", 4000, "info")
            return
        if not self._ensure_client():
            return
        comp = self._sync_inline_editor()
        if comp is None:
            self.api.show_status("没有可用的编辑器", 3000, "warning")
            return
        if not comp.request_now(force=True):
            # 未发起：可能光标列数不足或正在请求
            if comp._busy:
                self.api.show_status("正在请求补全…", 2000, "info")
            else:
                self.api.show_status("请先把光标移到已有代码行之后（至少 3 列）", 4000, "info")

    def _on_inline_accept(self):
        """快捷键：接受行内补全建议"""
        comp = getattr(self, "inline_completer", None)
        if comp is None or not comp.has_suggestion():
            return
        if comp.accept_suggestion():
            self.api.show_status("已插入 AI 补全（Ctrl+Z 可撤销）", 3000, "success")

    # --------------------------------------------------------
    # 命令面板集成
    # --------------------------------------------------------
