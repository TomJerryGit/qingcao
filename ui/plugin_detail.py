# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""插件详情/安装进度对话框（v2.23 D3 拆分）。"""

from ui.plugin_client import *  # noqa: F401,F403


class PluginDetailDialog(QDialog):
    """
    插件详情对话框。

    显示插件的完整信息。
    """

    install_clicked = pyqtSignal(object)
    uninstall_clicked = pyqtSignal(object)
    update_clicked = pyqtSignal(object)

    def __init__(self, info: PluginInfo, parent=None):
        super().__init__(parent)

        self.info = info
        self.setWindowTitle(f"插件详情 - {info.display_title}")
        self.resize(600, 500)

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 头部
        header = self._build_header()
        layout.addWidget(header)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #3c3c3c;")
        layout.addWidget(line)

        # 详细内容
        content = QTextBrowser()
        content.setOpenExternalLinks(True)
        content.setStyleSheet("""
            QTextBrowser {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
            }
        """)

        html = self._build_html()
        content.setHtml(html)
        layout.addWidget(content, 1)

        # 本地评分（v2.20 P1-3）
        try:
            layout.addWidget(self._build_rating_widget())
        except Exception:
            pass

        # 底部按钮
        btn_layout = QHBoxLayout()

        # 操作按钮
        self.action_btn = QPushButton()
        self.action_btn.setFixedWidth(100)
        self.action_btn.clicked.connect(self._on_action_clicked)
        btn_layout.addWidget(self.action_btn)

        btn_layout.addStretch()

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        self._update_action_button()

    def _build_rating_widget(self):
        """本地评分控件（仅本机）"""
        from PyQt5.QtWidgets import QGroupBox

        from ui.plugin_rating import LocalRatings, rating_text

        group = QGroupBox("本地评分（仅本机可见）")
        vbox = QVBoxLayout(group)
        row = QHBoxLayout()
        self.star_buttons = []
        try:
            existing = LocalRatings().get(self.info.name) or {}
        except Exception:
            existing = {}
        self._local_stars = int(existing.get("stars") or 0)
        for i in range(1, 6):
            btn = QPushButton("★" if i <= self._local_stars else "☆")
            btn.setFixedSize(30, 30)
            btn.setFlat(True)
            btn.clicked.connect(lambda _=False, n=i: self._set_local_stars(n))
            self.star_buttons.append(btn)
            row.addWidget(btn)
        self.rating_label = QLabel(rating_text(self._local_stars))
        self.rating_label.setStyleSheet("color: #7ec850;")
        row.addWidget(self.rating_label)
        row.addStretch()
        vbox.addLayout(row)
        self.rating_comment = QLineEdit(str(existing.get("comment") or ""))
        self.rating_comment.setPlaceholderText("简评（可选，仅本机保存）")
        vbox.addWidget(self.rating_comment)
        row2 = QHBoxLayout()
        save_btn = QPushButton("保存评分")
        save_btn.clicked.connect(self._save_local_rating)
        row2.addWidget(save_btn)
        self.rating_status = QLabel("")
        self.rating_status.setStyleSheet("color: #888; font-size: 11px;")
        row2.addWidget(self.rating_status)
        row2.addStretch()
        vbox.addLayout(row2)
        return group

    def _set_local_stars(self, stars):
        from ui.plugin_rating import rating_text

        self._local_stars = int(stars)
        for i, btn in enumerate(self.star_buttons, 1):
            btn.setText("★" if i <= stars else "☆")
        self.rating_label.setText(rating_text(stars))

    def _save_local_rating(self):
        from ui.plugin_rating import LocalRatings

        if self._local_stars <= 0:
            self.rating_status.setText("请先选择星级")
            return
        try:
            LocalRatings().set_rating(
                self.info.name, self._local_stars, self.rating_comment.text().strip()
            )
            self.rating_status.setText("已保存 ✓")
        except Exception as e:
            self.rating_status.setText("保存失败: %s" % e)

    def _build_header(self) -> QWidget:
        """构建头部"""
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)

        # 图标
        icon_label = QLabel()
        icon_label.setFixedSize(64, 64)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setText("🧩")
        icon_label.setStyleSheet("font-size: 40px; background-color: #2d2d2d; border-radius: 8px;")
        layout.addWidget(icon_label)

        # 信息
        info_layout = QVBoxLayout()

        name_label = QLabel(self.info.display_title)
        name_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #d4d4d4;")
        info_layout.addWidget(name_label)

        meta_parts = [f"v{self.info.version}"]

        if self.info.author:
            meta_parts.append(f"by {self.info.author}")

        if self.info.updated_at:
            try:
                date = self.info.updated_at[:10]
                meta_parts.append(f"更新于 {date}")
            except Exception:
                pass

        meta_label = QLabel(" · ".join(meta_parts))
        meta_label.setStyleSheet("color: #888; font-size: 12px;")
        info_layout.addWidget(meta_label)

        # 统计
        stats_layout = QHBoxLayout()

        if self.info.downloads > 0:
            downloads = QLabel(f"⬇ {self.info.downloads:,} 次下载")
            downloads.setStyleSheet("color: #666; font-size: 11px;")
            stats_layout.addWidget(downloads)

        if self.info.rating > 0:
            stars = "★" * int(self.info.rating) + "☆" * (5 - int(self.info.rating))
            rating = QLabel(f"{stars} ({self.info.rating_count})")
            rating.setStyleSheet("color: #f0ad4e; font-size: 11px;")
            stats_layout.addWidget(rating)
        try:
            from ui.plugin_client import get_community_rating

            _comm = get_community_rating(self.info.name)
            if _comm and _comm[1] > 0:
                c = QLabel("社区 ★ %.1f (%d 人)" % (_comm[0], _comm[1]))
                c.setStyleSheet("color: #61afef; font-size: 11px;")
                tip = "社区平均分 %.1f（%d 人评分，来自签名 ratings.json）" % (
                    _comm[0], _comm[1])
                if _comm[1] < 3:
                    tip += "\n样本不足 3 人，仅供参考"
                c.setToolTip(tip)
                stats_layout.addWidget(c)
        except Exception:
            pass

        stats_layout.addStretch()
        info_layout.addLayout(stats_layout)

        layout.addLayout(info_layout, 1)

        return header

    def _build_html(self) -> str:
        """构建详情 HTML"""
        html_parts = []

        try:
            _sec = plugin_signature_status(self.info)
            html_parts.append(f"<p>安全状态: <b>{_sec}</b></p>")
            _ok, _missing = self.info.get_dependency_status()
            if _ok:
                html_parts.append("<p>依赖状态: <b>全部满足</b></p>")
            else:
                html_parts.append("<p>依赖状态: <b>缺失 " + ", ".join(_missing) + "</b></p>")
        except Exception:
            pass

        html_parts.append("<style>")
        html_parts.append("""
            h3 { color: #7ec850; font-size: 14px;
                 border-bottom: 1px solid #3c3c3c;
                 padding-bottom: 4px; margin-top: 16px; }
            p { margin: 4px 0; }
            ul { margin: 4px 0; padding-left: 20px; }
            code { background-color: #2d2d2d; padding: 1px 4px;
                   border-radius: 3px; font-family: Consolas, monospace;
                   color: #ce9178; }
            .permission { color: #f0ad4e; }
            .dep { color: #9cdcfe; }
            .missing { color: #f14c4c; }
        """)
        html_parts.append("</style>")

        # 描述
        if self.info.description:
            html_parts.append(f"<p>{self.info.description}</p>")

        # 详细描述
        if self.info.long_description:
            html_parts.append("<h3>详细说明</h3>")
            html_parts.append(f"<p>{self.info.long_description}</p>")

        # 权限
        if self.info.permissions:
            html_parts.append("<h3>权限要求</h3>")
            html_parts.append("<ul>")
            for perm in self.info.permissions:
                desc = PERMISSION_DESCRIPTIONS.get(perm)
                if desc:
                    html_parts.append(f'<li class="permission">🔑 {desc[0]} - {desc[1]}</li>')
                else:
                    html_parts.append(f'<li class="permission">🔑 {perm}</li>')
            html_parts.append("</ul>")

        # 依赖
        if self.info.dependencies:
            html_parts.append("<h3>Python 依赖</h3>")
            satisfied, missing = self.info.get_dependency_status()

            html_parts.append("<ul>")
            for dep in self.info.dependencies:
                if dep in missing:
                    html_parts.append(f'<li class="missing">✗ {dep} (未安装)</li>')
                else:
                    html_parts.append(f'<li class="dep">✓ {dep}</li>')
            html_parts.append("</ul>")

        # 插件依赖
        if self.info.plugin_dependencies:
            html_parts.append("<h3>插件依赖</h3>")
            html_parts.append("<ul>")
            for dep in self.info.plugin_dependencies:
                html_parts.append(f"<li>🧩 {dep}</li>")
            html_parts.append("</ul>")

        # 链接
        links = []
        if self.info.homepage:
            links.append(f'<a href="{self.info.homepage}">🏠 主页</a>')
        if self.info.repository:
            links.append(f'<a href="{self.info.repository}">📦 仓库</a>')

        if links:
            html_parts.append("<h3>相关链接</h3>")
            html_parts.append("<p>" + " · ".join(links) + "</p>")

        # 技术信息
        html_parts.append("<h3>技术信息</h3>")
        html_parts.append("<ul>")
        html_parts.append(f"<li>类型: {self.info.type}</li>")
        html_parts.append(f"<li>分类: {self.info.category}</li>")
        html_parts.append(f"<li>版本: {self.info.version}</li>")

        if self.info.file_size > 0:
            size_str = self._format_size(self.info.file_size)
            html_parts.append(f"<li>大小: {size_str}</li>")

        if self.info.min_app_version:
            html_parts.append(f"<li>最低版本: {self.info.min_app_version}</li>")

        if self.info.max_app_version:
            html_parts.append(f"<li>最高版本: {self.info.max_app_version}</li>")

        _ok, _reason = check_plugin_compatibility(self.info)
        if _ok:
            html_parts.append("<li>✅ 兼容当前版本</li>")
        else:
            html_parts.append(f"<li>⚠️ 不兼容: {_reason}</li>")

        if getattr(self.info, "update_url", ""):
            _url = self.info.update_url
            html_parts.append(f"<li>更新地址: <a href='{_url}'>{_url}</a></li>")

        if getattr(self.info, "changelog", ""):
            html_parts.append("<li>更新日志: %s</li>" % self.info.changelog)

        if self.info.verified:
            html_parts.append("<li>✅ 已验证</li>")

        if self.info.tags:
            tags_str = ", ".join(self.info.tags)
            html_parts.append(f"<li>标签: {tags_str}</li>")

        html_parts.append("</ul>")

        html = "".join(html_parts)
        try:
            from ui.i18n_widgets import translate_html

            html = translate_html(html)
        except Exception:
            pass
        return html

    def _update_action_button(self):
        """更新操作按钮"""
        state = self.info.state

        if state == PluginState.NOT_INSTALLED:
            self.action_btn.setText("安装")
            self.action_btn.setStyleSheet(
                "background-color: #0e639c; color: white; "
                "border: none; border-radius: 4px; padding: 6px 12px;"
            )
            self.action_btn.setEnabled(True)

        elif state == PluginState.INSTALLED:
            self.action_btn.setText("卸载")
            self.action_btn.setEnabled(True)

        elif state == PluginState.UPDATE_AVAILABLE:
            self.action_btn.setText("更新")
            self.action_btn.setStyleSheet(
                "background-color: #7ec850; color: white; "
                "border: none; border-radius: 4px; padding: 6px 12px;"
            )
            self.action_btn.setEnabled(True)

        elif state == PluginState.DISABLED:
            self.action_btn.setText("启用")
            self.action_btn.setEnabled(True)

        else:
            self.action_btn.setText("不可用")
            self.action_btn.setEnabled(False)

    def _on_action_clicked(self):
        """操作按钮点击"""
        state = self.info.state

        if state == PluginState.NOT_INSTALLED:
            self.install_clicked.emit(self.info)
        elif state == PluginState.INSTALLED:
            self.uninstall_clicked.emit(self.info)
        elif state == PluginState.UPDATE_AVAILABLE:
            self.update_clicked.emit(self.info)
        elif state == PluginState.DISABLED:
            self.install_clicked.emit(self.info)

    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小"""
        if size < 1024:
            return f"{size} 字节"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / 1024 / 1024:.1f} MB"


class InstallProgressDialog(QDialog):
    """插件安装进度对话框"""

    def __init__(self, plugin_name: str, parent=None):
        super().__init__(parent)

        self.setWindowTitle("安装插件")
        self.setFixedSize(400, 150)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._cancelled = False

        layout = QVBoxLayout(self)

        # 插件名
        name_label = QLabel(f"正在安装: {plugin_name}")
        name_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(name_label)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        # 状态
        self.status_label = QLabel("准备中...")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.status_label)

        # 取消按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    def _on_cancel(self):
        """取消"""
        self._cancelled = True
        self.reject()

    def update_progress(self, value: int, status: str):
        """更新进度"""
        self.progress_bar.setValue(value)
        self.status_label.setText(status)

    def is_cancelled(self) -> bool:
        """是否已取消"""
        return self._cancelled
