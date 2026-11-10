# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""会话自动保存 worker（v2.24 从 session.py 拆出）。"""
from app.session_common import *  # noqa: F401,F403,F405


class SessionAutosaveWorker(QObject):
    """
    后台会话自动保存工作器（实验性）。

    将保存操作移至独立线程，避免阻塞主界面。
    仅用于大型会话（打开文件多、内容大）的场景。
    """

    saved = pyqtSignal(bool)
    error = pyqtSignal(str)

    def __init__(self, session_manager: "SessionManager", parent=None):
        super().__init__(parent)
        self.session_manager = session_manager

    def save_async(self, tab_widget, main_window):
        """异步触发保存（需在主线程调用）"""
        QTimer.singleShot(0, lambda: self._do_save(tab_widget, main_window))

    def _do_save(self, tab_widget, main_window):
        try:
            ok = self.session_manager.save(tab_widget, main_window)
            self.saved.emit(ok)
        except Exception as e:
            self.error.emit(str(e))


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys
    import tempfile

    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget

    app = QApplication(sys.argv)

    # 使用临时目录避免污染
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_session_test_")
    session_path = os.path.join(tmp_dir, "session.json")

    print("=" * 60)
    print("SessionManager 测试")
    print("=" * 60)

    manager = SessionManager(filepath=session_path)

    # ========================================================
    # 模拟数据
    # ========================================================
    class FakeEditor:
        def __init__(self, proxy=None):
            self.proxy = proxy

    class FakeProxy:
        def __init__(self, path):
            self.prov = type('P', (), {
                'filepath': path,
                'enc': 'utf-8',
                'document': None,
            })()
            self.document = type('D', (), {
                'filepath': path,
                'encoding': 'utf-8',
            })()
            self.is_modified = False
            self.sc = None

        def get_current_pos(self):
            return 0

    class FakeTabWidget:
        def __init__(self):
            self._tabs = []
            self._current = -1

        def count(self):
            return len(self._tabs)

        def widget(self, i):
            return self._tabs[i]

        def tabText(self, i):
            return f"Tab {i}"

        def currentIndex(self):
            return self._current

        def setCurrentIndex(self, i):
            self._current = i

        def add(self, editor):
            self._tabs.append(editor)

    # ========================================================
    # 测试 1：基本保存/加载
    # ========================================================
    print()
    print("=== 测试 1：保存与加载 ===")

    fake_tabs = FakeTabWidget()
    for path in ["/tmp/a.py", "/tmp/b.py"]:
        fake_tabs.add(FakeEditor(FakeProxy(path)))

    ok = manager.save(fake_tabs)
    print(f"保存结果: {ok}")
    print(f"会话文件存在: {os.path.exists(session_path)}")

    data = manager.load()
    print(f"加载的文件数: {len(data.get('files', []))}")
    print(f"活动标签: {data.get('active_tab')}")

    # ========================================================
    # 测试 2：会话信息
    # ========================================================
    print()
    print("=== 测试 2：会话信息 ===")
    info = manager.get_session_info()
    for k, v in info.items():
        print(f"  {k}: {v}")

    # ========================================================
    # 测试 3：自动备份
    # ========================================================
    print()
    print("=== 测试 3：自动备份 ===")

    # 标记第一个文件为已修改
    fake_tabs.widget(0).proxy.is_modified = True

    count = manager.save_autosave(fake_tabs)
    print(f"自动备份文件数: {count}")
    print(f"备份目录存在: {os.path.isdir(manager.autosave_dir)}")

    # 列出备份
    print()
    print(manager.dump_autosave())

    # ========================================================
    # 测试 4：崩溃恢复检查（不弹对话框）
    # ========================================================
    print()
    print("=== 测试 4：崩溃恢复检查 ===")
    # 用 None 作为 parent 不会弹框（因为没有 QMainWindow）
    print("(跳过实际恢复，仅验证检测逻辑)")

    # 手动检查是否有备份
    backup_exists = os.path.isdir(manager.autosave_dir)
    print(f"检测到备份: {backup_exists}")

    # ========================================================
    # 测试 5：清理
    # ========================================================
    print()
    print("=== 测试 5：清理自动备份 ===")
    manager.clear_autosave()
    print(f"清理后目录存在: {os.path.isdir(manager.autosave_dir)}")

    # ========================================================
    # 测试 6：旧版 API
    # ========================================================
    print()
    print("=== 测试 6：旧版 API ===")
    old_backup_dir = os.path.join(tmp_dir, "autosave_test")
    ok = manager.save_backup(fake_tabs, backup_dir=old_backup_dir)
    print(f"旧版备份: {ok}")
    detected = SessionManager.check_crash_recovery(tmp_dir)
    print(f"检测到备份: {detected}")

    # ========================================================
    # 测试 7：备份列表
    # ========================================================
    print()
    print("=== 测试 7：备份列表 ===")
    backups = manager.list_backups()
    print(f"备份数量: {len(backups)}")

    # ========================================================
    # 测试 8：导出/导入
    # ========================================================
    print()
    print("=== 测试 8：导出/导入 ===")
    export_path = os.path.join(tmp_dir, "exported.json")
    print(f"导出: {manager.export_session(export_path)}")
    print(f"导入: {manager.import_session(export_path)}")

    # ========================================================
    # 打印完整会话
    # ========================================================
    print()
    print("=== 会话内容 ===")
    print(manager.dump())

    # 清理测试目录
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print()
    print("=" * 60)
    print("测试完成")
    print("=" * 60)
    print(repr(manager))
