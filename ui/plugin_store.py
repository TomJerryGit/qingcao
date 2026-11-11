# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""插件市场主对话框（v2.23 D3 拆分）。

拆分为：plugin_client（常量/工具/PluginInfo/Client/Worker）、plugin_detail（详情/安装进度）、本文件（列表/卡片/主对话框）。
"""

from ui.plugin_client import *  # noqa: F401,F403
from ui.plugin_detail import *  # noqa: F401,F403


class PluginCard(QFrame):
    """
    插件卡片控件。

    展示单个插件的信息，支持点击安装/卸载。
    """

    install_clicked = pyqtSignal(object)  # PluginInfo
    uninstall_clicked = pyqtSignal(object)
    update_clicked = pyqtSignal(object)
    detail_clicked = pyqtSignal(object)

    def __init__(self, info: PluginInfo, parent=None):
        super().__init__(parent)

        self.info = info
        self.setObjectName("PluginCard")
        self.setFrameShape(QFrame.StyledPanel)

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        """构建 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # 左侧：图标
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(40, 40)
        self.icon_label.setAlignment(Qt.AlignCenter)

        # 根据类型选择图标
        if self.info.type == PLUGIN_TYPE_THEME:
            self.icon_label.setText("🎨")
        elif self.info.type == PLUGIN_TYPE_LANGUAGE:
            self.icon_label.setText("🌐")
        elif self.info.type == PLUGIN_TYPE_TOOL:
            self.icon_label.setText("🔧")
        else:
            self.icon_label.setText("🧩")

        self.icon_label.setStyleSheet(
            "font-size: 24px; background-color: #2d2d2d; border-radius: 6px;"
        )
        layout.addWidget(self.icon_label)

        # 中间：信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        # 标题行
        title_layout = QHBoxLayout()
        title_layout.setSpacing(6)

        self.title_label = QLabel(self.info.display_title)
        self.title_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #d4d4d4;")
        title_layout.addWidget(self.title_label)

        # 版本
        self.version_label = QLabel(f"v{self.info.version}")
        self.version_label.setStyleSheet("font-size: 11px; color: #888;")
        title_layout.addWidget(self.version_label)

        try:
            _badge = QLabel(plugin_source_badge(self.info))
            _badge.setStyleSheet(
                "font-size:10px; color:#9cdcfe; "
                "border:1px solid #3c3c3c; border-radius:3px; "
                "padding:1px 4px;"
            )
            title_layout.addWidget(_badge)
            _sec = QLabel(plugin_security_bucket(self.info))
            _sec.setStyleSheet("font-size:10px; color:#888;")
            _sec.setToolTip("安全状态")
            title_layout.addWidget(_sec)
        except Exception:
            pass

        # 兼容性徽章（列表行内，与详情页一致）
        self._compat_ok, self._compat_reason = check_plugin_compatibility(self.info)
        self.compat_label = QLabel("✅ 兼容" if self._compat_ok else "⚠️ 不兼容")
        self.compat_label.setToolTip(self._compat_reason or "与当前应用版本兼容")
        self.compat_label.setStyleSheet(
            "font-size: 11px; color: #4caf50;"
            if self._compat_ok
            else "font-size: 11px; color: #ff9800;"
        )
        title_layout.addWidget(self.compat_label)

        # 认证标记
        if self.info.verified:
            verified_label = QLabel("✅")
            verified_label.setToolTip("已验证插件")
            title_layout.addWidget(verified_label)

        # 精选标记
        if self.info.featured:
            featured_label = QLabel("⭐")
            featured_label.setToolTip("精选插件")
            title_layout.addWidget(featured_label)

        title_layout.addStretch()
        info_layout.addLayout(title_layout)

        # 描述
        self.desc_label = QLabel(self.info.description or "（无描述）")
        self.desc_label.setStyleSheet("font-size: 11px; color: #888;")
        self.desc_label.setWordWrap(True)
        info_layout.addWidget(self.desc_label)

        # 底部：作者、统计
        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(10)

        if self.info.author:
            author_label = QLabel(f"👤 {self.info.author}")
            author_label.setStyleSheet("font-size: 10px; color: #666;")
            meta_layout.addWidget(author_label)

        if self.info.downloads > 0:
            downloads_label = QLabel(f"⬇ {self._format_number(self.info.downloads)}")
            downloads_label.setStyleSheet("font-size: 10px; color: #666;")
            meta_layout.addWidget(downloads_label)

        if self.info.rating > 0:
            stars = "★" * int(self.info.rating) + "☆" * (5 - int(self.info.rating))
            rating_label = QLabel(f"{stars} {self.info.rating:.1f}")
            rating_label.setStyleSheet("font-size: 10px; color: #f0ad4e;")
            meta_layout.addWidget(rating_label)
        try:
            from ui.plugin_client import get_community_rating

            _comm = get_community_rating(self.info.name)
            if _comm and _comm[1] > 0:
                _c = QLabel("★ %.1f 社区 (%d)" % (_comm[0], _comm[1]))
                _c.setStyleSheet("font-size: 10px; color: #61afef;")
                _c.setToolTip("社区平均分（静态聚合，只读）")
                meta_layout.addWidget(_c)
        except Exception:
            pass
        try:
            from ui.plugin_rating import LocalRatings

            _lr = LocalRatings().get(self.info.name)
            if _lr and _lr.get("stars"):
                _lbl = QLabel("★ %d 本地" % int(_lr["stars"]))
                _lbl.setStyleSheet("font-size: 10px; color: #7ec850;")
                _lbl.setToolTip("本地评分（仅本机）")
                meta_layout.addWidget(_lbl)
        except Exception:
            pass

        meta_layout.addStretch()
        info_layout.addLayout(meta_layout)

        layout.addLayout(info_layout, 1)

        # 右侧：操作按钮
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(4)
        btn_layout.setAlignment(Qt.AlignVCenter)

        self.action_btn = QPushButton()
        self.action_btn.setFixedWidth(80)
        self.action_btn.clicked.connect(self._on_action_clicked)
        btn_layout.addWidget(self.action_btn)

        self.detail_btn = QToolButton()
        self.detail_btn.setText("详情")
        self.detail_btn.setFixedSize(44, 24)
        self.detail_btn.setToolTip("查看详情 / 评分")
        self.detail_btn.setStyleSheet("font-size: 11px;")
        self.detail_btn.clicked.connect(lambda: self.detail_clicked.emit(self.info))
        btn_layout.addWidget(self.detail_btn)

        layout.addLayout(btn_layout)

        # 发现性：双击卡片 / 回车打开详情（评分入口）
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip("双击查看详情 / 评分")

        # 更新按钮状态
        self._update_action_button()

    def mouseDoubleClickEvent(self, event):
        self.detail_clicked.emit(self.info)
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.detail_clicked.emit(self.info)
            event.accept()
            return
        super().keyPressEvent(event)

    def _update_action_button(self):
        """更新操作按钮状态"""
        state = self.info.state

        if state == PluginState.NOT_INSTALLED:
            self.action_btn.setText("安装")
            self.action_btn.setStyleSheet(
                "background-color: #0e639c; color: white; "
                "border: none; border-radius: 3px; padding: 4px;"
            )
            self.action_btn.setEnabled(True)

        elif state == PluginState.INSTALLED:
            self.action_btn.setText("卸载")
            self.action_btn.setStyleSheet(
                "background-color: #5a5a5a; color: white; "
                "border: none; border-radius: 3px; padding: 4px;"
            )
            self.action_btn.setEnabled(True)

        elif state == PluginState.UPDATE_AVAILABLE:
            self.action_btn.setText("更新")
            self.action_btn.setStyleSheet(
                "background-color: #7ec850; color: white; "
                "border: none; border-radius: 3px; padding: 4px; "
                "font-weight: bold;"
            )
            self.action_btn.setEnabled(True)

        elif state == PluginState.DISABLED:
            self.action_btn.setText("启用")
            self.action_btn.setStyleSheet(
                "background-color: #f0ad4e; color: white; "
                "border: none; border-radius: 3px; padding: 4px;"
            )
            self.action_btn.setEnabled(True)

        else:
            self.action_btn.setText("不可用")
            self.action_btn.setEnabled(False)

        # 不兼容 → 安装/更新按钮置灰（卸载/启用不受限）
        if state in (PluginState.NOT_INSTALLED, PluginState.UPDATE_AVAILABLE) and not getattr(
            self, "_compat_ok", True
        ):
            self.action_btn.setText("不兼容")
            self.action_btn.setEnabled(False)
            self.action_btn.setToolTip(self._compat_reason)

    def _on_action_clicked(self):
        """按钮点击"""
        state = self.info.state
        if state in (PluginState.NOT_INSTALLED, PluginState.UPDATE_AVAILABLE):
            if not getattr(self, "_compat_ok", True):
                return

        if state == PluginState.NOT_INSTALLED:
            self.install_clicked.emit(self.info)
        elif state == PluginState.INSTALLED:
            self.uninstall_clicked.emit(self.info)
        elif state == PluginState.UPDATE_AVAILABLE:
            self.update_clicked.emit(self.info)
        elif state == PluginState.DISABLED:
            self.install_clicked.emit(self.info)  # 复用为启用

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QFrame#PluginCard {
                background-color: #2d2d2d;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
            }
            QFrame#PluginCard:hover {
                background-color: #333333;
                border-color: #4c4c4c;
            }
            QFrame#PluginCard QLabel {
                background-color: transparent;
            }
        """)

    @staticmethod
    def _format_number(n: int) -> str:
        """格式化数字"""
        if n < 1000:
            return str(n)
        elif n < 1000000:
            return f"{n / 1000:.1f}K"
        else:
            return f"{n / 1000000:.1f}M"

    def refresh(self):
        """刷新卡片"""
        self._update_action_button()


class PluginStoreDialog(QDialog):
    """
    插件市场对话框。

    主界面，包含:
    - 搜索栏
    - 分类筛选
    - 排序选项
    - 插件卡片列表
    - 详情对话框
    - 安装/卸载/更新操作

    信号:
        plugin_installed(str): 插件安装完成（插件名）
        plugin_uninstalled(str): 插件卸载完成（插件名）
        plugin_updated(str): 插件更新完成（插件名）
    """

    plugin_installed = pyqtSignal(str)
    plugin_uninstalled = pyqtSignal(str)
    plugin_updated = pyqtSignal(str)

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent or main_window)

        self.main_window = main_window
        self.setWindowTitle("青草插件市场")
        self.resize(800, 600)

        # 客户端
        self.client = PluginStoreClient()

        # v2.9: 从 QSettings 加载自定义注册表 URL
        # 允许用户覆盖默认注册表地址（适配网络环境）
        self._settings = QSettings("QingCao", "PluginStore")
        custom_url = self._settings.value("registry_url", "", type=str)
        if custom_url:
            self.client.registry_url = custom_url

        # 插件列表
        self._all_plugins: List[PluginInfo] = []
        self._filtered_plugins: List[PluginInfo] = []

        # 设置
        self._settings = QSettings("QingCao", "PluginStore")
        self._current_category = "all"
        self._current_sort = "downloads"
        self._search_text = ""

        # 构建 UI
        self._build_ui()

        # 加载插件
        QTimer.singleShot(100, self._load_plugins)

    # --------------------------------------------------------
    # UI 构建
    # --------------------------------------------------------
    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 顶部工具栏
        toolbar = self._build_toolbar()
        layout.addWidget(toolbar)

        # 中间：插件列表
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #1e1e1e;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
            }
            QScrollBar:vertical {
                background-color: #2d2d2d;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #555;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #777;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

        # 插件容器
        self.plugins_container = QWidget()
        self.plugins_layout = QVBoxLayout(self.plugins_container)
        self.plugins_layout.setContentsMargins(8, 8, 8, 8)
        self.plugins_layout.setSpacing(6)
        self.plugins_layout.addStretch()

        self.scroll_area.setWidget(self.plugins_container)
        layout.addWidget(self.scroll_area, 1)

        # 状态栏
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")
        layout.addWidget(self.status_label)

        # 底部按钮
        bottom = QHBoxLayout()

        self.check_updates_btn = QPushButton("🔍 检查更新")
        self.check_updates_btn.clicked.connect(self._check_updates)
        bottom.addWidget(self.check_updates_btn)
        self.update_all_btn = QPushButton("⬆ 全部更新")
        self.update_all_btn.setToolTip("检查并更新所有兼容的插件（不兼容项自动跳过）")
        self.update_all_btn.clicked.connect(self._check_updates)
        self.update_all_btn.setObjectName("update_all_btn")
        self.update_all_btn.setStyleSheet(
            "QPushButton { background: #4a90d9; color: white; "
            "padding: 4px 12px; border-radius: 3px; }"
        )
        bottom.addWidget(self.update_all_btn)

        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.clicked.connect(self._refresh_plugins)
        bottom.addWidget(self.refresh_btn)

        bottom.addStretch()

        self.install_local_btn = QPushButton("📦 安装本地插件")
        self.install_local_btn.clicked.connect(self._install_local)
        bottom.addWidget(self.install_local_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)

        layout.addLayout(bottom)

        # 应用样式
        self._apply_style()

    def _build_toolbar(self) -> QWidget:
        """构建工具栏（v2.9：两行布局）"""
        toolbar = QWidget()
        outer = QVBoxLayout(toolbar)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # ====================================================
        # v2.9: 注册表 URL 配置行
        # ====================================================
        url_row = QHBoxLayout()
        url_row.setContentsMargins(0, 0, 0, 0)
        url_row.setSpacing(6)

        url_label = QLabel("注册表 URL:")
        url_label.setStyleSheet("color: #888; font-size: 11px;")
        url_row.addWidget(url_label)

        self.registry_url_edit = QLineEdit()
        self.registry_url_edit.setPlaceholderText("留空使用默认（jsDelivr CDN）")
        self.registry_url_edit.setText(self._settings.value("registry_url", "", type=str))
        self.registry_url_edit.setClearButtonEnabled(True)
        self.registry_url_edit.returnPressed.connect(self._on_registry_url_changed)
        url_row.addWidget(self.registry_url_edit, 1)

        self.apply_url_btn = QPushButton("应用并刷新")
        self.apply_url_btn.clicked.connect(self._on_registry_url_changed)
        url_row.addWidget(self.apply_url_btn)

        reset_url_btn = QPushButton("重置")
        reset_url_btn.setToolTip("恢复默认注册表地址")
        reset_url_btn.clicked.connect(self._on_reset_registry_url)
        url_row.addWidget(reset_url_btn)

        outer.addLayout(url_row)

        # v2.19：访问令牌 + TLS 校验（P1 审计缺口修复）
        auth_row = QHBoxLayout()
        auth_row.setContentsMargins(0, 0, 0, 0)
        auth_row.setSpacing(6)
        token_label = QLabel("访问令牌:")
        token_label.setStyleSheet("color: #888; font-size: 11px;")
        auth_row.addWidget(token_label)
        self.registry_token_edit = QLineEdit()
        self.registry_token_edit.setEchoMode(QLineEdit.Password)
        self.registry_token_edit.setPlaceholderText("Bearer Token（可选，留空表示未配置）")
        self.registry_token_edit.setText(self._settings.value("registry_token", "", type=str))
        self.registry_token_edit.setClearButtonEnabled(True)
        auth_row.addWidget(self.registry_token_edit, 1)
        self.registry_tls_cb = QCheckBox("校验 TLS 证书")
        self.registry_tls_cb.setChecked(
            self._settings.value("registry_verify_tls", True, type=bool)
        )
        auth_row.addWidget(self.registry_tls_cb)
        outer.addLayout(auth_row)

        # ====================================================
        # 原有的搜索/分类/排序行
        # ====================================================
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(8)

        # 临时把 layout 指向 filter_row，后面的 addWidget 会加到这一行
        layout = filter_row

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索插件...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_edit, 1)

        # 分类下拉
        self.category_combo = QComboBox()
        for key, name in CATEGORIES:
            self.category_combo.addItem(name, key)
        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        layout.addWidget(self.category_combo)

        # 排序下拉
        self.sort_combo = QComboBox()
        for key, name in SORT_OPTIONS:
            self.sort_combo.addItem(name, key)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        layout.addWidget(self.sort_combo)

        # 把 filter_row 加到 toolbar 的 outer 布局
        # 安全状态筛选（v2.17）
        self.security_combo = QComboBox()
        for _key, _label in SECURITY_FILTERS:
            self.security_combo.addItem(_label, _key)
        self.security_combo.currentIndexChanged.connect(lambda *a: self._apply_filters())
        filter_row.addWidget(self.security_combo)

        outer.addLayout(filter_row)

        return toolbar

    # ========================================================
    # v2.9: 注册表 URL 处理
    # ========================================================
    def _on_registry_url_changed(self):
        """用户点击"应用并刷新"或按回车"""
        url = self.registry_url_edit.text().strip()

        # 简单校验
        if url and not (url.startswith("http://") or url.startswith("https://")):
            QMessageBox.warning(self, "URL 格式错误", "注册表 URL 必须以 http:// 或 https:// 开头")
            return

        # 保存到 QSettings
        if url:
            self._settings.setValue("registry_url", url)
        else:
            self._settings.remove("registry_url")

        # v2.19：访问令牌 + TLS 校验
        token = ""
        try:
            token = self.registry_token_edit.text().strip()
        except Exception:
            token = ""
        if token:
            self._settings.setValue("registry_token", token)
        else:
            self._settings.remove("registry_token")
        verify_tls = True
        try:
            verify_tls = self.registry_tls_cb.isChecked()
        except Exception:
            verify_tls = True
        self._settings.setValue("registry_verify_tls", verify_tls)

        # 应用到 client
        if url:
            self.client.registry_url = url
        else:
            # 恢复默认
            self.client.registry_url = DEFAULT_REGISTRY_URL

        # v2.19：应用到客户端（Token / TLS）
        try:
            self.client.registry_token = token
            self.client.verify_tls = verify_tls
        except Exception:
            pass

        # 清缓存并刷新
        self.client.clear_cache()
        self._load_plugins(force=True)

        QMessageBox.information(
            self, "已应用", f"注册表地址已更新：\n{url or '(默认)'}\n\n正在重新拉取插件列表..."
        )

    def _on_reset_registry_url(self):
        """重置为默认 URL"""
        self.registry_url_edit.clear()
        self._settings.remove("registry_url")
        self.client.registry_url = DEFAULT_REGISTRY_URL
        self.client.clear_cache()
        self._load_plugins(force=True)

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #007acc;
            }
            QComboBox {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
                min-width: 120px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: #d4d4d4;
                selection-background-color: #094771;
                border: 1px solid #3c3c3c;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0a4d7a;
            }
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #666;
            }
        """)

    # --------------------------------------------------------
    # 加载插件
    # --------------------------------------------------------
    def _load_plugins(self, force: bool = False):
        """加载插件列表（异步）。

        修复说明（异步加载）:
            原实现同步调用 get_all_plugins()，内部 fetch_registry()
            会顺序请求主 URL + fallback URL，每次 requests.get()
            超时 30 秒 → 主线程被阻塞 30~60 秒，窗口"未响应"。

            新实现分两步：
              1. 立即同步加载本地插件（毫秒级）并显示
              2. 后台线程拉远程注册表，完成后通过信号回传刷新
        """
        # ---- 第 1 步：立即显示本地插件 ----
        self._load_community_ratings()
        self.status_label.setText("正在扫描本地插件...")
        self.refresh_btn.setEnabled(False)

        try:
            # v2.9: 先用 cache_first 快速合并（本地 + 磁盘缓存）
            # 不发起网络请求，确保 UI 立即有内容
            try:
                fast_registry = self.client.fetch_registry(force=False, cache_first=True)
            except Exception:
                fast_registry = None

            if fast_registry:
                # 有磁盘缓存：一次性合并远程 + 本地
                self._all_plugins = self.client.get_all_plugins(force=False)
                self.status_label.setText(
                    f"已从缓存加载 {len(self._all_plugins)} 个插件，后台刷新中..."
                )
            else:
                # 无缓存：只显示本地
                local_plugins = self.client.scan_local_plugins()
                self._all_plugins = list(local_plugins.values())
                for p in self._all_plugins:
                    p.state = PluginState.INSTALLED
                self.status_label.setText(
                    f"已加载 {len(self._all_plugins)} 个本地插件，正在拉取远程列表..."
                )
            self._apply_filters()

        except Exception as e:
            print(f"[PluginStore] 加载插件失败: {e}")
            self._all_plugins = []
            self._apply_filters()

        # ---- 第 2 步：后台拉远程 ----
        # 用 QThread 避免阻塞主线程。
        self._registry_worker = RegistryFetchWorker(self.client, force=force, parent=self)
        self._registry_worker.registry_ready.connect(self._on_registry_loaded)
        self._registry_worker.failed.connect(self._on_registry_failed)
        self._registry_worker.start()

    def _on_registry_loaded(self, registry: dict):
        """后台拉取远程注册表成功"""
        try:
            # 重新合并远程 + 本地
            self._all_plugins = self.client.get_all_plugins(force=False)
            self._apply_filters()
            self.status_label.setText(f"共 {len(self._all_plugins)} 个插件")
        except Exception as e:
            print(f"[PluginStore] 合并远程插件失败: {e}")
        finally:
            self.refresh_btn.setEnabled(True)

    def _on_registry_failed(self, error: str):
        """后台拉取远程注册表失败（已 fallback 到本地）"""
        print(f"[PluginStore] 远程注册表不可用: {error}")
        self.status_label.setText(f"共 {len(self._all_plugins)} 个插件（离线模式）")
        self.refresh_btn.setEnabled(True)

    def _load_community_ratings(self):
        """拉取静态 ratings.json（失败静默回退本地评分）。"""
        if getattr(self, "_community_ratings", None) is not None:
            return
        self._community_ratings = {}
        try:
            data = self.client.fetch_ratings() if hasattr(self.client, "fetch_ratings") else None
            plugins = (data or {}).get("plugins") or {}
            from ui.plugin_client import set_community_ratings

            set_community_ratings(plugins)
            self._community_ratings = plugins
        except Exception:
            self._community_ratings = {}

    def _refresh_plugins(self):
        """刷新插件列表"""
        self.client.clear_cache()
        self._load_plugins(force=True)

    # --------------------------------------------------------
    # 过滤与排序
    # --------------------------------------------------------
    def _on_search_changed(self, text: str):
        """搜索变化"""
        self._search_text = text.strip().lower()
        self._apply_filters()

    def _on_category_changed(self, index: int):
        """分类变化"""
        self._current_category = self.category_combo.currentData()
        self._apply_filters()

    def _on_sort_changed(self, index: int):
        """排序变化"""
        self._current_sort = self.sort_combo.currentData()
        self._apply_filters()

    def _apply_filters(self):
        """应用过滤和排序"""
        plugins = list(self._all_plugins)

        # 分类过滤
        if self._current_category == "installed":
            plugins = [p for p in plugins if p.is_installed]
        elif self._current_category == "updates":
            plugins = [p for p in plugins if p.has_update]
        elif self._current_category == "featured":
            plugins = [p for p in plugins if p.featured]
        elif self._current_category != "all":
            plugins = [p for p in plugins if p.category == self._current_category]

        # 搜索过滤
        if self._search_text:
            text = self._search_text
            plugins = [
                p
                for p in plugins
                if (
                    text in p.name.lower()
                    or text in p.display_name.lower()
                    or text in p.description.lower()
                    or any(text in tag.lower() for tag in p.tags)
                )
            ]

        # 安全状态筛选（v2.17）
        try:
            _sec_mode = self.security_combo.currentData()
        except Exception:
            _sec_mode = "all"
        plugins = filter_plugins_by_security(plugins, _sec_mode)

        # 排序
        if self._current_sort == "downloads":
            plugins.sort(key=lambda p: p.downloads, reverse=True)
        elif self._current_sort == "rating":
            plugins.sort(key=lambda p: p.rating, reverse=True)
        elif self._current_sort == "local_rating":
            try:
                from ui.plugin_rating import LocalRatings

                _lr = LocalRatings().all()
            except Exception:
                _lr = {}
            plugins.sort(key=lambda p: (_lr.get(p.name) or {}).get("stars", 0), reverse=True)
        elif self._current_sort == "updated":
            plugins.sort(key=lambda p: p.updated_at or "", reverse=True)
        elif self._current_sort == "name":
            plugins.sort(key=lambda p: p.display_title.lower())
        elif self._current_sort == "community_rating":
            from ui.plugin_client import get_community_rating

            def _community_score(p):
                r = get_community_rating(p.name)
                return (r[0] if r else 0.0)

            plugins.sort(key=_community_score, reverse=True)
        elif self._current_sort == "trending":
            # 按下载量 + 评分综合
            plugins.sort(key=lambda p: p.downloads * 0.7 + p.rating * 100 * 0.3, reverse=True)

        self._filtered_plugins = plugins
        self._render_plugins()

    def _render_plugins(self):
        """渲染插件列表"""
        # 清空现有卡片
        while self.plugins_layout.count() > 1:
            item = self.plugins_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 无结果
        if not self._filtered_plugins:
            empty_label = QLabel("没有找到匹配的插件")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
            self.plugins_layout.insertWidget(0, empty_label)
            self.status_label.setText("无结果")
            return

        # 添加卡片
        for plugin in self._filtered_plugins:
            card = PluginCard(plugin)
            card.install_clicked.connect(self._on_install)
            card.uninstall_clicked.connect(self._on_uninstall)
            card.update_clicked.connect(self._on_update)
            card.detail_clicked.connect(self._on_show_detail)

            self.plugins_layout.insertWidget(self.plugins_layout.count() - 1, card)

        self.status_label.setText(
            f"显示 {len(self._filtered_plugins)} / {len(self._all_plugins)} 个插件"
        )

    # --------------------------------------------------------
    # 操作处理
    # --------------------------------------------------------
    def _on_install(self, info: PluginInfo):
        """
                # 兼容性门控：不兼容直接拒绝（与更新器后端门控一致）
                _ok, _reason = check_plugin_compatibility(info)
                if not _ok:
                    QMessageBox.warning(
                        self, "不兼容",
                        "该插件与当前版本不兼容，已取消：\n\n" + _reason)
                    return
        安装插件"""
        if not self._confirm_risk(info, "安装"):
            return

        # 检查依赖
        satisfied, missing = info.get_dependency_status()
        if not satisfied:
            msg = (
                "以下 Python 依赖未安装：\n\n"
                + "\n".join(f"• {d}" for d in missing)
                + "\n\n是否尝试自动安装？"
            )

            reply = QMessageBox.question(
                self, "缺少依赖", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )

            if reply != QMessageBox.Yes:
                return

        # 显示进度
        progress_dlg = InstallProgressDialog(info.display_title, self)
        progress_dlg.show()

        def on_progress(value: int, status: str):
            progress_dlg.update_progress(value, status)
            QApplication.processEvents()

            if progress_dlg.is_cancelled():
                return

        # 执行安装
        success, msg = self.client.install_plugin(info, progress_callback=on_progress)

        progress_dlg.close()

        if success:
            QMessageBox.information(self, "安装成功", msg)
            self.plugin_installed.emit(info.name)

            # 刷新列表
            self._load_plugins()

            # 通知用户重启
            QMessageBox.information(
                self, "提示", "插件已安装，请重载插件（插件面板 → 重载）或重启编辑器后生效。"
            )
        else:
            QMessageBox.critical(self, "安装失败", msg)

    def _confirm_risk(self, info, action="安装"):
        """高权限插件安装/更新前的显式确认（默认拒绝高风险）。"""
        try:
            from core.plugin_risk import classify_plugin_risk, risk_message

            level = classify_plugin_risk(
                getattr(info, "permissions", []),
                sandboxed=bool(getattr(info, "sandbox", False)),
            )
            if level == "low":
                return True
            title, msg, _level = risk_message(info, action)
            default = QMessageBox.No if level == "high" else QMessageBox.Yes
            reply = QMessageBox.question(
                self, title, msg, QMessageBox.Yes | QMessageBox.No, default
            )
            return reply == QMessageBox.Yes
        except Exception:
            return False

    def _on_uninstall(self, info: PluginInfo):
        """卸载插件"""
        reply = QMessageBox.question(
            self,
            "确认卸载",
            f"确定要卸载插件 {info.display_title} 吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        success, msg = self.client.uninstall_plugin(info)

        if success:
            QMessageBox.information(self, "卸载成功", msg)
            self.plugin_uninstalled.emit(info.name)
            self._load_plugins()
        else:
            QMessageBox.critical(self, "卸载失败", msg)

    def _on_update(self, info: PluginInfo):
        """
                # 兼容性门控：不兼容直接拒绝（与更新器后端门控一致）
                _ok, _reason = check_plugin_compatibility(info)
                if not _ok:
                    QMessageBox.warning(
                        self, "不兼容",
                        "该插件与当前版本不兼容，已取消：\n\n" + _reason)
                    return
        更新插件"""
        if not self._confirm_risk(info, "更新"):
            return
        progress_dlg = InstallProgressDialog(info.display_title, self)
        progress_dlg.show()

        def on_progress(value: int, status: str):
            progress_dlg.update_progress(value, status)
            QApplication.processEvents()

        success, msg = self.client.update_plugin(info, progress_callback=on_progress)

        progress_dlg.close()

        if success:
            QMessageBox.information(self, "更新成功", msg)
            self.plugin_updated.emit(info.name)
            self._load_plugins()
        else:
            QMessageBox.critical(self, "更新失败", msg)

    def _on_show_detail(self, info: PluginInfo):
        """显示详情"""
        dlg = PluginDetailDialog(info, self)
        dlg.install_clicked.connect(self._on_install)
        dlg.uninstall_clicked.connect(self._on_uninstall)
        dlg.update_clicked.connect(self._on_update)
        dlg.exec()

    # --------------------------------------------------------
    # 检查更新
    # --------------------------------------------------------
    def _check_updates(self):
        """检查所有插件的更新"""
        self.status_label.setText("正在检查更新...")
        self.check_updates_btn.setEnabled(False)

        try:
            updates = self.client.check_updates()

            if updates:
                msg = f"发现 {len(updates)} 个插件可更新：\n\n"
                msg += "\n".join(
                    f"• {p.display_title} ({p.installed_version} → {p.version})"
                    for p in updates[:10]
                )
                if len(updates) > 10:
                    msg += f"\n... 及其他 {len(updates) - 10} 个"

                reply = QMessageBox.question(
                    self,
                    "检查更新",
                    msg + "\n\n是否全部更新？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )

                if reply == QMessageBox.Yes:
                    self._update_all(updates)
            else:
                QMessageBox.information(self, "检查更新", "所有插件都是最新的")

        except Exception as e:
            QMessageBox.warning(self, "检查更新失败", str(e))

        finally:
            self.check_updates_btn.setEnabled(True)
            self.status_label.setText("")

    def _update_all(self, updates: List[PluginInfo]):
        """批量更新（不兼容项自动跳过，NPP Plugins Admin 同款）"""
        _compat, _skipped = [], []
        for _info in updates:
            _ok, _reason = check_plugin_compatibility(_info)
            if _ok:
                _compat.append(_info)
            else:
                _skipped.append((_info, _reason))
        if _skipped:
            QMessageBox.information(
                self,
                "跳过不兼容",
                "以下插件与当前应用版本不兼容，已跳过更新：\n\n"
                + "\n".join("• %s：%s" % (i.display_title, r) for i, r in _skipped),
            )
        updates = _compat
        if not updates:
            return

        success_count = 0
        failed_count = 0

        progress_dlg = InstallProgressDialog(f"{len(updates)} 个插件", self)
        progress_dlg.show()

        for i, info in enumerate(updates):
            if progress_dlg.is_cancelled():
                break

            progress_dlg.update_progress(
                int((i / len(updates)) * 100), f"更新 {info.display_title}..."
            )
            QApplication.processEvents()

            success, msg = self.client.update_plugin(info)

            if success:
                success_count += 1
            else:
                failed_count += 1

        progress_dlg.close()

        QMessageBox.information(
            self, "批量更新完成", f"成功: {success_count} 个\n失败: {failed_count} 个"
        )

        self._load_plugins()

    # --------------------------------------------------------
    # 安装本地插件
    # --------------------------------------------------------
    def _install_local(self):
        """安装本地插件（ZIP 文件）"""
        from PyQt5.QtWidgets import QFileDialog

        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择插件包", "", "插件包 (*.zip);;所有文件 (*.*)"
        )

        if not filepath:
            return

        try:
            # 读取文件
            with open(filepath, "rb") as f:
                data = f.read()

            # 获取插件名
            name = os.path.splitext(os.path.basename(filepath))[0]

            # 解压
            success, msg = self.client._extract_plugin(
                data, self.client.plugins_dir, name, PLUGIN_TYPE_PLUGIN
            )

            if success:
                QMessageBox.information(
                    self,
                    "安装成功",
                    f"插件已从 {os.path.basename(filepath)} 安装。\n重启编辑器后生效。",
                )
                self._load_plugins()
            else:
                QMessageBox.critical(self, "安装失败", msg)

        except Exception as e:
            QMessageBox.critical(self, "安装失败", str(e))

    # --------------------------------------------------------
    # 调试
    # --------------------------------------------------------
    def dump(self) -> str:
        """导出插件市场信息"""
        lines = ["PluginStoreDialog", "=" * 60]
        lines.append(f"插件总数: {len(self._all_plugins)}")
        lines.append(f"筛选后: {len(self._filtered_plugins)}")
        lines.append(f"当前分类: {self._current_category}")
        lines.append(f"当前排序: {self._current_sort}")
        lines.append(f"搜索: {self._search_text}")

        cache_info = self.client.get_cache_info()
        lines.append(f"缓存: {cache_info}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"<PluginStoreDialog plugins={len(self._all_plugins)} "
            f"filtered={len(self._filtered_plugins)}>"
        )


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # 测试客户端
    print("=== 测试 PluginStoreClient ===")
    client = PluginStoreClient()

    # 扫描本地插件
    local = client.scan_local_plugins()
    print(f"本地插件数: {len(local)}")
    for name, info in local.items():
        print(f"  - {name} v{info.version} ({info.type})")
    print()

    # 测试插件信息
    print("=== 测试 PluginInfo ===")
    info = PluginInfo(
        name="test_plugin",
        display_name="测试插件",
        version="1.0.0",
        description="这是一个测试插件",
        author="TomJerry",
        dependencies=["requests", "chardet"],
        permissions=["filesystem", "network"],
    )
    print(f"插件: {info}")
    print(f"显示标题: {info.display_title}")
    print(f"依赖状态: {info.get_dependency_status()}")
    print()

    # 测试版本比较
    print("=== 测试版本比较 ===")
    test_cases = [
        ("1.0.0", "1.0.1", True),
        ("1.0.1", "1.0.0", False),
        ("1.0.0", "2.0.0", True),
        ("2.0.0", "1.9.9", False),
        ("1.0.0", "1.0.0", False),
    ]
    for old, new, expected in test_cases:
        result = PluginStoreClient._is_newer_version(old, new)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {old} -> {new}: {result}")
    print()

    # 显示插件市场对话框
    print("=== 显示插件市场 ===")
    dlg = PluginStoreDialog()
    dlg.show()

    # 5 秒后退出
    from PyQt5.QtCore import QTimer

    QTimer.singleShot(5000, app.quit)

    sys.exit(app.exec())
