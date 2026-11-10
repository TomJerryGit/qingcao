# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""会话保存/备份职责（v2.24 拆出）。"""
from app.session_common import *  # noqa: F401,F403,F405


class SessionSaveMixin:
    def save(self, tab_widget, main_window: Optional[QMainWindow] = None) -> bool:
        """
        保存当前会话。

        参数:
            tab_widget: 标签管理器（TabManager）
            main_window: 主窗口（可选，若已 bind_window 则忽略）

        返回:
            是否保存成功
        """
        if not self.enabled:
            return False

        if main_window is None:
            main_window = self._main_window

        try:
            data = self._collect_session_data(tab_widget, main_window)
            data['version'] = SESSION_VERSION
            data['saved_at'] = datetime.datetime.now().isoformat()

            # 原子写入
            if self._write_atomic(self.filepath, data):
                self._session_data = data
                self._last_save_time = time.time()
                self.session_saved.emit(self.filepath)
                return True
            return False

        except Exception as e:
            self.session_error.emit(str(e))
            print(f"[Session] 保存失败: {e}")
            return False

    def _collect_session_data(self, tab_widget, main_window) -> Dict[str, Any]:
        """收集会话数据"""
        data: Dict[str, Any] = {
            'files': [],
            'geometry': {},
            'docks': {},
            'splitters': {},
            'active_tab': -1,
            'project': None,
        }

        # 收集打开的文件
        try:
            for i in range(tab_widget.count()):
                editor = tab_widget.widget(i)
                if not hasattr(editor, 'proxy'):
                    continue
                proxy = editor.proxy

                file_info: Dict[str, Any] = {
                    'filepath': None,
                    'cursor_pos': 0,
                    'first_line': 0,
                    'scroll_x': 0,
                    'encoding': 'utf-8',
                    'modified': False,
                    'bookmarks': [],
                    'folded_lines': [],
                    'title': tab_widget.tabText(i),
                }

                # 获取文件路径（兼容 proxy.document）
                try:
                    if proxy.document:
                        file_info['filepath'] = proxy.document.filepath
                        file_info['encoding'] = (
                            proxy.document.encoding or 'utf-8'
                        )
                except Exception:
                    pass

                # 获取 Scintilla 状态
                try:
                    sc = proxy.sc
                    file_info['cursor_pos'] = proxy.get_current_pos()
                    file_info['first_line'] = sc.SendScintilla(
                        sc.SCI_GETFIRSTVISIBLELINE
                    )
                    file_info['scroll_x'] = sc.horizontalScrollBar().value()
                    file_info['modified'] = proxy.is_modified
                    file_info['bookmarks'] = self._get_bookmarks(sc)
                    file_info['folded_lines'] = self._get_folded_lines(sc)
                except Exception:
                    pass

                data['files'].append(file_info)

            data['active_tab'] = tab_widget.currentIndex()

        except Exception as e:
            print(f"[Session] 收集文件信息失败: {e}")

        # 收集窗口几何
        if main_window and hasattr(main_window, 'geometry'):
            try:
                geo = main_window.geometry()
                data['geometry'] = {
                    'x': geo.x(),
                    'y': geo.y(),
                    'w': geo.width(),
                    'h': geo.height(),
                    'maximized': main_window.isMaximized(),
                    'fullscreen': main_window.isFullScreen(),
                }
            except Exception:
                pass

        # 收集面板状态
        #
        # 注意（真实缺陷）：面板是**延迟构造**的，若本次运行从未打开任何面板，
        # `findChildren(QDockWidget)` 会返回空集合，于是这里会把 `docks` 写成
        # **空字典**，在关闭时**覆盖掉用户已有的面板布局** —— 下次启动便
        # 无面板可恢复，界面看起来"功能没了"。
        #
        # 因此：只在**确实采集到面板**时才写入；否则保留原有记录不动。
        if main_window:
            try:
                docks = {}
                for dock in main_window.findChildren(QDockWidget):
                    name = dock.objectName() or dock.windowTitle()
                    if not name:
                        continue
                    docks[name] = {
                        'visible': dock.isVisible(),
                        'floating': dock.isFloating(),
                        'area': int(main_window.dockWidgetArea(dock)),
                    }
                if docks:
                    data['docks'] = docks
                else:
                    # 不覆盖：沿用上一份会话里的面板布局
                    prev = getattr(self, '_previous_docks', None)
                    if prev:
                        data['docks'] = prev
                    else:
                        data.pop('docks', None)
            except Exception:
                pass

        # 收集分屏状态
        if main_window and hasattr(main_window, 'splitter'):
            try:
                splitter = main_window.splitter
                if isinstance(splitter, QSplitter):
                    data['splitters']['main'] = splitter.sizes()
            except Exception:
                pass

        # 收集当前项目
        if main_window and hasattr(main_window, 'current_project'):
            try:
                project = main_window.current_project
                if project and hasattr(project, 'to_dict'):
                    data['project'] = project.to_dict()
            except Exception:
                pass

        return data

    # 折叠状态扫描上限：`SCI_GETFOLDEXPANDED` 只能逐行查询，
    # 50 万行文档会做 50 万次 SendScintilla（实测 ~0.5s）。
    # 超过上限时放弃折叠状态（退出后重新展开，不影响内容）。
    MAX_FOLD_SCAN_LINES = 50_000

    def _get_bookmarks(self, editor) -> List[int]:
        """获取编辑器中所有书签行号（从 0 开始）

        ★ 性能（cProfile 实测）：原实现逐行 `SCI_MARKERGET`，
        50 万行文档要 50 万次 SendScintilla（~0.5s）。
        改用 `SCI_MARKERNEXT` **直接跳到下一个带标记行**，
        成本只与书签数成正比（通常 0~几十个）。
        """
        bookmarks = []
        try:
            mask = 1 << 0
            line = editor.SendScintilla(editor.SCI_MARKERNEXT, 0, mask)
            guard = 0
            while line >= 0 and guard < 100_000:
                bookmarks.append(line)
                line = editor.SendScintilla(
                    editor.SCI_MARKERNEXT, line + 1, mask)
                guard += 1
        except Exception:
            pass
        return bookmarks

    def _get_folded_lines(self, editor) -> List[int]:
        """获取已折叠的行号列表

        大文档超过 `MAX_FOLD_SCAN_LINES` 时返回空列表：
        折叠状态可重建，不值得为它阻塞退出/自动保存。
        """
        folded = []
        try:
            line_count = editor.SendScintilla(editor.SCI_GETLINECOUNT)
            if line_count > self.MAX_FOLD_SCAN_LINES:
                return folded
            for line in range(line_count):
                expanded = editor.SendScintilla(
                    editor.SCI_GETFOLDEXPANDED, line
                )
                if expanded == 0:
                    folded.append(line)
        except Exception:
            pass
        return folded

    # ========================================================
    # 原子写入
    # ========================================================

    def _write_atomic(self, filepath: str, data: Dict[str, Any]) -> bool:
        """
        原子写入 JSON 文件。
        写入临时文件后重命名，避免中途失败导致文件损坏。
        """
        try:
            dirpath = os.path.dirname(os.path.abspath(filepath))
            os.makedirs(dirpath, exist_ok=True)

            # 先备份旧文件
            if os.path.exists(filepath):
                self._backup_existing(filepath)

            # 写入临时文件
            fd, tmp_path = tempfile.mkstemp(
                dir=dirpath, prefix='.session_', suffix='.tmp'
            )
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())

                # 原子重命名
                if sys.platform == 'win32' and os.path.exists(filepath):
                    os.replace(tmp_path, filepath)
                else:
                    os.rename(tmp_path, filepath)
                return True
            except Exception:
                # 清理临时文件
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                raise

        except Exception as e:
            print(f"[Session] 原子写入失败: {e}")
            return False

    def _backup_existing(self, filepath: str):
        """备份已存在的会话文件"""
        try:
            os.makedirs(SESSION_BACKUP_DIR, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"session_{timestamp}.json"
            backup_path = os.path.join(SESSION_BACKUP_DIR, backup_name)
            shutil.copy(filepath, backup_path)

            # 清理过多的备份
            self._cleanup_backups()
        except Exception as e:
            print(f"[Session] 备份失败: {e}")

    def _cleanup_backups(self):
        """清理超出数量限制的备份"""
        try:
            if not os.path.exists(SESSION_BACKUP_DIR):
                return
            backups = []
            for name in os.listdir(SESSION_BACKUP_DIR):
                if name.startswith("session_") and name.endswith(".json"):
                    path = os.path.join(SESSION_BACKUP_DIR, name)
                    backups.append((path, os.path.getmtime(path)))
            backups.sort(key=lambda x: x[1], reverse=True)
            for path, _ in backups[MAX_SESSION_BACKUPS:]:
                try:
                    os.remove(path)
                except Exception:
                    pass
        except Exception:
            pass

    # ========================================================
    # 加载会话
    # ========================================================

    def save_autosave(self, tab_widget,
                       main_window: Optional[QMainWindow] = None,
                       auto_save_dir: Optional[str] = None) -> int:
        """
        保存自动备份（未保存的文件）。

        参数:
            tab_widget: 标签管理器
            main_window: 主窗口（可选）
            auto_save_dir: 备份目录（默认 backup/autosave）

        返回:
            成功备份的文件数
        """
        if auto_save_dir is None:
            auto_save_dir = self.autosave_dir

        try:
            os.makedirs(auto_save_dir, exist_ok=True)

            files = []
            for i in range(tab_widget.count()):
                widget = tab_widget.widget(i)
                if not hasattr(widget, 'proxy'):
                    continue
                proxy = widget.proxy
                if not proxy:
                    continue

                # 只备份已修改的文件
                is_modified = getattr(proxy, 'is_modified', False)
                if not is_modified:
                    continue

                # 获取内容
                try:
                    content = proxy.sc.text() if proxy.sc else ""
                except Exception:
                    continue

                if not content:
                    continue

                # 原文件路径
                original = ""
                try:
                    if proxy.document:
                        original = proxy.document.filepath or ""
                except Exception:
                    pass

                # 生成安全的备份文件名
                if original:
                    base = os.path.basename(original)
                    name = self._sanitize_filename(base) + ".tmp"
                else:
                    name = "untitled_%d.tmp" % i

                backup_path = os.path.join(auto_save_dir, name)

                # 写入文件（末尾记录原始路径）
                try:
                    with open(backup_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                        if original:
                            f.write(
                                f"\n\n###QINGCAO_ORIGINAL_PATH:{original}###"
                            )
                except Exception as e:
                    print(f"[Session] 备份 {name} 失败: {e}")
                    continue

                files.append({
                    'backup': name,
                    'original': original,
                    'title': tab_widget.tabText(i),
                })

            # 写元数据
            #
            # 只有**确实备份到了内容**时才写 meta.json。
            #
            # 原因（真实缺陷）：崩溃恢复的判定是"meta.json 是否存在"
            # （main.py 的 deferred_init / check_and_recover_crash）。
            # 若没有修改中的文件也照写 meta（count=0），
            # 那么每次正常退出都会留下一个"看起来有可恢复内容"的 meta，
            # 下次启动就可能弹出一个**空的崩溃恢复**，误导用户。
            if files:
                meta = {
                    'timestamp': datetime.datetime.now().isoformat(),
                    'count': len(files),
                    'files': files,
                }
                meta_path = os.path.join(auto_save_dir, AUTOSAVE_META)
                # 原子写：先写临时文件再替换，避免写一半留下坏 meta
                tmp_path = meta_path + '.tmp'
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(meta, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, meta_path)

                print(f"[Session] 自动备份: {len(files)} 个文件")
                self.autosave_saved.emit(len(files))
            else:
                # 没有需要备份的内容：清掉可能残留的旧 meta，
                # 避免"空的崩溃恢复"
                try:
                    meta_path = os.path.join(auto_save_dir, AUTOSAVE_META)
                    if os.path.exists(meta_path):
                        os.remove(meta_path)
                except Exception:
                    pass

            return len(files)

        except Exception as e:
            print(f"[Session] 自动备份失败: {e}")
            return 0

    def clear_autosave(self, auto_save_dir: Optional[str] = None):
        """
        清理自动备份目录（正常退出时调用）。

        参数:
            auto_save_dir: 备份目录（默认 backup/autosave）
        """
        if auto_save_dir is None:
            auto_save_dir = self.autosave_dir

        try:
            if os.path.exists(auto_save_dir):
                shutil.rmtree(auto_save_dir, ignore_errors=True)
                print(f"[Session] 已清理自动备份: {auto_save_dir}")
        except Exception as e:
            print(f"[Session] 清理自动备份失败: {e}")

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """清理文件名中的非法字符"""
        invalid_chars = '<>:"/\\|?*'
        for c in invalid_chars:
            name = name.replace(c, '_')
        return name.strip() or "untitled"

    # ========================================================
    # 崩溃恢复（新增）
    # ========================================================

    def save_backup(self, tab_widget, main_window: Optional[QMainWindow] = None,
                    backup_dir: Optional[str] = None) -> bool:
        """
        保存崩溃恢复备份（旧版 API）。

        参数:
            tab_widget: 标签管理器
            main_window: 主窗口
            backup_dir: 备份目录（默认 backup/autosave_TIMESTAMP）

        返回:
            是否成功
        """
        try:
            if backup_dir is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_dir = os.path.join(
                os.path.dirname(AUTOSAVE_DIR),
                f"autosave_{timestamp}"
            )

            os.makedirs(backup_dir, exist_ok=True)

            # 保存每个未保存的文件内容
            saved_count = 0
            for i in range(tab_widget.count()):
                editor = tab_widget.widget(i)
                if not hasattr(editor, 'proxy'):
                    continue
                proxy = editor.proxy
                if not proxy.is_modified:
                    continue

                filepath = None
                try:
                    if proxy.document:
                        filepath = proxy.document.filepath
                except Exception:
                    pass

                if not filepath:
                    backup_file = os.path.join(
                        backup_dir, f"untitled_{i}.tmp"
                    )
                else:
                    safe_name = os.path.basename(filepath)
                    backup_file = os.path.join(
                        backup_dir, f"{safe_name}.tmp"
                    )

                try:
                    content = proxy.sc.text() if proxy.sc else ""
                    with open(backup_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                        f.write(
                            f"\n\n###QINGCAO_ORIGINAL_PATH:{filepath}###"
                        )
                    saved_count += 1
                except Exception as e:
                    print(f"[Session] 备份文件 {i} 失败: {e}")

            # 保存元数据
            meta = {
                'timestamp': datetime.datetime.now().isoformat(),
                'file_count': saved_count,
                'files': [
                    {
                        'original': None,
                        'backup': os.path.basename(bf)
                    }
                    for bf in os.listdir(backup_dir)
                    if bf.endswith('.tmp')
                ]
            }
            meta_path = os.path.join(backup_dir, "meta.json")
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2)

            print(f"[Session] 崩溃备份: {saved_count} 个文件 -> {backup_dir}")
            return True

        except Exception as e:
            print(f"[Session] 崩溃备份失败: {e}")
            return False

    @staticmethod
    def cleanup_backup(backup_dir: str):
        """清理指定备份目录"""
        try:
            if os.path.exists(backup_dir):
                shutil.rmtree(backup_dir, ignore_errors=True)
        except Exception:
            pass

    @staticmethod
    def cleanup_old_backups(backup_root: str = "backup",
                            keep_days: int = 7):
        """
        清理超过保留天数的备份。

        参数:
            backup_root: 备份根目录
            keep_days: 保留天数
        """
        try:
            if not os.path.exists(backup_root):
                return
            now = time.time()
            cutoff = now - keep_days * 86400
            for name in os.listdir(backup_root):
                path = os.path.join(backup_root, name)
                if os.path.isdir(path) and name.startswith("autosave_"):
                    if os.path.getmtime(path) < cutoff:
                        shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass

    # ========================================================
    # 删除会话
    # ========================================================
