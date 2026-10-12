# -*- coding: utf-8 -*-
"""崩溃上报器"""
import datetime
import json
import os
import platform
import sys
import traceback
import urllib.parse
from typing import Any, Dict, Optional


# P1-1: 版本号唯一来源
try:
    from version import __version__ as _APP_VERSION
except ImportError:  # pragma: no cover
    _APP_VERSION = "0.0.0"


class CrashReporter:
    """崩溃信息收集与上报"""

    GITHUB_ISSUE_URL = "https://github.com/qingcao-editor/qingcao/issues/new"

    def __init__(self, app_version: str = _APP_VERSION):
        self.app_version = app_version

    def collect_context(self, exc_info=None) -> Dict[str, Any]:
        """收集崩溃上下文"""
        ctx = {
            'app_version': self.app_version,
            'timestamp': datetime.datetime.now().isoformat(),
            'platform': sys.platform,
            'os': platform.platform(),
            'python': sys.version,
            'executable': sys.executable,
            'cwd': os.getcwd(),
        }

        # 依赖版本
        try:
            from PyQt5.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
            ctx['qt'] = QT_VERSION_STR
            ctx['pyqt'] = PYQT_VERSION_STR
        except Exception:
            pass

        try:
            from PyQt5.Qsci import QSCINTILLA_VERSION_STR
            ctx['qscintilla'] = QSCINTILLA_VERSION_STR
        except Exception:
            pass

        # 异常信息
        if exc_info:
            exc_type, exc_value, exc_tb = exc_info
            ctx['exception_type'] = exc_type.__name__
            ctx['exception_message'] = str(exc_value)
            ctx['traceback'] = ''.join(traceback.format_exception(
                exc_type, exc_value, exc_tb
            ))
        else:
            ctx['traceback'] = traceback.format_exc()

        # 打开的文件
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                # 尝试找主窗口
                for w in app.topLevelWidgets():
                    if w.__class__.__name__ == 'MainWindow':
                        if hasattr(w, 'tabs'):
                            files = []
                            for i in range(w.tabs.count()):
                                widget = w.tabs.widget(i)
                                if hasattr(widget, 'proxy'):
                                    proxy = widget.proxy
                                    if proxy and proxy.document:
                                        fp = proxy.document.filepath
                                        files.append(fp or '(untitled)')
                            ctx['open_files'] = files
                            ctx['open_file_count'] = len(files)
                        break
        except Exception:
            pass

        # 已加载插件
        try:
            plugins = []
            plugins_dir = 'plugins'
            if os.path.isdir(plugins_dir):
                for d in os.listdir(plugins_dir):
                    manifest = os.path.join(plugins_dir, d, 'plugin.json')
                    if os.path.exists(manifest):
                        plugins.append(d)
            ctx['plugins'] = plugins
        except Exception:
            pass

        return ctx

    def save_crash_report(self, ctx, output_dir="data/crashes") -> str:
        """保存崩溃报告到文件"""
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(
            output_dir, "crash_" + timestamp + ".json"
        )

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(ctx, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("[CrashReporter] 保存失败: %s" % e)

        return filepath

    def build_github_url(self, ctx) -> str:
        """构建 GitHub Issue URL"""
        title = "[CRASH] %s: %s" % (
            ctx.get('exception_type', 'Error'),
            ctx.get('exception_message', '')[:80]
        )

        body = (
            "## 崩溃报告\n\n"
            "**版本**: %s\n"
            "**平台**: %s\n"
            "**Python**: %s\n"
            "**Qt**: %s\n\n"
            "**异常**: %s\n\n"
            "**消息**: %s\n\n"
            "**堆栈**:\n"
            "```\n%s\n```\n\n"
            "**打开的文件** (%d):\n"
            "%s\n\n"
            "**已加载插件**: %s\n"
            % (
                ctx.get('app_version', '?'),
                ctx.get('os', '?'),
                ctx.get('python', '').split()[0] if ctx.get('python') else '?',
                ctx.get('qt', '?'),
                ctx.get('exception_type', '?'),
                ctx.get('exception_message', '?'),
                ctx.get('traceback', ''),
                ctx.get('open_file_count', 0),
                "\n".join("- " + f for f in ctx.get('open_files', [])[:10]),
                ", ".join(ctx.get('plugins', [])) or "(无)",
            )
        )

        params = {
            'title': title,
            'body': body,
            'labels': 'bug,crash',
        }
        return self.GITHUB_ISSUE_URL + "?" + urllib.parse.urlencode(params)

    def show_crash_dialog(self, parent=None, exc_info=None):
        """显示崩溃对话框"""
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtWidgets import (
            QDialog,
            QHBoxLayout,
            QLabel,
            QMessageBox,
            QPushButton,
            QTextBrowser,
            QVBoxLayout,
        )

        ctx = self.collect_context(exc_info)
        report_path = self.save_crash_report(ctx)
        github_url = self.build_github_url(ctx)

        dlg = QDialog(parent)
        dlg.setWindowTitle("程序遇到错误")
        dlg.resize(600, 500)

        layout = QVBoxLayout(dlg)

        # 标题
        title = QLabel(
            "<h2 style='color:#f14c4c;'>⚠ 程序遇到未预期的错误</h2>"
            "<p>很抱歉给您带来不便。您可以：</p>"
            "<ul>"
            "<li>复制下方信息，提交到 GitHub Issue</li>"
            "<li>或直接点击\"打开 Issue\"按钮</li>"
            "<li>报告已保存到本地，可手动查看</li>"
            "</ul>"
        )
        title.setWordWrap(True)
        title.setStyleSheet("color: #d4d4d4; padding: 8px;")
        layout.addWidget(title)

        # 报告内容
        report = QTextBrowser()
        report.setPlainText(json.dumps(ctx, indent=2, ensure_ascii=False))
        report.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; "
            "border: 1px solid #3c3c3c; padding: 8px; "
            "font-family: Consolas; font-size: 10pt;"
        )
        layout.addWidget(report, 1)

        # 按钮
        btn_layout = QHBoxLayout()

        copy_btn = QPushButton("📋 复制报告")
        copy_btn.clicked.connect(
            lambda: self._copy_to_clipboard(report.toPlainText(), dlg)
        )
        btn_layout.addWidget(copy_btn)

        open_issue_btn = QPushButton("🌐 打开 Issue")
        open_issue_btn.setStyleSheet(
            "background-color: #7ec850; color: white;"
        )
        open_issue_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(github_url))
        )
        btn_layout.addWidget(open_issue_btn)

        btn_layout.addStretch()

        open_folder_btn = QPushButton("📁 打开报告目录")
        open_folder_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(os.path.dirname(report_path))
            )
        )
        btn_layout.addWidget(open_folder_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dlg.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        dlg.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #1177bb; }
        """)

        dlg.exec_()
        return report_path

    def _copy_to_clipboard(self, text, parent=None):
        """复制到剪贴板"""
        from PyQt5.QtWidgets import QApplication, QMessageBox
        QApplication.clipboard().setText(text)
        QMessageBox.information(parent, "已复制", "崩溃报告已复制到剪贴板")


# 全局单例
_reporter = None


def get_crash_reporter(app_version: str = _APP_VERSION):
    global _reporter
    if _reporter is None:
        _reporter = CrashReporter(app_version)
    return _reporter