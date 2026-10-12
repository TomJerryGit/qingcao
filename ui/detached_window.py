#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""标签分离独立窗口"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow, QMessageBox


class DetachedWindow(QMainWindow):
    """标签分离后的独立窗口"""

    def __init__(self, editor, title="青草编辑器 - 独立窗口", parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle(title)
        self.resize(900, 600)
        self.setCentralWidget(editor)
        editor.show()
        self._closed = False

    def closeEvent(self, event):
        """关闭事件"""
        if self._closed:
            event.accept()
            return

        try:
            if hasattr(self.editor, 'proxy') and self.editor.proxy.is_modified:
                ret = QMessageBox.question(
                    self, "未保存的修改",
                    "文件已修改，是否保存？",
                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
                )

                if ret == QMessageBox.Save:
                    try:
                        self.editor.proxy.save_file()
                    except Exception as e:
                        QMessageBox.critical(self, "保存失败", str(e))
                        event.ignore()
                        return
                elif ret == QMessageBox.Cancel:
                    event.ignore()
                    return

        except Exception:
            pass

        self._closed = True
        event.accept()