# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""声音管理器（v2.24 拆分：common/assets/manager）。"""

from infrastructure.sound_assets import *  # noqa: F401,F403
from infrastructure.sound_manager_common import *  # noqa: F401,F403


class SoundManager(QObject):
    """
    音效管理器（单例）。

    统一管理所有音效，支持:
    - 分类音量控制
    - 静音
    - 节流
    - 缓存
    - 内置音效回退
    - 系统提示音回退
    - 配置持久化

    修复说明（P2-6）:
        - 当 QtMultimedia 不可用时，_init_sounds 不再尝试加载音效，
          play() 直接调用 _play_system_sound()（QApplication.beep()）。
        - 主流程（初始化、配置读写等）不受影响。

    信号:
        enabled_changed(bool): 启用状态变更
        volume_changed(float): 主音量变更
    """

    enabled_changed = pyqtSignal(bool)
    volume_changed = pyqtSignal(float)

    _instance: Optional["SoundManager"] = None
    _lock = threading.RLock()

    def __new__(cls, *args, **kwargs):
        """单例"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, sound_dir: str = DEFAULT_SOUND_DIR, parent: Optional[QObject] = None):
        """
        参数:
            sound_dir: 音效目录
            parent: 父 QObject
        """
        if getattr(self, "_initialized", False):
            return

        super().__init__(parent)

        self.sound_dir = sound_dir

        # 设置
        self._settings = QSettings("QingCao", "SoundManager")

        # 状态
        self._enabled = True  # 总开关
        self._muted = False  # 静音
        self._master_volume = DEFAULT_MASTER_VOLUME

        # 分类音量
        self._category_volumes: Dict[SoundCategory, float] = {
            category: 1.0 for category in SoundCategory
        }

        # 分类启用状态
        self._category_enabled: Dict[SoundCategory, bool] = {
            category: True for category in SoundCategory
        }

        # 音效缓存
        self.cache = SoundCache()

        # 事件到音效映射
        self._event_sounds: Dict[SoundEvent, SoundEffect] = {}

        # 节流记录：event -> last_play_time
        self._throttle: Dict[SoundEvent, float] = {}
        self._throttle_ms = DEFAULT_THROTTLE_MS

        # 活动音效列表（用于统一管理）
        self._active_effects: List[SoundEffect] = []

        # 加载配置
        self._load_settings()

        # 初始化
        self._init_sounds()

        self._initialized = True

    # ========================================================
    # 初始化
    # ========================================================
    def _init_sounds(self):
        """初始化音效"""
        # 若 QtMultimedia 不可用，跳过所有音效加载
        if not _MULTIMEDIA_OK:
            print("[SoundManager] QtMultimedia 不可用，跳过音效预加载")
            return

        # 扫描音效目录
        if not os.path.isdir(self.sound_dir):
            try:
                os.makedirs(self.sound_dir, exist_ok=True)
            except Exception:
                pass

        # 尝试为每个事件加载音效
        for event in SoundEvent:
            self._load_event_sound(event)

    def _load_event_sound(self, event: SoundEvent) -> bool:
        """
        加载事件对应的音效。

        优先级:
        1. 音效目录中的文件
        2. 内置生成的音效

        参数:
            event: 音效事件

        返回:
            是否成功
        """
        if not _MULTIMEDIA_OK:
            return False

        # 尝试从目录加载
        filename = EVENT_FILE_MAP.get(event, f"{event.value}.wav")
        filepath = os.path.join(self.sound_dir, filename)

        if os.path.exists(filepath):
            effect = SoundEffect(filepath, self)
            if effect.available:
                self._event_sounds[event] = effect
                return True

        # 回退到内置音效
        try:
            data = BuiltinSounds.get(event)
            if data:
                effect = SoundEffect("", self)
                if effect.load_from_data(data, "wav"):
                    self._event_sounds[event] = effect
                    return True
        except Exception as e:
            print(f"[SoundManager] 生成内置音效失败 ({event.value}): {e}")

        return False

    # ========================================================
    # 播放
    # ========================================================
    def play(self, event: SoundEvent, force: bool = False) -> bool:
        """播放音效。

        参数:
            event: 音效事件
            force: 强制执行（忽略节流）

        返回:
            是否成功播放

        P1-2: 增加编辑器偏好开关 ``sound_effects``（默认关闭）。
        修复前该模块全仓零调用，是个"死模块"；现在由主窗口在
        文件打开/保存/出错时调用，并可通过首选项关闭。
        """
        if not self._pref_enabled():
            return False

        if not self._enabled or self._muted:
            return False

        # 检查分类是否启用
        category = EVENT_CATEGORY_MAP.get(event, SoundCategory.UI)
        if not self._category_enabled.get(category, True):
            return False

        # 节流检查
        if not force:
            now = time.time() * 1000
            last = self._throttle.get(event, 0)

            if now - last < self._throttle_ms:
                return False

            self._throttle[event] = now

        # 若 QtMultimedia 不可用，直接回退到系统提示音
        if not _MULTIMEDIA_OK:
            return self._play_system_sound(event)

        # 获取音效
        effect = self._event_sounds.get(event)
        if not effect or not effect.available:
            # 尝试回退到系统提示音
            return self._play_system_sound(event)

        # 设置音量
        effect.volume = self._calculate_volume(category)

        # 播放
        try:
            effect.play()
            return True
        except Exception as e:
            print(f"[SoundManager] 播放失败 ({event.value}): {e}")
            return False

    def play_file(self, filepath: str, volume: float = 1.0) -> bool:
        """
        播放指定文件。

        参数:
            filepath: 音效文件路径
            volume: 音量

        返回:
            是否成功
        """
        if not self._enabled or self._muted:
            return False

        if not _MULTIMEDIA_OK:
            # 无 QtMultimedia，回退 beep
            return self._play_system_sound(SoundEvent.UI_CLICK)

        if not os.path.exists(filepath):
            return False

        try:
            # 从缓存获取或创建
            effect = self.cache.get(filepath)

            if effect is None:
                effect = SoundEffect(filepath, self)
                if not effect.available:
                    return False
                self.cache.put(filepath, effect)

            effect.volume = volume * self._master_volume
            effect.play()

            return True

        except Exception as e:
            print(f"[SoundManager] 播放失败: {e}")
            return False

    def _play_system_sound(self, event: SoundEvent) -> bool:
        """
        回退到系统提示音。

        参数:
            event: 音效事件

        返回:
            是否成功
        """
        try:
            # 使用 QApplication 的 beep 作为最终回退
            if QApplication.instance():
                QApplication.beep()
                return True
        except Exception:
            pass

        return False

    # ========================================================
    # 音量计算
    # ========================================================
    def _calculate_volume(self, category: SoundCategory) -> float:
        """
        计算最终音量。

        参数:
            category: 音效分类

        返回:
            0.0 - 1.0 之间的音量
        """
        master = self._master_volume
        cat_vol = self._category_volumes.get(category, 1.0)

        return max(0.0, min(1.0, master * cat_vol))

    # ========================================================
    # 启用/禁用
    # ========================================================
    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        if self._enabled != value:
            self._enabled = bool(value)

            if not self._enabled:
                self.stop_all()

            self._save_settings()
            self.enabled_changed.emit(self._enabled)

    def set_enabled(self, enabled: bool):
        """设置启用状态"""
        self.enabled = enabled

    def is_enabled(self) -> bool:
        """是否启用"""
        return self._enabled

    # ========================================================
    # 静音
    # ========================================================
    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, value: bool):
        if self._muted != value:
            self._muted = bool(value)

            if self._muted:
                self.stop_all()

            self._save_settings()

    def set_muted(self, muted: bool):
        """设置静音"""
        self.muted = muted

    def toggle_muted(self) -> bool:
        """切换静音"""
        self.muted = not self._muted
        return self._muted

    def is_muted(self) -> bool:
        """是否静音"""
        return self._muted

    # ========================================================
    # 主音量
    # ========================================================
    @property
    def master_volume(self) -> float:
        return self._master_volume

    @master_volume.setter
    def master_volume(self, value: float):
        value = max(0.0, min(1.0, value))

        if abs(self._master_volume - value) > 0.001:
            self._master_volume = value
            self._save_settings()
            self.volume_changed.emit(value)

    def set_master_volume(self, volume: float):
        """设置主音量"""
        self.master_volume = volume

    def get_master_volume(self) -> float:
        """获取主音量"""
        return self._master_volume

    # ========================================================
    # 分类音量
    # ========================================================
    def set_category_volume(self, category: SoundCategory, volume: float):
        """设置分类音量"""
        volume = max(0.0, min(1.0, volume))
        self._category_volumes[category] = volume
        self._save_settings()

    def get_category_volume(self, category: SoundCategory) -> float:
        """获取分类音量"""
        return self._category_volumes.get(category, 1.0)

    # ========================================================
    # 分类启用
    # ========================================================
    def set_category_enabled(self, category: SoundCategory, enabled: bool):
        """启用/禁用分类"""
        self._category_enabled[category] = bool(enabled)
        self._save_settings()

    def is_category_enabled(self, category: SoundCategory) -> bool:
        """分类是否启用"""
        return self._category_enabled.get(category, True)

    # ========================================================
    # 节流配置
    # ========================================================
    def set_throttle(self, ms: int):
        """设置节流时间"""
        self._throttle_ms = max(0, ms)

    def get_throttle(self) -> int:
        """获取节流时间"""
        return self._throttle_ms

    # ========================================================
    # 停止
    # ========================================================
    def stop_all(self):
        """停止所有音效"""
        for effect in self._event_sounds.values():
            try:
                effect.stop()
            except Exception:
                pass

        for effect in self._active_effects:
            try:
                effect.stop()
            except Exception:
                pass

        self._active_effects.clear()

    def stop_event(self, event: SoundEvent):
        """停止指定事件的音效"""
        effect = self._event_sounds.get(event)
        if effect:
            effect.stop()

    # ========================================================
    # 配置持久化
    # ========================================================
    def _pref_enabled(self) -> bool:
        """编辑器偏好中的音效总开关（P1-2）

        以 app.preferences 的 ``sound_effects`` 为准（默认 False），
        读不到时才回退到本模块自己的 QSettings 值。
        """
        try:
            from app.preferences import Preferences

            return bool(Preferences().get("sound_effects", False))
        except Exception:
            return True

    def _load_settings(self):
        """加载设置"""
        try:
            self._enabled = self._settings.value("enabled", True, type=bool)
            self._muted = self._settings.value("muted", False, type=bool)
            self._master_volume = self._settings.value(
                "master_volume", DEFAULT_MASTER_VOLUME, type=float
            )
            self._throttle_ms = self._settings.value("throttle_ms", DEFAULT_THROTTLE_MS, type=int)

            # 分类音量
            for category in SoundCategory:
                key = f"category_volume_{category.value}"
                vol = self._settings.value(key, 1.0, type=float)
                self._category_volumes[category] = vol

                key_enabled = f"category_enabled_{category.value}"
                enabled = self._settings.value(key_enabled, True, type=bool)
                self._category_enabled[category] = enabled

        except Exception as e:
            print(f"[SoundManager] 加载设置失败: {e}")

    def _save_settings(self):
        """保存设置"""
        try:
            self._settings.setValue("enabled", self._enabled)
            self._settings.setValue("muted", self._muted)
            self._settings.setValue("master_volume", self._master_volume)
            self._settings.setValue("throttle_ms", self._throttle_ms)

            for category, vol in self._category_volumes.items():
                key = f"category_volume_{category.value}"
                self._settings.setValue(key, vol)

            for category, enabled in self._category_enabled.items():
                key = f"category_enabled_{category.value}"
                self._settings.setValue(key, enabled)

        except Exception as e:
            print(f"[SoundManager] 保存设置失败: {e}")

    def reset_settings(self):
        """重置设置"""
        self._enabled = True
        self._muted = False
        self._master_volume = DEFAULT_MASTER_VOLUME
        self._throttle_ms = DEFAULT_THROTTLE_MS

        for category in SoundCategory:
            self._category_volumes[category] = 1.0
            self._category_enabled[category] = True

        self._save_settings()

    # ========================================================
    # 音效管理
    # ========================================================
    def register_sound(self, event: SoundEvent, filepath: str) -> bool:
        """
        注册自定义音效。

        参数:
            event: 事件
            filepath: 音效文件路径

        返回:
            是否成功
        """
        if not _MULTIMEDIA_OK:
            return False

        if not os.path.exists(filepath):
            return False

        try:
            effect = SoundEffect(filepath, self)
            if effect.available:
                self._event_sounds[event] = effect
                return True
        except Exception as e:
            print(f"[SoundManager] 注册失败: {e}")

        return False

    def unregister_sound(self, event: SoundEvent):
        """注销音效"""
        self._event_sounds.pop(event, None)

    def reload_sounds(self):
        """重新加载所有音效"""
        # 停止所有
        self.stop_all()

        # 清空缓存
        self.cache.clear()

        # 清空事件映射
        self._event_sounds.clear()

        # 重新加载
        self._init_sounds()

    def list_events(self) -> List[SoundEvent]:
        """列出所有已加载的事件"""
        return list(self._event_sounds.keys())

    def has_sound(self, event: SoundEvent) -> bool:
        """检查事件是否有音效"""
        effect = self._event_sounds.get(event)
        return effect is not None and effect.available

    # ========================================================
    # 便捷函数
    # ========================================================
    def beep(self):
        """系统提示音"""
        try:
            if QApplication.instance():
                QApplication.beep()
        except Exception:
            pass

    def preview(self, event: SoundEvent):
        """
        预览音效（用于设置界面）。

        参数:
            event: 事件
        """
        # 临时启用
        old_enabled = self._enabled
        old_muted = self._muted
        old_volume = self._master_volume

        try:
            self._enabled = True
            self._muted = False
            self._master_volume = 1.0

            self.play(event, force=True)

        finally:
            self._enabled = old_enabled
            self._muted = old_muted
            self._master_volume = old_volume

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出管理器信息"""
        lines = ["SoundManager", "=" * 60]
        lines.append(f"启用: {self._enabled}")
        lines.append(f"静音: {self._muted}")
        lines.append(f"主音量: {self._master_volume:.2f}")
        lines.append(f"节流: {self._throttle_ms} ms")
        lines.append(f"音效目录: {self.sound_dir}")
        lines.append(f"缓存大小: {self.cache.size()}")
        lines.append(f"已加载事件数: {len(self._event_sounds)}")
        lines.append(f"QtMultimedia 可用: {_MULTIMEDIA_OK}")

        lines.append("")
        lines.append("分类设置:")
        for category in SoundCategory:
            vol = self._category_volumes.get(category, 1.0)
            enabled = self._category_enabled.get(category, True)
            marker = "✓" if enabled else "✗"
            lines.append(f"  {marker} {category.value:15s} 音量={vol:.2f}")

        lines.append("")
        lines.append("事件映射:")
        for event in SoundEvent:
            has = self.has_sound(event)
            marker = "✓" if has else "✗"
            lines.append(f"  {marker} {event.value}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"<SoundManager enabled={self._enabled} "
            f"muted={self._muted} "
            f"volume={self._master_volume:.2f}>"
        )


# ============================================================
# 全局单例访问
# ============================================================


def get_sound_manager(sound_dir: str = DEFAULT_SOUND_DIR) -> SoundManager:
    """
    获取全局 SoundManager 单例。

    参数:
        sound_dir: 音效目录（仅首次创建时有效）

    返回:
        SoundManager 实例
    """
    return SoundManager(sound_dir=sound_dir)


def play_sound(event: SoundEvent, force: bool = False) -> bool:
    """
    播放音效的便捷函数。

    参数:
        event: 音效事件
        force: 强制执行

    返回:
        是否成功
    """
    manager = get_sound_manager()
    return manager.play(event, force)


# ============================================================
# 模块测试
# ============================================================
