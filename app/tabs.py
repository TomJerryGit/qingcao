# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405,F811
"""标签管理（v2.24 拆分：生命周期/UI/文件监视/悬浮窗口）。"""
from app.tabs_common import *  # noqa: F401,F403,F405
from app.tabs_lifecycle import TabOpenCloseMixin
from app.tabs_ui import TabUiMixin
from app.tabs_watch import TabFileWatchMixin


class TabManager(TabOpenCloseMixin, TabUiMixin, TabFileWatchMixin, QTabWidget):
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


from app.tabs_detached import DetachedWindow  # noqa: E402,F401
