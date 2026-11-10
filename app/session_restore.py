# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""会话恢复职责（v2.24 拆出）。"""
from app.session_common import *  # noqa: F401,F403,F405


class SessionRestoreMixin:
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

    def _pick_screen_for_geometry(self, x: int, y: int, w: int, h: int):
        """为保存的窗口几何挑选"最合适的屏幕"（多显示器感知）

        ★ 真实缺陷（多显示器/高 DPI 验证发现）：

            原实现只拿 `QApplication.primaryScreen()` 的可用区域来夹取
            `x/y`，带来三个问题：

            1. **窗口永远回主屏**：保存在第二块显示器（例如主屏右侧
               x=2200）的窗口，下次启动会被强行拉回主屏 ——
               多显示器用户每次启动都要重新拖窗口；
            2. **尺寸从不夹取**：在大屏（2560x1440）上保存的窗口
               换到小屏（1366x768）后仍是 2560x1440，
               **底部和右侧大半个窗口在屏幕外**，保存按钮/状态栏都看不到；
            3. **只夹左上角**：判断条件是 `x > right-100`，
               窗口宽 1000 放在 `right-950` 时仍会越界。

        现在的策略（顺序）：

            1. 用**窗口中点**调 `screenAt()` 找屏幕 —— 中点比左上角更能
               代表"用户把窗口放在了哪块屏"；
            2. 中点不在任何屏幕（显示器被拔掉）时，找**最近的屏幕**，
               但距离超过 2000px 视为完全无效，退回主屏；
            3. 把 `w/h` 夹到该屏幕可用区域，再把 `x/y` 夹到
               `[left, right-w]` / `[top, bottom-h]`，保证**完整可见**。
        """
        try:
            from PyQt5.QtCore import QPoint
            from PyQt5.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None:
                return None
            screens = list(app.screens())
            if not screens:
                return None
            if len(screens) == 1:
                return screens[0]

            # 1) 中点所在屏幕
            if hasattr(app, "screenAt"):
                middle = QPoint(x + max(1, w // 2), y + max(1, h // 2))
                scr = app.screenAt(middle)
                if scr is not None:
                    return scr
                # 左上角也算一次（窗口很宽/很高时中点可能在屏外）
                scr = app.screenAt(QPoint(x + 50, y + 50))
                if scr is not None:
                    return scr

            # 2) 最近的屏幕（距离过远则视为无效）
            best = None
            best_dist = None
            for scr in screens:
                geo = scr.availableGeometry()
                dx = max(geo.left() - x, 0, x - (geo.right() + 1))
                dy = max(geo.top() - y, 0, y - (geo.bottom() + 1))
                dist = dx * dx + dy * dy
                if best_dist is None or dist < best_dist:
                    best, best_dist = scr, dist
            if best is not None and best_dist is not None \
                    and best_dist <= 2000 * 2000:
                return best

            # 3) 退回主屏
            return app.primaryScreen() or screens[0]
        except Exception as e:
            print(f"[Session] 选择屏幕失败: {e}")
            return None

    def _restore_geometry(self, main_window: QMainWindow,
                          geometry: Dict[str, Any]):
        """恢复窗口几何（多显示器 + 尺寸夹取）

        修复记录见 `_pick_screen_for_geometry` 的 docstring。
        """
        try:
            x = int(geometry.get('x', -1))
            y = int(geometry.get('y', -1))
            w = max(200, int(geometry.get('w', 1100)))
            h = max(150, int(geometry.get('h', 750)))

            screen = self._pick_screen_for_geometry(x, y, w, h)
            if screen is not None:
                avail = screen.availableGeometry()
                # 尺寸先夹（大屏 → 小屏时窗口必须缩得下）
                w = min(w, avail.width())
                h = min(h, avail.height())
                # 再把左上角夹进可用区域，保证整个窗口可见
                x = min(max(x, avail.left()), avail.right() - w + 1)
                y = min(max(y, avail.top()), avail.bottom() - h + 1)

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

    def find_recoverable_drafts(self) -> list:
        """查找可恢复的草稿（崩溃/异常退出留下的未保存内容）

        缺陷背景（真实缺陷，已核实）：
            `core/document.py` 每 60 秒把未保存内容写进
            `backup/drafts/<hash>.draft`，但**全仓没有任何代码读取它**
            —— 只写、只删。于是崩溃后用户的未保存内容确实躺在磁盘上，
            却永远不会被捞回来，等价于没有备份。

        本方法提供读取端；由启动流程调用并询问用户是否恢复。

        返回:
            [{'path': 草稿路径, 'original': 原文路径, 'text': 正文,
              'mtime': 时间戳}, ...]，按时间倒序
        """
        try:
            # ⚠️ 修复（Lead 实测的真实缺陷）：`list_drafts()` 定义在
            #   **`Document`** 上，`DocumentModel` **没有**这个方法。
            #   原代码调 `DocumentModel.list_drafts()` 必然抛
            #   `AttributeError`，又被这里的 `except` 吞掉并 `return []`
            #   —— 于是**草稿恢复恒为空**：即便 `main.py` 已经接线调用本方法，
            #   用户的未保存内容仍然捞不回来（等于没接）。
            from core.document import Document
            drafts = Document.list_drafts()
        except Exception as e:
            print(f"[Session] 读取草稿失败: {e}")
            return []

        return [
            {'path': p, 'original': orig, 'text': text, 'mtime': mt}
            for (p, orig, text, mt) in drafts
        ]

    def check_and_recover_drafts(self, parent=None,
                                 drafts: Optional[list] = None) -> int:
        """提示用户恢复草稿，返回实际恢复的文件数

        参数:
            parent: 父窗口（用于弹对话框）
            drafts: 草稿列表（默认自动查找）
        """
        if drafts is None:
            drafts = self.find_recoverable_drafts()
        if not drafts:
            return 0

        # 询问用户
        if parent is not None:
            try:
                from PyQt5.QtWidgets import QMessageBox
                preview = "\n".join(
                    "  · %s" % (d['original'] or "(未命名)")
                    for d in drafts[:8]
                )
                more = "" if len(drafts) <= 8 else \
                    "\n  … 另有 %d 个" % (len(drafts) - 8)
                btn = QMessageBox.question(
                    parent,
                    "恢复未保存的内容",
                    "检测到上次退出时**未保存**的内容（共 %d 项）：\n\n%s%s\n\n"
                    "是否现在恢复？"
                    % (len(drafts), preview, more),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if btn != QMessageBox.Yes:
                    return 0
            except Exception as e:
                print(f"[Session] 草稿恢复询问失败: {e}")

        tabs = self._get_tabs()
        if tabs is None:
            return 0

        # 与 `_recover_files` 相同的加载方式：MemoryProvider + EditorWidget
        EditorWidget = None
        try:
            from ui.editor_view import EditorWidget as EW
            EditorWidget = EW
        except ImportError:
            pass

        from core.content_provider import MemoryProvider

        restored = 0
        for d in drafts:
            try:
                text = d['text']
                original = d['original']

                provider = MemoryProvider()
                provider.open(initial_text=text)

                if EditorWidget is None:
                    continue
                editor = EditorWidget(provider=provider)

                if original:
                    title = os.path.basename(original) + " [未保存]"
                else:
                    title = "未命名 [未保存]"

                if hasattr(tabs, 'addTab'):
                    idx = tabs.addTab(editor, title)
                    tabs.setCurrentIndex(idx)
                elif hasattr(tabs, 'add_tab'):
                    tabs.add_tab(title)

                # 标记为已修改：它会被再次纳入自动备份，不会二次丢失
                try:
                    proxy = getattr(editor, 'proxy', None)
                    if proxy is not None:
                        proxy.is_modified = True
                        if getattr(proxy, 'sc', None) is not None:
                            proxy.sc.setModified(True)
                except Exception:
                    pass

                restored += 1
            except Exception as e:
                print(f"[Session] 恢复草稿失败: {e}")

        if restored:
            print(f"[Session] 已恢复 {restored} 个未保存草稿")
            try:
                self.drafts_recovered.emit(restored)
            except Exception:
                pass
        return restored

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
