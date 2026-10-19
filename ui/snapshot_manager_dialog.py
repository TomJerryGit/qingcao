# -*- coding: utf-8 -*-
"""会话快照管理"""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.snapshot import SnapshotManager


class SnapshotDialog(QDialog):
    """会话快照对话框"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window)
        self.setWindowTitle("会话快照")
        self.resize(500, 400)

        self.main_window = main_window
        self.mgr = SnapshotManager()

        self._build_ui()
        self._apply_style()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "快照可保存当前所有打开的文件、光标位置、窗口布局，"
            "随时一键恢复。"
        ))

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_restore)
        layout.addWidget(self.list_widget, 1)

        # 按钮
        btn_layout = QHBoxLayout()

        new_btn = QPushButton("➕ 新建快照")
        new_btn.clicked.connect(self._on_new)
        btn_layout.addWidget(new_btn)

        restore_btn = QPushButton("↺ 恢复")
        restore_btn.clicked.connect(self._on_restore)
        btn_layout.addWidget(restore_btn)

        delete_btn = QPushButton("🗑 删除")
        delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; }
            QListWidget {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #2d2d2d;
            }
            QListWidget::item:hover { background-color: #2a2d2e; }
            QListWidget::item:selected { background-color: #094771; }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #1177bb; }
        """)

    def refresh(self):
        self.list_widget.clear()
        for snap in self.mgr.list_snapshots():
            created = snap['created_at'][:19].replace('T', ' ')
            item = QListWidgetItem(
                "📸 %s\n    %d 个文件 · %s"
                % (snap['name'], snap['file_count'], created)
            )
            item.setData(Qt.UserRole, snap['name'])
            self.list_widget.addItem(item)

    def _on_new(self):
        name, ok = QInputDialog.getText(
            self, "新建快照", "快照名称:",
            text="快照_" + __import__('datetime').datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )
        )
        if not ok or not name.strip():
            return

        tabs = self.main_window.tabs
        if self.mgr.save_snapshot(name.strip(), tabs, self.main_window):
            QMessageBox.information(self, "成功", "快照已保存")
            self.refresh()
        else:
            QMessageBox.warning(self, "失败", "保存失败")

    def _on_restore(self):
        item = self.list_widget.currentItem()
        if not item:
            return

        name = item.data(Qt.UserRole)

        # ★ 未保存修改保护（接线时补）
        #
        # `SnapshotManager.restore_snapshot()` 会**关闭当前所有标签**，
        # 而 `TabManager.close_tab()` 对每个已修改标签都会弹一次模态确认框。
        # 若用户在恢复途中点了"取消"，就会出现"前面的标签已关、后面的还在"
        # 的**半恢复状态**，且没有回退。
        #
        # 因此这里先统一检查：有未保存修改时，让用户先决定"保存全部再恢复"
        # 还是放弃本次恢复 —— 而不是把一堆模态框丢给用户去逐个点。
        modified = self._collect_modified_tabs()
        if modified:
            preview = "\n".join(
                "  · %s" % os.path.basename(p or "(未命名)")
                for p in modified[:10]
            )
            more = "" if len(modified) <= 10 else \
                "\n  … 以及另外 %d 个" % (len(modified) - 10)
            reply = QMessageBox.warning(
                self, "有未保存的修改",
                "恢复快照会关闭当前所有标签，但以下文件还有未保存的修改：\n\n"
                "%s%s\n\n"
                "是否先保存这些文件再恢复？（选「取消」则本次恢复中止）"
                % (preview, more),
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if reply == QMessageBox.Cancel:
                return
            if reply == QMessageBox.Save:
                failed = self._save_all_modified()
                if failed:
                    QMessageBox.critical(
                        self, "保存失败",
                        "以下文件保存失败，已中止恢复：\n\n%s"
                        % "\n".join("  · %s" % f for f in failed[:10])
                    )
                    return

        reply = QMessageBox.question(
            self, "恢复快照",
            "恢复快照 '%s'？\n\n当前打开的所有标签会被关闭。" % name,
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        count = self.mgr.restore_snapshot(
            name, self.main_window.tabs, self.main_window
        )
        QMessageBox.information(
            self, "成功", "已恢复 %d 个文件" % count
        )

    def _collect_modified_tabs(self) -> list:
        """返回当前有未保存修改的文件路径列表（空串表示未命名）"""
        paths = []
        try:
            tabs = self.main_window.tabs
            for i in range(tabs.count()):
                w = tabs.widget(i)
                proxy = getattr(w, 'proxy', None) if w else None
                if proxy is None:
                    continue
                try:
                    if not proxy.is_modified:
                        continue
                except Exception:
                    continue
                doc = getattr(proxy, 'document', None)
                paths.append(getattr(doc, 'filepath', '') or '')
        except Exception as e:
            print("[Snapshot] 检查未保存修改失败: %s" % e)
        return paths

    def _save_all_modified(self) -> list:
        """保存所有已修改标签，返回保存失败的文件名列表"""
        failed = []
        try:
            tabs = self.main_window.tabs
            for i in range(tabs.count()):
                w = tabs.widget(i)
                proxy = getattr(w, 'proxy', None) if w else None
                if proxy is None:
                    continue
                try:
                    if not proxy.is_modified:
                        continue
                except Exception:
                    continue
                try:
                    ok = proxy.save_file()
                except Exception as e:
                    print("[Snapshot] 保存失败: %s" % e)
                    ok = False
                if not ok:
                    doc = getattr(proxy, 'document', None)
                    failed.append(getattr(doc, 'filepath', '') or "(未命名)")
        except Exception as e:
            print("[Snapshot] 批量保存失败: %s" % e)
        return failed

    def _on_delete(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "确认删除", "删除快照 '%s'？" % name
        )
        if reply == QMessageBox.Yes:
            self.mgr.delete_snapshot(name)
            self.refresh()