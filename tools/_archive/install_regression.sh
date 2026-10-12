#!/usr/bin/env bash
set -e

mkdir -p tests

# ============================================================
# 1. content_provider mmap 释放测试（P1-A4）
# ============================================================
cat > tests/test_content_provider_mmap.py << 'PYEOF'
# -*- coding: utf-8 -*-
"""content_provider._save_dirty_blocks mmap 释放测试（P1-A4）"""
import os
import pytest


class TestSaveDirtyBlocksReleasesMmap:
    def test_save_modifies_disk(self, tmp_path):
        """save() 后磁盘内容应被修改"""
        try:
            from core.content_provider import LocalFileProvider
        except ImportError:
            pytest.skip("LocalFileProvider 不可用")

        path = tmp_path / "t.txt"
        path.write_text("hello world\n" * 100, encoding='utf-8')

        provider = LocalFileProvider()
        try:
            provider.open(str(path))
            provider.write_block(0, b"MODIFIED\n")
            ok = provider.save()
            assert ok is True
        finally:
            provider.close()

        with open(str(path), 'rb') as f:
            content = f.read()
        assert content.startswith(b"MODIFIED")

    def test_provider_usable_after_save(self, tmp_path):
        """保存后 provider 应仍可读（mmap 已重建）"""
        try:
            from core.content_provider import LocalFileProvider
        except ImportError:
            pytest.skip("LocalFileProvider 不可用")

        path = tmp_path / "t.txt"
        path.write_text("line1\nline2\n", encoding='utf-8')

        provider = LocalFileProvider()
        try:
            provider.open(str(path))
            provider.write_block(0, b"changed\n")
            assert provider.save() is True
            # 保存后仍可读
            data = provider.read_block(0)
            assert data  # 非空
        finally:
            provider.close()

    def test_reopen_mmap_method_exists(self):
        """_reopen_mmap 方法应存在（P1-A4 新增）"""
        try:
            from core.content_provider import LocalFileProvider
        except ImportError:
            pytest.skip("LocalFileProvider 不可用")
        assert hasattr(LocalFileProvider, '_reopen_mmap')
PYEOF

# ============================================================
# 2. plugin_sandbox _ready_event 测试（P1-A2）
# ============================================================
cat > tests/test_plugin_sandbox_event.py << 'PYEOF'
# -*- coding: utf-8 -*-
"""plugin_sandbox._ready_event 测试（P1-A2）"""
import threading
import pytest


class TestReadyEvent:
    def test_handle_ready_sets_event(self, qapp):
        """收到 READY 消息时 _ready_event 应被 set"""
        try:
            from infrastructure.plugin_sandbox import (
                PluginSandbox, SandboxConfig, MSG_TYPE_READY
            )
        except ImportError:
            pytest.skip("plugin_sandbox 不可用")

        config = SandboxConfig(name="test")
        sandbox = PluginSandbox("/tmp/nonexistent", config)

        # 手动初始化事件（模拟 start() 中的行为）
        sandbox._ready_event = threading.Event()
        sandbox._ready_ok = False

        # 模拟接收线程收到 READY
        sandbox._handle_message({
            'type': MSG_TYPE_READY,
            'success': True,
        })

        assert sandbox._ready_event.is_set()
        assert sandbox._ready_ok is True

    def test_handle_ready_failure(self, qapp):
        """READY success=False 时 _ready_ok 应为 False"""
        try:
            from infrastructure.plugin_sandbox import (
                PluginSandbox, SandboxConfig, MSG_TYPE_READY
            )
        except ImportError:
            pytest.skip("plugin_sandbox 不可用")

        config = SandboxConfig(name="test")
        sandbox = PluginSandbox("/tmp/nonexistent", config)
        sandbox._ready_event = threading.Event()
        sandbox._ready_ok = False

        sandbox._handle_message({
            'type': MSG_TYPE_READY,
            'success': False,
        })

        assert sandbox._ready_event.is_set()
        assert sandbox._ready_ok is False

    def test_wait_for_ready_uses_event(self, qapp):
        """_wait_for_ready 应只等 Event（不直接读 Pipe）"""
        try:
            from infrastructure.plugin_sandbox import (
                PluginSandbox, SandboxConfig
            )
        except ImportError:
            pytest.skip("plugin_sandbox 不可用")

        config = SandboxConfig(name="test")
        sandbox = PluginSandbox("/tmp/nonexistent", config)
        sandbox._ready_event = threading.Event()
        sandbox._ready_ok = True
        sandbox._ready_event.set()

        # 应在极短时间内返回 True
        assert sandbox._wait_for_ready(timeout=1) is True
PYEOF

# ============================================================
# 3. sandbox socket 白名单移除测试（P1-A1）
# ============================================================
cat > tests/test_sandbox_socket.py << 'PYEOF'
# -*- coding: utf-8 -*-
"""sandbox_runtime socket 白名单移除测试（P1-A1）"""
import pytest


