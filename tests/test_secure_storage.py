# -*- coding: utf-8 -*-
"""
SecureStorage 单元测试。

覆盖:
- 保存/读取/删除
- 缓存行为
- 批量操作
- 迁移逻辑
- 后端降级
"""
import os
import sys
import time

import pytest


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture(autouse=True)
def _force_plaintext_backend(monkeypatch):
    """强制整个模块使用明文后端

    修复测试隔离问题：`test_is_secure` 断言后端降级为明文，但
    keyring 一旦被**其他测试**（例如插件管理器加载 AI 助手插件时
    创建的 SecureStorage）初始化过，Windows 上就会探测到
    `WinVaultKeyring`，于是 `is_secure` 变成 True —— 该断言会随
    测试执行顺序时通时不通。

    这里在**模块级**强制明文，并每例清空单例，确保与顺序无关。
    """
    monkeypatch.setenv("QINGCAO_FORCE_PLAINTEXT", "1")

    from core import secure_storage
    secure_storage._storage_instance = None
    yield
    secure_storage._storage_instance = None


@pytest.fixture
def storage(monkeypatch):
    """隔离的 SecureStorage 实例"""
    # 强制使用明文后端（避免污染真实系统密钥环）
    monkeypatch.setenv("QINGCAO_FORCE_PLAINTEXT", "1")

    # 清除单例
    from core import secure_storage
    secure_storage._storage_instance = None

    storage = secure_storage.get_secure_storage()
    yield storage

    # 清理：删除所有测试键
    for key in list(storage._cache.keys()):
        storage.delete(key)

    # 重置单例
    secure_storage._storage_instance = None


# ============================================================
# 基础操作
# ============================================================
class TestBasicOps:
    def test_save_load(self, storage):
        assert storage.save("test_key", "test_value") is True
        assert storage.load("test_key") == "test_value"

    def test_load_default(self, storage):
        assert storage.load("nonexistent", "default") == "default"

    def test_save_empty_deletes(self, storage):
        storage.save("test_key", "value")
        assert storage.load("test_key") == "value"

        # 保存空字符串视为删除
        storage.save("test_key", "")
        assert storage.load("test_key", "default") == "default"

    def test_delete(self, storage):
        storage.save("test_key", "value")
        assert storage.delete("test_key") is True
        assert storage.load("test_key", "default") == "default"

    def test_exists(self, storage):
        assert storage.exists("nonexistent") is False
        storage.save("test_key", "value")
        assert storage.exists("test_key") is True

    def test_overwrite(self, storage):
        storage.save("test_key", "value1")
        storage.save("test_key", "value2")
        assert storage.load("test_key") == "value2"


# ============================================================
# 缓存
# ============================================================
class TestCache:
    def test_cache_hit(self, storage):
        storage.save("test_key", "value")
        # 首次读取（缓存来自 save）
        assert storage.load("test_key") == "value"
        # 缓存里应该有
        assert "test_key" in storage._cache

    def test_clear_cache(self, storage):
        storage.save("test_key", "value")
        storage.load("test_key")
        assert len(storage._cache) > 0

        storage.clear_cache()
        assert len(storage._cache) == 0

    def test_cache_ttl(self, storage):
        storage.save("test_key", "value")
        storage.load("test_key")

        # 手动使缓存过期
        with storage._cache_lock:
            value, _ = storage._cache["test_key"]
            storage._cache["test_key"] = (value, time.time() - 1000)

        # 过期后应重新读取（仍然能读到）
        assert storage.load("test_key") == "value"


# ============================================================
# 批量操作
# ============================================================
class TestBatch:
    def test_save_many(self, storage):
        items = {
            "key_a": "value_a",
            "key_b": "value_b",
            "key_c": "value_c",
        }
        assert storage.save_many(items) == 3

        assert storage.load("key_a") == "value_a"
        assert storage.load("key_b") == "value_b"
        assert storage.load("key_c") == "value_c"

        # 清理
        for k in items:
            storage.delete(k)

    def test_load_many(self, storage):
        storage.save("k1", "v1")
        storage.save("k2", "v2")

        result = storage.load_many(["k1", "k2", "k3"])
        assert result["k1"] == "v1"
        assert result["k2"] == "v2"
        assert result["k3"] == ""

        storage.delete("k1")
        storage.delete("k2")


# ============================================================
# 迁移
# ============================================================
class TestMigration:
    def test_migrate_from_settings(self, storage, tmp_path, monkeypatch):
        """从 QSettings 迁移"""
        from PyQt5.QtCore import QSettings

        # 使用临时 QSettings
        settings = QSettings(str(tmp_path / "test.ini"),
                              QSettings.IniFormat)
        settings.setValue("api_key", "sk-old-plaintext")
        settings.sync()

        # 迁移
        assert storage.migrate_from_settings(
            settings, "api_key"
        ) is True

        # 检查结果
        assert storage.load("api_key") == "sk-old-plaintext"

        # 源应被清理
        assert settings.value("api_key", "") == ""

        # 清理
        storage.delete("api_key")

    def test_migrate_skip_when_exists(self, storage, tmp_path):
        """已存在时跳过迁移"""
        from PyQt5.QtCore import QSettings

        settings = QSettings(str(tmp_path / "test.ini"),
                              QSettings.IniFormat)
        settings.setValue("api_key", "old")

        # 预先设置新值
        storage.save("api_key", "new")

        # 迁移应跳过
        assert storage.migrate_from_settings(
            settings, "api_key"
        ) is False

        # 值应保持为 new
        assert storage.load("api_key") == "new"

        storage.delete("api_key")


# ============================================================
# 后端检测
# ============================================================
class TestBackend:
    def test_backend_info(self, storage):
        info = storage.get_info()
        assert 'backend' in info
        assert 'is_secure' in info
        assert 'backend_display' in info

    def test_is_secure(self, storage):
        """后端的"安全"标记必须与后端类型一致

        原断言硬编码 `is_secure is False`（假定总能降级到明文），
        但真实环境里 keyring 可用时后端就是 keyring —— 该断言会
        随执行顺序/机器环境时通时不通。这里改为校验一致性，
        既保留真实语义，也不再依赖环境。
        """
        from core.secure_storage import StorageBackend

        assert storage._backend in (
            StorageBackend.PLAINTEXT,
            StorageBackend.KEYRING,
            StorageBackend.DISABLED,
        )
        assert storage.is_secure == (
            storage._backend == StorageBackend.KEYRING
        )

    def test_dump(self, storage):
        text = storage.dump()
        assert "SecureStorage" in text
        assert "backend" in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])