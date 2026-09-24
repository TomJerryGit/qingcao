"""sandbox_runtime socket 白名单移除测试（P1-A1）"""
import pytest


class TestSocketRejected:
    def test_socket_not_in_internal_whitelist(self):
        """socket 不应在 INTERNAL_ALLOWED_MODULES"""
        try:
            from infrastructure.sandbox_runtime import (
                INTERNAL_ALLOWED_MODULES
            )
        except ImportError:
            pytest.skip("sandbox_runtime 不可用")

        assert 'socket' not in INTERNAL_ALLOWED_MODULES
        assert '_socket' not in INTERNAL_ALLOWED_MODULES

    def test_safefinder_rejects_socket(self):
        """SafeFinder 应拒绝无 network 权限的 socket 导入"""
        try:
            from infrastructure.sandbox_runtime import SafeFinder
            from core.sandbox_policy import SandboxPolicy
        except ImportError:
            pytest.skip("依赖不可用")

        policy = SandboxPolicy.from_permissions([])  # 无权限
        finder = SafeFinder(policy)

        with pytest.raises(ImportError):
            finder.find_spec('socket')

    def test_safefinder_allows_safe_module(self):
        """SafeFinder 应放行 SAFE_MODULES"""
        try:
            from infrastructure.sandbox_runtime import SafeFinder
            from core.sandbox_policy import SandboxPolicy
        except ImportError:
            pytest.skip("依赖不可用")

        policy = SandboxPolicy.from_permissions([])
        finder = SafeFinder(policy)
        # math 在 SAFE_MODULES 里
        result = finder.find_spec('math')
        assert result is None  # None 表示让后续 Finder 处理