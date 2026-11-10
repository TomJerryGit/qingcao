# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""悬浮窗口（v2.24 从 tabs.py 拆出）。"""
from app.tabs_common import *  # noqa: F401,F403,F405


class DetachedWindow(QMainWindow):
    """
    标签分离后的独立窗口。

    将 EditorWidget 从主窗口移出，放入独立窗口。
    关闭时可将内容重新合并到主窗口（可选）。
    """

    def __init__(self, editor, title: str = "",
                 parent: Optional[QMainWindow] = None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle(title or "青草编辑器 - 独立窗口")
        self.resize(900, 600)

        # 将编辑器设为中央控件
        self.setCentralWidget(editor)
        editor.show()

        # 关闭时提示
        self._closed = False

    def closeEvent(self, event):
        """关闭窗口时的处理"""
        if self._closed:
            event.accept()
            return

        # 检查是否有未保存修改
        has_modified = False
        try:
            if hasattr(self.editor, 'proxy') and self.editor.proxy:
                has_modified = getattr(self.editor.proxy,
                                        'is_modified', False)
        except Exception:
            pass

        if has_modified:
            ret = QMessageBox.question(
                self, "未保存的修改",
                "文件已修改，是否保存？",
                QMessageBox.Save | QMessageBox.Discard |
                QMessageBox.Cancel
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

        self._closed = True
        event.accept()


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

    app = QApplication(sys.argv)

    # 创建主窗口
    win = QMainWindow()
    win.setWindowTitle("青草编辑器 - TabManager 测试")
    win.resize(1000, 700)

    # 创建标签管理器
    tabs = TabManager()
    win.setCentralWidget(tabs)
    win.show()

    # 添加测试标签
    tabs.add_tab("未命名 1")
    tabs.add_tab("未命名 2")

    # 打开测试文件
    test_files = [
        __file__,
        os.path.join(os.path.dirname(__file__), "actions.py"),
        os.path.join(os.path.dirname(__file__), "event_bus.py"),
    ]
    for f in test_files:
        if os.path.exists(f):
            tabs.open_file(f)

    # 显示信息
    print(tabs.dump())
    print()
    print(f"内存使用: {tabs.get_memory_usage()}")
    print(f"打开的标签数: {tabs.count()}")
    print(f"有未保存修改: {tabs.has_unsaved_changes()}")

    # 测试当前编辑器
    proxy = tabs.current_proxy()
    if proxy:
        print(f"当前文件: {tabs.current_filepath()}")

    sys.exit(app.exec_())