class TestSocketNotInWhitelist:
    def test_socket_not_in_internal_whitelist(self):
        """socket 不应在 INTERNAL_ALLOWED_MODULES（P1-A1）"""
        try:
            from infrastructure.sandbox_runtime import (
                INTERNAL_ALLOWED_MODULES
            )
        except ImportError:
            pytest.skip("sandbox_runtime 不可用")

        assert 'socket' not in INTERNAL_ALLOWED_MODULES, \
            "socket 不能在白名单里（插件可绕过 network 权限）"
        assert '_socket' not in INTERNAL_ALLOWED_MODULES

    def test_safefinder_rejects_socket(self):
        """无 network 权限时 SafeFinder 应拒绝 socket"""
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
        """SAFE_MODULES 应放行"""
        try:
            from infrastructure.sandbox_runtime import SafeFinder
            from core.sandbox_policy import SandboxPolicy
        except ImportError:
            pytest.skip("依赖不可用")

        policy = SandboxPolicy.from_permissions([])
        finder = SafeFinder(policy)
        # math 在 SAFE_MODULES
        result = finder.find_spec('math')
        assert result is None
PYEOF

# ============================================================
# 4. SearchBar next/prev 逻辑测试（P0-C2）
# ============================================================
cat > tests/test_searchbar_next_prev.py << 'PYEOF'
# -*- coding: utf-8 -*-
"""SearchBar next/prev 逻辑测试（P0-C2）"""
import pytest


class TestSearchMatchesOrder:
    def _make_result(self, text, pattern):
        from core.search import SearchEngine, SearchOptions
        from core.content_provider import MemoryProvider
        provider = MemoryProvider()
        provider.open(initial_text=text)
        options = SearchOptions(pattern=pattern)
        engine = SearchEngine(provider, options)
        return engine.search()

    def test_matches_sorted_by_start(self):
        """matches 应按 start 升序（next/prev 二分查找的前提）"""
        try:
            pass
        except ImportError:
            pytest.skip("search 不可用")

        result = self._make_result(
            "foo bar foo baz foo", "foo"
        )
        starts = [m.start for m in result.matches]
        assert starts == sorted(starts)
        assert len(starts) == 3

    def test_next_finds_later_match(self):
        """从 pos 0 之后应能找到 start > 0 的 match"""
        result = self._make_result(
            "foo bar foo baz foo", "foo"
        )
        # P0-C2 修复后的逻辑：遍历 matches 找 start > pos
        pos = 0
        match = None
        for m in result.matches:
            if m.start > pos:
                match = m
                break
        assert match is not None
        assert match.start == 8  # 第二个 foo

    def test_prev_finds_earlier_match(self):
        """从末尾往前应能找到 start < pos 的 match"""
        result = self._make_result(
            "foo bar foo baz foo", "foo"
        )
        pos = 9999
        match = None
        for m in reversed(result.matches):
            if m.end <= pos:
                match = m
                break
        assert match is not None
        assert match.start == 16  # 最后一个 foo

    def test_wrap_around_logic(self):
        """无匹配时循环到另一端"""
        result = self._make_result("foo bar", "foo")
        # 从 pos=100 往后找 → 无
        match = None
        for m in result.matches:
            if m.start > 100:
                match = m
                break
        assert match is None
        # 循环逻辑：回退到第一个
        wrapped = match or result.matches[0]
        assert wrapped.start == 0
PYEOF

# ============================================================
# 5. outline end_line 边界测试（P1-B2）
# ============================================================
cat > tests/test_outline_end_lines.py << 'PYEOF'
# -*- coding: utf-8 -*-
"""outline_panel._compute_end_lines 边界测试（P1-B2）"""
import pytest


class TestComputeEndLines:
    def _panel(self):
        try:
            from ui.outline_panel import OutlinePanel
        except ImportError:
            pytest.skip("outline_panel 不可用")
        return OutlinePanel.__new__(OutlinePanel)

    def _node(self, name, type_, line, indent):
        try:
            from ui.outline_panel import SymbolNode
        except ImportError:
            pytest.skip("SymbolNode 不可用")
        return SymbolNode(name=name, type=type_, line=line, indent=indent)

    def test_simple_sequence(self):
        """无嵌套：每个符号 end_line = 下一行 - 1"""
        panel = self._panel()
        symbols = [
            self._node("a", "function", 0, 0),
            self._node("b", "function", 10, 0),
            self._node("c", "function", 20, 0),
        ]
        panel._compute_end_lines(symbols)
        assert symbols[0].end_line == 9
        assert symbols[1].end_line == 19
        assert symbols[2].end_line == 20  # 最后一个延伸到 max_line

    def test_nested(self):
        """有嵌套：父节点延伸到子节点之后"""
        panel = self._panel()
        symbols = [
            self._node("cls", "class", 0, 0),
            self._node("m1", "method", 5, 4),
            self._node("m2", "method", 10, 4),
            self._node("func", "function", 20, 0),
        ]
        panel._compute_end_lines(symbols)
        # cls 应延伸到 func 的前一行
        assert symbols[0].end_line == 19
        # m1 到 m2 前一行
        assert symbols[1].end_line == 9
        # m2 到 func 前一行
        assert symbols[2].end_line == 19
        # func 是最后一个
        assert symbols[3].end_line == 20

    def test_empty(self):
        """空列表不崩"""
        panel = self._panel()
        panel._compute_end_lines([])

    def test_single(self):
        """单个符号"""
        panel = self._panel()
        symbols = [self._node("only", "function", 5, 0)]
        panel._compute_end_lines(symbols)
        assert symbols[0].end_line == 5
