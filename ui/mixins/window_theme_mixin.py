# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""MainWindow theme 职责（v2.23 D2 拆分）。"""

from ui.main_window_common import *  # noqa: F401,F403
from ui.main_window_common import _TopLevelThemeFilter  # noqa: F401


class WindowThemeMixin:
    # ========================================================
    # 中央区域
    # ========================================================
    def _build_central(self):
        """构建中央区域"""
        # 用 QStackedWidget 实现欢迎页与编辑区的切换
        self.central_stack = QStackedWidget()

        # 标签管理器
        try:
            from app.tabs import TabManager

            self.tabs = TabManager()
        except Exception as e:
            print(f"[MainWindow] TabManager 加载失败: {e}")
            self.tabs = self._create_fallback_tabs()

        self.central_stack.addWidget(self.tabs)

        # 欢迎页
        try:
            from ui.welcome_widget import WelcomeWidget

            self.welcome = WelcomeWidget(self)

            # 兼容不同的信号名
            if hasattr(self.welcome, "new_file_requested"):
                self.welcome.new_file_requested.connect(self._new_file)
            elif hasattr(self.welcome, "new_file"):
                self.welcome.new_file.connect(self._new_file)

            if hasattr(self.welcome, "open_file_requested"):
                self.welcome.open_file_requested.connect(self._open_file)
            elif hasattr(self.welcome, "open_file"):
                self.welcome.open_file.connect(self._open_file)

            if hasattr(self.welcome, "open_folder_requested"):
                self.welcome.open_folder_requested.connect(self._open_folder)

            if hasattr(self.welcome, "open_recent_file"):
                self.welcome.open_recent_file.connect(self._open_recent_file)

            if hasattr(self.welcome, "open_recent_project"):
                self.welcome.open_recent_project.connect(self._open_recent_project)

            if hasattr(self.welcome, "open_plugin_store"):
                self.welcome.open_plugin_store.connect(self._show_plugin_store)

            if hasattr(self.welcome, "open_command_palette"):
                self.welcome.open_command_palette.connect(self._show_command_palette)

            self.central_stack.addWidget(self.welcome)
        except Exception as e:
            print(f"[MainWindow] WelcomeWidget 加载失败: {e}")
            self.welcome = None

        # 默认显示欢迎页（视图 → 显示欢迎页 可关闭；NPP 默认无欢迎页）
        show_welcome = True
        try:
            show_welcome = bool(self.prefs.get("show_welcome_page", True))
        except Exception:
            pass
        self._welcome_visible_pref = show_welcome
        if self.tabs.count() == 0 and show_welcome:
            self.central_stack.setCurrentIndex(1)
        else:
            self.central_stack.setCurrentIndex(0)

        self.setCentralWidget(self.central_stack)

        # 标签切换信号
        try:
            self.tabs.currentChanged.connect(self._on_tab_changed)
        except Exception:
            pass

        try:
            self.tabs.all_tabs_closed.connect(self._on_all_tabs_closed)
        except Exception:
            pass

        # 外部文件变更 → 在正常事件层级询问用户是否重新加载
        #
        # 为什么不在这里之外的地方弹框：信号由 `QFileSystemWatcher` 回调
        # 发出，在回调里直接弹模态对话框会重入事件循环，并在窗口销毁阶段
        # 崩溃（实测段错误 0xC0000005）。见 `TabManager._handle_file_change`。
        try:
            self.tabs.file_changed_externally.connect(self._on_file_changed_externally)
        except Exception:
            pass

    def _on_file_changed_externally(self, filepath: str):
        """外部文件变更：询问用户是否重新加载"""
        if getattr(self, "_closing", False):
            return
        try:
            editor = None
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                proxy = getattr(w, "proxy", None)
                doc = getattr(proxy, "document", None) if proxy else None
                fp = getattr(doc, "filepath", None) if doc else None
                if fp and os.path.normcase(os.path.abspath(fp)) == os.path.normcase(
                    os.path.abspath(filepath)
                ):
                    editor = w
                    break
            if editor is None:
                return

            ret = QMessageBox.question(
                self,
                "文件已修改",
                f"文件已被外部程序修改：\n{os.path.basename(filepath)}\n\n是否重新加载？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if ret == QMessageBox.Yes:
                self.tabs._reload_file(filepath, editor)
        except Exception as e:
            logger.debug("处理外部文件变更失败: %s", e)

    def _create_fallback_tabs(self):
        """创建后备标签管理器（当 TabManager 加载失败时使用）"""
        from PyQt5.QtWidgets import QTabWidget

        tabs = QTabWidget()
        tabs.setTabsClosable(True)
        tabs.setMovable(True)
        tabs._editors = []

        def add_tab(title="未命名"):
            try:
                from ui.editor_view import EditorWidget

                editor = EditorWidget()
                idx = tabs.addTab(editor, title)
                tabs.setCurrentIndex(idx)
                tabs._editors.append(editor)
                return editor.proxy
            except Exception as e:
                import traceback

                traceback.print_exc()
                print(f"[fallback] add_tab 失败: {e}")
                return None

        def close_tab(index):
            w = tabs.widget(index)
            tabs.removeTab(index)
            if w in tabs._editors:
                tabs._editors.remove(w)

        def current_proxy():
            w = tabs.currentWidget()
            return w.proxy if w and hasattr(w, "proxy") else None

        def open_file(path):
            try:
                from core.content_provider import LocalFileProvider
                from ui.editor_view import EditorWidget

                provider = LocalFileProvider()
                provider.open(path)

                editor = EditorWidget(provider=provider)
                idx = tabs.addTab(editor, os.path.basename(path))
                tabs.setCurrentIndex(idx)
                tabs._editors.append(editor)

                editor.proxy.open_file(path)
                return editor.proxy
            except Exception as e:
                import traceback

                traceback.print_exc()
                print(f"[fallback] open_file 失败: {e}")
                return None

        def count():
            return tabs.count()

        def currentIndex():
            return tabs.currentIndex()

        tabs.tabCloseRequested.connect(close_tab)
        tabs.add_tab = add_tab
        tabs.open_file = open_file
        tabs.current_proxy = current_proxy
        tabs.count = count
        tabs.currentIndex = currentIndex

        return tabs

    def _apply_theme_by_name(self, name: str):
        # 函数内后文有局部 `from PyQt5.QtWidgets import QApplication`，
        # Python 会把 QApplication 当整个函数的局部变量；若在 import
        # 之前使用（如"跟随系统"分支）会抛 UnboundLocalError。
        from PyQt5.QtWidgets import QApplication

        """按名称应用主题"""
        try:
            from infrastructure.theme_loader import ThemeLoader

            loader = ThemeLoader()

            if name == "__system__":
                loader.apply_system_theme(QApplication.instance(), self.tabs.currentWidget())
                self.status_bar.showMessage("已切换到跟随系统", 2000)
                return

            theme = loader.load_by_name(name)
            if not theme:
                self._show_error("主题加载失败", f"未找到主题: {name}")
                return

            for i in range(self.tabs.count()):
                loader.apply(self.tabs.widget(i), theme)

            # A(主题): 用 loader.apply_qss 处理无 qss 主题
            # 原实现只在 `if theme.qss:` 时才 setStyleSheet，而
            # themes/*.json 里都没有 qss 字段，导致 QSS 从未应用。
            # apply_qss 会在 qss 为空时从 colors 生成 QSS。
            try:
                from PyQt5.QtWidgets import QApplication

                _app = QApplication.instance()
                if _app is not None:
                    _pm = getattr(self, "plugin_manager", None)
                    if _pm is not None:
                        try:
                            _pm.pause_deferred_activation()
                        except Exception:
                            _pm = None
                    try:
                        # C-2：实测窗口级 QSS 35-49ms，应用级全局
                        # setStyleSheet 90-424ms；改为窗口级应用 +
                        # palette 兜底（子对话框随父控件继承样式）。
                        try:
                            loader.apply_palette(_app, theme)
                            self.setPalette(_app.palette())
                        except Exception:
                            pass
                        self._current_theme_name = name
                        _qss = loader.build_qss(theme)
                        if _qss:
                            try:
                                from ui.accessibility import focus_ring_qss

                                _acc = focus_ring_qss()
                            except Exception:
                                _acc = ""
                            _qss = (_qss or "") + _acc
                            self._current_theme_qss = _qss
                            self.setStyleSheet(_qss)
                            self._apply_theme_to_top_levels(_qss)
                            self._ensure_toplevel_theme_filter()
                    finally:
                        if _pm is not None:
                            try:
                                _pm.resume_deferred_activation()
                            except Exception:
                                pass
                    # 有些 QSS 选择器（QMainWindow 等）需要重设
                    _app.setStyleSheet(_app.styleSheet())
            except Exception as _e:
                print(f"[Theme] apply_qss 失败: {_e}")
                if theme.qss:
                    self.setStyleSheet(theme.qss)

            # v3.0: 先统一适配硬编码 QSS，再通知面板刷新（v2.14.1 顺序修复）
            try:
                adapt_widget_styles(self, theme)
            except Exception:
                pass
            loader.notify_widgets(self, theme)

            # B: 遍历所有顶层窗口（含独立对话框）
            # notify_widgets 只处理 self.findChildren，独立打开的
            # 对话框（AI 配置、Git 提交、快捷键编辑器等）不在其中
            try:
                from PyQt5.QtWidgets import QApplication

                for w in QApplication.topLevelWidgets():
                    if w is self:
                        continue
                    fn = getattr(w, "refresh_theme", None)
                    if callable(fn):
                        try:
                            fn(theme)
                        except Exception:
                            pass
            except Exception:
                pass

            # 持久化
            from PyQt5.QtCore import QSettings

            settings = QSettings("QingCao", "Editor")
            settings.setValue("theme_name", name)

            self.status_bar.showMessage(f"主题已切换: {name}", 2000)
        except Exception as e:
            self._show_error("主题切换失败", str(e))

    def _show_theme_editor(self):
        """打开主题编辑器（含实时预览）"""
        try:
            from ui.theme_editor import ThemeEditor

            dlg = ThemeEditor(self)

            # 保存后立即应用 + 刷新主题菜单
            def on_saved(path):
                try:
                    from infrastructure.theme_loader import ThemeLoader

                    loader = ThemeLoader()
                    theme = loader.load(path)
                    if theme:
                        for i in range(self.tabs.count()):
                            loader.apply(self.tabs.widget(i), theme)
                        if theme.qss:
                            self.setStyleSheet(theme.qss)
                    # 重新构建菜单
                    self.theme_menu.clear()
                    self._build_full_theme_menu()
                except Exception as e:
                    print(f"[ThemeEditor] 保存后应用失败: {e}")

            dlg.theme_saved.connect(on_saved)
            dlg.exec_()
        except Exception as e:
            self._show_error("打开主题编辑器失败", str(e))

    def _show_theme_market(self):
        """打开主题市场"""
        try:
            from ui.theme_market import ThemeMarketDialog

            dlg = ThemeMarketDialog(self, self)

            def on_installed(name):
                # 刷新菜单
                self.theme_menu.clear()
                self._build_full_theme_menu()

            def on_deleted(name):
                self.theme_menu.clear()
                self._build_full_theme_menu()

            dlg.theme_installed.connect(on_installed)
            dlg.theme_deleted.connect(on_deleted)
            dlg.exec_()
        except Exception as e:
            self._show_error("打开主题市场失败", str(e))

    def _import_theme_pack(self):
        """导入主题包（zip）"""
        try:
            from PyQt5.QtWidgets import QFileDialog

            from core.theme_pack import ThemePack

            path, _ = QFileDialog.getOpenFileName(
                self, "导入主题包", "", "主题包 (*.zip);;所有文件 (*.*)"
            )
            if not path:
                return

            themes_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "themes"
            )
            ok, msg = ThemePack.import_theme(path, themes_dir)
            if ok:
                QMessageBox.information(self, "成功", msg)
                # 刷新菜单
                self.theme_menu.clear()
                self._build_full_theme_menu()
            else:
                QMessageBox.warning(self, "导入失败", msg)
        except Exception as e:
            self._show_error("导入失败", str(e))

    def _export_theme_pack(self):
        """导出当前主题为 zip 包"""
        try:
            from PyQt5.QtCore import QSettings
            from PyQt5.QtWidgets import QFileDialog

            from core.theme_pack import ThemePack

            settings = QSettings("QingCao", "Editor")
            theme_name = settings.value("theme_name", "", type=str)
            if not theme_name:
                self._show_info("提示", "当前没有选中主题")
                return

            themes_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "themes"
            )
            source = os.path.join(themes_dir, f"{theme_name}.json")
            if not os.path.exists(source):
                self._show_error("导出失败", f"主题文件不存在: {source}")
                return

            path, _ = QFileDialog.getSaveFileName(
                self, "导出主题包", f"{theme_name}.zip", "主题包 (*.zip)"
            )
            if not path:
                return

            ok, msg = ThemePack.export_theme(source, path)
            if ok:
                QMessageBox.information(self, "成功", msg)
            else:
                QMessageBox.warning(self, "导出失败", msg)
        except Exception as e:
            self._show_error("导出失败", str(e))

    def _open_theme_dir(self):
        """打开主题目录"""
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QDesktopServices

        themes_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "themes"
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(themes_dir))

    def _show_preferences(self):
        """打开首选项面板"""
        try:
            from ui.preferences_panel import PreferencesDialog

            dlg = PreferencesDialog(self, self)
            dlg.exec_()
        except Exception as e:
            self._show_error("打开首选项失败", str(e))

    def _canonical_action_name(self, text: str, shortcut: Optional[str]) -> Optional[str]:
        """给一个菜单项决定它在 `ActionManager` 里的名字

        两级策略：

        1. **映射表优先**：`ACTION_NAME_BY_TEXT` 里的名字是
           `core/keymap_profiles.py` 的方案 overrides 直接引用的
           （如 `file.save` / `edit.find`）—— 必须逐字一致，
           否则 `set_shortcut()` 会静默返回 False，方案失效。
        2. **兜底自动生成**：其余带快捷键的项用一个由文本+快捷键导出的
           稳定 slug（`misc.<hash>`）。这样快捷键编辑器能列出**真实全量**
           动作，而不是只有 15 个；同时 `defaults` 被填上，
           `reset_to_defaults()` 不会把它们的快捷键清空。

        没有快捷键又不在映射表里的项返回 None（不注册）——
        它们进快捷键编辑器没有意义。
        """
        if text in ACTION_NAME_BY_TEXT:
            return ACTION_NAME_BY_TEXT[text]
        if not shortcut:
            return None
        digest = hashlib.md5(("%s|%s" % (text, shortcut)).encode("utf-8")).hexdigest()[:10]
        return "misc.%s" % digest

    # ========================================================
    # 运行 / 转到定义 / LSP（P8-2 / P6）
    # ========================================================
    def _run_current_file(self):
        """运行当前文件（P8-2: F5）。

        优先交给已激活的调试类插件（如 python_debugger）；插件未激活
        时**明确提示**用户，而不是静默什么都不做。
        """
        try:
            proxy = self.tabs.current_proxy()
            if not proxy:
                self.status_bar.showMessage("没有打开的编辑器，无法运行", 4000)
                return

            filepath = ""
            try:
                filepath = (proxy.document.filepath or "") if proxy.document else ""
            except Exception:
                filepath = ""

            if not filepath:
                self.status_bar.showMessage("请先保存文件再运行", 4000)
                return

            # 1) 已激活的调试插件
            for plugin in self.plugins or []:
                runner = getattr(plugin, "run_current", None)
                if callable(runner):
                    try:
                        runner()
                        return
                    except Exception as e:
                        logger.error("插件运行当前文件失败: %s", e)
                        self.status_bar.showMessage(f"运行失败: {e}", 5000)
                        return

            # 2) 没有调试插件：给出可操作的提示（不静默失败）
            self.status_bar.showMessage(
                "未启用调试插件，无法运行当前文件；"
                "请启用「python_debugger」等调试插件（工具 → 插件管理）。"
                f"（{os.path.basename(filepath)}）",
                6000,
            )
            logger.warning("运行当前文件：没有可用的调试插件（filepath=%s）", filepath)
        except Exception as e:
            logger.error("运行当前文件失败: %s", e)
            try:
                self.status_bar.showMessage(f"运行失败: {e}", 5000)
            except Exception:
                pass
