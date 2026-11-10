# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405,F811
"""会话管理（v2.24 拆分：保存/恢复/自动保存 worker）。"""
from app.session_common import *  # noqa: F401,F403,F405
from app.session_restore import SessionRestoreMixin
from app.session_save import SessionSaveMixin


class SessionManager(SessionSaveMixin, SessionRestoreMixin, QObject):
    """
    会话管理器。

    职责:
    - 保存/恢复打开的文件、光标位置、滚动位置
    - 保存/恢复标签顺序与活动标签
    - 保存/恢复书签、折叠状态
    - 保存/恢复窗口几何、面板布局
    - 保存/恢复分屏状态
    - 自动保存防止崩溃丢失
    - 会话文件损坏自修复
    - 会话版本兼容与迁移
    - 自动备份未保存文件
    - 崩溃恢复

    信号:
        session_saved(str): 会话保存成功（文件路径）
        session_loaded(str, dict): 会话加载成功（文件路径，数据）
        session_error(str): 会话操作失败（错误信息）
        session_restored(int): 会话恢复完成（恢复的文件数量）
        autosave_saved(int): 自动备份完成（备份的文件数）
        crash_recovered(int): 崩溃恢复完成（恢复的文件数）
    """

    # 信号
    session_saved = pyqtSignal(str)
    session_loaded = pyqtSignal(str, dict)
    session_error = pyqtSignal(str)
    session_restored = pyqtSignal(int)
    autosave_saved = pyqtSignal(int)
    crash_recovered = pyqtSignal(int)
    # 草稿恢复完成（恢复的未保存文件数量）
    drafts_recovered = pyqtSignal(int)

    # --------------------------------------------------------

    def __init__(self, parent: Optional[QObject] = None,
                 filepath: str = SESSION_FILE,
                 enabled: bool = True):
        """
        参数:
            parent: 父 QObject
            filepath: 会话文件路径（默认 session.json）
            enabled: 是否启用会话保存（可由偏好设置控制）
        """
        super().__init__(parent)

        self.filepath = filepath
        self.enabled = enabled

        # 会话数据缓存
        self._session_data: Dict[str, Any] = {}

        # 上一次加载到的面板布局。
        # 用途：面板是延迟构造的，若本次运行从未打开面板，保存时会采集到
        # 空集合；此时沿用这份记录，避免把用户布局覆盖成空。
        self._previous_docks: Dict[str, Any] = {}

        # 自动保存定时器
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(AUTOSAVE_INTERVAL_MS)
        self._autosave_timer.timeout.connect(self._autosave_tick)

        # 引用主窗口（用于恢复时操作）
        self._main_window: Optional[QMainWindow] = None

        # 上次保存时间
        self._last_save_time: float = 0.0

        # 是否处于恢复过程中（避免重复保存）
        self._restoring: bool = False

        # 自动备份路径
        self.autosave_dir = AUTOSAVE_DIR

    # ========================================================
    # 主窗口绑定
    # ========================================================

    def bind_window(self, main_window: QMainWindow):
        """
        绑定主窗口。绑定后可使用 restore() 恢复会话。

        参数:
            main_window: 主窗口实例
        """
        self._main_window = main_window

    # ========================================================
    # 自动保存
    # ========================================================

    def start_autosave(self):
        """启动自动保存定时器"""
        if self.enabled:
            self._autosave_timer.start()

    def stop_autosave(self):
        """停止自动保存定时器"""
        self._autosave_timer.stop()

    def _autosave_tick(self):
        """定时器回调：自动保存会话"""
        if not self.enabled or not self._main_window:
            return

        try:
            # 保存会话
            tabs = self._get_tabs()
            if tabs:
                self.save(tabs, self._main_window)

                # 保存自动备份（未保存的文件）
                self.save_autosave(tabs, self._main_window)
        except Exception as e:
            # 自动保存静默失败，不打断用户
            print(f"[Session] 自动保存失败: {e}")

    def _get_tabs(self):
        """从主窗口获取标签管理器"""
        if not self._main_window:
            return None
        return getattr(self._main_window, 'tabs', None)

    # ========================================================
    # 保存会话
    # ========================================================

    def delete(self) -> bool:
        """删除当前会话文件"""
        try:
            if os.path.exists(self.filepath):
                os.remove(self.filepath)
            self._session_data = {}
            return True
        except Exception as e:
            self.session_error.emit(str(e))
            return False

    def clear(self):
        """清空内存中的会话数据"""
        self._session_data = {}

    # ========================================================
    # 查询
    # ========================================================

    def exists(self) -> bool:
        """检查会话文件是否存在"""
        return os.path.exists(self.filepath)

    def get_session_info(self) -> Dict[str, Any]:
        """
        获取会话信息摘要（用于启动时的提示）。

        返回:
            {
                'exists': bool,
                'file_count': int,
                'saved_at': str,
                'files': list,
                'age_seconds': float,
            }
        """
        info: Dict[str, Any] = {
            'exists': self.exists(),
            'file_count': 0,
            'saved_at': None,
            'files': [],
            'age_seconds': 0,
        }

        if not info['exists']:
            return info

        try:
            data = self.load()
            info['file_count'] = len(data.get('files', []))
            info['saved_at'] = data.get('saved_at')
            info['files'] = [
                f.get('filepath') for f in data.get('files', [])
                if f.get('filepath')
            ]
            if info['saved_at']:
                saved_time = datetime.datetime.fromisoformat(info['saved_at'])
                delta = datetime.datetime.now() - saved_time
                info['age_seconds'] = delta.total_seconds()
        except Exception:
            pass

        return info

    def get_session_data(self) -> Dict[str, Any]:
        """获取当前缓存或文件的会话数据"""
        if not self._session_data:
            self._session_data = self.load()
        return self._session_data

    # ========================================================
    # 备份列表
    # ========================================================

    def list_backups(self) -> List[Tuple[str, float, int]]:
        """
        列出所有备份。

        返回:
            [(路径, 修改时间, 文件数量), ...] 按时间倒序
        """
        result = []
        try:
            if not os.path.exists(SESSION_BACKUP_DIR):
                return result
            for name in os.listdir(SESSION_BACKUP_DIR):
                if name.startswith("session_") and name.endswith(".json"):
                    path = os.path.join(SESSION_BACKUP_DIR, name)
                    mtime = os.path.getmtime(path)
                    try:
                        with open(path, encoding='utf-8') as f:
                            data = json.load(f)
                        count = len(data.get('files', []))
                    except Exception:
                        count = 0
                    result.append((path, mtime, count))
        except Exception:
            pass
        result.sort(key=lambda x: x[1], reverse=True)
        return result

    def export_session(self, filepath: str) -> bool:
        """导出会话到指定文件"""
        try:
            if not self._session_data:
                self._session_data = self.load()
            if not self._session_data:
                return False
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self._session_data, f,
                          indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[Session] 导出失败: {e}")
            return False

    def import_session(self, filepath: str) -> bool:
        """从指定文件导入会话"""
        try:
            with open(filepath, encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return False
            self._session_data = data
            return True
        except Exception as e:
            print(f"[Session] 导入失败: {e}")
            return False

    # ========================================================
    # 调试与信息
    # ========================================================

    def dump(self) -> str:
        """导出会话数据为可读文本"""
        data = self.get_session_data()
        lines = ["会话数据", "=" * 60]
        lines.append(f"版本: {data.get('version', '?')}")
        lines.append(f"保存时间: {data.get('saved_at', '?')}")
        lines.append(f"文件数量: {len(data.get('files', []))}")
        lines.append(f"活动标签: {data.get('active_tab', -1)}")
        lines.append("")

        lines.append("打开的文件:")
        for i, f in enumerate(data.get('files', [])):
            fp = f.get('filepath') or '(未命名)'
            modified = ' [已修改]' if f.get('modified') else ''
            lines.append(f"  {i + 1}. {fp}{modified}")

        lines.append("")
        geo = data.get('geometry', {})
        if geo:
            lines.append(f"窗口几何: {geo.get('w')}x{geo.get('h')} "
                         f"@ ({geo.get('x')}, {geo.get('y')})")

        docks = data.get('docks', {})
        if docks:
            lines.append(f"面板数量: {len(docks)}")

        return "\n".join(lines)

    def dump_autosave(self) -> str:
        """导出自动备份信息"""
        lines = ["自动备份", "=" * 60]

        if not os.path.isdir(self.autosave_dir):
            lines.append("(无自动备份)")
            return "\n".join(lines)

        meta_path = os.path.join(self.autosave_dir, AUTOSAVE_META)
        if not os.path.exists(meta_path):
            lines.append("(无元数据)")
            return "\n".join(lines)

        try:
            with open(meta_path, encoding='utf-8') as f:
                meta = json.load(f)

            lines.append(f"备份时间: {meta.get('timestamp', '?')}")
            lines.append(f"文件数量: {meta.get('count', 0)}")
            lines.append("")
            lines.append("备份的文件:")
            for f in meta.get('files', []):
                orig = f.get('original') or '(未命名)'
                lines.append(f"  - {orig} -> {f.get('backup', '')}")
        except Exception as e:
            lines.append(f"读取失败: {e}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        info = self.get_session_info()
        return (f"<SessionManager exists={info['exists']} "
                f"files={info['file_count']} saved_at={info['saved_at']}>")


# ============================================================
# 会话自动保存工作器（实验性，用于后台保存）
# ============================================================


from app.session_worker import SessionAutosaveWorker  # noqa: E402,F401
