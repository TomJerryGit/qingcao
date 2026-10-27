#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为敏感信息加密存储模块，包含：
- SecureStorage：基于系统密钥环的安全存储（跨平台）
- 自动迁移：从旧的明文 QSettings 迁移到密钥环
- 优雅降级：keyring 不可用时回退到明文，附带警告
- 缓存：避免频繁访问系统密钥环
- 批量操作：一次读写多个条目

设计原则:
    1. 敏感信息（API Key、Token、密码）统一走此模块
    2. 非敏感信息（模型名、Base URL、偏好）保持 QSettings
    3. 用户可见的存储方式（在首选项 → 隐私中显示）
    4. 任何失败都不应导致编辑器崩溃

依赖:
    keyring >= 23.0.0 （推荐）
    Windows 需要 pywin32-ctypes

用法:
    from core.secure_storage import SecureStorage

    storage = SecureStorage()

    # 写入
    storage.save("ai_api_key", "sk-xxx")

    # 读取
    key = storage.load("ai_api_key", "")

    # 删除
    storage.delete("ai_api_key")

    # 迁移（首次升级时调用）
    storage.migrate_from_settings(
        settings, key="api_key", service="QingCao", app="AI"
    )
"""

import json
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, QSettings, pyqtSignal


# ============================================================
# 常量
# ============================================================
# keyring 服务名（在系统密钥环中显示的标识）
KEYRING_SERVICE = "QingCaoEditor"

# 缓存过期时间（秒）—— 避免频繁访问系统密钥环
CACHE_TTL = 300

# 环境变量：强制禁用 keyring（用于测试）
ENV_DISABLE_KEYRING = "QINGCAO_DISABLE_KEYRING"

# 环境变量：强制使用明文存储（调试）
ENV_FORCE_PLAINTEXT = "QINGCAO_FORCE_PLAINTEXT"

# 明文存储的 QSettings 键前缀
PLAINTEXT_PREFIX = "secure_plaintext_"


# ============================================================
# 存储后端枚举
# ============================================================
class StorageBackend:
    """存储后端类型"""
    KEYRING = "keyring"       # 系统密钥环（推荐）
    PLAINTEXT = "plaintext"   # QSettings 明文（降级）
    DISABLED = "disabled"     # 完全禁用


# ============================================================
# 安全存储
# ============================================================
class SecureStorage(QObject):
    """
    敏感信息的安全存储管理器（单例）。

    职责:
        - 提供跨平台的敏感信息读写接口
        - 自动检测可用的后端（keyring / 明文）
        - 提供从旧 QSettings 的自动迁移
        - 所有操作都不抛出异常（内部捕获 + 日志）

    信号:
        backend_changed(str): 后端变更（新后端名）
        migration_completed(int): 迁移完成（迁移条目数）
        security_warning(str): 安全警告（如降级到明文）
    """

    backend_changed = pyqtSignal(str)
    migration_completed = pyqtSignal(int)
    security_warning = pyqtSignal(str)

    _instance: Optional['SecureStorage'] = None
    _lock = threading.RLock()

    def __new__(cls, *args, **kwargs):
        """单例"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, parent: Optional[QObject] = None):
        if getattr(self, '_initialized', False):
            return

        super().__init__(parent)

        # 后端状态
        self._backend: str = StorageBackend.DISABLED
        self._keyring_available: bool = False
        self._keyring_module = None
        self._keyring_error: str = ""

        # 缓存 {key: (value, timestamp)}
        self._cache: Dict[str, Tuple[str, float]] = {}
        self._cache_lock = threading.RLock()

        # 明文降级时使用的 QSettings
        self._plaintext_settings = QSettings("QingCao", "SecureStorage")

        # 初始化后端
        self._detect_backend()

        self._initialized = True

    # ========================================================
    # 后端检测
    # ========================================================
    def _detect_backend(self):
        """检测并初始化可用的后端"""
        # 1. 环境变量禁用
        if os.environ.get(ENV_DISABLE_KEYRING, "").lower() in ("1", "true", "yes"):
            self._backend = StorageBackend.DISABLED
            self._keyring_available = False
            print("[SecureStorage] 已通过环境变量禁用（测试模式）")
            return

        # 2. 环境变量强制明文
        if os.environ.get(ENV_FORCE_PLAINTEXT, "").lower() in ("1", "true", "yes"):
            self._backend = StorageBackend.PLAINTEXT
            self._keyring_available = False
            print("[SecureStorage] 已通过环境变量强制使用明文存储")
            return

        # 3. 尝试导入 keyring
        try:
            import keyring
            from keyring.errors import KeyringError

            # 测试一下能否读写（防止某些后端未配置）
            test_key = "_qingcao_secure_storage_test_"
            test_value = f"test_{int(time.time())}"
            try:
                keyring.set_password(KEYRING_SERVICE, test_key, test_value)
                result = keyring.get_password(KEYRING_SERVICE, test_key)
                keyring.delete_password(KEYRING_SERVICE, test_key)

                if result == test_value:
                    self._keyring_module = keyring
                    self._keyring_available = True
                    self._backend = StorageBackend.KEYRING
                    print(f"[SecureStorage] 已启用 keyring 后端: "
                          f"{keyring.get_keyring().__class__.__name__}")
                    return
            except KeyringError as e:
                self._keyring_error = str(e)
            except Exception as e:
                self._keyring_error = str(e)

        except ImportError as e:
            self._keyring_error = f"keyring 未安装: {e}"
        except Exception as e:
            self._keyring_error = str(e)

        # 4. 降级到明文
        self._backend = StorageBackend.PLAINTEXT
        self._keyring_available = False
        warning = (
            f"敏感信息将以明文存储（不推荐）。\n"
            f"原因: {self._keyring_error or '未知'}\n"
            f"建议: pip install keyring"
        )
        print(f"[SecureStorage] 降级到明文存储。{warning}")
        self.security_warning.emit(warning)

    # ========================================================
    # 属性
    # ========================================================
    @property
    def backend(self) -> str:
        """当前后端类型"""
        return self._backend

    @property
    def is_secure(self) -> bool:
        """是否使用安全后端（keyring）"""
        return self._backend == StorageBackend.KEYRING

    @property
    def backend_display(self) -> str:
        """后端的人类可读描述"""
        if self._backend == StorageBackend.KEYRING:
            name = "未知"
            try:
                if self._keyring_module:
                    name = self._keyring_module.get_keyring().__class__.__name__
            except Exception:
                pass
            return f"系统密钥环 ({name})"
        elif self._backend == StorageBackend.PLAINTEXT:
            return "明文存储（不安全）"
        else:
            return "已禁用"

    # ========================================================
    # 核心 API
    # ========================================================
    def save(self, key: str, value: str) -> bool:
        """
        保存敏感信息。

        参数:
            key: 键名（如 "ai_api_key"）
            value: 值（如 "sk-xxx"）

        返回:
            是否成功
        """
        if not key:
            return False

        if not value:
            # 空值视为删除
            return self.delete(key)

        try:
            if self._backend == StorageBackend.KEYRING:
                self._keyring_module.set_password(
                    KEYRING_SERVICE, key, value
                )
            elif self._backend == StorageBackend.PLAINTEXT:
                self._plaintext_settings.setValue(
                    PLAINTEXT_PREFIX + key, value
                )
                self._plaintext_settings.sync()
            else:
                return False

            # 更新缓存
            with self._cache_lock:
                self._cache[key] = (value, time.time())

            return True

        except Exception as e:
            print(f"[SecureStorage] 保存 {key} 失败: {e}")
            return False

    def load(self, key: str, default: str = "") -> str:
        """
        读取敏感信息。

        参数:
            key: 键名
            default: 默认值

        返回:
            存储的值或默认值
        """
        if not key:
            return default

        # 检查缓存
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached:
                value, timestamp = cached
                if time.time() - timestamp < CACHE_TTL:
                    return value
                else:
                    del self._cache[key]

        try:
            value = None

            if self._backend == StorageBackend.KEYRING:
                value = self._keyring_module.get_password(
                    KEYRING_SERVICE, key
                )
            elif self._backend == StorageBackend.PLAINTEXT:
                value = self._plaintext_settings.value(
                    PLAINTEXT_PREFIX + key, "", type=str
                )

            if value is None or value == "":
                return default

            # 更新缓存
            with self._cache_lock:
                self._cache[key] = (value, time.time())

            return value

        except Exception as e:
            print(f"[SecureStorage] 读取 {key} 失败: {e}")
            return default

    def delete(self, key: str) -> bool:
        """
        删除敏感信息。

        参数:
            key: 键名

        返回:
            是否成功
        """
        if not key:
            return False

        try:
            if self._backend == StorageBackend.KEYRING:
                try:
                    self._keyring_module.delete_password(
                        KEYRING_SERVICE, key
                    )
                except Exception:
                    # 键不存在也是正常的
                    pass
            elif self._backend == StorageBackend.PLAINTEXT:
                self._plaintext_settings.remove(PLAINTEXT_PREFIX + key)
                self._plaintext_settings.sync()

            # 清除缓存
            with self._cache_lock:
                self._cache.pop(key, None)

            return True

        except Exception as e:
            print(f"[SecureStorage] 删除 {key} 失败: {e}")
            return False

    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        return bool(self.load(key, ""))

    def clear_cache(self):
        """清空内存缓存"""
        with self._cache_lock:
            self._cache.clear()

    # ========================================================
    # 批量操作
    # ========================================================
    def save_many(self, items: Dict[str, str]) -> int:
        """批量保存，返回成功数量"""
        count = 0
        for key, value in items.items():
            if self.save(key, value):
                count += 1
        return count

    def load_many(self, keys: List[str]) -> Dict[str, str]:
        """批量读取"""
        return {key: self.load(key) for key in keys}

    # ========================================================
    # 迁移
    # ========================================================
    def migrate_from_settings(
        self,
        settings: QSettings,
        key: str,
        service: str = "QingCao",
        app: str = "AI",
        delete_source: bool = True,
    ) -> bool:
        """
        从 QSettings 明文迁移到安全存储。

        参数:
            settings: 源 QSettings（或 None 则使用默认）
            key: 待迁移的键名
            service: QSettings 的服务名（仅日志用）
            app: QSettings 的应用名（仅日志用）
            delete_source: 迁移后是否删除源（默认 True）

        返回:
            是否发生了迁移
        """
        try:
            if settings is None:
                settings = QSettings(service, app)

            plaintext = settings.value(key, "", type=str)
            if not plaintext:
                return False

            # 已存在安全存储中，跳过
            if self.exists(key):
                # 但仍清理明文源
                if delete_source:
                    settings.remove(key)
                    settings.sync()
                return False

            # 迁移
            if self.save(key, plaintext):
                if delete_source:
                    settings.remove(key)
                    settings.sync()
                print(f"[SecureStorage] 已迁移 {key} 从明文到 {self.backend}")
                self.migration_completed.emit(1)
                return True

        except Exception as e:
            print(f"[SecureStorage] 迁移 {key} 失败: {e}")

        return False

    def migrate_all_from_ai_settings(self) -> int:
        """
        迁移 AI 相关设置中的所有敏感信息。

        迁移项:
            - api_key

        返回:
            迁移的条目数
        """
        try:
            settings = QSettings("QingCao", "AI")
            count = 0

            if self.migrate_from_settings(
                settings, "api_key", "QingCao", "AI"
            ):
                count += 1

            return count
        except Exception as e:
            print(f"[SecureStorage] AI 迁移失败: {e}")
            return 0

    # ========================================================
    # 诊断
    # ========================================================
    def get_info(self) -> Dict[str, Any]:
        """获取存储信息摘要"""
        return {
            'backend': self._backend,
            'backend_display': self.backend_display,
            'is_secure': self.is_secure,
            'keyring_available': self._keyring_available,
            'keyring_error': self._keyring_error,
            'cache_size': len(self._cache),
            'service': KEYRING_SERVICE,
        }

    def dump(self) -> str:
        """导出信息"""
        info = self.get_info()
        lines = ["SecureStorage", "=" * 60]
        for k, v in info.items():
            lines.append(f"  {k:20s}: {v}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<SecureStorage backend={self._backend} "
                f"secure={self.is_secure}>")


