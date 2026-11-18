# -*- coding: utf-8 -*-
"""Markdown 预览插件"""

import os

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QDockWidget, QTextBrowser

from app.plugins import PluginBase
from core.plugin_i18n import tr


def extract_headings(text):
    """提取 Markdown 标题 → [(level, title, line)]。"""
    out = []
    for idx, line in enumerate((text or "").splitlines()):
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        level = len(stripped) - len(stripped.lstrip("#"))
        title = stripped[level:].strip()
        if 1 <= level <= 6 and title:
            out.append((level, title, idx + 1))
    return out


class MarkdownPanel(QDockWidget):
    """Markdown 预览面板"""

    def __init__(self, parent=None):
        super().__init__("Markdown 预览", parent)
        self.setObjectName("MarkdownPreviewPanel")

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setFont(QFont("Microsoft YaHei", 11))

        self.setWidget(self.browser)
        self._apply_style()

    def _apply_style(self):
        self._base_qss = """
            QDockWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QDockWidget::title {
                background-color: #2d2d2d;
                padding: 4px 8px;
            }
            QTextBrowser {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                padding: 12px;
                selection-background-color: #264f78;
            }
"""
        self.setStyleSheet(self._base_qss)

    def refresh_theme(self, theme):
        """主题切换：按当前主题适配面板 QSS（v2.14 插件 UI 统一）"""
        try:
            from infrastructure.theme_loader import adapt_qss_colors

            base = getattr(self, "_base_qss", "")
            if base:
                self.setStyleSheet(adapt_qss_colors(base, theme))
        except Exception:
            pass

    def render(self, text):
        """渲染"""
        try:
            self.browser.setMarkdown(text)
        except Exception as e:
            self.browser.setPlainText(f"渲染失败: {e}")


