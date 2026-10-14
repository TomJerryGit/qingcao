#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为会话管理模块，包含：
- SessionManager：会话保存与恢复
- 打开文件列表、光标位置、滚动位置记忆
- 标签顺序、活动标签记忆
- 书签持久化
- 折叠状态持久化
- 窗口几何与布局记忆
- 面板可见性与位置记忆
- 分屏状态记忆
- 自动保存与崩溃恢复
- 会话版本兼容与迁移
- 会话文件原子写入
- 会话文件损坏自修复

新增（v2.1）：
- save_autosave：自动备份未保存文件
- clear_autosave：正常退出时清理自动备份
- check_and_recover_crash：启动时检测并恢复崩溃备份

统一使用 PyQt5（pyqtSignal 而非 Signal）
"""

import datetime
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QDockWidget, QMainWindow, QSplitter


# ============================================================
# 常量定义
# ============================================================
SESSION_FILE = "session.json"
SESSION_VERSION = 2
SESSION_BACKUP_DIR = "data/backups"
MAX_SESSION_BACKUPS = 5
AUTOSAVE_INTERVAL_MS = 120000  # 2 分钟
MAX_RECENT_SESSIONS = 10

# 自动备份目录（相对项目根目录）
# 基于应用根目录的绝对路径（相对路径会随工作目录变化）
try:
    from infrastructure.plugin_loader import app_root_dir as _app_root
    AUTOSAVE_DIR = os.path.join(_app_root(), "backup", "autosave")
except Exception:  # pragma: no cover
    AUTOSAVE_DIR = os.path.join("backup", "autosave")
AUTOSAVE_META = "meta.json"


# ============================================================
# 会话管理器
# ============================================================
class SessionManager(QObject):
    """
    会话管理器。

    职责:
    - 保存/恢复打开的文件、光标位置、滚动位置
    - 保存/恢复标签顺序与活动标签
    - 保存/恢复书签、折叠状态
    - 保存/恢复窗口几何、面板布局
    - 保存/恢复分屏状态
    - 自动保存防止崩溃丢失
    - 会话文件损坏自修复
    - 会话版本兼容与迁移
    - 自动备份未保存文件
    - 崩溃恢复

    信号:
        session_saved(str): 会话保存成功（文件路径）
        session_loaded(str, dict): 会话加载成功（文件路径，数据）
        session_error(str): 会话操作失败（错误信息）
        session_restored(int): 会话恢复完成（恢复的文件数量）
        autosave_saved(int): 自动备份完成（备份的文件数）
        crash_recovered(int): 崩溃恢复完成（恢复的文件数）
    """

    # 信号
    session_saved = pyqtSignal(str)
    session_loaded = pyqtSignal(str, dict)
    session_error = pyqtSignal(str)
    session_restored = pyqtSignal(int)
    autosave_saved = pyqtSignal(int)
    crash_recovered = pyqtSignal(int)

    # --------------------------------------------------------
    def __init__(self, parent: Optional[QObject] = None,
                 filepath: str = SESSION_FILE,
                 enabled: bool = True):
        """
        参数:
            parent: 父 QObject
            filepath: 会话文件路径（默认 session.json）
            enabled: 是否启用会话保存（可由偏好设置控制）
        """
        super().__init__(parent)

        self.filepath = filepath
        self.enabled = enabled

        # 会话数据缓存
        self._session_data: Dict[str, Any] = {}

        # 上一次加载到的面板布局。
        # 用途：面板是延迟构造的，若本次运行从未打开面板，保存时会采集到
        # 空集合；此时沿用这份记录，避免把用户布局覆盖成空。
        self._previous_docks: Dict[str, Any] = {}

        # 自动保存定时器
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(AUTOSAVE_INTERVAL_MS)
        self._autosave_timer.timeout.connect(self._autosave_tick)

        # 引用主窗口（用于恢复时操作）
        self._main_window: Optional[QMainWindow] = None

        # 上次保存时间
        self._last_save_time: float = 0.0

        # 是否处于恢复过程中（避免重复保存）
        self._restoring: bool = False

        # 自动备份路径
        self.autosave_dir = AUTOSAVE_DIR

    # ========================================================
    # 主窗口绑定
    # ========================================================
    def bind_window(self, main_window: QMainWindow):
        """
        绑定主窗口。绑定后可使用 restore() 恢复会话。

        参数:
            main_window: 主窗口实例
        """
        self._main_window = main_window

    # ========================================================
    # 自动保存
    # ========================================================
    def start_autosave(self):
        """启动自动保存定时器"""
        if self.enabled:
            self._autosave_timer.start()

    def stop_autosave(self):
        """停止自动保存定时器"""
        self._autosave_timer.stop()

    def _autosave_tick(self):
        """定时器回调：自动保存会话"""
        if not self.enabled or not self._main_window:
            return

        try:
            # 保存会话
            tabs = self._get_tabs()
            if tabs:
                self.save(tabs, self._main_window)

                # 保存自动备份（未保存的文件）
                self.save_autosave(tabs, self._main_window)
        except Exception as e:
            # 自动保存静默失败，不打断用户
            print(f"[Session] 自动保存失败: {e}")

    def _get_tabs(self):
        """从主窗口获取标签管理器"""
        if not self._main_window:
            return None
        return getattr(self._main_window, 'tabs', None)

    # ========================================================
    # 保存会话
    # ========================================================
    def save(self, tab_widget, main_window: Optional[QMainWindow] = None) -> bool:
        """
        保存当前会话。

        参数:
            tab_widget: 标签管理器（TabManager）
            main_window: 主窗口（可选，若已 bind_window 则忽略）

        返回:
            是否保存成功
        """
        if not self.enabled:
            return False

        if main_window is None:
            main_window = self._main_window

        try:
            data = self._collect_session_data(tab_widget, main_window)
            data['version'] = SESSION_VERSION
            data['saved_at'] = datetime.datetime.now().isoformat()

            # 原子写入
            if self._write_atomic(self.filepath, data):
                self._session_data = data
                self._last_save_time = time.time()
                self.session_saved.emit(self.filepath)
                return True
            return False

        except Exception as e:
            self.session_error.emit(str(e))
            print(f"[Session] 保存失败: {e}")
            return False

    def _collect_session_data(self, tab_widget, main_window) -> Dict[str, Any]:
        """收集会话数据"""
        data: Dict[str, Any] = {
            'files': [],
            'geometry': {},
            'docks': {},
            'splitters': {},
            'active_tab': -1,
            'project': None,
        }

        # 收集打开的文件
        try:
            for i in range(tab_widget.count()):
                editor = tab_widget.widget(i)
                if not hasattr(editor, 'proxy'):
                    continue
                proxy = editor.proxy

                file_info: Dict[str, Any] = {
                    'filepath': None,
                    'cursor_pos': 0,
                    'first_line': 0,
                    'scroll_x': 0,
                    'encoding': 'utf-8',
                    'modified': False,
                    'bookmarks': [],
                    'folded_lines': [],
                    'title': tab_widget.tabText(i),
                }

                # 获取文件路径（兼容 proxy.document）
                try:
                    if proxy.document:
                        file_info['filepath'] = proxy.document.filepath
                        file_info['encoding'] = (
                            proxy.document.encoding or 'utf-8'
                        )
                except Exception:
                    pass

                # 获取 Scintilla 状态
                try:
                    sc = proxy.sc
                    file_info['cursor_pos'] = proxy.get_current_pos()
                    file_info['first_line'] = sc.SendScintilla(
                        sc.SCI_GETFIRSTVISIBLELINE
                    )
                    file_info['scroll_x'] = sc.horizontalScrollBar().value()
                    file_info['modified'] = proxy.is_modified
                    file_info['bookmarks'] = self._get_bookmarks(sc)
                    file_info['folded_lines'] = self._get_folded_lines(sc)
                except Exception:
                    pass

                data['files'].append(file_info)

            data['active_tab'] = tab_widget.currentIndex()

        except Exception as e:
            print(f"[Session] 收集文件信息失败: {e}")

        # 收集窗口几何
        if main_window and hasattr(main_window, 'geometry'):
            try:
                geo = main_window.geometry()
                data['geometry'] = {
                    'x': geo.x(),
                    'y': geo.y(),
                    'w': geo.width(),
                    'h': geo.height(),
                    'maximized': main_window.isMaximized(),
                    'fullscreen': main_window.isFullScreen(),
                }
            except Exception:
                pass

        # 收集面板状态
        #
        # 注意（真实缺陷）：面板是**延迟构造**的，若本次运行从未打开任何面板，
        # `findChildren(QDockWidget)` 会返回空集合，于是这里会把 `docks` 写成
        # **空字典**，在关闭时**覆盖掉用户已有的面板布局** —— 下次启动便
        # 无面板可恢复，界面看起来"功能没了"。
        #
        # 因此：只在**确实采集到面板**时才写入；否则保留原有记录不动。
        if main_window:
            try:
                docks = {}
                for dock in main_window.findChildren(QDockWidget):
                    name = dock.objectName() or dock.windowTitle()
                    if not name:
                        continue
                    docks[name] = {
                        'visible': dock.isVisible(),
                        'floating': dock.isFloating(),
                        'area': int(main_window.dockWidgetArea(dock)),
                    }
                if docks:
                    data['docks'] = docks
                else:
                    # 不覆盖：沿用上一份会话里的面板布局
                    prev = getattr(self, '_previous_docks', None)
                    if prev:
                        data['docks'] = prev
                    else:
                        data.pop('docks', None)
            except Exception:
                pass

        # 收集分屏状态
        if main_window and hasattr(main_window, 'splitter'):
            try:
                splitter = main_window.splitter
                if isinstance(splitter, QSplitter):
                    data['splitters']['main'] = splitter.sizes()
            except Exception:
                pass

        # 收集当前项目
        if main_window and hasattr(main_window, 'current_project'):
            try:
                project = main_window.current_project
                if project and hasattr(project, 'to_dict'):
                    data['project'] = project.to_dict()
            except Exception:
                pass

        return data

    def _get_bookmarks(self, editor) -> List[int]:
        """获取编辑器中所有书签行号（从 0 开始）"""
        bookmarks = []
        try:
            line_count = editor.SendScintilla(editor.SCI_GETLINECOUNT)
            for line in range(line_count):
                if editor.SendScintilla(editor.SCI_MARKERGET, line) & (1 << 0):
                    bookmarks.append(line)
        except Exception:
            pass
        return bookmarks

    def _get_folded_lines(self, editor) -> List[int]:
        """获取已折叠的行号列表"""
        folded = []
        try:
            line_count = editor.SendScintilla(editor.SCI_GETLINECOUNT)
            for line in range(line_count):
                expanded = editor.SendScintilla(
                    editor.SCI_GETFOLDEXPANDED, line
                )
                if expanded == 0:
                    folded.append(line)
        except Exception:
            pass
        return folded

    # ========================================================
    # 原子写入
    # ========================================================
    def _write_atomic(self, filepath: str, data: Dict[str, Any]) -> bool:
        """
        原子写入 JSON 文件。
        写入临时文件后重命名，避免中途失败导致文件损坏。
        """
        try:
            dirpath = os.path.dirname(os.path.abspath(filepath))
            os.makedirs(dirpath, exist_ok=True)

            # 先备份旧文件
            if os.path.exists(filepath):
                self._backup_existing(filepath)

            # 写入临时文件
            fd, tmp_path = tempfile.mkstemp(
                dir=dirpath, prefix='.session_', suffix='.tmp'
            )
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())

                # 原子重命名
                if sys.platform == 'win32' and os.path.exists(filepath):
                    os.replace(tmp_path, filepath)
                else:
                    os.rename(tmp_path, filepath)
                return True
            except Exception:
                # 清理临时文件
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                raise

        except Exception as e:
            print(f"[Session] 原子写入失败: {e}")
            return False

    def _backup_existing(self, filepath: str):
        """备份已存在的会话文件"""
        try:
            os.makedirs(SESSION_BACKUP_DIR, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"session_{timestamp}.json"
            backup_path = os.path.join(SESSION_BACKUP_DIR, backup_name)
            shutil.copy(filepath, backup_path)

            # 清理过多的备份
            self._cleanup_backups()
        except Exception as e:
            print(f"[Session] 备份失败: {e}")

    def _cleanup_backups(self):
        """清理超出数量限制的备份"""
        try:
            if not os.path.exists(SESSION_BACKUP_DIR):
                return
            backups = []
            for name in os.listdir(SESSION_BACKUP_DIR):
                if name.startswith("session_") and name.endswith(".json"):
                    path = os.path.join(SESSION_BACKUP_DIR, name)
                    backups.append((path, os.path.getmtime(path)))
            backups.sort(key=lambda x: x[1], reverse=True)
            for path, _ in backups[MAX_SESSION_BACKUPS:]:
                try:
                    os.remove(path)
                except Exception:
                    pass
        except Exception:
            pass

    # ========================================================
    # 加载会话
    # ========================================================
    def load(self) -> Dict[str, Any]:
        """
        加载会话数据。

        返回:
            会话数据字典（若失败返回空字典）
        """
        if not os.path.exists(self.filepath):
            return {}

        try:
            with open(self.filepath, encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise ValueError("会话文件格式错误")

            # 版本迁移
            data = self._migrate(data)

            self._session_data = data
            self.session_loaded.emit(self.filepath, data)
            return data

        except json.JSONDecodeError as e:
            # JSON 损坏，尝试备份恢复
            self._handle_corrupted_session(f"JSON 解析错误: {e}")
            return {}
        except Exception as e:
            self.session_error.emit(str(e))
            print(f"[Session] 加载失败: {e}")
            return {}

    def _migrate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        会话数据版本迁移。

        参数:
            data: 原始数据

        返回:
            迁移后的数据
        """
        version = data.get('version', 1)

        if version < 2:
            # 从 v1 迁移到 v2
            for file_info in data.get('files', []):
                file_info.setdefault('folded_lines', [])
                file_info.setdefault('scroll_x', 0)
                file_info.setdefault('encoding', 'utf-8')
            data['version'] = 2

        return data

    def _handle_corrupted_session(self, reason: str):
        """处理损坏的会话文件"""
        try:
            # 备份损坏的文件
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs(SESSION_BACKUP_DIR, exist_ok=True)
            broken_path = os.path.join(
                SESSION_BACKUP_DIR,
                f"session.broken.{timestamp}.json"
            )
            shutil.copy(self.filepath, broken_path)

            # 尝试从最近的备份恢复
            restored = self._try_restore_from_backup()
            if restored:
                print("[Session] 已从备份恢复会话")
                self.session_loaded.emit(self.filepath, restored)
            else:
                # 无法恢复，删除损坏的文件
                os.remove(self.filepath)
                print(f"[Session] 会话文件损坏（{reason}），已备份至 {broken_path}")

            self.session_error.emit(reason)

        except Exception as e:
            print(f"[Session] 处理损坏会话失败: {e}")

    def _try_restore_from_backup(self) -> Dict[str, Any]:
        """尝试从最近的备份恢复会话"""
        try:
            if not os.path.exists(SESSION_BACKUP_DIR):
                return {}

            backups = []
            for name in os.listdir(SESSION_BACKUP_DIR):
                if name.startswith("session_") and name.endswith(".json"):
                    path = os.path.join(SESSION_BACKUP_DIR, name)
                    backups.append((path, os.path.getmtime(path)))

            backups.sort(key=lambda x: x[1], reverse=True)
            for path, _ in backups:
                try:
                    with open(path, encoding='utf-8') as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        # 恢复到主文件
                        self._write_atomic(self.filepath, data)
                        return data
                except Exception:
                    continue
        except Exception:
            pass
        return {}

    # ========================================================
    # 恢复会话
    # ========================================================
    def restore(self, tab_widget, main_window: Optional[QMainWindow] = None,
                confirm_recovery: bool = False) -> int:
        """
        恢复会话。

        参数:
            tab_widget: 标签管理器
            main_window: 主窗口
            confirm_recovery: 是否在恢复前弹窗确认

        返回:
            恢复的文件数量
        """
        if main_window is None:
            main_window = self._main_window

        data = self.load()
        if not data:
            return 0

        self._restoring = True
        restored_count = 0

        try:
            # 确认恢复
            if confirm_recovery:
                from PyQt5.QtWidgets import QMessageBox
                files = data.get('files', [])
                existing = [f for f in files
                            if f.get('filepath')
                            and os.path.exists(f['filepath'])]
                if not existing:
                    self._restoring = False
                    return 0
                msg = (f"检测到上次的会话，共 {len(existing)} 个文件。\n"
                       f"是否恢复这些文件？")
                ret = QMessageBox.question(
                    main_window, "恢复会话", msg,
                    QMessageBox.Yes | QMessageBox.No
                )
                if ret != QMessageBox.Yes:
                    self._restoring = False
                    return 0

            # 恢复文件
            files = data.get('files', [])
            for file_info in files:
                try:
                    filepath = file_info.get('filepath')
                    if not filepath or not os.path.exists(filepath):
                        continue

                    proxy = tab_widget.open_file(filepath)
                    if proxy is None:
                        continue

                    # 恢复光标位置
                    cursor_pos = file_info.get('cursor_pos', 0)
                    if cursor_pos > 0:
                        try:
                            sc = proxy.sc
                            max_pos = sc.SendScintilla(
                                sc.SCI_GETLENGTH
                            )
                            pos = min(cursor_pos, max_pos)
                            sc.SendScintilla(sc.SCI_GOTOPOS, pos)
                        except Exception:
                            pass

                    # 恢复滚动位置
                    first_line = file_info.get('first_line', 0)
                    if first_line > 0:
                        try:
                            sc = proxy.sc
                            sc.SendScintilla(
                                sc.SCI_SETFIRSTVISIBLELINE, first_line
                            )
                        except Exception:
                            pass

                    # 恢复水平滚动
                    scroll_x = file_info.get('scroll_x', 0)
                    if scroll_x > 0:
                        try:
                            proxy.sc.horizontalScrollBar().setValue(scroll_x)
                        except Exception:
                            pass

                    # 恢复书签
                    bookmarks = file_info.get('bookmarks', [])
                    for line in bookmarks:
                        try:
                            proxy.sc.markerAdd(line, 0)
                        except Exception:
                            pass

                    # 恢复折叠状态
                    folded_lines = file_info.get('folded_lines', [])
                    for line in folded_lines:
                        try:
                            proxy.sc.SendScintilla(
                                proxy.sc.SCI_TOGGLEFOLD, line
                            )
                        except Exception:
                            pass

                    restored_count += 1

                except Exception as e:
                    print(f"[Session] 恢复文件失败: {e}")
                    continue

            # 恢复活动标签
            active_tab = data.get('active_tab', -1)
            if 0 <= active_tab < tab_widget.count():
                try:
                    tab_widget.setCurrentIndex(active_tab)
                except Exception:
                    pass

            # 恢复窗口几何
            geometry = data.get('geometry', {})
            if geometry and main_window:
                self._restore_geometry(main_window, geometry)

            # 恢复面板状态
            docks_data = data.get('docks', {})
            # 记住上一份布局：本次运行若从未打开面板，保存时不要把它覆盖成空
            self._previous_docks = dict(docks_data or {})
            if docks_data and main_window:
                self._restore_docks(main_window, docks_data)

            # 恢复分屏
            splitters = data.get('splitters', {})
            if splitters and main_window:
                self._restore_splitters(main_window, splitters)

            # 恢复项目
            project = data.get('project')
            if project and main_window and hasattr(main_window, 'open_project'):
                try:
                    pass  # 项目恢复由主窗口处理
                except Exception:
                    pass

            self.session_restored.emit(restored_count)

        except Exception as e:
            self.session_error.emit(str(e))
            print(f"[Session] 恢复失败: {e}")

        finally:
            self._restoring = False

        return restored_count

    def _restore_geometry(self, main_window: QMainWindow,
                          geometry: Dict[str, Any]):
        """恢复窗口几何"""
        try:
            from PyQt5.QtCore import QRect
            x = geometry.get('x', -1)
            y = geometry.get('y', -1)
            w = geometry.get('w', 1100)
            h = geometry.get('h', 750)

            # 确保在屏幕范围内
            from PyQt5.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            if screen:
                screen_geo = screen.availableGeometry()
                if x < screen_geo.left() or x > screen_geo.right() - 100:
                    x = screen_geo.left() + 50
                if y < screen_geo.top() or y > screen_geo.bottom() - 100:
                    y = screen_geo.top() + 50

            main_window.setGeometry(x, y, w, h)

            if geometry.get('maximized'):
                main_window.showMaximized()
            if geometry.get('fullscreen'):
                main_window.showFullScreen()

        except Exception as e:
            print(f"[Session] 恢复几何失败: {e}")

    def _restore_docks(self, main_window: QMainWindow,
                       docks_data: Dict[str, Any]):
        """恢复面板状态

        注意（延迟构造相关）：面板是按需构造的，会话里记录的面板此刻可能
        还不存在。原实现只遍历 `findChildren(QDockWidget)`，对未构造的面板
        直接跳过 —— 于是"上次打开过的面板"再也不会出现。这里改为：先按
        会话记录**构造**对应面板，再设置其可见性。
        """
        # area 值映射（PyQt5 5.15+ 要求必须是 Qt.DockWidgetArea 枚举）
        AREA_MAP = {
            1: Qt.LeftDockWidgetArea,
            2: Qt.RightDockWidgetArea,
            4: Qt.TopDockWidgetArea,
            8: Qt.BottomDockWidgetArea,
        }

        # 会话记录的名字 -> 惰性面板属性名（用于按需构造）
        #   TodoPanel / WordCountPanel 由插件自己创建（是 QDockWidget 子类），
        #   不属于主窗口的惰性面板，因此不在这里映射；它们由插件在激活时
        #   自行按偏好决定是否显示。
        NAME_TO_PANEL = {
            "OutlinePanel": "outline",
            "OutlineEnhancedDock": "outline_enhanced",
            "DirectoryTreeDock": "dir_tree",
            "MinimapDock": "minimap",
            "GlobalSearchPanel": "gsearch",
            "PythonConsole": "console",
            "PluginsPanel": "plugins_panel",
            "PerfMonitor": "perf_monitor",
            "SearchBar": "search_bar",
        }

        try:
            # 1) 先按会话记录构造缺失的面板
            ensure = getattr(main_window, "_ensure_panel", None)
            if callable(ensure):
                for name in list(docks_data.keys()):
                    panel = NAME_TO_PANEL.get(name)
                    if panel:
                        try:
                            ensure(panel)
                        except Exception:
                            pass

            # 2) 再恢复位置与可见性
            for dock in main_window.findChildren(QDockWidget):
                name = dock.objectName() or dock.windowTitle()
                info = docks_data.get(name)
                if not info:
                    continue

                try:
                    if info.get('floating'):
                        dock.setFloating(True)
                    else:
                        area_value = info.get('area', 2)
                        area = AREA_MAP.get(
                            area_value, Qt.RightDockWidgetArea
                        )
                        main_window.addDockWidget(area, dock)
                    dock.setVisible(info.get('visible', True))
                except Exception:
                    pass
        except Exception as e:
            print(f"[Session] 恢复面板失败: {e}")

    def _restore_splitters(self, main_window: QMainWindow,
                           splitters_data: Dict[str, Any]):
        """恢复分屏状态"""
        try:
            main_sizes = splitters_data.get('main')
            if main_sizes and hasattr(main_window, 'splitter'):
                splitter = main_window.splitter
                if isinstance(splitter, QSplitter):
                    splitter.setSizes(main_sizes)
        except Exception as e:
            print(f"[Session] 恢复分屏失败: {e}")

    # ========================================================
    # 自动备份（新增）
    # ========================================================
    def save_autosave(self, tab_widget,
                       main_window: Optional[QMainWindow] = None,
                       auto_save_dir: Optional[str] = None) -> int:
        """
        保存自动备份（未保存的文件）。

        参数:
            tab_widget: 标签管理器
            main_window: 主窗口（可选）
            auto_save_dir: 备份目录（默认 backup/autosave）

        返回:
            成功备份的文件数
        """
        if auto_save_dir is None:
            auto_save_dir = self.autosave_dir

        try:
            os.makedirs(auto_save_dir, exist_ok=True)

            files = []
            for i in range(tab_widget.count()):
                widget = tab_widget.widget(i)
                if not hasattr(widget, 'proxy'):
                    continue
                proxy = widget.proxy
                if not proxy:
                    continue

                # 只备份已修改的文件
                is_modified = getattr(proxy, 'is_modified', False)
                if not is_modified:
                    continue

                # 获取内容
                try:
                    content = proxy.sc.text() if proxy.sc else ""
                except Exception:
                    continue

                if not content:
                    continue

                # 原文件路径
                original = ""
                try:
                    if proxy.document:
                        original = proxy.document.filepath or ""
                except Exception:
                    pass

                # 生成安全的备份文件名
                if original:
                    base = os.path.basename(original)
                    name = self._sanitize_filename(base) + ".tmp"
                else:
                    name = "untitled_%d.tmp" % i

                backup_path = os.path.join(auto_save_dir, name)

                # 写入文件（末尾记录原始路径）
                try:
                    with open(backup_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                        if original:
                            f.write(
                                f"\n\n###QINGCAO_ORIGINAL_PATH:{original}###"
                            )
                except Exception as e:
                    print(f"[Session] 备份 {name} 失败: {e}")
                    continue

                files.append({
                    'backup': name,
                    'original': original,
                    'title': tab_widget.tabText(i),
                })

            # 写元数据
            meta = {
                'timestamp': datetime.datetime.now().isoformat(),
                'count': len(files),
                'files': files,
            }
            meta_path = os.path.join(auto_save_dir, AUTOSAVE_META)
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)

            if files:
                print(f"[Session] 自动备份: {len(files)} 个文件")
                self.autosave_saved.emit(len(files))

            return len(files)

        except Exception as e:
            print(f"[Session] 自动备份失败: {e}")
            return 0

    def clear_autosave(self, auto_save_dir: Optional[str] = None):
        """
        清理自动备份目录（正常退出时调用）。

        参数:
            auto_save_dir: 备份目录（默认 backup/autosave）
        """
        if auto_save_dir is None:
            auto_save_dir = self.autosave_dir

        try:
            if os.path.exists(auto_save_dir):
                shutil.rmtree(auto_save_dir, ignore_errors=True)
                print(f"[Session] 已清理自动备份: {auto_save_dir}")
        except Exception as e:
            print(f"[Session] 清理自动备份失败: {e}")

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """清理文件名中的非法字符"""
        invalid_chars = '<>:"/\\|?*'
        for c in invalid_chars:
            name = name.replace(c, '_')
        return name.strip() or "untitled"

    # ========================================================
    # 崩溃恢复（新增）
    # ========================================================
    def check_and_recover_crash(self, parent=None,
                                 auto_save_dir: Optional[str] = None
                                 ) -> int:
        """
        检查上次是否异常退出，并提供恢复。

        参数:
            parent: 父窗口（用于弹对话框）
            auto_save_dir: 备份目录（默认 backup/autosave）

        返回:
            恢复的文件数量
        """
        if auto_save_dir is None:
            auto_save_dir = self.autosave_dir

        # 检查备份目录
        if not os.path.isdir(auto_save_dir):
            return 0

        meta_path = os.path.join(auto_save_dir, AUTOSAVE_META)
        if not os.path.exists(meta_path):
            return 0

        # 读取元数据
        try:
            with open(meta_path, encoding='utf-8') as f:
                meta = json.load(f)
        except Exception as e:
            print(f"[Session] 读取备份元数据失败: {e}")
            return 0

        files = meta.get('files', [])
        if not files:
            # 清理空目录
            try:
                shutil.rmtree(auto_save_dir, ignore_errors=True)
            except Exception:
                pass
            return 0

        # 计算可以恢复的文件数
        recoverable = []
        for f in files:
            backup_path = os.path.join(auto_save_dir, f.get('backup', ''))
            if os.path.exists(backup_path):
                recoverable.append(f)

        if not recoverable:
            try:
                shutil.rmtree(auto_save_dir, ignore_errors=True)
            except Exception:
                pass
            return 0

        # 询问用户
        try:
            from PyQt5.QtWidgets import QMessageBox
            timestamp = meta.get('timestamp', '')
            if timestamp:
                try:
                    dt = datetime.datetime.fromisoformat(timestamp)
                    time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    time_str = timestamp
            else:
                time_str = "未知时间"

            msg = (
                f"检测到上次未正常退出。\n\n"
                f"备份时间: {time_str}\n"
                f"可恢复文件: {len(recoverable)} 个\n\n"
                f"是否恢复这些文件？"
            )

            reply = QMessageBox.question(
                parent, "崩溃恢复", msg,
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Discard,
                QMessageBox.Yes
            )

            if reply == QMessageBox.Discard:
                try:
                    shutil.rmtree(auto_save_dir, ignore_errors=True)
                except Exception:
                    pass
                return 0

            if reply != QMessageBox.Yes:
                # 用户选择稍后，不删除也不恢复
                return 0

        except Exception as e:
            print(f"[Session] 显示崩溃恢复对话框失败: {e}")
            return 0

        # 恢复文件
        restored = self._recover_files(
            recoverable, auto_save_dir, parent
        )

        # 恢复完成后清理备份目录
        if restored > 0:
            try:
                shutil.rmtree(auto_save_dir, ignore_errors=True)
            except Exception:
                pass

        if restored > 0:
            self.crash_recovered.emit(restored)

        return restored

    def _recover_files(self, recoverable: List[Dict[str, Any]],
                        auto_save_dir: str, parent=None) -> int:
        """
        恢复备份文件。

        返回:
            恢复的数量
        """
        tabs = self._get_tabs()
        if not tabs:
            return 0

        restored = 0

        try:
            from core.content_provider import MemoryProvider

            # 尝试导入 EditorWidget
            EditorWidget = None
            try:
                from ui.editor_view import EditorWidget as EW
                EditorWidget = EW
            except ImportError:
                pass

            for finfo in recoverable:
                backup_path = os.path.join(
                    auto_save_dir, finfo.get('backup', '')
                )

                if not os.path.exists(backup_path):
                    continue

                try:
                    with open(backup_path, encoding='utf-8',
                              errors='replace') as f:
                        content = f.read()

                    # 提取原始路径
                    original_path = finfo.get('original', '')
                    if not original_path and \
                            '###QINGCAO_ORIGINAL_PATH:' in content:
                        idx = content.find('###QINGCAO_ORIGINAL_PATH:')
                        end_idx = content.find('###', idx + 26)
                        if end_idx > 0:
                            original_path = content[idx + 26:end_idx]
                            content = content[:idx].rstrip()

                    # 用内存 provider 加载
                    provider = MemoryProvider()
                    provider.open(initial_text=content)

                    # 用 EditorWidget 或 fallback
                    if EditorWidget is not None:
                        editor = EditorWidget(provider=provider)
                    else:
                        # 无 UI 情况下直接 tab 显示
                        continue

                    # 标题
                    if original_path:
                        title = os.path.basename(original_path) + " [恢复]"
                    else:
                        title = finfo.get('title', '未命名') + " [恢复]"

                    # 添加标签
                    if hasattr(tabs, 'addTab'):
                        idx = tabs.addTab(editor, title)
                        tabs.setCurrentIndex(idx)
                    elif hasattr(tabs, 'add_tab'):
                        tabs.add_tab(title)

                    # 标记为已修改
                    try:
                        if hasattr(editor, 'proxy') and editor.proxy:
                            editor.proxy.sc.setModified(True)
                    except Exception:
                        pass

                    restored += 1

                except Exception as e:
                    print(f"[Session] 恢复 {finfo} 失败: {e}")
                    continue

        except Exception as e:
            print(f"[Session] 恢复过程失败: {e}")
            traceback.print_exc()

        return restored

    # ========================================================
    # 崩溃备份（旧版 API 保留）
    # ========================================================
    def save_backup(self, tab_widget, main_window: Optional[QMainWindow] = None,
                    backup_dir: Optional[str] = None) -> bool:
        """
        保存崩溃恢复备份（旧版 API）。

        参数:
            tab_widget: 标签管理器
            main_window: 主窗口
            backup_dir: 备份目录（默认 backup/autosave_TIMESTAMP）

        返回:
            是否成功
        """
        try:
            if backup_dir is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_dir = os.path.join(
                os.path.dirname(AUTOSAVE_DIR),
                f"autosave_{timestamp}"
            )

            os.makedirs(backup_dir, exist_ok=True)

            # 保存每个未保存的文件内容
            saved_count = 0
            for i in range(tab_widget.count()):
                editor = tab_widget.widget(i)
                if not hasattr(editor, 'proxy'):
                    continue
                proxy = editor.proxy
                if not proxy.is_modified:
                    continue

                filepath = None
                try:
                    if proxy.document:
                        filepath = proxy.document.filepath
                except Exception:
                    pass

                if not filepath:
                    backup_file = os.path.join(
                        backup_dir, f"untitled_{i}.tmp"
                    )
                else:
                    safe_name = os.path.basename(filepath)
                    backup_file = os.path.join(
                        backup_dir, f"{safe_name}.tmp"
                    )

                try:
                    content = proxy.sc.text() if proxy.sc else ""
                    with open(backup_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                        f.write(
                            f"\n\n###QINGCAO_ORIGINAL_PATH:{filepath}###"
                        )
                    saved_count += 1
                except Exception as e:
                    print(f"[Session] 备份文件 {i} 失败: {e}")

            # 保存元数据
            meta = {
                'timestamp': datetime.datetime.now().isoformat(),
                'file_count': saved_count,
                'files': [
                    {
                        'original': None,
                        'backup': os.path.basename(bf)
                    }
                    for bf in os.listdir(backup_dir)
                    if bf.endswith('.tmp')
                ]
            }
            meta_path = os.path.join(backup_dir, "meta.json")
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2)

            print(f"[Session] 崩溃备份: {saved_count} 个文件 -> {backup_dir}")
            return True

        except Exception as e:
            print(f"[Session] 崩溃备份失败: {e}")
            return False

    @staticmethod
    def check_crash_recovery(backup_root: str = "backup") -> Optional[str]:
        """
        检查是否有未处理的崩溃备份（旧版 API）。

        参数:
            backup_root: 备份根目录

        返回:
            最新备份目录路径或 None
        """
        if not os.path.exists(backup_root):
            return None

        backups = []
        try:
            for name in os.listdir(backup_root):
                path = os.path.join(backup_root, name)
                if os.path.isdir(path) and name.startswith("autosave_"):
                    files = [f for f in os.listdir(path) if f.endswith(".tmp")]
                    if files:
                        backups.append((path, os.path.getmtime(path)))
        except Exception:
            return None

        if not backups:
            return None

        backups.sort(key=lambda x: x[1], reverse=True)
        return backups[0][0]

    @staticmethod
    def cleanup_backup(backup_dir: str):
        """清理指定备份目录"""
        try:
            if os.path.exists(backup_dir):
                shutil.rmtree(backup_dir, ignore_errors=True)
        except Exception:
            pass

    @staticmethod
    def cleanup_old_backups(backup_root: str = "backup",
                            keep_days: int = 7):
        """
        清理超过保留天数的备份。

        参数:
            backup_root: 备份根目录
            keep_days: 保留天数
        """
        try:
            if not os.path.exists(backup_root):
                return
            now = time.time()
            cutoff = now - keep_days * 86400
            for name in os.listdir(backup_root):
                path = os.path.join(backup_root, name)
                if os.path.isdir(path) and name.startswith("autosave_"):
                    if os.path.getmtime(path) < cutoff:
                        shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass

    # ========================================================
    # 删除会话
    # ========================================================
    def delete(self) -> bool:
        """删除当前会话文件"""
        try:
            if os.path.exists(self.filepath):
                os.remove(self.filepath)
            self._session_data = {}
            return True
        except Exception as e:
            self.session_error.emit(str(e))
            return False

    def clear(self):
        """清空内存中的会话数据"""
        self._session_data = {}

    # ========================================================
    # 查询
    # ========================================================
    def exists(self) -> bool:
        """检查会话文件是否存在"""
        return os.path.exists(self.filepath)

    def get_session_info(self) -> Dict[str, Any]:
        """
        获取会话信息摘要（用于启动时的提示）。

        返回:
            {
                'exists': bool,
                'file_count': int,
                'saved_at': str,
                'files': list,
                'age_seconds': float,
            }
        """
        info: Dict[str, Any] = {
            'exists': self.exists(),
            'file_count': 0,
            'saved_at': None,
            'files': [],
            'age_seconds': 0,
        }

        if not info['exists']:
            return info

        try:
            data = self.load()
            info['file_count'] = len(data.get('files', []))
            info['saved_at'] = data.get('saved_at')
            info['files'] = [
                f.get('filepath') for f in data.get('files', [])
                if f.get('filepath')
            ]
            if info['saved_at']:
                saved_time = datetime.datetime.fromisoformat(info['saved_at'])
                delta = datetime.datetime.now() - saved_time
                info['age_seconds'] = delta.total_seconds()
        except Exception:
            pass

        return info

    def get_session_data(self) -> Dict[str, Any]:
        """获取当前缓存或文件的会话数据"""
        if not self._session_data:
            self._session_data = self.load()
        return self._session_data

    # ========================================================
    # 备份列表
    # ========================================================
    def list_backups(self) -> List[Tuple[str, float, int]]:
        """
        列出所有备份。

        返回:
            [(路径, 修改时间, 文件数量), ...] 按时间倒序
        """
        result = []
        try:
            if not os.path.exists(SESSION_BACKUP_DIR):
                return result
            for name in os.listdir(SESSION_BACKUP_DIR):
                if name.startswith("session_") and name.endswith(".json"):
                    path = os.path.join(SESSION_BACKUP_DIR, name)
                    mtime = os.path.getmtime(path)
                    try:
                        with open(path, encoding='utf-8') as f:
                            data = json.load(f)
                        count = len(data.get('files', []))
                    except Exception:
                        count = 0
                    result.append((path, mtime, count))
        except Exception:
            pass
        result.sort(key=lambda x: x[1], reverse=True)
        return result

    def restore_from_backup(self, backup_path: str) -> bool:
        """从指定备份恢复会话"""
        try:
            if not os.path.exists(backup_path):
                return False
            with open(backup_path, encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return False
            return self._write_atomic(self.filepath, data)
        except Exception as e:
            print(f"[Session] 从备份恢复失败: {e}")
            return False

    # ========================================================
    # 导出/导入
    # ========================================================
    def export_session(self, filepath: str) -> bool:
        """导出会话到指定文件"""
        try:
            if not self._session_data:
                self._session_data = self.load()
            if not self._session_data:
                return False
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self._session_data, f,
                          indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[Session] 导出失败: {e}")
            return False

    def import_session(self, filepath: str) -> bool:
        """从指定文件导入会话"""
        try:
            with open(filepath, encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return False
            self._session_data = data
            return True
        except Exception as e:
            print(f"[Session] 导入失败: {e}")
            return False

    # ========================================================
    # 调试与信息
    # ========================================================
    def dump(self) -> str:
        """导出会话数据为可读文本"""
        data = self.get_session_data()
        lines = ["会话数据", "=" * 60]
        lines.append(f"版本: {data.get('version', '?')}")
        lines.append(f"保存时间: {data.get('saved_at', '?')}")
        lines.append(f"文件数量: {len(data.get('files', []))}")
        lines.append(f"活动标签: {data.get('active_tab', -1)}")
        lines.append("")

        lines.append("打开的文件:")
        for i, f in enumerate(data.get('files', [])):
            fp = f.get('filepath') or '(未命名)'
            modified = ' [已修改]' if f.get('modified') else ''
            lines.append(f"  {i + 1}. {fp}{modified}")

        lines.append("")
        geo = data.get('geometry', {})
        if geo:
            lines.append(f"窗口几何: {geo.get('w')}x{geo.get('h')} "
                         f"@ ({geo.get('x')}, {geo.get('y')})")

        docks = data.get('docks', {})
        if docks:
            lines.append(f"面板数量: {len(docks)}")

        return "\n".join(lines)

    def dump_autosave(self) -> str:
        """导出自动备份信息"""
        lines = ["自动备份", "=" * 60]

        if not os.path.isdir(self.autosave_dir):
            lines.append("(无自动备份)")
            return "\n".join(lines)

        meta_path = os.path.join(self.autosave_dir, AUTOSAVE_META)
        if not os.path.exists(meta_path):
            lines.append("(无元数据)")
            return "\n".join(lines)

        try:
            with open(meta_path, encoding='utf-8') as f:
                meta = json.load(f)

            lines.append(f"备份时间: {meta.get('timestamp', '?')}")
            lines.append(f"文件数量: {meta.get('count', 0)}")
            lines.append("")
            lines.append("备份的文件:")
            for f in meta.get('files', []):
                orig = f.get('original') or '(未命名)'
                lines.append(f"  - {orig} -> {f.get('backup', '')}")
        except Exception as e:
            lines.append(f"读取失败: {e}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        info = self.get_session_info()
        return (f"<SessionManager exists={info['exists']} "
                f"files={info['file_count']} saved_at={info['saved_at']}>")


# ============================================================
# 会话自动保存工作器（实验性，用于后台保存）
# ============================================================
class SessionAutosaveWorker(QObject):
    """
    后台会话自动保存工作器（实验性）。

    将保存操作移至独立线程，避免阻塞主界面。
    仅用于大型会话（打开文件多、内容大）的场景。
    """

    saved = pyqtSignal(bool)
    error = pyqtSignal(str)

    def __init__(self, session_manager: SessionManager, parent=None):
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