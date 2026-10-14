#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为音效管理器模块，包含：
- SoundManager：音效管理器（单例）
- SoundEffect：音效对象（播放、循环、音量）
- SoundEvent：音效事件枚举
- SoundCategory：音效分类
- SoundLibrary：音效库（内置音效）
- SoundCache：音效缓存
- SoundPlayer：多通道播放器
- 音量控制（主音量/分类音量）
- 静音控制
- 音效淡入淡出
- 音效优先级
- 节流控制（防止频繁触发）
- 音效配置持久化
- 系统提示音回退
- 程序化生成音效
- 音效资源扫描

修复记录:
- 将 QtMultimedia 的导入包裹在 try/except 中（P2-6）。
  某些 PyQt5 安装不包含 QtMultimedia（如 Linux 精简安装、
  使用 pip install PyQt5 而非完整 Qt 包），会导致整个模块
  导入失败。现在缺失时会优雅降级：
    * SoundEffect 内部将 self._effect 置为 None
    * SoundManager 播放时回退到 QApplication.beep()
    * 不再因 import 失败而中断启动
"""

import io
import math
import os
import struct
import sys
import tempfile
import threading
import time
import wave
from collections import deque
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QObject,
    QSettings,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt5.QtWidgets import QApplication


# ============================================================
# QtMultimedia 安全导入（P2-6 修复）
# ============================================================
# 某些 PyQt5 安装（尤其 Linux 精简包）不包含 QtMultimedia 模块。
# 直接 import 会导致整个 sound_manager.py 加载失败，
# 进而影响 SoundManager 的调用方（主窗口、插件等）。
#
# 这里采用 try/except 包裹导入，缺失时将 QSoundEffect 等置为 None，
# 并在 SoundEffect / SoundManager 内部通过 _MULTIMEDIA_OK 判断降级。
try:
    from PyQt5.QtMultimedia import QAudioDeviceInfo, QAudioOutput, QMediaPlayer, QSoundEffect
    _MULTIMEDIA_OK = True
except ImportError as _mm_err:
    QSoundEffect = None
    QAudioOutput = None
    QMediaPlayer = None
    QAudioDeviceInfo = None
    _MULTIMEDIA_OK = False
    print(f"[SoundManager] QtMultimedia 不可用，音效将回退到系统提示音: {_mm_err}")


# ============================================================
# 常量
# ============================================================
# 默认音效目录
def _default_sound_dir() -> str:
    """资源目录用绝对路径（相对路径随工作目录变化）"""
    try:
        from infrastructure.plugin_loader import app_root_dir
        return os.path.join(app_root_dir(), "resources", "sounds")
    except Exception:  # pragma: no cover
        return os.path.join("resources", "sounds")


DEFAULT_SOUND_DIR = _default_sound_dir()

# 默认主音量（0.0 - 1.0）
DEFAULT_MASTER_VOLUME = 0.7

# 节流时间（毫秒）：同一音效在此时段内不重复播放
DEFAULT_THROTTLE_MS = 50

# 最大同时播放的通道数
MAX_CHANNELS = 16

# 缓存大小
MAX_CACHE_SIZE = 100

# 声音采样率
SAMPLE_RATE = 44100

# 淡出/淡入持续时间（毫秒）
FADE_DURATION_MS = 200


# ============================================================
# 音效分类枚举
# ============================================================
class SoundCategory(Enum):
    """音效分类"""
    UI = "ui"              # 界面交互
    EDITOR = "editor"      # 编辑操作
    NOTIFICATION = "notification"  # 通知
    ERROR = "error"        # 错误
    SUCCESS = "success"    # 成功
    SYSTEM = "system"      # 系统


# ============================================================
# 音效事件枚举
# ============================================================
class SoundEvent(Enum):
    """音效事件"""
    # 文件操作
    FILE_NEW = "file_new"
    FILE_OPEN = "file_open"
    FILE_SAVE = "file_save"
    FILE_CLOSE = "file_close"
    FILE_DELETE = "file_delete"

    # 编辑
    EDIT_TYPE = "edit_type"
    EDIT_DELETE = "edit_delete"
    EDIT_PASTE = "edit_paste"
    EDIT_UNDO = "edit_undo"
    EDIT_REDO = "edit_redo"
    EDIT_FIND = "edit_find"
    EDIT_REPLACE = "edit_replace"

    # 界面
    UI_CLICK = "ui_click"
    UI_TOGGLE = "ui_toggle"
    UI_HOVER = "ui_hover"
    UI_SCROLL = "ui_scroll"
    UI_TAB_SWITCH = "ui_tab_switch"
    UI_MENU_OPEN = "ui_menu_open"

    # 通知
    NOTIFY_INFO = "notify_info"
    NOTIFY_WARNING = "notify_warning"
    NOTIFY_ERROR = "notify_error"
    NOTIFY_SUCCESS = "notify_success"

    # 其他
    MACRO_START = "macro_start"
    MACRO_STOP = "macro_stop"
    SEARCH_FOUND = "search_found"
    SEARCH_NOT_FOUND = "search_not_found"
    TYPING = "typing"


# ============================================================
# 音效事件到分类的映射
# ============================================================
EVENT_CATEGORY_MAP: Dict[SoundEvent, SoundCategory] = {
    SoundEvent.FILE_NEW: SoundCategory.UI,
    SoundEvent.FILE_OPEN: SoundCategory.UI,
    SoundEvent.FILE_SAVE: SoundCategory.SUCCESS,
    SoundEvent.FILE_CLOSE: SoundCategory.UI,
    SoundEvent.FILE_DELETE: SoundCategory.UI,

    SoundEvent.EDIT_TYPE: SoundCategory.EDITOR,
    SoundEvent.EDIT_DELETE: SoundCategory.EDITOR,
    SoundEvent.EDIT_PASTE: SoundCategory.EDITOR,
    SoundEvent.EDIT_UNDO: SoundCategory.EDITOR,
    SoundEvent.EDIT_REDO: SoundCategory.EDITOR,
    SoundEvent.EDIT_FIND: SoundCategory.EDITOR,
    SoundEvent.EDIT_REPLACE: SoundCategory.EDITOR,

    SoundEvent.UI_CLICK: SoundCategory.UI,
    SoundEvent.UI_TOGGLE: SoundCategory.UI,
    SoundEvent.UI_HOVER: SoundCategory.UI,
    SoundEvent.UI_SCROLL: SoundCategory.UI,
    SoundEvent.UI_TAB_SWITCH: SoundCategory.UI,
    SoundEvent.UI_MENU_OPEN: SoundCategory.UI,

    SoundEvent.NOTIFY_INFO: SoundCategory.NOTIFICATION,
    SoundEvent.NOTIFY_WARNING: SoundCategory.NOTIFICATION,
    SoundEvent.NOTIFY_ERROR: SoundCategory.ERROR,
    SoundEvent.NOTIFY_SUCCESS: SoundCategory.SUCCESS,

    SoundEvent.MACRO_START: SoundCategory.NOTIFICATION,
    SoundEvent.MACRO_STOP: SoundCategory.NOTIFICATION,
    SoundEvent.SEARCH_FOUND: SoundCategory.NOTIFICATION,
    SoundEvent.SEARCH_NOT_FOUND: SoundCategory.NOTIFICATION,
    SoundEvent.TYPING: SoundCategory.EDITOR,
}


# ============================================================
# 音效事件到文件的映射（默认）
# ============================================================
EVENT_FILE_MAP: Dict[SoundEvent, str] = {
    SoundEvent.FILE_NEW: "file_new.wav",
    SoundEvent.FILE_OPEN: "file_open.wav",
    SoundEvent.FILE_SAVE: "file_save.wav",
    SoundEvent.FILE_CLOSE: "file_close.wav",
    SoundEvent.FILE_DELETE: "file_delete.wav",

    SoundEvent.EDIT_TYPE: "type.wav",
    SoundEvent.EDIT_DELETE: "delete.wav",
    SoundEvent.EDIT_PASTE: "paste.wav",
    SoundEvent.EDIT_UNDO: "undo.wav",
    SoundEvent.EDIT_REDO: "redo.wav",
    SoundEvent.EDIT_FIND: "find.wav",
    SoundEvent.EDIT_REPLACE: "replace.wav",

    SoundEvent.UI_CLICK: "click.wav",
    SoundEvent.UI_TOGGLE: "toggle.wav",
    SoundEvent.UI_HOVER: "hover.wav",
    SoundEvent.UI_SCROLL: "scroll.wav",
    SoundEvent.UI_TAB_SWITCH: "tab_switch.wav",
    SoundEvent.UI_MENU_OPEN: "menu_open.wav",

    SoundEvent.NOTIFY_INFO: "info.wav",
    SoundEvent.NOTIFY_WARNING: "warning.wav",
    SoundEvent.NOTIFY_ERROR: "error.wav",
    SoundEvent.NOTIFY_SUCCESS: "success.wav",

    SoundEvent.MACRO_START: "macro_start.wav",
    SoundEvent.MACRO_STOP: "macro_stop.wav",
    SoundEvent.SEARCH_FOUND: "found.wav",
    SoundEvent.SEARCH_NOT_FOUND: "not_found.wav",
    SoundEvent.TYPING: "type.wav",
}


# ============================================================
# 音效对象
# ============================================================
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

    def __init__(self, filepath: str = "",
                 parent: Optional[QObject] = None):
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
            with tempfile.NamedTemporaryFile(
                suffix=f".{format}", delete=False
            ) as tmp:
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
        current = (self._fade_start_volume +
                    (self._fade_target_volume -
                     self._fade_start_volume) * progress)

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
        if hasattr(self, '_temp_path') and os.path.exists(self._temp_path):
            try:
                os.remove(self._temp_path)
            except Exception:
                pass

    def __repr__(self) -> str:
        return (f"<SoundEffect {os.path.basename(self.filepath)} "
                f"vol={self._volume:.2f} "
                f"playing={self.is_playing()}>")


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
    def generate_tone(frequency: float, duration_ms: int,
                       volume: float = 0.5,
                       fade_in_ms: int = 5,
                       fade_out_ms: int = 20,
                       waveform: str = "sine") -> bytes:
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
    def _pack_wav(samples: List[int], sample_rate: int,
                   channels: int = 1, sample_width: int = 2) -> bytes:
        """将 PCM 数据打包为 WAV 字节"""
        buffer = io.BytesIO()

        with wave.open(buffer, 'wb') as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(sample_width)
            wav.setframerate(sample_rate)

            # 打包样本
            frames = struct.pack(
                f'<{len(samples)}h', *samples
            )
            wav.writeframes(frames)

        return buffer.getvalue()

    @staticmethod
    def click() -> bytes:
        """点击音效"""
        return BuiltinSounds.generate_tone(
            frequency=1200, duration_ms=30, volume=0.15,
            fade_in_ms=2, fade_out_ms=15, waveform="sine"
        )

    @staticmethod
    def toggle() -> bytes:
        """切换音效"""
        return BuiltinSounds.generate_tone(
            frequency=800, duration_ms=50, volume=0.15,
            fade_in_ms=2, fade_out_ms=30, waveform="triangle"
        )

    @staticmethod
    def hover() -> bytes:
        """悬停音效"""
        return BuiltinSounds.generate_tone(
            frequency=1800, duration_ms=15, volume=0.08,
            fade_in_ms=1, fade_out_ms=10, waveform="sine"
        )

    @staticmethod
    def type_key() -> bytes:
        """打字音效"""
        return BuiltinSounds.generate_tone(
            frequency=1500 + math.sin(time.time() * 100) * 100,
            duration_ms=12, volume=0.06,
            fade_in_ms=1, fade_out_ms=8, waveform="square"
        )

    @staticmethod
    def delete() -> bytes:
        """删除音效"""
        return BuiltinSounds.generate_tone(
            frequency=600, duration_ms=40, volume=0.12,
            fade_in_ms=2, fade_out_ms=25, waveform="triangle"
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
            frequency=1000, duration_ms=80, volume=0.12,
            fade_in_ms=5, fade_out_ms=40, waveform="sine"
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

    _instance: Optional['SoundManager'] = None
    _lock = threading.RLock()

    def __new__(cls, *args, **kwargs):
        """单例"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, sound_dir: str = DEFAULT_SOUND_DIR,
                 parent: Optional[QObject] = None):
        """
        参数:
            sound_dir: 音效目录
            parent: 父 QObject
        """
        if getattr(self, '_initialized', False):
            return

        super().__init__(parent)

        self.sound_dir = sound_dir

        # 设置
        self._settings = QSettings("QingCao", "SoundManager")

        # 状态
        self._enabled = True           # 总开关
        self._muted = False            # 静音
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
    def play(self, event: SoundEvent,
             force: bool = False) -> bool:
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
    def set_category_volume(self, category: SoundCategory,
                             volume: float):
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
    def set_category_enabled(self, category: SoundCategory,
                              enabled: bool):
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
            self._enabled = self._settings.value(
                "enabled", True, type=bool
            )
            self._muted = self._settings.value(
                "muted", False, type=bool
            )
            self._master_volume = self._settings.value(
                "master_volume", DEFAULT_MASTER_VOLUME, type=float
            )
            self._throttle_ms = self._settings.value(
                "throttle_ms", DEFAULT_THROTTLE_MS, type=int
            )

            # 分类音量
            for category in SoundCategory:
                key = f"category_volume_{category.value}"
                vol = self._settings.value(key, 1.0, type=float)
                self._category_volumes[category] = vol

                key_enabled = f"category_enabled_{category.value}"
                enabled = self._settings.value(
                    key_enabled, True, type=bool
                )
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
            lines.append(
                f"  {marker} {category.value:15s} "
                f"音量={vol:.2f}"
            )

        lines.append("")
        lines.append("事件映射:")
        for event in SoundEvent:
            has = self.has_sound(event)
            marker = "✓" if has else "✗"
            lines.append(f"  {marker} {event.value}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<SoundManager enabled={self._enabled} "
                f"muted={self._muted} "
                f"volume={self._master_volume:.2f}>")


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
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # 创建音效管理器
    manager = SoundManager()

    print("=== SoundManager 测试 ===")
    print(manager.dump())
    print()

    # 连接信号
    manager.enabled_changed.connect(
        lambda enabled: print(f"[信号] 启用状态: {enabled}")
    )
    manager.volume_changed.connect(
        lambda vol: print(f"[信号] 音量变更: {vol:.2f}")
    )

    # 测试内置音效生成
    print("=== 测试内置音效生成 ===")

    test_events = [
        SoundEvent.UI_CLICK,
        SoundEvent.EDIT_TYPE,
        SoundEvent.NOTIFY_SUCCESS,
        SoundEvent.NOTIFY_ERROR,
        SoundEvent.NOTIFY_WARNING,
    ]

    for event in test_events:
        has = manager.has_sound(event)
        print(f"  {event.value}: {'✓' if has else '✗'}")

    print()

    # 测试播放（可能听不到，取决于系统）
    print("=== 测试播放 ===")
    for event in test_events:
        success = manager.play(event, force=True)
        print(f"  {event.value}: {'播放成功' if success else '播放失败'}")
        QApplication.processEvents()
        time.sleep(0.15)

    print()

    # 测试音量控制
    print("=== 测试音量控制 ===")
    manager.set_master_volume(0.5)
    print(f"主音量设为 0.5: {manager.get_master_volume()}")

    manager.set_category_volume(SoundCategory.UI, 0.8)
    print(f"UI 分类音量: {manager.get_category_volume(SoundCategory.UI)}")

    print()

    # 测试静音
    print("=== 测试静音 ===")
    manager.set_muted(True)
    print(f"静音状态: {manager.is_muted()}")

    result = manager.play(SoundEvent.UI_CLICK)
    print(f"静音时播放: {result} (应为 False)")

    manager.set_muted(False)
    print(f"取消静音: {manager.is_muted()}")
    print()

    # 测试节流
    print("=== 测试节流 ===")
    manager.set_throttle(500)

    success_count = 0
    for _ in range(10):
        if manager.play(SoundEvent.UI_CLICK):
            success_count += 1

    print(f"连续调用 10 次，成功 {success_count} 次（节流生效）")
    print()

    # 测试禁用
    print("=== 测试禁用 ===")
    manager.set_enabled(False)
    print(f"启用状态: {manager.is_enabled()}")

    result = manager.play(SoundEvent.UI_CLICK)
    print(f"禁用时播放: {result} (应为 False)")

    manager.set_enabled(True)
    print()

    # 恢复默认
    print("=== 恢复默认设置 ===")
    manager.reset_settings()
    print(manager.dump())
    print()

    # 定时退出
    from PyQt5.QtCore import QTimer

    def cleanup_and_quit():
        manager.stop_all()
        print()
        print("测试完成。")
        app.quit()

    QTimer.singleShot(2000, cleanup_and_quit)

    sys.exit(app.exec())