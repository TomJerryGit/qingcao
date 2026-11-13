# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""插件卡片与评分筛选辅助（v2.25 从 plugin_store 拆出）。"""

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
                _tip = "社区平均分 %.1f（%d 人评分，来自签名 ratings.json）" % (_comm[0], _comm[1])
                if _comm[1] < 3:
                    _tip += "\n样本不足 3 人，仅供参考"
                _c.setToolTip(_tip)
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


def should_show_rating_invite(plugins, local_ratings, dismissed) -> bool:
    """是否展示评分邀请：未关闭、从未评分、且至少安装过 1 个插件。"""
    if dismissed:
        return False
    if local_ratings:
        return False
    try:
        return any(getattr(p, "is_installed", False) for p in (plugins or []))
    except Exception:
        return False


RATING_FILTERS = [
    ("all", "全部评分"),
    ("4", "★4 分以上"),
    ("3", "★3 分以上"),
    ("none", "未评分"),
]


def plugin_rating_score(plugin, community_getter, local_ratings):
    """返回 (平均分, 人数)：优先社区评分，其次本地评分。"""
    try:
        c = community_getter(plugin.name)
    except Exception:
        c = None
    if c and c[1] > 0:
        return c
    rec = (local_ratings or {}).get(plugin.name) or {}
    try:
        if rec.get("stars"):
            return (float(rec["stars"]), 1)
    except Exception:
        pass
    return (0.0, 0)


def passes_rating_filter(score, mode):
    avg, count = score
    if mode == "all":
        return True
    if mode == "none":
        return count == 0
    try:
        threshold = float(mode)
    except Exception:
        return True
    return count > 0 and avg >= threshold


def update_count(plugins):
    return sum(1 for p in (plugins or []) if getattr(p, "has_update", False))