# ============================================================
# 全局单例
# ============================================================
_storage_instance: Optional[SecureStorage] = None


def get_secure_storage() -> SecureStorage:
    """获取全局 SecureStorage 单例"""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = SecureStorage()
    return _storage_instance


# ============================================================
# 便捷函数
# ============================================================
def save_secret(key: str, value: str) -> bool:
    """保存敏感信息"""
    return get_secure_storage().save(key, value)


def load_secret(key: str, default: str = "") -> str:
    """读取敏感信息"""
    return get_secure_storage().load(key, default)


def delete_secret(key: str) -> bool:
    """删除敏感信息"""
    return get_secure_storage().delete(key)


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    print("=" * 60)
    print("SecureStorage 测试")
    print("=" * 60)

    storage = get_secure_storage()
    print()
    print(storage.dump())
    print()

    if not storage.is_secure:
        print("⚠ 当前使用明文后端，测试会污染 QSettings")
        print("  设置环境变量 QINGCAO_DISABLE_KEYRING=1 可跳过")
        response = input("是否继续? [y/N]: ")
        if response.lower() != 'y':
            sys.exit(0)

    # 测试 1: 保存/读取
    print("=== 测试 1: 保存/读取 ===")
    test_key = "_test_secure_storage_key_"
    test_value = "test_value_123"

    print(f"保存: {storage.save(test_key, test_value)}")
    print(f"读取: {storage.load(test_key)}")
    assert storage.load(test_key) == test_value

    print(f"exists: {storage.exists(test_key)}")
    assert storage.exists(test_key)

    # 测试 2: 缓存
    print()
    print("=== 测试 2: 缓存 ===")
    print(f"缓存大小: {len(storage._cache)}")

    # 测试 3: 删除
    print()
    print("=== 测试 3: 删除 ===")
    print(f"删除: {storage.delete(test_key)}")
    print(f"读取默认值: {storage.load(test_key, 'default')}")
    assert storage.load(test_key, "default") == "default"

    # 测试 4: 批量操作
    print()
    print("=== 测试 4: 批量 ===")
    batch = {
        "_test_a": "value_a",
        "_test_b": "value_b",
        "_test_c": "value_c",
    }
    saved = storage.save_many(batch)
    print(f"批量保存: {saved}/3")

    loaded = storage.load_many(["_test_a", "_test_b", "_test_c"])
    print(f"批量读取: {loaded}")

    # 清理
    for k in batch:
        storage.delete(k)

    print()
    print("=" * 60)
    print("✓ 所有测试通过")
    print("=" * 60)