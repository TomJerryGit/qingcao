# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""MainWindow actions 职责（v2.23 D2 拆分）。"""

from ui.main_window_common import *  # noqa: F401,F403
from ui.main_window_common import _TopLevelThemeFilter  # noqa: F401


class WindowActionsMixin:
    def _build_emoji_icon(self, text: str):
        """用 emoji 生成工具栏图标（无需图片资源）"""
        from PyQt5.QtCore import Qt as _Qt
        from PyQt5.QtGui import QFont, QPainter, QPixmap

        emoji = "🔹"
        for key, e in self._TOOLBAR_ICONS:
            if key in (text or ""):
                emoji = e
                break
        pm = QPixmap(22, 22)
        pm.fill(_Qt.transparent)
        painter = QPainter(pm)
        try:
            font = QFont()
            font.setPointSize(13)
            painter.setFont(font)
            painter.drawText(pm.rect(), _Qt.AlignCenter, emoji)
        finally:
            painter.end()
        return QIcon(pm)

    def _set_welcome_page_enabled(self, enabled: bool):
        """视图 → 显示欢迎页（持久化偏好；NPP 默认无欢迎页）"""
        enabled = bool(enabled)
        self._welcome_visible_pref = enabled
        try:
            self.prefs.set("show_welcome_page", enabled)
        except Exception:
            pass
        try:
            if not enabled:
                self.central_stack.setCurrentIndex(0)
            elif self.tabs.count() == 0 and getattr(self, "welcome", None) is not None:
                self.central_stack.setCurrentIndex(1)
        except Exception:
            pass

    def _apply_language_by_extension(self):
        """语言 → 自动：按当前文件扩展名重新应用词法器"""
        try:
            proxy = self.tabs.current_proxy()
            sc = getattr(proxy, "sc", None) if proxy else None
            if sc is None:
                self.status_bar.showMessage("没有打开的编辑器", 2500)
                return
            path = ""
            try:
                path = getattr(proxy.document, "filepath", "") or ""
            except Exception:
                pass
            sc._last_lexer_filepath = None
            self._active_language_pack_name = None
            sc.set_lexer_by_filename(path)
            self.status_bar.showMessage("语言：已按扩展名自动识别", 2000)
        except Exception as e:
            self.status_bar.showMessage("切换语言失败: %s" % e, 3000)

    def _apply_language_pack(self, pack):
        """语言 → 声明式语言包：对当前编辑器应用通用词法器"""
        try:
            proxy = self.tabs.current_proxy()
            sc = getattr(proxy, "sc", None) if proxy else None
            if sc is None:
                self.status_bar.showMessage("没有打开的编辑器", 2500)
                return
            from ui.generic_lexer import create_generic_lexer

            self._active_language_pack_name = pack.name
            sc.set_lexer(create_generic_lexer(pack, sc))
            self.status_bar.showMessage("语言：已应用 %s" % (pack.name or "语言包"), 2000)
        except Exception as e:
            self.status_bar.showMessage("应用语言包失败: %s" % e, 3000)

    def _show_search(self):
        """显示搜索栏"""
        try:
            # P1-3: 惰性构造
            self._ensure_panel("search_bar")
            if self.search_bar:
                self.search_bar.show()
                if hasattr(self.search_bar, "show_and_focus"):
                    self.search_bar.show_and_focus()
        except Exception as e:
            print(f"[MainWindow] 显示搜索栏失败: {e}")

    def _show_global_search(self):
        """显示全局搜索"""
        try:
            # P1-3: 惰性构造
            self._ensure_panel("gsearch")
            if self.gsearch:
                self.gsearch.show()
                if hasattr(self.gsearch, "focus_search"):
                    self.gsearch.focus_search()
        except Exception as e:
            print(f"[MainWindow] 显示全局搜索失败: {e}")

    def _goto_line_dialog(self):
        """跳转到行（对话框形式，P3-2 由 _show_line_palette 改名）"""
        try:
            proxy = self.tabs.current_proxy()
            if not proxy or not proxy.sc:
                return

            total = proxy.sc.SendScintilla(proxy.sc.SCI_GETLINECOUNT)
            if total <= 0:
                total = 1
            line, ok = QInputDialog.getInt(self, "跳转到行", "行号:", 1, 1, total)
            if ok:
                proxy.sc.setCursorPosition(line - 1, 0)
                proxy.sc.ensureLineVisible(line - 1)
        except Exception as e:
            print(f"[MainWindow] 跳转失败: {e}")

    # 向后兼容别名（P3-2）
    def _show_line_palette(self):
        """[已弃用] 请使用 _goto_line_dialog"""
        return self._goto_line_dialog()

    # ========================================================
    # 视图操作
    # ========================================================
    def _toggle_column_mode(self, checked=None):
        """切换列模式。

        修复 P0-C4:
            菜单里的"▦ 列模式"用 _add_action 创建的非 checkable
            QAction，triggered 信号固定传 checked=False。
            原代码 `if isinstance(checked, bool): enabled = checked`
            会因此认为"用户想关闭列模式"，从菜单点击无效。

            改为：始终基于工具栏 action 的**真实状态**翻转，
            忽略 triggered 传入的 checked 参数。
        """
        try:
            if hasattr(self, "column_mode_action"):
                # 修复 P0-C4: 忽略 triggered 的 checked 参数，
                # 始终基于工具栏 action 的当前状态翻转
                enabled = not self.column_mode_action.isChecked()
                self.column_mode_action.blockSignals(True)
                self.column_mode_action.setChecked(enabled)
                self.column_mode_action.blockSignals(False)
            else:
                # 无工具栏按钮时，退回到 checked 参数
                enabled = not (checked if isinstance(checked, bool) else False)

            proxy = self.tabs.current_proxy()
            if proxy and hasattr(proxy, "set_column_mode"):
                proxy.set_column_mode(enabled)

            self.status_bar.showMessage("列模式" if enabled else "流模式", 2000)
        except Exception as e:
            print(f"[MainWindow] 切换列模式失败: {e}")

    def toggle_fullscreen(self):
        """切换全屏"""
        if self._fullscreen_mode:
            self.showNormal()
            self._fullscreen_mode = False
        else:
            self.showFullScreen()
            self._fullscreen_mode = True

    def _zoom_in(self):
        """放大字体"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.sc:
                proxy.sc.zoomIn()
        except Exception:
            pass

    def _zoom_out(self):
        """缩小字体"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.sc:
                proxy.sc.zoomOut()
        except Exception:
            pass

    def _zoom_reset(self):
        """重置字体"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.sc:
                font = QFont("Consolas", 12)
                proxy.sc.setFont(font)
        except Exception:
            pass

    # ========================================================
    # 大文件高亮开关（性能 vs 视觉的显式取舍）
    # ========================================================
    def _toggle_force_highlight_large_files(self, checked: bool):
        """切换"大文件强制高亮"

        默认关闭：大文档（>20 万行或 >8MB）跳过语法高亮与缩略图，
        把 2MB/50 万行的打开时间从 2.1s 降到 ~0.5s。
        开启后对当前标签立即重新应用词法器（用户自己承担耗时）。
        """
        self._force_highlight_large_files = bool(checked)
        try:
            proxy = self.tabs.current_proxy()
        except Exception:
            proxy = None
        sc = getattr(proxy, "sc", None) if proxy is not None else None
        if sc is None:
            return
        try:
            # 清掉去重标记，强制重新判定
            sc._last_lexer_filepath = None
            path = ""
            try:
                path = getattr(proxy.document, "filepath", "") or ""
            except Exception:
                pass
            sc.set_lexer_by_filename(path)
            if self.minimap is not None:
                self.minimap.set_editor(sc)
            self.statusBar().showMessage(
                "大文件强制高亮：%s" % ("已开启" if checked else "已关闭"), 3000
            )
        except Exception as e:
            print(f"[MainWindow] 切换大文件高亮失败: {e}")

    # ========================================================
    # 面板切换
    # ========================================================
    def _toggle_outline(self, checked):
        """切换大纲面板（基础版）"""
        if self._ensure_panel("outline") and self.outline:
            self.outline.setVisible(checked)

    def _toggle_outline_enhanced(self, checked):
        """切换增强版大纲面板"""
        if self._ensure_panel("outline_enhanced") and self.outline_enhanced:
            self.outline_enhanced.setVisible(checked)

    def _toggle_directory(self, checked):
        """切换目录树面板"""
        if self._ensure_panel("dir_tree") and self.dir_tree_dock:
            self.dir_tree_dock.setVisible(checked)

    def _toggle_minimap(self, checked):
        """切换 Minimap"""
        if self._ensure_panel("minimap") and self.minimap_dock:
            self.minimap_dock.setVisible(checked)

    def _toggle_global_search(self, checked):
        """切换全局搜索"""
        if self._ensure_panel("gsearch") and self.gsearch:
            self.gsearch.setVisible(checked)

    def _toggle_console(self):
        """切换控制台"""
        try:
            if self._ensure_panel("console") and self.console:
                self.console.setVisible(not self.console.isVisible())
        except Exception as e:
            print(f"[MainWindow] 控制台切换失败: {e}")

    def _toggle_perf_monitor(self, checked):
        """切换性能监控"""
        if self._ensure_panel("perf_monitor") and self.perf_monitor:
            self.perf_monitor.setVisible(checked)

    # ========================================================
    # 工具
    # ========================================================
    def _show_command_palette(self):
        """显示命令面板"""
        try:
            from ui.command_palette import create_command_palette

            palette = create_command_palette(
                self.act_mgr, self, tab_mgr=self.tabs, outline=self.outline
            )
            if hasattr(palette, "center_on_parent"):
                palette.center_on_parent()
            palette.exec_()
        except Exception as e:
            import traceback

            traceback.print_exc()
            print(f"[MainWindow] 命令面板失败: {e}")

    def _show_file_palette(self):
        """显示文件切换面板"""
        try:
            from ui.command_palette import create_file_palette

            palette = create_file_palette(self.act_mgr, self.tabs, self)
            if hasattr(palette, "center_on_parent"):
                palette.center_on_parent()
            palette.exec_()
        except Exception as e:
            print(f"[MainWindow] 文件面板失败: {e}")

    def _show_symbol_palette(self):
        """显示符号跳转面板"""
        try:
            from ui.command_palette import create_symbol_palette

            palette = create_symbol_palette(self.act_mgr, self.tabs, self.outline, self)
            if hasattr(palette, "center_on_parent"):
                palette.center_on_parent()
            palette.exec_()
        except Exception as e:
            print(f"[MainWindow] 符号面板失败: {e}")

    def _current_undo_manager(self):
        """当前标签 proxy 的 UndoManager（P0-1 的绑定来源）

        为什么是"回调"而不是保存一个引用:
            每个标签页都有自己的 `EditorProxy` 与 `UndoManager`
            （`core/editor.py` 的 `EditorProxy.__init__`），用户随时可能
            切换标签。若在构造 `MacroRecorder` 时固定绑定一个 manager，
            录制中切换标签就会记到错误的对象上（或什么都记不到）。
            `MacroRecorder` 在 start()/stop() 时会调用本方法重新解析。
        """
        try:
            proxy = self.tabs.current_proxy()
        except Exception:
            return None
        if proxy is None:
            return None
        return getattr(proxy, "undo_manager", None)

    def _on_macro_error(self, message: str):
        """宏录制/回放错误 → 状态栏（P0-1）

        缺陷背景：`MacroRecorder.error_occurred` 原先**没有任何接收者**，
        录不到命令时只有 `print()`（GUI 打包后不可见）—— 用户看到的是
        "录制中"却录不到东西的静默失败。
        """
        try:
            self.status_bar.showMessage(f"宏: {message}", 5000)
        except Exception:
            pass

    def _toggle_macro(self):
        """切换宏录制"""
        if not self.macro:
            self.status_bar.showMessage("宏功能不可用", 2000)
            return
        try:
            # 兼容不同版本：使用 recording 属性或 is_recording 方法
            is_recording = False
            if hasattr(self.macro, "recording"):
                is_recording = bool(self.macro.recording)
            elif hasattr(self.macro, "is_recording"):
                is_recording = bool(self.macro.is_recording())

            if is_recording:
                macro = self.macro.stop()
                self.rec_label.hide()
                # P0-1: 明确回报录到几条 —— "录制中"却不显示数量时，
                # 用户无法察觉"录到 0 条"这种静默失败。
                count = 0
                try:
                    count = len(getattr(macro, "commands", []) or [])
                except Exception:
                    count = 0
                self.status_bar.showMessage(f"宏录制已停止（{count} 条命令）", 3000)
            else:
                # P0-1: 开始录制前先绑定当前标签的 undo_manager
                # （标签可能自上次录制后已切换；start() 内部也会再解析一次）
                if hasattr(self.macro, "bind_current_undo_manager"):
                    self.macro.bind_current_undo_manager()
                self.macro.start()
                self.rec_label.setText("● REC")
                self.rec_label.show()
                # 没绑上 = 必然录到 0 条：立刻可见地告诉用户，
                # 而不是等他录完、回放时才提示"没有可回放的宏"。
                if hasattr(self.macro, "has_hook") and not self.macro.has_hook:
                    self.status_bar.showMessage(
                        "宏录制已开始，但当前没有可录制的编辑器（请先打开或新建标签）", 5000
                    )
                else:
                    self.status_bar.showMessage("宏录制已开始", 2000)
        except Exception as e:
            print(f"[MainWindow] 宏录制失败: {e}")

    def _play_macro(self):
        """回放宏"""
        if not self.macro:
            self.status_bar.showMessage("宏功能不可用", 2000)
            return
        try:
            proxy = self.tabs.current_proxy()
            if not proxy:
                return

            has_commands = False
            if hasattr(self.macro, "has_commands"):
                has_commands = self.macro.has_commands()
            elif hasattr(self.macro, "commands"):
                has_commands = bool(self.macro.commands)

            if not has_commands:
                self.status_bar.showMessage("没有可回放的宏", 2000)
                return

            self.macro.replay(proxy, repeat=1)
            self.status_bar.showMessage("宏回放完成", 2000)
        except Exception as e:
            self._show_error("宏回放失败", str(e))

    def _show_keymap_editor(self):
        """显示快捷键编辑器"""
        try:
            from ui.keymap_editor import KeymapEditor

            dlg = KeymapEditor(self.act_mgr, self)
            dlg.exec_()
        except Exception as e:
            self._show_error("快捷键编辑器失败", str(e))

    def _show_perf_monitor(self):
        """显示性能监控面板"""
        try:
            # P1-3: 惰性构造
            self._ensure_panel("perf_monitor")
            if self.perf_monitor:
                self.perf_monitor.show()
                self.perf_monitor.raise_()
        except Exception as e:
            self._show_error("性能监控失败", str(e))

    # VimMode 实例（增强：信号连接 + setFocus）
    def _toggle_vim_mode(self, checked: bool):
        """切换 Vim 模式

        为当前编辑器附加/移除 VimMode 实例。
        """
        try:
            from core.vim_mode import VimMode

            proxy = self.tabs.current_proxy()
            if not proxy or not proxy.sc:
                self.status_bar.showMessage("没有活动的编辑器", 2000)
                self.vim_mode_action.setChecked(False)
                return

            editor = proxy.sc

            if checked:
                vim = getattr(editor, "_vim_mode", None)
                if vim is None:
                    vim = VimMode(editor)
                    editor._vim_mode = vim

                # 首次创建时连接信号（状态栏显示模式）
                if not getattr(vim, "_signal_connected", False):
                    try:
                        vim.status_message.connect(
                            lambda msg: self.status_bar.showMessage(msg, 2000) if msg else None
                        )
                        vim.state_changed.connect(
                            lambda st: self.status_bar.showMessage(f"Vim: {st}", 1500)
                        )
                        vim._signal_connected = True
                    except Exception:
                        pass

                vim.set_enabled(True)

                # 焦点给编辑器，否则按键进不来
                try:
                    editor.setFocus()
                except Exception:
                    pass

                # A: 缩短启用提示，避免覆盖 VimMode 的状态显示
                # 原来显示 4000ms，会盖住 VimMode 的 "-- 普通 --"
                self.status_bar.showMessage("Vim 模式已启用", 1500)
                print("[MainWindow] Vim 模式已启用")
            else:
                vim = getattr(editor, "_vim_mode", None)
                if vim is not None:
                    vim.set_enabled(False)
                self.status_bar.showMessage("Vim 模式已禁用", 2000)
                print("[MainWindow] Vim 模式已禁用")
        except Exception as e:
            print(f"[MainWindow] Vim 切换失败: {e}")
            import traceback

            traceback.print_exc()
            self.status_bar.showMessage(f"Vim 切换失败: {e}", 3000)

    def _export_config(self):
        """导出配置"""
        try:
            from app.config_manager import ConfigManager

            cm = ConfigManager()
            cm.export_config(self)
        except Exception as e:
            self._show_error("导出失败", str(e))

    def _import_config(self):
        """导入配置"""
        try:
            from app.config_manager import ConfigManager

            cm = ConfigManager()
            cm.import_config(self)
        except Exception as e:
            self._show_error("导入失败", str(e))

    # ========================================================
    # 帮助
    # ========================================================
    def _show_shortcuts(self):
        """显示快捷键参考"""
        shortcuts = [
            ("Ctrl+N", "新建文件"),
            ("Ctrl+O", "打开文件"),
            ("Ctrl+S", "保存文件"),
            ("Ctrl+Shift+S", "另存为"),
            ("Ctrl+W", "关闭标签"),
            ("Ctrl+Z / Ctrl+Y", "撤销 / 重做"),
            ("Ctrl+X/C/V", "剪切 / 复制 / 粘贴"),
            ("Ctrl+F", "查找"),
            ("Ctrl+Shift+F", "全局搜索"),
            ("Ctrl+Shift+P", "命令面板"),
            ("Ctrl+P", "文件切换"),
            ("Ctrl+Alt+R", "符号跳转"),
            ("Ctrl+G", "跳转到行"),
            ("Ctrl+/", "注释切换"),
            ("Ctrl+D", "选择下一项"),
            ("Alt+C", "列模式"),
            ("Ctrl+`", "Python 控制台"),
            ("Ctrl+Space", "自动补全"),
            ("F5", "插入日期时间"),
            ("F11", "无干扰模式"),
            ("Shift+F11", "全屏"),
        ]

        text = "青草编辑器快捷键参考\n" + "=" * 40 + "\n\n"
        for key, desc in shortcuts:
            text += f"{key:25s} {desc}\n"

        dlg = QDialog(self)
        dlg.setWindowTitle("快捷键参考")
        dlg.resize(500, 600)
        layout = QVBoxLayout(dlg)

        browser = QTextBrowser()
        browser.setPlainText(text)
        layout.addWidget(browser)

        btn = QPushButton("关闭")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)

        dlg.exec_()

    def _show_daily_tip(self, manual: bool = False):
        """
        显示每日技巧。

        P2-8: 一天只显示一次（基于 QSettings 记录日期）。
        P2-C4: manual=True 时（菜单手动点击）跳过日期限制，
               否则用户当天已自动弹过，手动点击就没反应了。
        """
        try:
            import datetime

            settings = QSettings(ORG_NAME, "Editor")
            today = datetime.date.today().isoformat()

            last_date = settings.value("last_tip_date", "", type=str)
            # P2-C4: manual 参数
            if not manual and last_date == today:
                return  # 今天已弹过，且是自动触发

            # 标记今天已弹
            # P2-2: 仅自动触发时更新 last_tip_date
            # 原实现手动点击也更新，导致用户当天手动点一次后，
            # 第二天的自动弹出会被抑制到后天。
            if not manual:
                settings.setValue("last_tip_date", today)
                settings.sync()
        except Exception as e:
            # 若 QSettings 异常，则退回为"每次都弹"
            print(f"[MainWindow] 每日技巧日期检查失败: {e}")

        # 显示技巧
        try:
            from ui.tips import get_tip

            tip = get_tip()
        except Exception:
            tips = [
                "按 Ctrl+Shift+P 打开命令面板，搜索所有功能。",
                "按 Alt+C 进入列模式，可同时编辑多行。",
                "Ctrl+D 选中当前单词，再按一次选中下一个相同单词。",
                "拖拽标签到窗口外可分离为独立窗口。",
                "按 Ctrl+Shift+R 录制宏，Ctrl+Shift+M 回放。",
                "选中文本后输入括号可自动包裹。",
                "按 F5 插入当前日期时间。",
                "按 Ctrl+/ 注释或取消注释当前行。",
            ]
            import random

            tip = random.choice(tips)

        QMessageBox.information(self, "💡 每日技巧", tip)

    def _show_online_docs(self):
        """打开在线文档"""
        try:
            QDesktopServices.openUrl(QUrl("https://qingcao-editor.github.io/docs"))
        except Exception:
            pass

    def _show_github(self):
        """打开 GitHub"""
        try:
            QDesktopServices.openUrl(QUrl("https://github.com/qingcao-editor/qingcao"))
        except Exception:
            pass

    def _about(self):
        """关于对话框"""
        QMessageBox.about(
            self,
            "关于青草编辑器",
            f"<h2>{APP_NAME} v{APP_VERSION}</h2>"
            "<p>轻量 · 极速 · 可扩展</p>"
            "<p>开发者：TomJerry</p>"
            "<p>联系：1265338136@qq.com</p>"
            "<p><i>青草枯荣，野火重生。</i></p>",
        )
