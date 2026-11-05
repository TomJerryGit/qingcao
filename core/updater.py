# -*- coding: utf-8 -*-
"""自动更新检查"""

import json
import logging
import os

from PyQt5.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


# P1-1: 版本号唯一来源
try:
    from version import __version__ as _APP_VERSION
except ImportError:  # pragma: no cover - 仅打包异常时触发
    _APP_VERSION = "0.0.0"


UPDATE_CHECK_URL = "https://api.github.com/repos/TomJerryGit/qingcao/releases/latest"


class UpdateChecker(QObject):
    """更新检查器（v2.22：QNetworkAccessManager 主线程异步，无后台 DNS 线程）"""

    check_completed = pyqtSignal(dict)  # 更新信息
    check_failed = pyqtSignal(str)
    no_update = pyqtSignal(str)  # 当前版本

    def __init__(self, current_version: str = _APP_VERSION, parent=None):
        super().__init__(parent)
        self.current_version = current_version
        self._cancel = False
        self._log = logging.getLogger("qingcao.updater")
        self._manager = QNetworkAccessManager(self)
        self._reply = None
        self._timeout = None

    def cancel(self):
        """取消更新检查（退出/关闭时调用）"""
        self._cancel = True
        if self._reply is not None:
            try:
                self._reply.abort()
            except Exception:
                pass

    def check_async(self):
        """异步检查更新（Qt 事件循环内，主线程发起）"""
        if self._cancel or self._reply is not None:
            return
        self._log.debug("更新检查：开始请求 %s", UPDATE_CHECK_URL)
        req = QNetworkRequest(QUrl(UPDATE_CHECK_URL))
        req.setHeader(QNetworkRequest.UserAgentHeader, "QingCaoEditor-update-check")
        self._reply = self._manager.get(req)
        self._reply.finished.connect(self._on_finished)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._on_timeout)
        self._timeout.start(15000)

    def _on_timeout(self):
        if self._reply is not None:
            self._log.warning("更新检查超时，取消请求")
            self._cancel = True
            try:
                self._reply.abort()
            except Exception:
                pass

    def _on_finished(self):
        reply = self._reply
        self._reply = None
        if self._timeout is not None:
            self._timeout.stop()
        if reply is None:
            return
        try:
            if self._cancel:
                self._log.debug("更新检查：已取消，忽略响应")
                return
            if reply.error() != QNetworkReply.NoError:
                self.check_failed.emit(reply.errorString() or "网络错误")
                return
            data = json.loads(bytes(reply.readAll()).decode("utf-8"))
            self._handle_data(data)
        except Exception as e:
            self.check_failed.emit(str(e))
        finally:
            try:
                reply.deleteLater()
            except Exception:
                pass

    def _handle_data(self, data):
        """解析 GitHub Release JSON 并发出信号"""
        latest = data.get("tag_name", "").lstrip("v")
        if not latest:
            self.check_failed.emit("无效的版本信息")
            return
        if self._is_newer(latest, self.current_version):
            assets = data.get("assets", [])
            download_url = data.get("html_url", "")
            for asset in assets:
                name = asset.get("name", "").lower()
                if "windows" in name or "win" in name:
                    download_url = asset.get("browser_download_url", download_url)
                    break
            self.check_completed.emit(
                {
                    "latest_version": latest,
                    "current_version": self.current_version,
                    "download_url": download_url,
                    "release_notes": data.get("body", ""),
                    "published_at": data.get("published_at", ""),
                }
            )
        else:
            self.no_update.emit(self.current_version)

    def check_when_idle(self, delay_ms=15000, retry_ms=3000, max_retries=20):
        """延迟到界面空闲（无模态框）时再检查更新。

        背景：Windows 上后台线程 getaddrinfo 与模态对话框并发可能触发
        fatal exception 0x8001010d；v2.22 起迁移到 Qt 主线程异步并避开该时序。
        """
        self._retries = 0

        def _try():
            if self._cancel:
                return
            from PyQt5.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None and app.activeModalWidget() is not None:
                self._retries += 1
                self._log.debug("更新检查延后：存在模态窗口（第 %d 次）", self._retries)
                if self._retries <= max_retries:
                    QTimer.singleShot(retry_ms, _try)
                return
            self._log.debug("更新检查开始（界面空闲）")
            self.check_async()

        QTimer.singleShot(delay_ms, _try)

    @staticmethod
    def _is_newer(v1, v2):
        """比较版本号"""
        try:

            def parse(v):
                v = v.split("-")[0]
                return [int(x) for x in v.split(".")]

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
        % (update_info["current_version"], update_info["latest_version"])
    )
    title.setStyleSheet("color: #d4d4d4;")
    layout.addWidget(title)

    layout.addWidget(QLabel("更新内容:"))

    notes = QTextBrowser()
    notes.setPlainText(update_info.get("release_notes", "(无说明)"))
    notes.setStyleSheet(
        "background-color: #1e1e1e; color: #d4d4d4; border: 1px solid #3c3c3c; padding: 8px;"
    )
    layout.addWidget(notes)

    # 按钮
    btn_layout = QHBoxLayout()

    download_btn = QPushButton("⬇ 前往下载")
    download_btn.setStyleSheet(
        "background-color: #7ec850; color: white; padding: 8px 16px; border-radius: 4px;"
    )
    download_btn.clicked.connect(
        lambda: QDesktopServices.openUrl(QUrl(update_info["download_url"]))
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
