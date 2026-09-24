#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - 主题市场
============================================================
- ThemeMarketDialog: 主对话框
- ThemeMarketClient: 拉远程 + 本地兜底
- ThemeMarketWorker: 异步拉取

复用：
- core/theme_pack.py     导入导出主题包
- infrastructure/theme_loader.py   加载应用主题

用法：
    dlg = ThemeMarketDialog(main_window)
    dlg.exec_()
"""

import os
import sys
import json
import time
from typing import Optional, List, Dict, Any, Tuple

from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QMessageBox, QFileDialog, QScrollArea, QFrame,
    QApplication, QComboBox, QProgressDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSettings
from PyQt5.QtGui import QColor, QIcon, QFont


# ============================================================
# 常量
# ============================================================
THEME_MARKET_TIMEOUT = 5

DEFAULT_MARKET_URL = (
    "https://cdn.jsdelivr.net/gh/"
    "qingcao-editor/themes-registry@main/registry.json"
)

FALLBACK_MARKET_URLS = [
    "https://raw.githubusercontent.com/"
    "qingcao-editor/themes-registry/main/registry.json",
    "https://gitee.com/qingcao-editor/themes-registry/raw/main/registry.json",
]


# ============================================================
# 异步 Worker
# ============================================================
class ThemeMarketWorker(QThread):
    """后台拉取主题市场"""

    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, client, force: bool = False, parent=None):
        super().__init__(parent)
        self.client = client
        self.force = force

    def run(self):
        try:
            data = self.client.fetch_registry(force=self.force)
            if data:
                self.finished.emit(data)
            else:
                self.failed.emit("无法获取主题市场数据")
        except Exception as e:
            self.failed.emit(str(e))


# ============================================================
# 市场客户端
# ============================================================
class ThemeMarketClient:
    """主题市场客户端"""

    def __init__(self, registry_url: str = DEFAULT_MARKET_URL):
        self.registry_url = registry_url
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time = 0.0

    def fetch_registry(self, force: bool = False,
                       cache_first: bool = False) -> Optional[Dict[str, Any]]:
        """拉取主题注册表"""
        # 内存缓存
        if not force and self._cache is not None:
            if time.time() - self._cache_time < 300:
                return self._cache

        # cache_first：读本地兜底
        if cache_first:
            fallback = self._load_fallback()
            if fallback:
                self._cache = fallback
                self._cache_time = time.time()
                return fallback
            return None

        # 尝试远程
        urls = [self.registry_url] + FALLBACK_MARKET_URLS
        for url in urls:
            try:
                data = self._download_json(url)
                if data and isinstance(data, dict):
                    self._cache = data
                    self._cache_time = time.time()
                    return data
            except Exception as e:
                print(f"[ThemeMarket] 拉取失败 ({url}): {e}")
                continue

        # 兜底
        fallback = self._load_fallback()
        if fallback:
            print("[ThemeMarket] 使用本地兜底")
            self._cache = fallback
            self._cache_time = time.time()
        return fallback

    def _download_json(self, url: str) -> Optional[Dict[str, Any]]:
        try:
            import requests
            resp = requests.get(url, timeout=THEME_MARKET_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            return None
        except ImportError:
            import urllib.request
            with urllib.request.urlopen(url, timeout=THEME_MARKET_TIMEOUT) as f:
                return json.loads(f.read().decode('utf-8'))

    def _load_fallback(self) -> Optional[Dict[str, Any]]:
        """读取 resources/theme_fallback.json"""
        try:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(root, "resources", "theme_fallback.json")
            if not os.path.exists(path):
                return None
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data['_from_fallback'] = True
            return data
        except Exception as e:
            print(f"[ThemeMarket] 读取本地兜底失败: {e}")
            return None

    def clear_cache(self):
        """P2-C3: 加 clear_cache 公开方法。

        原来外部直接访问 client._cache = None，破坏封装。
        """
        self._cache = None
        self._cache_time = 0.0

    def list_installed_themes(self) -> List[str]:
        """列出本地已安装主题（themes/*.json 的 name 字段）"""
        themes_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "themes"
        )
        result = []
        if os.path.isdir(themes_dir):
            for f in os.listdir(themes_dir):
                if f.endswith('.json'):
                    result.append(os.path.splitext(f)[0])
        return result

    def install_theme(self, theme: Dict[str, Any]) -> Tuple[bool, str]:
        """
        安装主题。

        支持两种来源：
        1. download_url 指向 zip 主题包 → 用 ThemePack.import_theme
        2. 直接内嵌 theme_data 字段 → 直接写 themes/{name}.json
        """
        try:
            from core.theme_pack import ThemePack
            from PyQt5.QtWidgets import QFileDialog

            # 来源 1：内嵌数据
            if theme.get('theme_data'):
                themes_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "themes"
                )
                os.makedirs(themes_dir, exist_ok=True)
                name = theme.get('name', 'theme')
                target = os.path.join(themes_dir, f"{name}.json")
                with open(target, 'w', encoding='utf-8') as f:
                    json.dump(theme['theme_data'], f, indent=2,
                              ensure_ascii=False)
                return True, f"已安装: {name}"

            # 来源 2：远程 zip
            url = theme.get('download_url', '')
            if not url:
                return False, "缺少下载地址"

            # 下载到临时文件
            import tempfile
            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.zip')
            os.close(tmp_fd)
            try:
                import requests
                resp = requests.get(url, timeout=THEME_MARKET_TIMEOUT)
                if resp.status_code != 200:
                    return False, f"下载失败: HTTP {resp.status_code}"
                with open(tmp_path, 'wb') as f:
                    f.write(resp.content)

                themes_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "themes"
                )
                ok, msg = ThemePack.import_theme(tmp_path, themes_dir)
                return ok, msg
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        except Exception as e:
            return False, str(e)

    def delete_theme(self, name: str) -> Tuple[bool, str]:
        """删除本地主题"""
        try:
            themes_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "themes"
            )
            path = os.path.join(themes_dir, f"{name}.json")
            if not os.path.exists(path):
                return False, "主题不存在"
            os.remove(path)
            return True, f"已删除: {name}"
        except Exception as e:
            return False, str(e)


# ============================================================
# 主题卡片
# ============================================================
class ThemeCard(QFrame):
    """单个主题卡片"""

    install_clicked = pyqtSignal(dict)
    delete_clicked = pyqtSignal(dict)
    preview_clicked = pyqtSignal(dict)

    def __init__(self, theme: Dict[str, Any], installed: bool,
                 parent=None):
        super().__init__(parent)
        self.theme = theme
        self.installed = installed
        self.setObjectName("ThemeCard")
        self.setFrameShape(QFrame.StyledPanel)
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # 图标
        icon = QLabel("🎨")
        icon.setFixedSize(40, 40)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(
            "font-size: 24px; background-color: #2d2d2d; "
            "border-radius: 6px;"
        )
        layout.addWidget(icon)

        # 信息
        info = QVBoxLayout()
        info.setSpacing(2)

        # 标题行
        title_row = QHBoxLayout()
        title = QLabel(self.theme.get('display_name',
                                       self.theme.get('name', '未命名')))
        title.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #d4d4d4;"
        )
        title_row.addWidget(title)

        version = QLabel(f"v{self.theme.get('version', '1.0.0')}")
        version.setStyleSheet("font-size: 11px; color: #888;")
        title_row.addWidget(version)

        if self.theme.get('verified'):
            verified = QLabel("✅")
            verified.setToolTip("已验证")
            title_row.addWidget(verified)

        if self.theme.get('featured'):
            featured = QLabel("⭐")
            featured.setToolTip("精选")
            title_row.addWidget(featured)

        title_row.addStretch()
        info.addLayout(title_row)

        # 描述
        desc = QLabel(self.theme.get('description', '（无描述）'))
        desc.setStyleSheet("font-size: 11px; color: #888;")
        desc.setWordWrap(True)
        info.addWidget(desc)

        # 作者
        if self.theme.get('author'):
            author = QLabel(f"👤 {self.theme['author']}")
            author.setStyleSheet("font-size: 10px; color: #666;")
            info.addWidget(author)

        layout.addLayout(info, 1)

        # 按钮
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(4)

        if self.installed:
            self.action_btn = QPushButton("已安装")
            self.action_btn.setEnabled(False)
            self.action_btn.setStyleSheet(
                "background-color: #3c3c3c; color: #888;"
            )
        else:
            self.action_btn = QPushButton("安装")
            self.action_btn.setStyleSheet(
                "background-color: #0e639c; color: white;"
            )
            self.action_btn.clicked.connect(
                lambda: self.install_clicked.emit(self.theme)
            )
        self.action_btn.setFixedWidth(80)
        btn_layout.addWidget(self.action_btn)

        # 预览按钮
        self.preview_btn = QPushButton("预览")
        self.preview_btn.setFixedWidth(80)
        self.preview_btn.setStyleSheet(
            "background-color: #555; color: white;"
        )
        self.preview_btn.clicked.connect(
            lambda: self.preview_clicked.emit(self.theme)
        )
        btn_layout.addWidget(self.preview_btn)

        # 删除按钮（仅已安装）
        if self.installed:
            self.delete_btn = QPushButton("删除")
            self.delete_btn.setFixedWidth(80)
            self.delete_btn.setStyleSheet(
                "background-color: #8f1e1e; color: white;"
            )
            self.delete_btn.clicked.connect(
                lambda: self.delete_clicked.emit(self.theme)
            )
            btn_layout.addWidget(self.delete_btn)

        layout.addLayout(btn_layout)

    def _apply_style(self):
        self.setStyleSheet("""
            QFrame#ThemeCard {
                background-color: #2d2d2d;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
            }
            QFrame#ThemeCard:hover {
                background-color: #333333;
                border-color: #4c4c4c;
            }
            QFrame#ThemeCard QLabel {
                background-color: transparent;
            }
            QFrame#ThemeCard QPushButton {
                border: none;
                border-radius: 3px;
                padding: 5px;
                font-size: 11px;
            }
            QFrame#ThemeCard QPushButton:hover {
                background-color: #1177bb;
            }
        """)


# ============================================================
# 主题市场对话框
# ============================================================
class ThemeMarketDialog(QDialog):
    """
    主题市场对话框。

    布局:
        [搜索框] [分类▾] [注册表URL输入] [应用] [刷新]
        [主题卡片列表（滚动）]
        [状态栏] [关闭]
    """

    theme_installed = pyqtSignal(str)
    theme_deleted = pyqtSignal(str)

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.setWindowTitle("主题市场")
        self.resize(760, 560)

        self._settings = QSettings("QingCao", "ThemeMarket")
        self.client = ThemeMarketClient()

        custom_url = self._settings.value("registry_url", "", type=str)
        if custom_url:
            self.client.registry_url = custom_url

        self._all_themes: List[Dict[str, Any]] = []
        self._installed: List[str] = self.client.list_installed_themes()
        self._worker: Optional[ThemeMarketWorker] = None

        self._build_ui()
        self._apply_style()

        QTimer.singleShot(50, self._load)

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 工具栏（两行）
        toolbar = QVBoxLayout()
        toolbar.setSpacing(4)

        # 第一行：URL 配置
        url_row = QHBoxLayout()
        url_row.setSpacing(6)

        url_label = QLabel("注册表:")
        url_label.setStyleSheet("color: #888; font-size: 11px;")
        url_row.addWidget(url_label)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("留空使用默认")
        self.url_edit.setText(
            self._settings.value("registry_url", "", type=str)
        )
        self.url_edit.setClearButtonEnabled(True)
        url_row.addWidget(self.url_edit, 1)

        apply_url_btn = QPushButton("应用")
        apply_url_btn.clicked.connect(self._on_apply_url)
        url_row.addWidget(apply_url_btn)

        reset_url_btn = QPushButton("重置")
        reset_url_btn.setToolTip("恢复默认")
        reset_url_btn.clicked.connect(self._on_reset_url)
        url_row.addWidget(reset_url_btn)

        toolbar.addLayout(url_row)

        # 第二行：搜索 + 分类 + 刷新
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索主题...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.search_edit, 1)

        self.category_combo = QComboBox()
        self.category_combo.addItems([
            "全部", "已安装", "深色", "浅色", "高对比度"
        ])
        self.category_combo.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self.category_combo)

        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.clicked.connect(lambda: self._load(force=True))
        filter_row.addWidget(self.refresh_btn)

        toolbar.addLayout(filter_row)
        layout.addLayout(toolbar)

        # 卡片列表（滚动）
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setSpacing(6)
        self.cards_layout.addStretch()

        self.scroll.setWidget(self.cards_container)
        layout.addWidget(self.scroll, 1)

        # 状态栏
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            "color: #888; font-size: 11px; padding: 4px;"
        )
        layout.addWidget(self.status_label)

        # 底部按钮
        bottom = QHBoxLayout()
        bottom.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)

        layout.addLayout(bottom)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; }
            QLineEdit, QComboBox {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #007acc;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QScrollArea {
                background-color: #1e1e1e;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
            }
        """)

    # --------------------------------------------------------
    # 加载
    # --------------------------------------------------------
    def _load(self, force: bool = False):
        self.status_label.setText("正在加载...")
        self.refresh_btn.setEnabled(False)

        # 1. 先用本地兜底快速渲染
        try:
            quick = self.client.fetch_registry(cache_first=True)
            if quick:
                self._all_themes = (
                    quick.get('themes', []) + quick.get('plugins', [])
                )
                # 只保留 type=theme
                self._all_themes = [
                    t for t in self._all_themes
                    if t.get('type', 'theme') == 'theme'
                ]
                self._render()
                src = "本地兜底" if quick.get('_from_fallback') else "缓存"
                self.status_label.setText(
                    f"已从{src}加载 {len(self._all_themes)} 个主题，"
                    f"正在拉取远程..."
                )
        except Exception as e:
            print(f"[ThemeMarket] 快速加载失败: {e}")

        # 2. 后台拉远程
        self._worker = ThemeMarketWorker(self.client, force=force, parent=self)
        self._worker.finished.connect(self._on_remote_loaded)
        self._worker.failed.connect(self._on_remote_failed)
        self._worker.start()

    def _on_remote_loaded(self, data: dict):
        themes = data.get('themes', [])
        if not themes:
            # 兼容把主题混在 plugins 里的情况
            themes = [
                p for p in data.get('plugins', [])
                if p.get('type') == 'theme'
            ]

        self._all_themes = themes
        self._render()
        self.status_label.setText(f"共 {len(themes)} 个主题")
        self.refresh_btn.setEnabled(True)

    def _on_remote_failed(self, err: str):
        print(f"[ThemeMarket] 远程加载失败: {err}")
        self.status_label.setText(
            f"离线模式（{len(self._all_themes)} 个主题）"
        )
        self.refresh_btn.setEnabled(True)

    # --------------------------------------------------------
    # 过滤与渲染
    # --------------------------------------------------------
    def _apply_filter(self):
        self._render()

    def _render(self):
        # 清空旧卡片
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        keyword = self.search_edit.text().strip().lower()
        category = self.category_combo.currentText()

        shown = 0
        for theme in self._all_themes:
            name = theme.get('name', '')
            display = theme.get('display_name', name).lower()

            # 搜索
            if keyword:
                text = f"{name} {display} {theme.get('description', '')}".lower()
                if keyword not in text:
                    continue

            # 分类
            if category == "已安装":
                if name not in self._installed:
                    continue
            elif category == "深色":
                if theme.get('category') != 'dark':
                    continue
            elif category == "浅色":
                if theme.get('category') != 'light':
                    continue
            elif category == "高对比度":
                if theme.get('category') != 'high_contrast':
                    continue

            installed = name in self._installed
            card = ThemeCard(theme, installed)
            card.install_clicked.connect(self._on_install)
            card.delete_clicked.connect(self._on_delete)
            card.preview_clicked.connect(self._on_preview)

            self.cards_layout.insertWidget(
                self.cards_layout.count() - 1, card
            )
            shown += 1

        if shown == 0:
            empty = QLabel("没有匹配的主题")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                "color: #888; padding: 40px; font-size: 13px;"
            )
            self.cards_layout.insertWidget(0, empty)

    # --------------------------------------------------------
    # 操作
    # --------------------------------------------------------
    def _on_install(self, theme: dict):
        ok, msg = self.client.install_theme(theme)
        if ok:
            QMessageBox.information(self, "成功", msg)
            self._installed = self.client.list_installed_themes()
            self._render()
            self.theme_installed.emit(theme.get('name', ''))
        else:
            QMessageBox.warning(self, "安装失败", msg)

    def _on_delete(self, theme: dict):
        name = theme.get('name', '')
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除主题 {name} 吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        ok, msg = self.client.delete_theme(name)
        if ok:
            QMessageBox.information(self, "成功", msg)
            self._installed = self.client.list_installed_themes()
            self._render()
            self.theme_deleted.emit(name)
        else:
            QMessageBox.warning(self, "删除失败", msg)

    def _on_preview(self, theme: dict):
        """预览主题：临时应用到主窗口编辑器，3 秒后恢复"""
        if not self.main_window:
            return

        name = theme.get('name', '')
        from infrastructure.theme_loader import ThemeLoader
        loader = ThemeLoader()
        loaded = loader.load_by_name(name)
        if not loaded:
            QMessageBox.information(
                self, "提示",
                f"未找到主题文件: {name}\n请先安装后再预览。"
            )
            return

        # 记录当前主题
        current = loader.current_theme

        # P1-B8: generation counter 防止预览覆盖
        # 用户 3 秒内连点不同主题的"预览"，多个 restore 定时器
        # 会依次触发，把界面恢复成错误的状态。
        # 每次预览递增 generation，只有最新的 restore 才执行。
        self._preview_gen = getattr(self, '_preview_gen', 0) + 1
        gen = self._preview_gen

        # 临时应用
        try:
            for i in range(self.main_window.tabs.count()):
                loader.apply(self.main_window.tabs.widget(i), loaded)
            if loaded.qss:
                self.main_window.setStyleSheet(loaded.qss)

            # 3 秒后恢复
            def restore():
                # 有更新的预览请求 → 跳过本次恢复
                if getattr(self, '_preview_gen', 0) != gen:
                    return
                if current:
                    for i in range(self.main_window.tabs.count()):
                        loader.apply(
                            self.main_window.tabs.widget(i), current
                        )
                    if current.qss:
                        self.main_window.setStyleSheet(current.qss)

            QTimer.singleShot(3000, restore)
        except Exception as e:
            QMessageBox.warning(self, "预览失败", str(e))

    def _on_apply_url(self):
        url = self.url_edit.text().strip()
        if url and not url.startswith(('http://', 'https://')):
            QMessageBox.warning(
                self, "URL 错误",
                "URL 必须以 http:// 或 https:// 开头"
            )
            return
        if url:
            self._settings.setValue("registry_url", url)
            self.client.registry_url = url
        else:
            self._settings.remove("registry_url")
            self.client.registry_url = DEFAULT_MARKET_URL
        # P2-C3: 用公开方法
        self.client.clear_cache()
        self._load(force=True)

    def _on_reset_url(self):
        self.url_edit.clear()
        self._settings.remove("registry_url")
        self.client.registry_url = DEFAULT_MARKET_URL
        # P2-C3: 用公开方法
        self.client.clear_cache()
        self._load(force=True)