#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为标签管理器模块，包含：
- TabManager：多标签管理
- 标签新增、关闭、切换、排序
- 标签脏状态标记（*）
- 只读文件锁图标（🔒）
- Git 状态颜色标记
- 标签右键菜单（关闭其他、关闭右侧、复制路径等）
- 中键关闭标签
- 恢复最近关闭的标签
- 后台标签资源自动释放
- 标签拖拽分离为独立窗口
- 文件外部修改检测
- 事件总线联动

统一使用 PyQt5。

修复记录:
- 统一通过辅助方法 _get_proxy_filepath / _get_proxy_encoding /
  _get_proxy_provider 访问文件信息，避免 proxy.prov / proxy.document.enc
  等旧 API 崩溃
- 兼容新旧两种 EditorProxy 结构（document + prov）
- 所有直接访问 proxy.document / proxy.prov 的地方增加 hasattr 保护
- close_tab: 关闭时收集书签和折叠状态，供恢复使用（P1-4）
- restore_closed_tab: 恢复书签和折叠状态
"""

import logging
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QDateTime, QFileSystemWatcher, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QTabBar,
    QTabWidget,
    QWidget,
)

from app.event_bus import (
    FileClosedEvent,
    FileModifiedEvent,
    FileOpenedEvent,
    FileSavedEvent,
    TabAddedEvent,
    TabChangedEvent,
    TabRemovedEvent,
    bus,
)
from core.content_provider import (
    LocalFileProvider,
    MemoryProvider,
    is_binary_sample,
)


logger = logging.getLogger(__name__)


# ============================================================
# 常量
# ============================================================
MAX_CLOSED_TABS = 20             # 最多记录最近关闭的标签数量
IDLE_RELEASE_MINUTES = 30        # 后台标签闲置多久后释放内容
IDLE_CHECK_INTERVAL_MS = 60000   # 空闲检查间隔

# Git 状态颜色
GIT_MODIFIED_COLOR = QColor("#E5A72D")   # 橙色：已修改
GIT_ADDED_COLOR = QColor("#6A9955")      # 绿色：新增
GIT_DELETED_COLOR = QColor("#F14C4C")    # 红色：已删除
GIT_UNTRACKED_COLOR = QColor("#808080")  # 灰色：未跟踪

# 文件类型标签颜色（用于快速识别）
FILE_TYPE_COLORS = {
    '.py':   QColor("#3572A5"),
    '.pyw':  QColor("#3572A5"),
    '.cpp':  QColor("#f34b7d"),
    '.cc':   QColor("#f34b7d"),
    '.cxx':  QColor("#f34b7d"),
    '.h':    QColor("#f34b7d"),
    '.hpp':  QColor("#f34b7d"),
    '.c':    QColor("#555555"),
    '.js':   QColor("#f1e05a"),
    '.ts':   QColor("#2b7489"),
    '.jsx':  QColor("#61dafb"),
    '.tsx':  QColor("#61dafb"),
    '.java': QColor("#b07219"),
    '.rs':   QColor("#dea584"),
    '.go':   QColor("#00ADD8"),
    '.rb':   QColor("#701516"),
    '.php':  QColor("#4F5D95"),
    '.html': QColor("#e34c26"),
    '.htm':  QColor("#e34c26"),
    '.css':  QColor("#563d7c"),
    '.scss': QColor("#c6538c"),
    '.json': QColor("#f1e05a"),
    '.xml':  QColor("#0060ac"),
    '.md':   QColor("#083fa1"),
    '.txt':  QColor("#999999"),
    '.log':  QColor("#c0c0c0"),
    '.csv':  QColor("#1e8e3e"),
    '.ini':  QColor("#999999"),
    '.cfg':  QColor("#999999"),
    '.yml':  QColor("#cb171e"),
    '.yaml': QColor("#cb171e"),
    '.toml': QColor("#9c4221"),
    '.sh':   QColor("#89e051"),
    '.bat':  QColor("#C1F12E"),
    '.ps1':  QColor("#012456"),
    '.sql':  QColor("#e38c00"),
}

# 节点类型
NODE_TYPE_DIR = 0
NODE_TYPE_FILE = 1
NODE_TYPE_ROOT = 2


# ============================================================
# 标签管理器
# ============================================================
class TabManager(QTabWidget):
    """
    多标签管理器。

    特性:
    - 新建、打开、关闭、切换标签
    - 脏状态标记、只读标记、Git 状态颜色
    - 标签拖拽排序
    - 中键关闭
    - 右键菜单（关闭其他/右侧、复制路径、打开所在目录）
    - 双击标签分离为独立窗口
    - 恢复最近关闭的标签
    - 后台标签资源自动释放
    - 文件外部修改监听

    信号:
        tab_opened(int): 新标签打开（索引）
        tab_closed(int): 标签关闭（索引）
        tab_switched(int, int): 切换（旧索引, 新索引）
        all_tabs_closed(): 所有标签关闭
    """

    tab_opened = pyqtSignal(int)
    tab_closed = pyqtSignal(int)
    tab_switched = pyqtSignal(int, int)
    all_tabs_closed = pyqtSignal()
    # 文件被外部程序修改且需要用户确认重新加载（路径）
    #
    # 为什么用信号：本信号由 `QFileSystemWatcher` 回调发出。在回调里直接
    # 弹模态对话框会重入事件循环并在销毁阶段崩溃（实测 0xC0000005），
    # 因此把"问用户"这一步交给主窗口，在正常事件层级完成。
    file_changed_externally = pyqtSignal(str)

    # --------------------------------------------------------
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # 基础设置
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.setElideMode(Qt.ElideRight)
        self.setUsesScrollButtons(True)

        # 编辑器列表（与标签顺序同步）
        self._editors: List[Any] = []

        # 最近关闭的标签栈（用于 Ctrl+Shift+T 恢复）
        self._closed_tabs: List[Dict[str, Any]] = []

        # 每个标签的最后活动时间（用于空闲释放）
        self._last_active: Dict[Any, QDateTime] = {}

        # 被释放内容的标签缓存
        self._released_content: Dict[Any, str] = {}

        # 文件外部修改监听器
        self._file_watchers: Dict[str, QFileSystemWatcher] = {}
        self._watcher_paths: Dict[str, Any] = {}

        # 是否正在关闭/销毁：关闭后不再响应文件监听回调
        # （在销毁期间弹模态对话框会段错误，见 `_on_file_changed` 说明）
        self._shutting_down = False

        # 当前是否处于恢复过程中
        self._restoring = False

        # 是否正在处理一次外部文件变更（防重入，见 `_on_file_changed`）
        self._handling_file_change = False

        # 上次索引（用于 tab_switched 信号）
        self._last_index = -1

        # 连接信号
        self.tabCloseRequested.connect(self.close_tab)
        self.currentChanged.connect(self._on_current_changed)
        self.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabBar().customContextMenuRequested.connect(
            self._show_tab_context_menu
        )
        self.tabBar().tabMoved.connect(self._on_tab_moved)
        # 支持中键关闭
        self.tabBar().installEventFilter(self)

        # 空闲释放定时器
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(IDLE_CHECK_INTERVAL_MS)
        self._idle_timer.timeout.connect(self._check_idle_tabs)
        self._idle_timer.start()

        # 事件总线联动
        self._connect_events()

    # ========================================================
    # 辅助：统一提取 EditorProxy 的文件信息（兼容新旧 API）
    # ========================================================
    @staticmethod
    def _get_proxy_provider(proxy) -> Any:
        """
        从 EditorProxy 提取 provider。

        兼容：
            - 新 API：proxy.document.provider
            - 旧 API：proxy.prov
        """
        if not proxy:
            return None
        try:
            # 新 API
            if hasattr(proxy, 'document') and proxy.document:
                prov = getattr(proxy.document, 'provider', None)
                if prov is not None:
                    return prov
            # 旧 API
            if hasattr(proxy, 'prov') and proxy.prov:
                return proxy.prov
        except Exception:
            pass
        return None

    @staticmethod
    def _get_proxy_filepath(proxy) -> Optional[str]:
        """
        从 EditorProxy 提取文件路径。

        兼容：
            - 新 API：proxy.document.filepath
            - 旧 API：proxy.prov.filepath
        """
        if not proxy:
            return None
        try:
            # 新 API
            if hasattr(proxy, 'document') and proxy.document:
                fp = getattr(proxy.document, 'filepath', None)
                if fp:
                    return fp
            # 旧 API
            if hasattr(proxy, 'prov') and proxy.prov:
                fp = getattr(proxy.prov, 'filepath', None)
                if fp:
                    return fp
            # 兜底：EditorProxy 自身可能有 filepath 属性
            fp = getattr(proxy, 'filepath', None)
            if fp:
                return fp
        except Exception:
            pass
        return None

    @staticmethod
    def _get_proxy_encoding(proxy) -> str:
        """
        从 EditorProxy 提取编码。

        兼容：
            - 新 API：proxy.document.encoding
            - 旧 API：proxy.prov.enc
        """
        if not proxy:
            return 'utf-8'
        try:
            # 新 API
            if hasattr(proxy, 'document') and proxy.document:
                enc = getattr(proxy.document, 'encoding', None)
                if enc:
                    return enc
                # 兜底：有些旧版 Document 可能叫 enc
                enc = getattr(proxy.document, 'enc', None)
                if enc:
                    return enc
            # 旧 API
            if hasattr(proxy, 'prov') and proxy.prov:
                enc = getattr(proxy.prov, 'enc', None)
                if enc:
                    return enc
            # 兜底：EditorProxy 自身可能有 encoding 属性
            enc = getattr(proxy, 'encoding', None)
            if enc:
                return enc
        except Exception:
            pass
        return 'utf-8'

    # ========================================================
    # 事件总线联动
    # ========================================================
    def _connect_events(self):
        """连接事件总线信号"""
        try:
            bus.file_saved.connect(self._on_file_saved)
        except Exception:
            pass

    def _on_file_saved(self, event: FileSavedEvent):
        """文件保存后更新标签状态"""
        try:
            path = getattr(event, 'path', '')
            if path:
                idx = self.find_tab_by_path(path)
                if idx is not None:
                    widget = self.widget(idx)
                    if hasattr(widget, 'proxy') and widget.proxy:
                        self._update_tab_title(widget)
        except Exception:
            pass

    # ========================================================
    # 事件过滤器（中键关闭）
    # ========================================================
    def eventFilter(self, obj, event):
        """事件过滤器：捕获标签栏的中键点击"""
        try:
            if obj is self.tabBar():
                if event.type() == event.Type.MouseButtonPress:
                    if event.button() == Qt.MiddleButton:
                        index = self.tabBar().tabAt(event.pos())
                        if index >= 0:
                            self.close_tab(index)
                            return True
                # NPP 习惯：双击标签栏空白处新建文档
                if event.type() == event.Type.MouseButtonDblClick:
                    if event.button() == Qt.LeftButton:
                        if self.tabBar().tabAt(event.pos()) < 0:
                            self.add_tab()
                            return True
        except Exception:
            pass
        return super().eventFilter(obj, event)

    # ========================================================
    # 标签新增
    # ========================================================
    def add_tab(self, title: str = "未命名") -> Optional[Any]:
        """
        新增一个空白标签。

        参数:
            title: 标签标题

        返回:
            EditorWidget 实例（或 None 表示失败）
        """
        try:
            from ui.editor_view import EditorWidget

            editor = EditorWidget()
            index = self.addTab(editor, title)
            self.setCurrentIndex(index)
            self._editors.append(editor)

            # 连接脏状态信号（兼容 modified_changed 和 mod_state）
            try:
                if hasattr(editor.proxy, 'modified_changed'):
                    editor.proxy.modified_changed.connect(
                        lambda modified, w=editor: self._update_tab_title(w)
                    )
                elif hasattr(editor.proxy, 'mod_state'):
                    editor.proxy.mod_state.connect(
                        lambda modified, w=editor: self._update_tab_title(w)
                    )
            except Exception:
                pass

            # 记录活动时间
            self._last_active[editor] = QDateTime.currentDateTime()

            # 发射事件
            self.tab_opened.emit(index)
            try:
                bus.emit_event(TabAddedEvent(index=index, title=title))
            except Exception:
                pass

            return editor
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[TabManager] add_tab 失败: {e}")
            return None

    # ========================================================
    # 打开文件
    # ========================================================
    def open_file(self, filepath: str, line: int = 0) -> Optional[Any]:
        """
        打开一个文件到新标签。

        如果文件已打开，则激活现有标签。

        参数:
            filepath: 文件路径
            line: 跳转到的行号（从 0 开始，可选）

        返回:
            EditorProxy 实例或 None
        """
        try:
            filepath = os.path.abspath(filepath)

            # 检查是否已打开
            existing = self.find_tab_by_path(filepath)
            if existing is not None:
                self.setCurrentIndex(existing)
                if line > 0:
                    editor = self.widget(existing)
                    try:
                        editor.SendScintilla(editor.SCI_GOTOLINE, line)
                        editor.setFocus()
                    except Exception:
                        pass
                return self.widget(existing).proxy

            # 检查文件是否存在
            if not os.path.exists(filepath):
                QMessageBox.warning(
                    self, "文件不存在",
                    f"文件不存在：\n{filepath}"
                )
                return None

            if not os.path.isfile(filepath):
                QMessageBox.warning(
                    self, "无法打开",
                    f"路径不是文件：\n{filepath}"
                )
                return None

            # 检查是否二进制文件
            #
            # ★ 修复（混合场景压测实测发现）：
            #   原实现是 `if b'\x00' in chunk` → 判定二进制并弹
            #   「文件可能包含二进制内容，确定要打开吗？」。
            #   但 **UTF-16/UTF-32 文本必然含 NUL 字节**
            #   （ASCII 字符在 UTF-16 里是 `61 00`，换行是 `0A 00`）。
            #   实测：一个正常的 UTF-16 文本被拦下来询问，
            #   用户选「否」后**根本无法打开**。
            #
            #   现在改用 `is_binary_sample()`：有文本 BOM / 可严格 UTF-8 解码 /
            #   像无 BOM 的 UTF-16（NUL 集中在单侧且可打印比例高）都判为文本；
            #   只有 NUL 比例 > 5% 这类才判二进制。
            try:
                with open(filepath, 'rb') as f:
                    chunk = f.read(1024)
                if is_binary_sample(chunk) and not filepath.lower().endswith(
                    ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico',
                     '.pdf', '.zip', '.tar', '.gz', '.exe', '.dll',
                     '.so', '.dylib')
                ):
                    ret = QMessageBox.question(
                        self, "二进制文件",
                        f"文件可能包含二进制内容，确定要打开吗？\n"
                        f"{os.path.basename(filepath)}",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if ret != QMessageBox.Yes:
                        return None
            except PermissionError:
                QMessageBox.warning(
                    self, "权限不足",
                    f"没有权限读取文件：\n{filepath}"
                )
                return None
            except Exception as e:
                QMessageBox.warning(self, "打开失败", str(e))
                return None

            # 创建 EditorWidget
            try:
                from ui.editor_view import EditorWidget

                provider = LocalFileProvider()
                provider.open(filepath)

                editor = EditorWidget(provider=provider)

                # 打开文件（加载内容）
                try:
                    editor.proxy.open_file(filepath)
                except Exception as e:
                    print(f"[TabManager] open_file 加载内容失败: {e}")

                # 释放该文件的映射/句柄
                #
                # 为什么（Windows 文件锁定，实测确认）：
                #   即使**只读** mmap 也会阻止另一进程覆盖写该文件
                #   （`open(path,'w')` 报 `OSError: [Errno 22]`）。
                #   于是"编辑器打开着文件"就足以让 git / 构建工具 / 其它
                #   编辑器无法修改它 —— 外部变更检测与三方合并永远不会
                #   触发，而这正是本模块要支持的核心场景。
                #
                #   只释放**这个标签自己的** provider（不做全堆扫描，
                #   原因见 `_release_provider_handles` 的说明）。
                #   内容已加载进编辑器，后续需要时会由 `_ensure_handle()`
                #   按需重建句柄，因此释放不影响功能。
                try:
                    self._dispose_provider(
                        getattr(editor.proxy.document, 'provider', None)
                    )
                except Exception:
                    pass

                # 设置语法高亮
                if hasattr(editor, 'set_lexer_by_filename'):
                    try:
                        editor.set_lexer_by_filename(filepath)
                    except Exception as e:
                        print(f"[TabManager] 设置语法高亮失败: {e}")

                title = os.path.basename(filepath)
                index = self.addTab(editor, title)
                self.setCurrentIndex(index)
                self._editors.append(editor)

                # 连接脏状态信号
                try:
                    if hasattr(editor.proxy, 'modified_changed'):
                        editor.proxy.modified_changed.connect(
                            lambda modified, w=editor:
                            self._update_tab_title(w)
                        )
                    elif hasattr(editor.proxy, 'mod_state'):
                        editor.proxy.mod_state.connect(
                            lambda modified, w=editor:
                            self._update_tab_title(w)
                        )
                except Exception:
                    pass

                # 记录活动时间
                self._last_active[editor] = QDateTime.currentDateTime()

                # 跳转到指定行
                if line > 0:
                    try:
                        editor.SendScintilla(editor.SCI_GOTOLINE, line)
                    except Exception:
                        pass

                # 应用文件类型颜色
                self._apply_file_type_color(index, filepath)

                # 应用 Git 状态颜色
                try:
                    self._update_git_status(index, filepath)
                except Exception:
                    pass

                # 设置文件监听
                self._setup_file_watcher(filepath, editor)

                # 检查只读
                try:
                    if not os.access(filepath, os.W_OK):
                        editor.setReadOnly(True)
                except Exception:
                    pass

                # 更新标签标题（处理只读锁图标）
                self._update_tab_title(editor)

                # 发射事件
                self.tab_opened.emit(index)
                try:
                    size = os.path.getsize(filepath)
                    bus.emit_event(FileOpenedEvent(
                        path=filepath,
                        size=size,
                        encoding=provider.encoding,
                        is_readonly=not os.access(filepath, os.W_OK)
                    ))
                    bus.emit_event(TabAddedEvent(
                        index=index, title=title, filepath=filepath
                    ))
                except Exception:
                    pass

                return editor.proxy

            except Exception as e:
                import traceback
                traceback.print_exc()
                QMessageBox.critical(
                    self, "打开文件失败",
                    f"无法打开文件：\n{filepath}\n\n错误：{e}"
                )
                return None

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[TabManager] open_file 异常: {e}")
            return None

    def open_files(self, filepaths: List[str]) -> int:
        """
        批量打开多个文件。

        返回:
            成功打开的数量
        """
        count = 0
        for path in filepaths:
            if self.open_file(path):
                count += 1
        return count

    # ========================================================
    # 关闭标签
    # ========================================================
    def close_tab(self, index: int) -> bool:
        """
        关闭指定标签。

        参数:
            index: 标签索引

        返回:
            是否真正关闭（用户可能取消）
        """
        if index < 0 or index >= self.count():
            return False

        widget = self.widget(index)
        if not widget:
            return False

        # 检查是否有 proxy
        if not hasattr(widget, 'proxy'):
            # 无 proxy，直接移除
            self.removeTab(index)
            if widget in self._editors:
                self._editors.remove(widget)
            widget.deleteLater()
            return True

        proxy = widget.proxy

        # 检查是否有未保存的修改
        try:
            is_modified = getattr(proxy, 'is_modified', False)
            if is_modified:
                title = self.tabText(index)
                ret = QMessageBox.question(
                    self, "未保存的修改",
                    f"文件 {title} 已修改，是否保存？",
                    QMessageBox.Save | QMessageBox.Discard |
                    QMessageBox.Cancel,
                    QMessageBox.Save
                )

                if ret == QMessageBox.Save:
                    try:
                        proxy.save_file()
                        if proxy.is_modified:
                            # 保存失败或用户取消
                            return False
                    except Exception as e:
                        QMessageBox.critical(
                            self, "保存失败", str(e)
                        )
                        return False
                elif ret == QMessageBox.Cancel:
                    return False
        except Exception as e:
            print(f"[TabManager] 检查修改状态失败: {e}")

        # 收集关闭信息
        # 使用辅助方法统一提取（兼容新旧 API）
        filepath = self._get_proxy_filepath(proxy)
        encoding = self._get_proxy_encoding(proxy)
        cursor_pos = 0
        first_line = 0

        try:
            if hasattr(proxy, 'get_current_pos'):
                cursor_pos = proxy.get_current_pos()
            if hasattr(widget, 'SendScintilla'):
                first_line = widget.SendScintilla(
                    widget.SCI_GETFIRSTVISIBLELINE
                )
        except Exception as e:
            print(f"[TabManager] 收集关闭信息失败: {e}")

        # 收集书签与折叠状态（P1-4 修复：之前遗漏，导致恢复时丢失）
        bookmarks: List[int] = []
        folded_lines: List[int] = []
        try:
            if hasattr(proxy, 'document') and proxy.document:
                if hasattr(proxy.document, 'get_bookmarks'):
                    bookmarks = list(proxy.document.get_bookmarks())
                if hasattr(proxy.document, 'get_folded_lines'):
                    folded_lines = list(proxy.document.get_folded_lines())
        except Exception as e:
            print(f"[TabManager] 收集书签/折叠失败: {e}")

        info = {
            'filepath': filepath,
            'cursor_pos': cursor_pos,
            'first_line': first_line,
            'title': self.tabText(index),
            'encoding': encoding,
            'bookmarks': bookmarks,
            'folded_lines': folded_lines,
        }

        self._closed_tabs.append(info)
        if len(self._closed_tabs) > MAX_CLOSED_TABS:
            self._closed_tabs.pop(0)

        # 移除文件监听
        if filepath:
            self._remove_file_watcher(filepath)

        # 先中止大文件延迟分块加载（必须在 deleteLater 之前）
        #
        # ★ 修复（真实 UI 压测复现的段错误 0xC0000005）：
        #   大文件（>10MB）靠 `QTimer.singleShot(0, proxy._load_chunk_slice)`
        #   续跑。若用户在加载完成前关掉**单个标签**，Qt 销毁 QScintilla
        #   控件后，已排队的回调仍会执行 `self.sc.append(...)`
        #   → 作用在已销毁的 C++ 对象上 → 段错误。
        #   与 `dispose()` 里的处理同源，这里覆盖"只关一个标签"的路径。
        try:
            abort = getattr(proxy, 'abort_loading', None)
            if callable(abort):
                abort()
        except Exception:
            pass

        # 清理资源
        try:
            if hasattr(proxy, 'close'):
                proxy.close()
        except Exception:
            pass

        # 移除标签
        self.removeTab(index)
        if widget in self._editors:
            self._editors.remove(widget)
        self._last_active.pop(widget, None)
        self._released_content.pop(widget, None)

        try:
            widget.deleteLater()
        except Exception:
            pass

        # 发射事件
        self.tab_closed.emit(index)
        try:
            bus.emit_event(FileClosedEvent(path=filepath or ""))
            bus.emit_event(TabRemovedEvent(index=index))
        except Exception:
            pass

        # 检查是否所有标签都关闭
        if self.count() == 0:
            self.all_tabs_closed.emit()

        return True

    def close_all_tabs(self) -> bool:
        """
        关闭所有标签。

        返回:
            是否全部关闭（用户可能取消）
        """
        for i in range(self.count() - 1, -1, -1):
            if not self.close_tab(i):
                return False
        return True

    def close_other_tabs(self, keep_index: int):
        """关闭除指定索引外的所有标签"""
        for i in range(self.count() - 1, -1, -1):
            if i != keep_index:
                self.close_tab(i)

    def close_tabs_to_right(self, from_index: int):
        """关闭指定索引右侧的所有标签"""
        for i in range(self.count() - 1, from_index, -1):
            self.close_tab(i)

    def close_tabs_to_left(self, from_index: int):
        """关闭指定索引左侧的所有标签"""
        for i in range(from_index - 1, -1, -1):
            self.close_tab(i)

    # ========================================================
    # 恢复关闭的标签
    # ========================================================
    def restore_closed_tab(self) -> bool:
        """
        恢复最近关闭的标签。

        修复说明（P1-4）:
            - 增加书签和折叠状态的恢复。
            - 之前在 close_tab 中未收集，导致恢复时丢失。

        返回:
            是否成功恢复
        """
        if not self._closed_tabs:
            return False

        info = self._closed_tabs.pop()
        filepath = info.get('filepath')

        if not filepath or not os.path.exists(filepath):
            # 文件不存在，跳过
            if self._closed_tabs:
                return self.restore_closed_tab()
            return False

        proxy = self.open_file(filepath)
        if proxy is None:
            return False

        # 恢复光标和滚动
        try:
            cursor_pos = info.get('cursor_pos', 0)
            if cursor_pos > 0:
                max_pos = proxy.sc.SendScintilla(
                    proxy.sc.SCI_GETLENGTH
                )
                proxy.sc.SendScintilla(
                    proxy.sc.SCI_GOTOPOS, min(cursor_pos, max_pos)
                )
        except Exception:
            pass

        try:
            first_line = info.get('first_line', 0)
            if first_line > 0:
                proxy.sc.SendScintilla(
                    proxy.sc.SCI_SETFIRSTVISIBLELINE, first_line
                )
        except Exception:
            pass

        # 恢复书签（P1-4 修复）
        try:
            bookmarks = info.get('bookmarks', []) or []
            for line in bookmarks:
                try:
                    # Scintilla 标记号 0 为书签（与 EditorWidget 中定义一致）
                    proxy.sc.markerAdd(line, 0)
                    # 同步到 document
                    if hasattr(proxy, 'document') and proxy.document:
                        if hasattr(proxy.document, 'add_bookmark'):
                            proxy.document.add_bookmark(line)
                except Exception:
                    continue
        except Exception as e:
            print(f"[TabManager] 恢复书签失败: {e}")

        # 恢复折叠状态（P1-4 修复）
        try:
            folded_lines = info.get('folded_lines', []) or []
            for line in folded_lines:
                try:
                    proxy.sc.SendScintilla(
                        proxy.sc.SCI_TOGGLEFOLD, line
                    )
                    # 同步到 document
                    if hasattr(proxy, 'document') and proxy.document:
                        if hasattr(proxy.document, 'add_fold'):
                            proxy.document.add_fold(line)
                except Exception:
                    continue
        except Exception as e:
            print(f"[TabManager] 恢复折叠失败: {e}")

        return True

    def has_closed_tabs(self) -> bool:
        """检查是否有可恢复的已关闭标签"""
        return len(self._closed_tabs) > 0

    # ========================================================
    # 查找标签
    # ========================================================
    def find_tab_by_path(self, filepath: str) -> Optional[int]:
        """
        根据文件路径查找标签索引。

        参数:
            filepath: 文件路径

        返回:
            标签索引或 None
        """
        if not filepath:
            return None

        target = os.path.abspath(filepath)

        for i in range(self.count()):
            widget = self.widget(i)
            if not hasattr(widget, 'proxy'):
                continue
            proxy = widget.proxy
            if not proxy:
                continue

            # 使用辅助方法统一提取（兼容新旧 API）
            fp = self._get_proxy_filepath(proxy)
            if fp:
                try:
                    if os.path.abspath(fp) == target:
                        return i
                except Exception:
                    pass

        return None

    def find_tab_by_title(self, title: str) -> Optional[int]:
        """根据标题查找标签索引"""
        for i in range(self.count()):
            if self.tabText(i) == title:
                return i
        return None

    def get_open_files(self) -> List[str]:
        """获取所有打开的文件路径列表"""
        files = []
        for i in range(self.count()):
            widget = self.widget(i)
            if not hasattr(widget, 'proxy'):
                continue
            proxy = widget.proxy
            if not proxy:
                continue

            # 使用辅助方法
            fp = self._get_proxy_filepath(proxy)
            if fp:
                files.append(fp)

        return files

    # ========================================================
    # 当前编辑器访问
    # ========================================================
    def current_proxy(self) -> Optional[Any]:
        """获取当前编辑器的代理"""
        widget = self.currentWidget()
        if widget and hasattr(widget, 'proxy'):
            return widget.proxy
        return None

    def current_editor(self) -> Optional[Any]:
        """获取当前编辑器控件"""
        widget = self.currentWidget()
        return widget

    def current_filepath(self) -> Optional[str]:
        """获取当前文件路径"""
        proxy = self.current_proxy()
        if not proxy:
            return None

        # 使用辅助方法
        return self._get_proxy_filepath(proxy)

    # ========================================================
    # 标签标题更新
    # ========================================================
    def _update_tab_title(self, widget):
        """更新标签标题（脏标志、只读锁、文件名）"""
        if not widget:
            return

        try:
            index = self.indexOf(widget)
            if index < 0:
                return

            title = self.tabText(index)

            # 去掉已有的标记
            for prefix in ('🔒 ', '● '):
                if title.startswith(prefix):
                    title = title[len(prefix):]
            title = title.rstrip(' *').rstrip()

            # 只读标记
            is_readonly = False
            try:
                if hasattr(widget, 'proxy') and widget.proxy:
                    fp = self._get_proxy_filepath(widget.proxy)
                    if fp and os.path.exists(fp):
                        is_readonly = not os.access(fp, os.W_OK)
            except Exception:
                pass

            if is_readonly:
                title = '🔒 ' + title

            # 脏标志
            try:
                if hasattr(widget, 'proxy') and widget.proxy:
                    if getattr(widget.proxy, 'is_modified', False):
                        title = title + ' *'
            except Exception:
                pass

            self.setTabText(index, title)
        except Exception as e:
            print(f"[TabManager] 更新标题失败: {e}")

    def update_all_titles(self):
        """更新所有标签的标题"""
        for i in range(self.count()):
            widget = self.widget(i)
            if widget:
                self._update_tab_title(widget)

    # ========================================================
    # 文件类型颜色
    # ========================================================
    def _apply_file_type_color(self, index: int, filepath: str):
        """根据文件类型设置标签文本颜色"""
        if not filepath:
            return
        try:
            ext = os.path.splitext(filepath)[1].lower()
            color = FILE_TYPE_COLORS.get(ext)
            if color:
                self.tabBar().setTabTextColor(index, color)
        except Exception:
            pass

    def _apply_git_status_color(self, index: int, status: str):
        """根据 Git 状态设置标签颜色"""
        color_map = {
            'M': GIT_MODIFIED_COLOR,
            'A': GIT_ADDED_COLOR,
            'D': GIT_DELETED_COLOR,
            '?': GIT_UNTRACKED_COLOR,
            'R': GIT_MODIFIED_COLOR,
        }
        color = color_map.get(status)
        if color:
            try:
                self.tabBar().setTabTextColor(index, color)
            except Exception:
                pass

    def _update_git_status(self, index: int, filepath: str):
        """更新指定文件的 Git 状态颜色"""
        if not filepath or not os.path.exists(filepath):
            return

        try:
            # 查找 .git 目录
            dirpath = os.path.dirname(filepath)
            git_root = None
            check_path = dirpath

            while check_path != os.path.dirname(check_path):
                if os.path.isdir(os.path.join(check_path, '.git')):
                    git_root = check_path
                    break
                check_path = os.path.dirname(check_path)

            if not git_root:
                return

            # 执行 git status
            result = subprocess.run(
                ['git', '-C', git_root, 'status', '--porcelain',
                 '--', filepath],
                capture_output=True, text=True, timeout=2,
                encoding='utf-8', errors='replace'
            )

            if result.returncode == 0 and result.stdout.strip():
                status = result.stdout.strip()[0]
                self._apply_git_status_color(index, status)

        except Exception:
            pass

    def refresh_git_status(self):
        """刷新所有标签的 Git 状态"""
        for i in range(self.count()):
            widget = self.widget(i)
            if not hasattr(widget, 'proxy'):
                continue
            proxy = widget.proxy
            if not proxy:
                continue

            fp = self._get_proxy_filepath(proxy)
            if fp:
                self._update_git_status(i, fp)

    # ========================================================
    # 标签栏拖动/切换
    # ========================================================
    def _on_tab_moved(self, from_index: int, to_index: int):
        """标签顺序变更时同步 _editors 列表"""
        try:
            if 0 <= from_index < len(self._editors):
                editor = self._editors.pop(from_index)
                self._editors.insert(to_index, editor)
        except (IndexError, ValueError):
            pass

    def _on_current_changed(self, index: int):
        """
        当前标签变更。

        修复说明:
            - 使用 _get_proxy_filepath 辅助方法，避免
              proxy.prov / proxy.document.enc 属性访问崩溃
        """
        old_index = self._last_index
        self._last_index = index

        widget = self.widget(index) if index >= 0 else None
        if widget:
            self._last_active[widget] = QDateTime.currentDateTime()

            # 恢复被释放的内容
            #
            # 修复（审计用例 test_restore_after_release_keeps_clean_state）：
            #   `setText()` 会触发 SCN_MODIFIED，被 `_on_scintilla_modified`
            #   当成**用户编辑** → 标签立刻显示 '*'，即使内容与磁盘一致。
            #   恢复是程序行为，必须抑制回调。逻辑抽到
            #   `_restore_released_content`，与"释放"对称、可单独测试。
            self._restore_released_content(widget)

        # 发射信号
        self.tab_switched.emit(old_index, index)
        try:
            title = self.tabText(index) if index >= 0 else ""
            bus.emit_event(TabChangedEvent(
                index=index, old_index=old_index, title=title
            ))
        except Exception:
            pass

        # 刷新 Git 状态
        if index >= 0 and widget:
            try:
                if hasattr(widget, 'proxy') and widget.proxy:
                    fp = self._get_proxy_filepath(widget.proxy)
                    if fp:
                        self._update_git_status(index, fp)
            except Exception:
                pass

    # ========================================================
    # 右键菜单
    # ========================================================
    def _show_tab_context_menu(self, pos):
        """显示标签右键菜单"""
        try:
            index = self.tabBar().tabAt(pos)
            if index < 0:
                return

            menu = QMenu(self)

            # 关闭当前
            close_act = menu.addAction("❌ 关闭")
            close_act.triggered.connect(lambda: self.close_tab(index))

            # 关闭其他
            if self.count() > 1:
                close_others_act = menu.addAction("关闭其他标签")
                close_others_act.triggered.connect(
                    lambda: self.close_other_tabs(index)
                )

            # 关闭右侧
            if index < self.count() - 1:
                close_right_act = menu.addAction("关闭右侧标签")
                close_right_act.triggered.connect(
                    lambda: self.close_tabs_to_right(index)
                )

            # 关闭左侧
            if index > 0:
                close_left_act = menu.addAction("关闭左侧标签")
                close_left_act.triggered.connect(
                    lambda: self.close_tabs_to_left(index)
                )

            menu.addSeparator()

            # 文件相关操作
            widget = self.widget(index)
            filepath = None

            if widget and hasattr(widget, 'proxy') and widget.proxy:
                filepath = self._get_proxy_filepath(widget.proxy)

            if filepath:
                copy_path_act = menu.addAction("📋 复制文件路径")
                copy_path_act.triggered.connect(
                    lambda: self._copy_file_path(filepath)
                )

                copy_name_act = menu.addAction("📋 复制文件名")
                copy_name_act.triggered.connect(
                    lambda: self._copy_file_name(filepath)
                )

                menu.addSeparator()

                open_folder_act = menu.addAction("📂 打开文件所在位置")
                open_folder_act.triggered.connect(
                    lambda: self._open_file_location(filepath)
                )

                open_system_act = menu.addAction("🌐 用系统默认程序打开")
                open_system_act.triggered.connect(
                    lambda: self._open_with_system(filepath)
                )

                menu.addSeparator()

            # 复制标签标题
            copy_title_act = menu.addAction("📋 复制标签标题")
            copy_title_act.triggered.connect(
                lambda: QApplication.clipboard().setText(
                    self.tabText(index)
                )
            )

            # 重命名标签（仅未命名文件）
            if widget and hasattr(widget, 'proxy') and widget.proxy:
                fp = self._get_proxy_filepath(widget.proxy)

                if not fp:
                    rename_act = menu.addAction("✏ 重命名标签")
                    rename_act.triggered.connect(
                        lambda: self._rename_tab(index)
                    )

            menu.addSeparator()

            # 恢复关闭的标签
            if self.has_closed_tabs():
                restore_act = menu.addAction("↩ 恢复关闭的标签")
                restore_act.triggered.connect(self.restore_closed_tab)

            menu.addSeparator()

            # 在新窗口打开
            split_act = menu.addAction("⬌ 在新窗口打开")
            split_act.triggered.connect(lambda: self._detach_tab(index))

            # 显示菜单
            menu.exec_(self.tabBar().mapToGlobal(pos))
        except Exception as e:
            print(f"[TabManager] 右键菜单失败: {e}")

    def _copy_file_path(self, filepath: str):
        """复制文件路径到剪贴板"""
        QApplication.clipboard().setText(filepath)
        self._show_status("路径已复制到剪贴板")

    def _copy_file_name(self, filepath: str):
        """复制文件名到剪贴板"""
        QApplication.clipboard().setText(os.path.basename(filepath))
        self._show_status("文件名已复制到剪贴板")

    def _open_file_location(self, filepath: str):
        """打开文件所在目录"""
        try:
            folder = os.path.dirname(filepath)
            if sys.platform == 'win32':
                # P1-B1: /select, 必须作为单个参数
                subprocess.Popen(
                    ['explorer',
                     f'/select,{filepath.replace("/", chr(92))}']
                )
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', '-R', filepath])
            else:
                subprocess.Popen(['xdg-open', folder])
        except Exception as e:
            self._show_status(f"打开目录失败: {e}")

    def _open_with_system(self, filepath: str):
        """用系统默认程序打开文件"""
        try:
            if sys.platform == 'win32':
                os.startfile(filepath)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', filepath])
            else:
                subprocess.Popen(['xdg-open', filepath])
        except Exception as e:
            self._show_status(f"打开失败: {e}")

    def _rename_tab(self, index: int):
        """重命名标签（仅未命名文件可重命名）"""
        current = self.tabText(index)
        title, ok = QInputDialog.getText(
            self, "重命名标签", "新名称:", text=current
        )
        if ok and title:
            self.setTabText(index, title)

    def _detach_tab(self, index: int):
        """将标签分离为独立窗口"""
        widget = self.widget(index)
        if not widget:
            return

        # 检查是否有未保存的修改
        has_modified = False
        try:
            if hasattr(widget, 'proxy') and widget.proxy:
                has_modified = getattr(
                    widget.proxy, 'is_modified', False
                )
        except Exception:
            pass

        if has_modified:
            ret = QMessageBox.question(
                self, "分离标签",
                "分离标签前建议先保存文件。是否继续？",
                QMessageBox.Yes | QMessageBox.No
            )
            if ret != QMessageBox.Yes:
                return

        try:
            # 从当前标签移除
            title = self.tabText(index)
            self.removeTab(index)
            if widget in self._editors:
                self._editors.remove(widget)

            # 创建独立窗口
            from ui.detached_window import DetachedWindow
            detached = DetachedWindow(widget, title)
            detached.show()

        except ImportError:
            self._show_status("独立窗口功能不可用")
        except Exception as e:
            self._show_status(f"分离标签失败: {e}")

    # ========================================================
    # 文件外部修改监听
    # ========================================================
    def _setup_file_watcher(self, filepath: str, editor):
        """为文件设置外部修改监听"""
        if filepath in self._file_watchers:
            return

        try:
            watcher = QFileSystemWatcher(self)
            watcher.addPath(filepath)
            watcher.fileChanged.connect(
                lambda path, w=editor: self._on_file_changed(path, w)
            )
            self._file_watchers[filepath] = watcher
            self._watcher_paths[filepath] = editor
        except Exception as e:
            print(f"[TabManager] 设置文件监听失败: {e}")

    def dispose(self):
        """释放全部资源（关闭文件监听、provider 句柄）

        应在主窗口关闭时调用。修复两个真实问题：
          1. **段错误**：`QFileSystemWatcher` 的回调若在窗口销毁过程中
             触发，会弹模态对话框并访问正在析构的 Qt 对象（实测崩溃，
             见 `_on_file_changed`）。这里先置 `_shutting_down`，
             再断开并删除全部 watcher。
          2. **句柄泄漏**：每个标签的 provider 会持有文件句柄；不释放
             会在 Windows 上阻止文件被外部程序修改，且随标签数累积。
        """
        self._shutting_down = True

        # 第一步：中止所有标签的"大文件延迟分块加载"
        #
        # ★ 修复（真实 UI 压测复现的段错误 0xC0000005）：
        #   大文件（>10MB）先同步加载一部分，其余靠
        #   `QTimer.singleShot(0, proxy._load_chunk_slice)` 续跑。
        #   若用户在加载完成前关标签/关窗口，Qt 会销毁 QScintilla 控件，
        #   但**已排队的定时器回调仍会执行** → `self.sc.append(...)`
        #   作用在已销毁的 C++ 对象上 → 进程段错误，无 Python 异常可捕获
        #   （用户看到"关窗口时闪退"）。
        #
        #   必须放在 dispose 的**最前面**（早于释放 provider 句柄），
        #   否则回调可能在两者之间被事件循环调度到。
        try:
            for i in range(self.count()):
                w = self.widget(i)
                proxy = getattr(w, 'proxy', None) if w else None
                abort = getattr(proxy, 'abort_loading', None)
                if callable(abort):
                    abort()
        except Exception as e:
            logger.debug("中止延迟加载失败: %s", e)

        try:
            for path, watcher in list(self._file_watchers.items()):
                try:
                    watcher.fileChanged.disconnect()
                except Exception:
                    pass
                try:
                    watcher.removePaths(watcher.files())
                except Exception:
                    pass
                try:
                    watcher.deleteLater()
                except Exception:
                    pass
                self._file_watchers.pop(path, None)
            self._watcher_paths.clear()
        except Exception as e:
            logger.debug("释放文件监听失败: %s", e)

        # 释放各标签 provider 的映射/句柄
        try:
            for i in range(self.count()):
                widget = self.widget(i)
                if not widget:
                    continue
                proxy = getattr(widget, 'proxy', None)
                doc = getattr(proxy, 'document', None) if proxy else None
                self._dispose_provider(getattr(doc, 'provider', None))
        except Exception as e:
            logger.debug("释放 provider 失败: %s", e)

    def _remove_file_watcher(self, filepath: str):
        """移除文件监听"""
        if filepath in self._file_watchers:
            try:
                watcher = self._file_watchers.pop(filepath)
                watcher.deleteLater()
            except Exception:
                pass
        self._watcher_paths.pop(filepath, None)

    def _on_file_changed(self, filepath: str, editor):
        """文件外部修改回调"""
        try:
            # 关闭/销毁过程中不再弹任何对话框
            #
            # 缺陷背景（实测段错误 0xC0000005）：
            #   `QFileSystemWatcher` 的回调可能在**窗口销毁过程中**被事件
            #   循环触发。此时弹出模态 `QMessageBox` 会访问正在析构的
            #   Qt 对象 → 段错误。
            #
            #   实测：pytest teardown 阶段 `_process_events()` 触发本回调，
            #   faulthandler 明确指向下面的 `QMessageBox.question`。
            #   真实场景同理（关闭主窗口时外部程序恰好改了文件）。
            if self._shutting_down:
                return

            # 防止**重入**：本回调会弹出模态对话框（`QMessageBox.question`），
            # 而模态对话框自己会跑事件循环 —— 期间文件监听可能**再次**触发
            # 本回调，形成递归重入（每个嵌套层都新建对话框/重载文件）。
            # 实测这会在窗口销毁阶段演变成段错误（0xC0000005）。
            if self._handling_file_change:
                return
            self._handling_file_change = True
            try:
                self._handle_file_change(filepath, editor)
            finally:
                self._handling_file_change = False

        except Exception as e:
            print(f"[TabManager] 文件修改处理失败: {e}")

    def _handle_file_change(self, filepath: str, editor):
        """`_on_file_changed` 的实际处理（已由外层做好守卫）"""
        try:
            # 文件可能被删除
            if not os.path.exists(filepath):
                self._show_status(
                    f"文件已被删除: {os.path.basename(filepath)}",
                    5000, "warning"
                )
                return

            # 文件可能被重命名，重新添加监听
            if filepath not in self._file_watchers:
                return
            watcher = self._file_watchers[filepath]
            if filepath not in watcher.files():
                try:
                    watcher.addPath(filepath)
                except Exception:
                    pass

            # 检查编辑器是否已修改（避免覆盖用户修改）
            is_modified = False
            try:
                if hasattr(editor, 'proxy') and editor.proxy:
                    is_modified = getattr(
                        editor.proxy, 'is_modified', False
                    )
            except Exception:
                pass

            if is_modified:
                # 用户有未保存修改，提示
                self._show_status(
                    f"文件已被外部修改，但你有未保存的修改: "
                    f"{os.path.basename(filepath)}",
                    5000, "warning"
                )
                return

            # 请求重新加载 —— 通过**信号**交给主窗口，而不是在这里直接弹
            # 模态对话框。
            #
            # 修复（实测段错误 0xC0000005）：
            #   本方法是 `QFileSystemWatcher` 的回调。在回调里执行
            #   `QMessageBox.question`（模态，自己跑事件循环）是明确的
            #   反模式：它会重入事件循环，可能在窗口销毁过程中再次触发
            #   文件回调，并访问正在析构的 Qt 对象。
            #
            #   faulthandler 已明确指向这里的 `QMessageBox.question`
            #   （pytest teardown 的 `_process_events()` 恰好触发了 watcher）。
            #   交给主窗口后，对话框在正常的事件循环层级弹出，不再重入。
            self.file_changed_externally.emit(filepath)

        except Exception as e:
            print(f"[TabManager] 文件修改处理失败: {e}")

    def _reload_file(self, filepath: str, editor):
        """重新加载文件内容

        修复（两条审计用例）：
          * **INV-D 撤销栈失效**：重载后内容被整体替换，但 `undo_manager`
            仍保留针对**旧内容位置**的撤销命令 —— 用户按 Ctrl+Z 会把命令
            施加到新内容上，产生错乱的编辑甚至破坏文件。现在必须清空
            撤销栈（与 `_on_document_reloaded` 的做法一致）。
          * **句柄/mmap 泄漏**：原来直接用新 provider 覆盖
            `document.provider`，**从不 close 旧的** —— 旧的 mmap 与文件
            句柄一直持有，在 Windows 上会锁住文件导致外部程序写入失败
            （这正是"外部变更"场景本身）。现在先关闭旧 provider。
          * 顺带：`editor.clear()` / `append()` 是程序行为，需用
            `_restoring` 抑制，避免被当成用户编辑记进撤销栈并置脏。
        """
        try:
            cursor_pos = 0
            first_line = 0

            proxy = None
            try:
                if hasattr(editor, 'proxy') and editor.proxy:
                    proxy = editor.proxy
                    cursor_pos = proxy.get_current_pos()
                first_line = editor.SendScintilla(
                    editor.SCI_GETFIRSTVISIBLELINE
                )
            except Exception:
                pass

            # 重新打开文件
            provider = LocalFileProvider()
            provider.open(filepath)

            # 替换 provider，并**释放旧的**（否则 mmap/句柄泄漏）
            try:
                if proxy is not None and proxy.document:
                    old_provider = proxy.document.provider
                    proxy.document.provider = provider
                    if old_provider is not None and old_provider is not provider:
                        try:
                            old_provider.close()
                        except Exception as e:
                            logger.debug("关闭旧 provider 失败: %s", e)
            except Exception as e:
                logger.debug("替换 provider 失败: %s", e)

            # 程序性替换内容：抑制 SCN_MODIFIED 回调
            suppress = proxy is not None and hasattr(proxy, '_restoring')
            if suppress:
                proxy._restoring = True
            try:
                editor.clear()
                for i in range(provider.total_blocks):
                    data = provider.read_block(i)
                    editor.append(data.decode(provider.encoding,
                                              errors='replace'))

                # 恢复位置
                try:
                    max_pos = editor.SendScintilla(editor.SCI_GETLENGTH)
                    editor.SendScintilla(
                        editor.SCI_GOTOPOS, min(cursor_pos, max_pos)
                    )
                    editor.SendScintilla(
                        editor.SCI_SETFIRSTVISIBLELINE, first_line
                    )
                except Exception:
                    pass
            finally:
                if suppress:
                    proxy._restoring = False

            # 释放映射/句柄：Windows 上映射会阻止外部程序覆盖该文件，
            # 而本模块的职责正是"外部变更检测"。内容已读入编辑器，
            # 后续需要时会由 `_ensure_handle()` 按需重建。
            self._dispose_provider(provider)

            # 重置修改状态，并清空撤销栈
            #
            # 重载等于"文件被整体替换"，旧的撤销命令位置对新内容全部失效。
            try:
                editor.setModified(False)
                if proxy is not None:
                    proxy._modified = False
                    try:
                        if getattr(proxy, 'undo_manager', None) is not None:
                            proxy.undo_manager.clear()
                    except Exception:
                        pass
                    try:
                        editor.SendScintilla(
                            editor.SCI_EMPTYUNDOBUFFER
                        )
                    except Exception:
                        pass
                    try:
                        proxy.modified_changed.emit(False)
                    except Exception:
                        pass
            except Exception:
                pass

            self._update_tab_title(editor)

            self._show_status(
                f"已重新加载: {os.path.basename(filepath)}"
            )

        except Exception as e:
            self._show_status(f"重新加载失败: {e}", 3000, "error")

    # ========================================================
    # 后台标签资源释放
    # ========================================================
    def _check_idle_tabs(self):
        """检查并释放长时间闲置的后台标签内容"""
        now = QDateTime.currentDateTime()
        current_index = self.currentIndex()

        for i in range(self.count()):
            if i == current_index:
                continue

            widget = self.widget(i)
            if not widget:
                continue

            # 检查是否已释放
            if widget in self._released_content:
                continue

            # 检查最后活动时间
            last_active = self._last_active.get(widget)
            if last_active is None:
                self._last_active[widget] = now
                continue

            elapsed = last_active.secsTo(now)
            if elapsed > IDLE_RELEASE_MINUTES * 60:
                self._release_tab_content(widget)

    def _release_provider_handles(self, filepath: str):
        """释放指向该文件的 provider 映射/句柄（允许外部程序写入）

        为什么需要（Windows 文件锁定，已实测）：
            即使**只读**的内存映射也会阻止另一进程覆盖写该文件 ——
            `open(path, 'w')` 抛 `OSError: [Errno 22] Invalid argument`。
            于是编辑器一打开文件，git / 构建工具 / 其它编辑器就再也改不了
            它，而"外部变更检测 / 三方合并"因此永远不会触发。

        ⚠️ 为什么**不**用 `gc.get_objects()` 扫描（重要教训）：
            最初的实现靠遍历全堆对象来找出指向该文件的 provider。
            在 Qt 进程里这会导致**段错误**（退出码 0xC0000005）：
            遍历数十万个对象并与 Qt 的对象生命周期/GC 交织，是明确不安全
            的行为（实测：命令行单独跑可通过，pytest 中必崩，且与
            `release_mmap` 内部逻辑无关 —— 把它改成 no-op 仍然崩）。

            现在只处理调用方**明确持有**的目标 provider，不做任何堆扫描。
        """
        return

    def _dispose_provider(self, provider):
        """安全释放一个 provider 的映射与句柄（只影响这一个对象）"""
        if provider is None:
            return
        try:
            if hasattr(provider, 'release_mmap'):
                provider.release_mmap()
        except Exception as e:
            logger.debug("释放 provider 句柄失败: %s", e)

    def _restore_released_content(self, widget) -> bool:
        """恢复被内存回收释放的标签内容（返回是否发生了恢复）

        与 `_release_tab_content` 对称。设为独立方法的原因：
          * 切回标签（`_on_current_changed`）与"保存前需要内容"等场景
            都要用它，避免逻辑分叉；
          * 可被测试直接调用，测到的是**生产代码**而不是照抄一遍。

        关键点：`setText()` 会触发 SCN_MODIFIED，必须用 `_restoring`
        抑制 `_on_scintilla_modified` —— 否则恢复动作本身被当成用户编辑，
        标签会显示 '*'（内容其实与磁盘一致），退出时还会被问"是否保存"。
        """
        if widget is None or widget not in self._released_content:
            return False
        try:
            proxy = getattr(widget, 'proxy', None)
            suppress = proxy is not None and hasattr(proxy, '_restoring')
            if suppress:
                proxy._restoring = True
            try:
                widget.setText(self._released_content.pop(widget))
                if proxy is not None:
                    try:
                        proxy._modified = False
                        proxy.sc.setModified(False)
                    except Exception:
                        pass
            finally:
                if suppress:
                    proxy._restoring = False
            return True
        except Exception as e:
            print(f"[TabManager] 恢复标签内容失败: {e}")
            return False

    def _release_tab_content(self, widget):
        """释放标签的文本内容（保留元数据）"""
        try:
            # 检查是否已修改
            is_modified = False
            try:
                if hasattr(widget, 'proxy') and widget.proxy:
                    is_modified = getattr(
                        widget.proxy, 'is_modified', False
                    )
            except Exception:
                pass

            if is_modified:
                return

            # 内容太短不释放
            text = widget.text()
            if len(text) < 1000:
                return

            # 缓存内容的**权威版本**
            #
            # 修复（审计用例 test_save_all_after_release...）：
            #   `widget.text()` 是 Scintilla 归一化后的文本 —— 它会把 CRLF
            #   也报告为 `\n`（或按 eolMode 归一），与磁盘上的原始字节**不
            #   完全一致**。若直接把 `widget.text()` 当作缓存并在切回时
            #   `setText` 回去，就会**改写文件的行尾**（实测：原文 `\n`
            #   变成 `\r\n`）。
            #
            #   这里在释放前先把 provider（其内容来自磁盘）同步为当前
            #   缓冲区，再以 provider 的文本作为缓存 —— 保证"释放→恢复"
            #   是**无损**的。
            proxy = getattr(widget, 'proxy', None)
            cached = text
            try:
                if proxy is not None:
                    proxy._sync_content_to_provider(text)
                    provider = getattr(proxy.document, 'provider', None)
                    if provider is not None:
                        pt = provider.read_text()
                        if pt:
                            cached = pt
            except Exception:
                cached = text

            # 缓存内容
            self._released_content[widget] = cached

            # 清空编辑器
            #
            # 修复（审计用例 TestIdleReleaseVsSave，两条）：
            #   `widget.clear()` 会触发 SCN_MODIFIED，而
            #   `_on_scintilla_modified` 把它当成**用户编辑** —— 于是：
            #     1) 记入撤销栈（用户按 Ctrl+Z 会看到莫名其妙的"清空"）
            #     2) `proxy._modified` 被置 True → 标签页显示 '*'
            #     3) 自动保存为这个"已修改"的空内容生成备份
            #     4) 关窗时弹出"是否保存"的假警告
            #
            #   这是程序自身发起的变更，必须用 `_restoring` 抑制回调
            #   （与 `_on_document_reloaded` 等处的做法一致），
            #   并在之后把"是否有未保存修改"的语义恢复为清空前的值。
            suppress = proxy is not None and hasattr(proxy, '_restoring')
            if suppress:
                proxy._restoring = True
            try:
                widget.clear()
                if proxy is not None:
                    try:
                        proxy._modified = False
                        proxy.sc.setModified(False)
                    except Exception:
                        pass
            finally:
                if suppress:
                    proxy._restoring = False

            # 记录日志
            fp = "未命名"
            try:
                if hasattr(widget, 'proxy') and widget.proxy:
                    fp = self._get_proxy_filepath(widget.proxy) or "未命名"
            except Exception:
                pass

            print(f"[TabManager] 已释放后台标签内容: "
                  f"{os.path.basename(fp)} ({len(text)} 字符)")
        except Exception as e:
            print(f"[TabManager] 释放标签内容失败: {e}")

    def force_release_idle(self):
        """强制释放所有符合条件的闲置标签"""
        self._check_idle_tabs()

    def get_memory_usage(self) -> Dict[str, Any]:
        """获取标签内存使用情况"""
        total_chars = 0
        released_count = 0

        for i in range(self.count()):
            widget = self.widget(i)
            if not widget:
                continue
            if widget in self._released_content:
                released_count += 1
            else:
                try:
                    total_chars += len(widget.text())
                except Exception:
                    pass

        return {
            'tab_count': self.count(),
            'total_chars': total_chars,
            'released_count': released_count,
            'closed_history': len(self._closed_tabs),
        }

    # ========================================================
    # 状态提示
    # ========================================================
    def _show_status(self, message: str, timeout: int = 3000,
                     level: str = "info"):
        """显示状态栏消息"""
        try:
            from app.event_bus import StatusMessageEvent
            bus.emit_event(StatusMessageEvent(
                message=message, timeout=timeout, level=level
            ))
        except Exception:
            # 回退到主窗口状态栏
            try:
                win = self.window()
                if hasattr(win, 'statusBar') and callable(win.statusBar):
                    win.statusBar().showMessage(message, timeout)
            except Exception:
                pass

    # ========================================================
    # 批量操作
    # ========================================================
    def save_all(self) -> int:
        """
        保存所有已修改的标签。

        返回:
            成功保存的数量
        """
        saved = 0
        for i in range(self.count()):
            widget = self.widget(i)
            if not widget:
                continue
            if not hasattr(widget, 'proxy') or not widget.proxy:
                continue

            try:
                if getattr(widget.proxy, 'is_modified', False):
                    widget.proxy.save_file()
                    saved += 1
            except Exception as e:
                print(f"[TabManager] 保存失败: {e}")

        return saved

    def reload_all(self):
        """重新加载所有文件"""
        for i in range(self.count()):
            widget = self.widget(i)
            if not widget:
                continue

            fp = None
            try:
                if hasattr(widget, 'proxy') and widget.proxy:
                    fp = self._get_proxy_filepath(widget.proxy)
            except Exception:
                pass

            if fp:
                self._reload_file(fp, widget)

    def get_modified_files(self) -> List[str]:
        """获取所有已修改的文件路径"""
        result = []
        for i in range(self.count()):
            widget = self.widget(i)
            if not widget or not hasattr(widget, 'proxy') or not widget.proxy:
                continue

            try:
                if not getattr(widget.proxy, 'is_modified', False):
                    continue

                fp = self._get_proxy_filepath(widget.proxy)
                result.append(fp or "(未命名)")
            except Exception:
                pass

        return result

    def has_unsaved_changes(self) -> bool:
        """检查是否有未保存的修改"""
        for i in range(self.count()):
            widget = self.widget(i)
            if not widget or not hasattr(widget, 'proxy') or not widget.proxy:
                continue

            try:
                if getattr(widget.proxy, 'is_modified', False):
                    return True
            except Exception:
                pass

        return False

    # ========================================================
    # 标签信息查询
    # ========================================================
    def get_tab_info(self, index: int) -> Optional[Dict[str, Any]]:
        """获取指定标签的详细信息"""
        if index < 0 or index >= self.count():
            return None

        widget = self.widget(index)
        if not widget:
            return None

        info = {
            'index': index,
            'title': self.tabText(index),
            'filepath': None,
            'encoding': 'utf-8',
            'modified': False,
            'readonly': False,
            'line_count': 0,
            # P0-8：char_count 是**真实字符数**（Python str 长度），
            # byte_count 才是 Scintilla 的字节口径。
            'char_count': 0,
            'byte_count': 0,
            'cursor_line': 0,
            'cursor_col': 0,
        }

        try:
            if hasattr(widget, 'proxy') and widget.proxy:
                proxy = widget.proxy

                # 使用辅助方法
                info['filepath'] = self._get_proxy_filepath(proxy)
                info['encoding'] = self._get_proxy_encoding(proxy)
                info['modified'] = getattr(
                    proxy, 'is_modified', False
                )

            info['line_count'] = widget.SendScintilla(
                widget.SCI_GETLINECOUNT
            )

            # P0-8 修复：`SCI_GETLENGTH` 返回的是**字节数**，不是字符数。
            #   纯 ASCII 下两者相等，所以这个错标长期没被发现；含中文时
            #   （UTF-8 每字 3 字节）"字符数"会被高估约 3 倍。
            #   现在两个口径都给：byte_count 保留 Scintilla 原生值（零解码
            #   成本），char_count 用 QScintilla 解码后的 `text()` 长度。
            info['byte_count'] = widget.SendScintilla(
                widget.SCI_GETLENGTH
            )
            try:
                info['char_count'] = len(widget.text())
            except Exception:
                # 解码失败（极端情况）：退回字节数，好过没有值
                info['char_count'] = info['byte_count']

            line, col = widget.getCursorPosition()
            info['cursor_line'] = line + 1
            info['cursor_col'] = col + 1

            if info['filepath']:
                info['readonly'] = not os.access(
                    info['filepath'], os.W_OK
                )
        except Exception:
            pass

        return info

    def get_all_tabs_info(self) -> List[Dict[str, Any]]:
        """获取所有标签的信息"""
        result = []
        for i in range(self.count()):
            info = self.get_tab_info(i)
            if info:
                result.append(info)
        return result

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出标签信息为可读文本"""
        lines = [f"TabManager: {self.count()} 个标签", "=" * 60]

        for info in self.get_all_tabs_info():
            modified = ' *' if info['modified'] else ''
            readonly = ' 🔒' if info['readonly'] else ''
            filepath = info['filepath'] or '(未命名)'
            lines.append(
                f"  [{info['index']}] {info['title']}{modified}{readonly}"
            )
            lines.append(
                f"      {filepath} ({info['line_count']} 行, "
                f"{info['char_count']} 字符 / {info['byte_count']} 字节)"
            )

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<TabManager tabs={self.count()} "
                f"modified={len(self.get_modified_files())}>")


# ============================================================
# 独立窗口（用于标签分离）
# ============================================================
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