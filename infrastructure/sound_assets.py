# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""音效缓存/内置音（v2.24 拆出）。"""

from infrastructure.sound_manager_common import *  # noqa: F401,F403,F405


class SoundEffect(QObject):
    """
    单个音效对象。

    封装 QSoundEffect，提供音量、淡入淡出、循环等控制。

    修复说明（P2-6）:
        - 当 QtMultimedia 不可用时（_MULTIMEDIA_OK 为 False），
          self._effect 保持为 None，_available 恒为 False。
          所有方法均做 None 保护，调用不会崩溃。
    """

    finished = pyqtSignal()

    def __init__(self, filepath: str = "", parent: Optional[QObject] = None):
        super().__init__(parent)

        self.filepath = filepath
        self._volume = 1.0
        self._muted = False
        self._loops = 1
        self._playing = False
        self._available = False

        # QSoundEffect（可能为 None）
        if _MULTIMEDIA_OK and QSoundEffect is not None:
            self._effect = QSoundEffect(self)
            # 连接信号
            self._effect.playingChanged.connect(self._on_playing_changed)
            self._effect.statusChanged.connect(self._on_status_changed)
        else:
            self._effect = None

        # 淡出定时器
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(20)
        self._fade_timer.timeout.connect(self._fade_step)
        self._fade_start_volume = 1.0
        self._fade_target_volume = 1.0
        self._fade_steps = 0
        self._fade_current_step = 0

        # 加载
        if filepath:
            self.load(filepath)

    # --------------------------------------------------------
    # 加载
    # --------------------------------------------------------
    def load(self, filepath: str) -> bool:
        """
        加载音效文件。

        参数:
            filepath: 音效文件路径

        返回:
            是否成功
        """
        if not _MULTIMEDIA_OK or self._effect is None:
            # 无 QtMultimedia，直接标记为不可用
            self.filepath = filepath
            self._available = False
            return False

        if not os.path.exists(filepath):
            self._available = False
            return False

        try:
            self.filepath = filepath
            self._effect.setSource(QUrl.fromLocalFile(filepath))
            self._available = True
            return True

        except Exception as e:
            print(f"[SoundEffect] 加载失败 ({filepath}): {e}")
            self._available = False
            return False

    def load_from_data(self, data: bytes, format: str = "wav") -> bool:
        """
        从字节数据加载音效（用于程序化生成）。

        参数:
            data: WAV 格式字节数据
            format: 格式（仅支持 wav）

        返回:
            是否成功
        """
        if not _MULTIMEDIA_OK or self._effect is None:
            self._available = False
            return False

        try:
            # 写入临时文件
            with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as tmp:
                tmp.write(data)
                tmp_path = tmp.name

            self._temp_path = tmp_path

            return self.load(tmp_path)

        except Exception as e:
            print(f"[SoundEffect] 数据加载失败: {e}")
            return False

    # --------------------------------------------------------
    # 播放控制
    # --------------------------------------------------------
    def play(self):
        """播放音效"""
        if not self._available or self._muted:
            return

        if self._effect is None:
            return

        try:
            self._effect.setVolume(self._volume)
            self._effect.setLoopCount(self._loops)
            self._effect.play()
            self._playing = True

        except Exception as e:
            print(f"[SoundEffect] 播放失败: {e}")

    def stop(self):
        """停止播放"""
        try:
            if self._effect is not None:
                self._effect.stop()
            self._playing = False
        except Exception:
            pass

    def is_playing(self) -> bool:
        """是否正在播放"""
        try:
            if self._effect is not None:
                return self._effect.isPlaying()
            return self._playing
        except Exception:
            return self._playing

    @property
    def playing(self) -> bool:
        """播放状态"""
        return self.is_playing()

    @property
    def available(self) -> bool:
        """是否可用"""
        return self._available

    # --------------------------------------------------------
    # 音量
    # --------------------------------------------------------
    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, value: float):
        self._volume = max(0.0, min(1.0, value))
        try:
            if self._effect is not None:
                self._effect.setVolume(self._volume)
        except Exception:
            pass

    def set_volume(self, volume: float):
        """设置音量"""
        self.volume = volume

    def get_volume(self) -> float:
        """获取音量"""
        return self._volume

    # --------------------------------------------------------
    # 静音
    # --------------------------------------------------------
    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, value: bool):
        self._muted = bool(value)
        if self._muted:
            self.stop()

    # --------------------------------------------------------
    # 循环
    # --------------------------------------------------------
    def set_loops(self, loops: int):
        """设置循环次数（0 或 -1 表示无限）"""
        self._loops = loops
        try:
            if self._effect is not None:
                self._effect.setLoopCount(loops)
        except Exception:
            pass

    # --------------------------------------------------------
    # 淡入淡出
    # --------------------------------------------------------
    def fade_in(self, duration_ms: int = FADE_DURATION_MS):
        """淡入"""
        self._fade_start_volume = 0.0
        self._fade_target_volume = self._volume
        self._start_fade(duration_ms)
        self.play()

    def fade_out(self, duration_ms: int = FADE_DURATION_MS):
        """淡出"""
        self._fade_start_volume = self._volume
        self._fade_target_volume = 0.0
        self._start_fade(duration_ms)

    def _start_fade(self, duration_ms: int):
        """开始淡入淡出"""
        steps = max(1, duration_ms // 20)
        self._fade_steps = steps
        self._fade_current_step = 0
        self._fade_timer.start()

    def _fade_step(self):
        """淡入淡出单步"""
        self._fade_current_step += 1

        if self._fade_current_step >= self._fade_steps:
            self._fade_timer.stop()
            self._volume = self._fade_target_volume
            try:
                if self._effect is not None:
                    self._effect.setVolume(self._volume)
            except Exception:
                pass

            if self._fade_target_volume == 0.0:
                self.stop()
            return

        # 线性插值
        progress = self._fade_current_step / self._fade_steps
        current = (
            self._fade_start_volume
            + (self._fade_target_volume - self._fade_start_volume) * progress
        )

        try:
            if self._effect is not None:
                self._effect.setVolume(max(0.0, min(1.0, current)))
        except Exception:
            pass

    # --------------------------------------------------------
    # 内部回调
    # --------------------------------------------------------
    def _on_playing_changed(self):
        """播放状态变化"""
        if not self.is_playing():
            self._playing = False
            self.finished.emit()

    def _on_status_changed(self):
        """状态变化"""
        try:
            if self._effect is None:
                return
            status = self._effect.status()
            if status == QSoundEffect.Error:
                self._available = False
        except Exception:
            pass

    # --------------------------------------------------------
    # 清理
    # --------------------------------------------------------
    def cleanup(self):
        """清理临时文件"""
        if hasattr(self, "_temp_path") and os.path.exists(self._temp_path):
            try:
                os.remove(self._temp_path)
            except Exception:
                pass

    def __repr__(self) -> str:
        return (
            f"<SoundEffect {os.path.basename(self.filepath)} "
            f"vol={self._volume:.2f} "
            f"playing={self.is_playing()}>"
        )


# ============================================================
# 音效缓存
# ============================================================


class SoundCache:
    """
    音效缓存。

    缓存已加载的音效，减少重复加载。
    """

    def __init__(self, max_size: int = MAX_CACHE_SIZE):
        self.max_size = max_size
        self._cache: Dict[str, SoundEffect] = {}
        self._lock = threading.RLock()

    def get(self, filepath: str) -> Optional[SoundEffect]:
        """获取缓存的音效"""
        with self._lock:
            return self._cache.get(filepath)

    def put(self, filepath: str, effect: SoundEffect):
        """存入缓存"""
        with self._lock:
            if len(self._cache) >= self.max_size:
                self._evict()

            self._cache[filepath] = effect

    def _evict(self):
        """淘汰一个条目"""
        if not self._cache:
            return

        # 淘汰第一个（FIFO）
        key = next(iter(self._cache))
        self._cache.pop(key)

    def invalidate(self, filepath: str):
        """使失效"""
        with self._lock:
            self._cache.pop(filepath, None)

    def clear(self):
        """清空"""
        with self._lock:
            for effect in self._cache.values():
                try:
                    effect.cleanup()
                except Exception:
                    pass
            self._cache.clear()

    def size(self) -> int:
        """当前大小"""
        return len(self._cache)

    def __repr__(self) -> str:
        return f"<SoundCache size={len(self._cache)}/{self.max_size}>"


# ============================================================
# 内置音效生成器
# ============================================================


class BuiltinSounds:
    """
    内置音效生成器。

    通过程序化生成简单音效（无外部文件依赖）。
    """

    @staticmethod
    def generate_tone(
        frequency: float,
        duration_ms: int,
        volume: float = 0.5,
        fade_in_ms: int = 5,
        fade_out_ms: int = 20,
        waveform: str = "sine",
    ) -> bytes:
        """
        生成一个简单的音调。

        参数:
            frequency: 频率（Hz）
            duration_ms: 持续时间（毫秒）
            volume: 音量（0-1）
            fade_in_ms: 淡入时间
            fade_out_ms: 淡出时间
            waveform: 波形（sine/square/triangle/sawtooth）

        返回:
            WAV 格式字节数据
        """
        sample_rate = SAMPLE_RATE
        num_samples = int(sample_rate * duration_ms / 1000)

        fade_in_samples = int(sample_rate * fade_in_ms / 1000)
        fade_out_samples = int(sample_rate * fade_out_ms / 1000)

        samples = []

        for i in range(num_samples):
            t = i / sample_rate

            # 基础波形
            if waveform == "sine":
                value = math.sin(2 * math.pi * frequency * t)
            elif waveform == "square":
                value = 1.0 if math.sin(2 * math.pi * frequency * t) >= 0 else -1.0
            elif waveform == "triangle":
                value = 2 * abs(2 * (t * frequency - math.floor(t * frequency + 0.5)))
                value = value - 1
            elif waveform == "sawtooth":
                value = 2 * (t * frequency - math.floor(t * frequency + 0.5))
            else:
                value = math.sin(2 * math.pi * frequency * t)

            # 包络（淡入淡出）
            envelope = 1.0

            if i < fade_in_samples:
                envelope *= i / max(1, fade_in_samples)

            remaining = num_samples - i
            if remaining < fade_out_samples:
                envelope *= remaining / max(1, fade_out_samples)

            sample = value * envelope * volume
            samples.append(int(sample * 32767))

        # 打包为 WAV
        return BuiltinSounds._pack_wav(samples, sample_rate)

    @staticmethod
    def _pack_wav(
        samples: List[int], sample_rate: int, channels: int = 1, sample_width: int = 2
    ) -> bytes:
        """将 PCM 数据打包为 WAV 字节"""
        buffer = io.BytesIO()

        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(sample_width)
            wav.setframerate(sample_rate)

            # 打包样本
            frames = struct.pack(f"<{len(samples)}h", *samples)
            wav.writeframes(frames)

        return buffer.getvalue()

    @staticmethod
    def click() -> bytes:
        """点击音效"""
        return BuiltinSounds.generate_tone(
            frequency=1200,
            duration_ms=30,
            volume=0.15,
            fade_in_ms=2,
            fade_out_ms=15,
            waveform="sine",
        )

    @staticmethod
    def toggle() -> bytes:
        """切换音效"""
        return BuiltinSounds.generate_tone(
            frequency=800,
            duration_ms=50,
            volume=0.15,
            fade_in_ms=2,
            fade_out_ms=30,
            waveform="triangle",
        )

    @staticmethod
    def hover() -> bytes:
        """悬停音效"""
        return BuiltinSounds.generate_tone(
            frequency=1800,
            duration_ms=15,
            volume=0.08,
            fade_in_ms=1,
            fade_out_ms=10,
            waveform="sine",
        )

    @staticmethod
    def type_key() -> bytes:
        """打字音效"""
        return BuiltinSounds.generate_tone(
            frequency=1500 + math.sin(time.time() * 100) * 100,
            duration_ms=12,
            volume=0.06,
            fade_in_ms=1,
            fade_out_ms=8,
            waveform="square",
        )

    @staticmethod
    def delete() -> bytes:
        """删除音效"""
        return BuiltinSounds.generate_tone(
            frequency=600,
            duration_ms=40,
            volume=0.12,
            fade_in_ms=2,
            fade_out_ms=25,
            waveform="triangle",
        )

    @staticmethod
    def success() -> bytes:
        """成功音效（上升音调）"""
        samples = []
        sample_rate = SAMPLE_RATE

        # 上升音阶：C5 → E5 → G5
        notes = [523.25, 659.25, 783.99]
        note_duration = 60
        gap_duration = 10

        for i, freq in enumerate(notes):
            note_samples = int(sample_rate * note_duration / 1000)
            for j in range(note_samples):
                t = j / sample_rate
                value = math.sin(2 * math.pi * freq * t)

                # 包络
                envelope = 1.0
                fade_in = int(sample_rate * 3 / 1000)
                fade_out = int(sample_rate * 15 / 1000)

                if j < fade_in:
                    envelope *= j / max(1, fade_in)
                if note_samples - j < fade_out:
                    envelope *= (note_samples - j) / max(1, fade_out)

                samples.append(int(value * envelope * 0.18))

            # 音符间空隙
            if i < len(notes) - 1:
                gap_samples = int(sample_rate * gap_duration / 1000)
                samples.extend([0] * gap_samples)

        return BuiltinSounds._pack_wav(samples, sample_rate)

    @staticmethod
    def error() -> bytes:
        """错误音效（下降音调）"""
        samples = []
        sample_rate = SAMPLE_RATE

        # 下降音阶：G4 → D4
        notes = [392.00, 293.66]
        note_duration = 100
        gap_duration = 20

        for i, freq in enumerate(notes):
            note_samples = int(sample_rate * note_duration / 1000)
            for j in range(note_samples):
                t = j / sample_rate
                value = math.sin(2 * math.pi * freq * t)

                envelope = 1.0
                fade_in = int(sample_rate * 5 / 1000)
                fade_out = int(sample_rate * 40 / 1000)

                if j < fade_in:
                    envelope *= j / max(1, fade_in)
                if note_samples - j < fade_out:
                    envelope *= (note_samples - j) / max(1, fade_out)

                samples.append(int(value * envelope * 0.2))

            if i < len(notes) - 1:
                gap_samples = int(sample_rate * gap_duration / 1000)
                samples.extend([0] * gap_samples)

        return BuiltinSounds._pack_wav(samples, sample_rate)

    @staticmethod
    def warning() -> bytes:
        """警告音效"""
        samples = []
        sample_rate = SAMPLE_RATE

        # 双短音
        for _ in range(2):
            note_samples = int(sample_rate * 80 / 1000)
            for j in range(note_samples):
                t = j / sample_rate
                value = math.sin(2 * math.pi * 880 * t)

                envelope = 1.0
                fade_in = int(sample_rate * 5 / 1000)
                fade_out = int(sample_rate * 30 / 1000)

                if j < fade_in:
                    envelope *= j / max(1, fade_in)
                if note_samples - j < fade_out:
                    envelope *= (note_samples - j) / max(1, fade_out)

                samples.append(int(value * envelope * 0.18))

            # 间隔
            gap_samples = int(sample_rate * 50 / 1000)
            samples.extend([0] * gap_samples)

        return BuiltinSounds._pack_wav(samples, sample_rate)

    @staticmethod
    def info() -> bytes:
        """信息音效"""
        return BuiltinSounds.generate_tone(
            frequency=1000,
            duration_ms=80,
            volume=0.12,
            fade_in_ms=5,
            fade_out_ms=40,
            waveform="sine",
        )

    @staticmethod
    def get(event: SoundEvent) -> Optional[bytes]:
        """根据事件获取内置音效"""
        mapping = {
            SoundEvent.FILE_NEW: BuiltinSounds.click,
            SoundEvent.FILE_OPEN: BuiltinSounds.click,
            SoundEvent.FILE_SAVE: BuiltinSounds.success,
            SoundEvent.FILE_CLOSE: BuiltinSounds.click,
            SoundEvent.FILE_DELETE: BuiltinSounds.delete,
            SoundEvent.EDIT_TYPE: BuiltinSounds.type_key,
            SoundEvent.EDIT_DELETE: BuiltinSounds.delete,
            SoundEvent.EDIT_PASTE: BuiltinSounds.click,
            SoundEvent.EDIT_UNDO: BuiltinSounds.toggle,
            SoundEvent.EDIT_REDO: BuiltinSounds.toggle,
            SoundEvent.EDIT_FIND: BuiltinSounds.click,
            SoundEvent.EDIT_REPLACE: BuiltinSounds.click,
            SoundEvent.UI_CLICK: BuiltinSounds.click,
            SoundEvent.UI_TOGGLE: BuiltinSounds.toggle,
            SoundEvent.UI_HOVER: BuiltinSounds.hover,
            SoundEvent.UI_SCROLL: BuiltinSounds.hover,
            SoundEvent.UI_TAB_SWITCH: BuiltinSounds.click,
            SoundEvent.UI_MENU_OPEN: BuiltinSounds.click,
            SoundEvent.NOTIFY_INFO: BuiltinSounds.info,
            SoundEvent.NOTIFY_WARNING: BuiltinSounds.warning,
            SoundEvent.NOTIFY_ERROR: BuiltinSounds.error,
            SoundEvent.NOTIFY_SUCCESS: BuiltinSounds.success,
            SoundEvent.MACRO_START: BuiltinSounds.toggle,
            SoundEvent.MACRO_STOP: BuiltinSounds.toggle,
            SoundEvent.SEARCH_FOUND: BuiltinSounds.click,
            SoundEvent.SEARCH_NOT_FOUND: BuiltinSounds.error,
            SoundEvent.TYPING: BuiltinSounds.type_key,
        }

        factory = mapping.get(event)
        if factory:
            try:
                return factory()
            except Exception:
                return None

        return None


# ============================================================
# 音效管理器
# ============================================================