class Plugin(PluginBase):
    NAME = "markdown_preview"
    VERSION = "1.2.0"
    DESCRIPTION = "Markdown 预览"
    AUTHOR = "TomJerry"

    def on_activate(self):
        self.api.log("Markdown 预览插件已激活")
        self._panel = None

        # C2: 避开主窗口的 Ctrl+Shift+M（回放宏）
        self.api.add_menu("视图/Markdown 预览", self.toggle_preview, shortcut="Ctrl+Alt+M")

        # ---- v2.3/v2.4 扩展点 ----
        # 1) 符号：把 Markdown 标题贡献给「大纲」面板（NPP functionList 等价）
        self.api.register_symbol_provider(
            self._symbols, language_ids=["markdown", ".md", ".markdown"]
        )

        # 2) 诊断：把 Markdown 结构问题发布到「问题」面板
        self.api.add_menu("工具/Markdown/检查并报告到问题面板", self.check_and_report)
        self.api.add_menu("工具/Markdown/目录...", self.show_toc)
        self.api.add_menu("工具/Markdown/导出 HTML...", self.export_html)
        # 2) 设置 schema：「工具 → 插件设置」（无需 dialog 权限）
        self.api.register_settings_schema(
            [
                {
                    "key": "check_image_alt",
                    "label": "检查图片缺失 alt",
                    "type": "bool",
                    "default": True,
                },
                {
                    "key": "max_diagnostics",
                    "label": "最多报告条数",
                    "type": "int",
                    "default": 50,
                    "min": 1,
                    "max": 500,
                },
            ]
        )

        self._remote_panel = None
        if getattr(self.api, "is_isolated", False):
            try:
                self._remote_panel = self.api.register_remote_panel(
                    "Markdown 预览", [], self._remote_refresh, kind="markdown"
                )
            except Exception as e:
                self.api.log("远程面板注册失败: %s" % e, "warning")

        # 定时刷新
        self._timer = QTimer()
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

    def on_deactivate(self):
        try:
            self.api.clear_diagnostics()
        except Exception:
            pass
        if self._timer:
            self._timer.stop()
        if self._panel:
            self._panel.close()

    # --------------------------------------------------------
    # v2.3 符号：Markdown 标题 → 大纲
    # --------------------------------------------------------
    def _symbols(self, text, filepath="", language=""):
        """把 # / ## / ### 标题转成大纲符号"""
        items = []
        for idx, line in enumerate((text or "").splitlines()):
            stripped = line.strip()
            if not stripped.startswith("#"):
                continue
            level = len(stripped) - len(stripped.lstrip("#"))
            if level == 0 or level > 6 or len(stripped) <= level:
                continue
            if stripped[level : level + 1] not in (" ", "\t"):
                continue
            title = stripped[level:].strip()
            if not title:
                continue
            items.append(
                {
                    "name": title,
                    "type": "namespace",
                    "line": idx,
                    "indent": level - 1,
                }
            )
        return items

    # --------------------------------------------------------
    # v2.3 诊断：Markdown 结构检查
    # --------------------------------------------------------
    def _diagnose(self, text):
        """返回 [{"line","col","severity","message","code"}]"""
        issues = []
        try:
            max_items = int(self.api.get_config("max_diagnostics", 50))
        except Exception:
            max_items = 50
        try:
            check_alt = bool(self.api.get_config("check_image_alt", True))
        except Exception:
            check_alt = True

        lines = text.splitlines()
        fence_lines = []
        for idx, line in enumerate(lines):
            s = line.strip()
            if s.startswith("```"):
                fence_lines.append(idx)
            if check_alt and "![](" in s:
                issues.append(
                    {
                        "line": idx,
                        "col": max(0, s.find("![](")),
                        "severity": "warning",
                        "message": "图片缺少 alt 文本（空 []）",
                        "code": "MD001",
                    }
                )
            if len(issues) >= max_items:
                return issues
        if len(fence_lines) % 2 == 1:
            issues.append(
                {
                    "line": fence_lines[-1],
                    "col": 0,
                    "severity": "error",
                    "message": "代码围栏未闭合（``` 数量为奇数）",
                    "code": "MD002",
                }
            )
        return issues[:max_items]

    def show_toc(self):
        text = self.api.get_current_text() or ""
        headings = extract_headings(text)
        if not headings:
            self.api.show_status(tr("markdown.no_headings", "没有 Markdown 标题"), 2000)
            return
        lines = [
            "%s%s（第 %d 行）" % ("  " * (level - 1), title, line)
            for level, title, line in headings
        ]
        self.api.show_text_dialog("Markdown 目录", "\n".join(lines), 600, 420)

    def export_html(self):
        if getattr(self.api, "is_isolated", False):
            self.api.show_status(tr("markdown.isolated_export", "隔离模式暂不支持导出"), 2500)
            return
        if self._panel is None:
            self.api.show_status(tr("markdown.open_preview", "请先打开预览"), 2000)
            return
        from PyQt5.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self.api._host_window(), "导出 HTML", "preview.html", "HTML (*.html)"
        )
        if not path:
            return
        try:
            html = self._panel.browser.document().toHtml()
            open(path, "w", encoding="utf-8").write(html)
            self.api.show_status(tr("markdown.exported", "已导出 HTML"), 2000, "success")
        except Exception as e:
            self.api.show_message(tr("markdown.export_failed", "导出失败"), str(e))

    def check_and_report(self):
        """检查当前 Markdown 并把问题发布到「问题」面板"""
        try:
            filepath = self.api.get_current_filepath() or ""
            if not filepath.lower().endswith((".md", ".markdown")):
                self.api.show_status(tr("markdown.not_markdown", "当前文件不是 Markdown"), 2000, "warning")
                return 0
            text = self.api.get_current_text() or ""
            issues = self._diagnose(text)
            self.api.clear_diagnostics()
            if issues:
                n = self.api.publish_diagnostics(issues, filepath=filepath)
                self.api.show_status(tr("markdown.issues", "Markdown 检查：{n} 个问题已报告", n=n), 3000, "warning")
                return n
            self.api.show_status(tr("markdown.ok", "Markdown 检查通过"), 2500, "success")
            return 0
        except Exception as e:
            self.api.log("Markdown 检查失败: %s" % e, "error")
            return 0

    def _remote_refresh(self, text):
        return text or "(无内容)"

    def toggle_preview(self):
        """切换预览"""
        if getattr(self.api, "is_isolated", False):
            if self._remote_panel is None:
                self._remote_panel = self.api.register_remote_panel(
                    "Markdown 预览", [], self._remote_refresh, kind="markdown"
                )
            self.api.show_remote_panel(self._remote_panel)
            return
        if not self._panel:
            self._panel = MarkdownPanel(self.api._host_window())
            # 修复: 使用 Qt 枚举而非裸 int
            self.api._host_window().addDockWidget(Qt.RightDockWidgetArea, self._panel)

        visible = not self._panel.isVisible()
        self._panel.setVisible(visible)
        if visible:
            self._refresh()

    def _refresh(self):
        """刷新"""
        if getattr(self.api, "is_isolated", False):
            return
        if not self._panel or not self._panel.isVisible():
            return

        try:
            filepath = self.api.get_current_filepath()
            if not filepath or not filepath.lower().endswith((".md", ".markdown")):
                return

            text = self.api.get_current_text()
            self._panel.render(text)
        except Exception:
            pass