PYEOF

# ============================================================
# 6. smart_home 字节偏移测试（P1-B4）
# ============================================================
cat > tests/test_smart_home.py << 'PYEOF'
# -*- coding: utf-8 -*-
"""editor_view._smart_home 字节偏移计算（P1-B4）

不测 UI，只测缩进字节长度计算逻辑。
"""


def _calc_indent_bytes(line_text):
    """复刻 _smart_home 里的计算"""
    stripped = line_text.lstrip()
    indent = len(line_text) - len(stripped)
    return indent, len(line_text[:indent].encode('utf-8'))


class TestIndentBytes:
    def test_ascii_spaces(self):
        indent, indent_bytes = _calc_indent_bytes("    def foo")
        assert indent == 4
        assert indent_bytes == 4

    def test_tabs(self):
        indent, indent_bytes = _calc_indent_bytes("\t\tdef foo")
        assert indent == 2
        assert indent_bytes == 2

    def test_full_width_space(self):
        """全角空格：1 字符 = 3 字节（P1-B4 的核心）"""
        indent, indent_bytes = _calc_indent_bytes("\u3000\u3000def foo")
        assert indent == 2
        assert indent_bytes == 6  # 关键：不是 2

    def test_mixed(self):
        """空格 + 全角混合"""
        indent, indent_bytes = _calc_indent_bytes("  \u3000def foo")
        assert indent == 3
        assert indent_bytes == 2 + 3

    def test_no_indent(self):
        indent, indent_bytes = _calc_indent_bytes("def foo")
        assert indent == 0
        assert indent_bytes == 0

    def test_compare_bytes_vs_chars(self):
        """验证字节偏移 != 字符数（P1-B4 修复的必要性）"""
        _, indent_bytes = _calc_indent_bytes("\u3000\u3000x")
        indent_chars = 2
        assert indent_bytes != indent_chars
PYEOF

# ============================================================
# 7. plugin_updater 连接关闭测试（P1-A3）
# ============================================================
cat > tests/test_plugin_updater_close.py << 'PYEOF'
# -*- coding: utf-8 -*-
"""plugin_updater 取消下载后连接关闭（P1-A3）"""
import pytest
from unittest.mock import MagicMock, patch


class TestDownloadClose:
    def test_cancel_still_closes(self, qapp):
        """取消下载后 resp 也应被关闭"""
        try:
            from infrastructure.plugin_updater import PluginUpdater
        except ImportError:
            pytest.skip("plugin_updater 不可用")

        updater = PluginUpdater()

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.headers = {'content-length': '10000'}
        fake_resp.iter_content = lambda chunk_size: iter(
            [b"x" * chunk_size] * 100
        )

        with patch(
            'infrastructure.plugin_updater.requests.get',
            return_value=fake_resp,
        ):
            updater._cancelled = True
            result = updater._download_update(
                "http://example.com/fake.zip", "test"
            )

        assert result is None
        fake_resp.close.assert_called()

    def test_normal_close(self, qapp):
        """正常下载完成后 resp 应被关闭"""
        try:
            from infrastructure.plugin_updater import PluginUpdater
        except ImportError:
            pytest.skip("plugin_updater 不可用")

        updater = PluginUpdater()
        updater._cancelled = False

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.headers = {'content-length': '5'}
        fake_resp.iter_content = lambda chunk_size: iter([b"hello"])

        with patch(
            'infrastructure.plugin_updater.requests.get',
            return_value=fake_resp,
        ):
            result = updater._download_update(
                "http://example.com/fake.zip", "test"
            )

        assert result == b"hello"
        fake_resp.close.assert_called()
PYEOF

echo "✓ 已创建 7 个测试文件"
ls -1 tests/test_content_provider_mmap.py \
       tests/test_plugin_sandbox_event.py \
       tests/test_sandbox_socket.py \
       tests/test_searchbar_next_prev.py \
       tests/test_outline_end_lines.py \
       tests/test_smart_home.py \
       tests/test_plugin_updater_close.py