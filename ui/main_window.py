# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""主窗口聚合入口（v2.23 D2 拆分）。

拆分：main_window_common（公共导入/主题过滤器/样式适配）+ window_theme / window_lsp / window_remote / window_actions / window_session Mixin。
"""

from ui.main_window_common import *  # noqa: F401,F403
from ui.mixins.window_actions_mixin import WindowActionsMixin
from ui.mixins.window_lsp_mixin import WindowLSPMixin
from ui.mixins.window_remote_mixin import WindowRemoteMixin
from ui.mixins.window_session_mixin import WindowSessionMixin
from ui.mixins.window_theme_mixin import WindowThemeMixin


class MainWindow(
    WindowThemeMixin,
    WindowLSPMixin,
    WindowRemoteMixin,
    WindowActionsMixin,
    WindowSessionMixin,
    MenuBuilderMixin,
    PanelRegistryMixin,
    SandboxUIMixin,
    PluginsUIMixin,
    CapabilityWiringMixin,
    ProjectMixin,
    FileOpsMixin,
    EditOpsMixin,
    StatusBarMixin,
    QMainWindow,
):
    # 实时沙箱诊断的大文件阈值（超过则跳过，避免卡顿）
    MAX_LIVE_DIAGNOSTICS_BYTES = 5 * 1024 * 1024

    """
    青草编辑器主窗口。

    整合所有 UI 组件，协调应用层、核心层、UI 层。
    """

    # 自定义信号
    session_restored = pyqtSignal(int)

    def __init__(self, parent=None, startup_files: Optional[List[str]] = None):
        """
        参数:
            parent: 父窗口
            startup_files: 启动时打开的文件列表
        """
        super().__init__(parent)

        # 基础配置
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1100, 750)
        self.setMinimumSize(600, 400)

        # 启动文件
        self.startup_files = startup_files or []

        # 状态
        self._distraction_free = False
        self._fullscreen_mode = False
        self._hidden_widgets: List[QWidget] = []
        self._lsp_clients: Dict[str, Any] = {}
        self._current_project = None
        self.plugins: List[Any] = []
        self.api = None
        self.plugin_loader = None
        self.plugin_manager = None

        # P8-5: 快捷键 → QAction 的运行时登记表。
        # _add_action() 直接调用 QAction.setShortcut()，绕过了
        # app/actions.py 的冲突检测；这里补一道"重复绑定"防线。
        self._shortcut_owners: Dict[str, QAction] = {}

        # 关闭标志（避免 closeEvent 重入）
        self._closing = False

        # 偏好设置
        try:
            from app.preferences import Preferences

            self.prefs = Preferences()
        except Exception as e:
            print(f"[MainWindow] Preferences 加载失败: {e}")
            self.prefs = None

        # 动作管理器
        try:
            from app.actions import ActionManager

            self.act_mgr = ActionManager()
        except Exception as e:
            print(f"[MainWindow] ActionManager 加载失败: {e}")
            self.act_mgr = None

        # 宏录制
        try:
            from core.macro import MacroManager, MacroRecorder

            # P0-1 修复（实测：录制后命令数为 0）：
            #   原实现是 `MacroRecorder()` —— 没有 undo_manager。
            #   `core/macro.py` 的 `_register_hook()` 在
            #   `not self.undo_manager` 时直接 return，`record_hook`
            #   永不设置，于是录制器什么都收不到，录到 0 条。
            #
            #   这里不能简单地在构造时传一个固定引用：proxy 与其
            #   `UndoManager` 是**每个标签一个**（见 core/editor.py），
            #   而此刻 `self.tabs` 还没创建（`_build_central` 在后面）。
            #   因此传入"解析当前标签 undo_manager"的回调，
            #   由 MacroRecorder 在 start()/stop() 时动态绑定。
            self.macro = MacroRecorder(
                undo_manager_provider=self._current_undo_manager,
                parent=self,
            )
            # P0-1: 录制/回放的失败必须可见（原先只会 print 到控制台，
            # 打包成 GUI 程序后用户完全看不到）
            try:
                self.macro.error_occurred.connect(self._on_macro_error)
            except Exception:
                pass
            self.macro_manager = MacroManager()
        except Exception as e:
            print(f"[MainWindow] Macro 加载失败: {e}")
            self.macro = None
            self.macro_manager = None

        # 文档模型
        try:
            from core.document import DocumentModel

            self.doc_model = DocumentModel()
        except Exception as e:
            print(f"[MainWindow] DocumentModel 加载失败: {e}")
            self.doc_model = None

        # 会话管理
        try:
            from app.session import SessionManager

            self.session = SessionManager()
            self.session.bind_window(self)
        except Exception as e:
            print(f"[MainWindow] SessionManager 加载失败: {e}")
            self.session = None

        # 构建 UI
        self._build_central()

        # 项目状态（工作区/项目根）必须在 _build_menus 之前就绪：
        # `_setup_project_menu()` 会读 workspace 构建「最近项目」子菜单。
        self._init_project_state()

        self._build_menus()
        self._build_toolbar()
        self._build_docks()
        self._build_status_bar()
        self._build_npp_style_menus()
        self.setAcceptDrops(True)
        self._sandboxed_plugins = {}
        self._build_shortcuts()

        # 连接事件总线
        self._connect_event_bus()

        # 加载插件（延迟）
        QTimer.singleShot(100, self._load_plugins)

        # 恢复会话（延迟）
        QTimer.singleShot(200, self._restore_session)

        # 打开启动文件（延迟）
        if self.startup_files:
            QTimer.singleShot(300, self._open_startup_files)

        # 状态栏定时刷新
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(STATUS_REFRESH_INTERVAL)

        # 会话自动保存
        self._session_timer = QTimer(self)
        self._session_timer.timeout.connect(self._autosave_session)
        self._session_timer.start(SESSION_AUTOSAVE_INTERVAL)

        # 自动备份定时器（P1 修复：崩溃恢复的**生产者**）
        #
        # 缺陷背景（真实缺陷，已核实）：
        #   `SessionManager.start_autosave()` / `save_autosave()`
        #   —— 唯一会备份"未保存文件正文"的代码 —— **全仓零调用点**。
        #   于是 `backup/autosave/meta.json` 永不生成，
        #   main.py 的崩溃恢复分支（判 meta.json 是否存在）永不进入，
        #   草稿又没有任何读取端 → **崩溃后未保存内容 100% 丢失**。
        #
        #   注意：上面那个 `_session_timer` 连的是 `_autosave_session`，
        #   它只调 `session.save(...)`（存文件名/光标/布局），
        #   **不含正文**，因此不能替代本定时器。
        if self.session is not None:
            try:
                self.session.start_autosave()
            except Exception as e:
                logging.warning("启动自动备份定时器失败: %s", e)

    # ========================================================
    # 面板惰性构造（P1-3）
    # ========================================================
    # 修复说明:
    #   原实现在启动时同步构造全部 9 个面板（大纲×2、目录树、
    #   Minimap、全局搜索、Python 控制台、插件面板、性能监控、
    #   搜索栏），其中 6 个构造完立刻 hide()。实测
    #   MainWindow() 构造耗时约 2.46s，是冷启动的最大单项开销。
    #
    #   现在改为按需构造：_build_docks 只登记"面板还没建"，
    #   用户第一次打开某个面板（或外部代码首次访问）时才真正
    #   创建 widget。面板属性仍保持原名字与类型，调用方无需改动。
    _LAZY_PANELS = (
        "outline",
        "outline_enhanced",
        "dir_tree",
        "minimap",
        "gsearch",
        "console",
        "plugins_panel",
        "perf_monitor",
        "search_bar",
        "problems",
        # 本轮接线：两个此前零实例化的孤立面板
        # （`ui/lsp_panel.py` 含语言服务器安装向导；
        #   `ui/undo_history_panel.py` 展示自研撤销栈）
        "lsp",
        "undo_history",
        # 项目任务面板（`ui/task_panel.py` + `core/project_tasks.py`
        # 此前零实例化；由 project_mixin 绑定当前项目根）
        "task",
        # v2.21 P1-1：终端面板
        "terminal",
    )

    # 启动时构造的面板（**保留**延迟构造，但恢复"开箱即有"的界面）
    #
    # 为什么需要（真实回归）：改成纯延迟构造后，启动时一个面板都不存在
    #   → 会话保存采集到空的 docks
    #   → 关闭时覆盖掉用户已有的面板布局
    #   → 之后每次启动界面都是空的（只剩欢迎页）
    # 用户观感就是"功能不见了"。这里在启动时只构造这几个常用面板
    # （仍少于原先的 9 个），既保住冷启动优化，又让界面开箱可用。
    _DEFAULT_PANELS = (
        "dir_tree",  # 左侧：项目目录树
        "gsearch",  # 底部：全局搜索
        "plugins_panel",  # 右侧：插件
        "perf_monitor",  # 底部：性能监控
    )

    _TOOLBAR_ICONS = (
        ("新建", "📄"),
        ("打开", "📂"),
        ("保存", "💾"),
        ("撤销", "↶"),
        ("重做", "↷"),
        ("查找", "🔍"),
        ("替换", "🔁"),
        ("运行", "▶"),
        ("终端", "🖥"),
        ("插件", "🧩"),
        ("主题", "🎨"),
        ("格式化", "✨"),
        ("对比", "🔀"),
        ("书签", "🔖"),
        ("导出", "📤"),
    )

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出窗口信息"""
        lines = [f"{APP_NAME} v{APP_VERSION}", "=" * 60]
        lines.append(f"标签数: {self.tabs.count()}")
        lines.append(f"当前标签: {self.tabs.currentIndex()}")
        lines.append(f"全屏: {self._fullscreen_mode}")
        lines.append(f"无干扰: {self._distraction_free}")
        lines.append(f"插件数: {len(self.plugins)}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<MainWindow tabs={self.tabs.count()} current={self.tabs.currentIndex()}>"
