# -*- coding: utf-8 -*-
"""自动更新检查"""
import json
import os
import threading
from typing import Any, Dict, Optional

from PyQt5.QtCore import QObject, pyqtSignal


# P1-1: 版本号唯一来源
try:
    from version import __version__ as _APP_VERSION
except ImportError:  # pragma: no cover - 仅打包异常时触发
    _APP_VERSION = "0.0.0"


UPDATE_CHECK_URL = (
    "https://api.github.com/repos/qingcao-editor/qingcao/releases/latest"
)


class UpdateChecker(QObject):
    """更新检查器"""

    check_completed = pyqtSignal(dict)  # 更新信息
    check_failed = pyqtSignal(str)
    no_update = pyqtSignal(str)  # 当前版本

    def __init__(self, current_version: str = _APP_VERSION, parent=None):
        super().__init__(parent)
        self.current_version = current_version

    def check_async(self):
        """异步检查更新"""
        t = threading.Thread(target=self._check, daemon=True)
        t.start()

    def _check(self):
        """实际检查"""
        try:
            try:
                import requests
                resp = requests.get(UPDATE_CHECK_URL, timeout=10)
                if resp.status_code != 200:
                    self.check_failed.emit(
                        "HTTP " + str(resp.status_code)
                    )
                    return
                data = resp.json()
            except ImportError:
                import urllib.request
                with urllib.request.urlopen(
                    UPDATE_CHECK_URL, timeout=10
                ) as resp:
                    data = json.loads(resp.read().decode('utf-8'))

            latest = data.get('tag_name', '').lstrip('v')
            if not latest:
                self.check_failed.emit("无效的版本信息")
                return

            if self._is_newer(latest, self.current_version):
                # 找到对应平台的下载链接
                assets = data.get('assets', [])
                download_url = data.get('html_url', '')

                for asset in assets:
                    name = asset.get('name', '').lower()
                    if 'windows' in name or 'win' in name:
                        download_url = asset.get('browser_download_url',
                                                 download_url)
                        break

                self.check_completed.emit({
                    'latest_version': latest,
                    'current_version': self.current_version,
                    'download_url': download_url,
                    'release_notes': data.get('body', ''),
                    'published_at': data.get('published_at', ''),
                })
            else:
                self.no_update.emit(self.current_version)

        except Exception as e:
            self.check_failed.emit(str(e))

    @staticmethod
    def _is_newer(v1, v2):
        """比较版本号"""
        try:
            def parse(v):
                v = v.split('-')[0]
                return [int(x) for x in v.split('.')]
            return parse(v1) > parse(v2)
        except Exception:
            return v1 > v2


def show_update_dialog(parent, update_info):
    """显示更新对话框"""
    from PyQt5.QtCore import QUrl
    from PyQt5.QtGui import QDesktopServices
    from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout

    dlg = QDialog(parent)
    dlg.setWindowTitle("发现新版本")
    dlg.resize(500, 400)

    layout = QVBoxLayout(dlg)

    title = QLabel(
        "<h2>🎉 发现新版本</h2>"
        "<p>当前版本: <b>v%s</b></p>"
        "<p>最新版本: <b style='color: #7ec850;'>v%s</b></p>"
        % (update_info['current_version'],
           update_info['latest_version'])
    )
    title.setStyleSheet("color: #d4d4d4;")
    layout.addWidget(title)

    layout.addWidget(QLabel("更新内容:"))

    notes = QTextBrowser()
    notes.setPlainText(update_info.get('release_notes', '(无说明)'))
    notes.setStyleSheet(
        "background-color: #1e1e1e; color: #d4d4d4; "
        "border: 1px solid #3c3c3c; padding: 8px;"
    )
    layout.addWidget(notes)

    # 按钮
    btn_layout = QHBoxLayout()

    download_btn = QPushButton("⬇ 前往下载")
    download_btn.setStyleSheet(
        "background-color: #7ec850; color: white; "
        "padding: 8px 16px; border-radius: 4px;"
    )
    download_btn.clicked.connect(
        lambda: QDesktopServices.openUrl(
            QUrl(update_info['download_url'])
        )
    )
    btn_layout.addWidget(download_btn)

    btn_layout.addStretch()

    later_btn = QPushButton("稍后提醒")
    later_btn.clicked.connect(dlg.reject)
    btn_layout.addWidget(later_btn)

    close_btn = QPushButton("忽略此版本")
    close_btn.clicked.connect(dlg.reject)
    btn_layout.addWidget(close_btn)

    layout.addLayout(btn_layout)

    dlg.exec_()