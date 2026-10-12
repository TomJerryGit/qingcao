# -*- coding: utf-8 -*-
"""
端到端（E2E）测试。

覆盖:
- 打开文件 → 编辑 → 保存 → 重新打开
- 多文件标签管理
- 事件总线联动
- 搜索/替换
"""

import os
import sys
import time

import pytest


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================
# 编辑器核心流程
# ============================================================
class TestEditorFlow:
    """测试编辑器核心流程"""

    def test_open_edit_save_reopen(self, qapp, tmp_text_file):
        """打开 → 编辑 → 保存 → 重新打开"""
        from core.document import Document

        # 1. 打开
        doc = Document()
        assert doc.open(tmp_text_file)

        original = doc.get_text()
        assert "line 1" in original

        # 2. 编辑（模拟：直接替换文本）
        new_text = original + "new line\n"
        doc.set_text(new_text)
        assert doc.is_modified

        # 3. 保存
        assert doc.save()
        assert not doc.is_modified

        # 4. 关闭并重新打开
        doc.close()

        doc2 = Document()
        assert doc2.open(tmp_text_file)
        reopened = doc2.get_text()
        assert "new line" in reopened
        doc2.close()

    def test_multiple_documents(self, qapp, tmp_path):
        """多文档管理"""
        from core.document import DocumentModel

        # 创建 3 个文件
        files = []
        for i in range(3):
            p = tmp_path / f"file{i}.txt"
            p.write_text(f"content {i}\n", encoding="utf-8")
            files.append(str(p))

        model = DocumentModel()
        try:
            for f in files:
                doc = model.open_document(f)
                assert doc is not None

            assert model.count() == 3
            assert len(model.get_open_files()) == 3

        finally:
            model.close_all()
            assert model.count() == 0


# ============================================================
# 事件总线
# ============================================================
class TestEventBus:
    """测试事件总线"""

    def test_emit_and_receive(self, qapp):
        from app.event_bus import EventBus, StatusMessageEvent

        bus = EventBus(debug=False)
        received = []

        bus.status_message.connect(lambda e: received.append(e))

        event = StatusMessageEvent(message="test", level="info")
        bus.emit_event(event)

        assert len(received) == 1
        assert received[0].message == "test"

    def test_event_history(self, qapp):
        from app.event_bus import EventBus, StatusMessageEvent

        bus = EventBus(debug=False)
        for i in range(5):
            bus.emit_event(StatusMessageEvent(message=f"msg{i}"))

        history = bus.history.get_all()
        assert len(history) == 5

    def test_pause_resume(self, qapp):
        from app.event_bus import EventBus, StatusMessageEvent

        bus = EventBus(debug=False)
        received = []
        bus.status_message.connect(lambda e: received.append(e))

        bus.pause()
        bus.emit_event(StatusMessageEvent(message="paused"))
        assert len(received) == 0

        bus.resume()
        assert len(received) == 1


# ============================================================
# 搜索
# ============================================================
class TestSearch:
    """测试搜索"""

    def test_basic_search(self, qapp):
        from core.content_provider import MemoryProvider
        from core.search import SearchEngine, SearchOptions

        provider = MemoryProvider()
        provider.open(initial_text="hello world\nhello again\n")

        options = SearchOptions(pattern="hello")
        engine = SearchEngine(provider, options)
        result = engine.search()

        assert result.count == 2

    def test_regex_search(self, qapp):
        from core.content_provider import MemoryProvider
        from core.search import SearchEngine, SearchOptions

        provider = MemoryProvider()
        provider.open(initial_text="abc123\ndef456\n")

        options = SearchOptions(pattern=r"\d+", is_regex=True)
        engine = SearchEngine(provider, options)
        result = engine.search()

        assert result.count == 2

    def test_case_insensitive(self, qapp):
        from core.content_provider import MemoryProvider
        from core.search import SearchEngine, SearchOptions

        provider = MemoryProvider()
        provider.open(initial_text="Hello HELLO hello\n")

        options = SearchOptions(pattern="hello", case_sensitive=False)
        engine = SearchEngine(provider, options)
        result = engine.search()

        assert result.count == 3


# ============================================================
# 命令系统
# ============================================================
class TestCommands:
    """测试命令系统"""

    def test_serialize_deserialize(self, qapp):
        from core.commands import CommandSerializer, DeleteCmd, InsertCmd, ReplaceCmd

        cmds = [
            InsertCmd(0, "hello"),
            DeleteCmd(5, 3, b"abc"),
            ReplaceCmd(10, 5, "old", "new"),
        ]

        # 序列化
        data = CommandSerializer.serialize(cmds)
        assert data['count'] == 3

        # 反序列化
        restored = CommandSerializer.deserialize(data)
        assert len(restored) == 3

    def test_command_merge(self, qapp):
        from core.commands import InsertCmd, merge_commands

        c1 = InsertCmd(0, "a")
        c2 = InsertCmd(1, "b")
        c2.timestamp = c1.timestamp + 0.01  # 10ms 内

        merged = merge_commands([c1, c2])
        assert len(merged) == 1
        assert merged[0].text == "ab"


# ============================================================
# 偏好设置
# ============================================================
class TestPreferences:
    """测试偏好设置"""

    def test_set_get(self, qapp, preferences):
        if preferences is None:
            pytest.skip("Preferences 不可用")

        preferences.set("tab_width", 2)
        assert preferences.get("tab_width") == 2

    def test_default_value(self, qapp, preferences):
        if preferences is None:
            pytest.skip("Preferences 不可用")

        # 未设置的值返回默认
        val = preferences.get("nonexistent_key_xyz", "default")
        assert val == "default"

    def test_reset_to_defaults(self, qapp, preferences):
        if preferences is None:
            pytest.skip("Preferences 不可用")

        preferences.set("tab_width", 2)
        preferences.reset_to_defaults("tab_")
        # 恢复默认（通常是 4）
        assert preferences.get("tab_width") == 4


# ============================================================
# 动作管理
# ============================================================
class TestActions:
    """测试动作管理"""

    def test_register_and_get(self, qapp, action_manager):
        if action_manager is None:
            pytest.skip("ActionManager 不可用")

        from PyQt5.QtWidgets import QAction

        action = QAction("Test", None)
        action_manager.register("test.action", action, "Ctrl+T")

        assert action_manager.exists("test.action")
        assert action_manager.get("test.action") is action

    def test_shortcut_conflict(self, qapp, action_manager):
        if action_manager is None:
            pytest.skip("ActionManager 不可用")

        from PyQt5.QtWidgets import QAction

        a1 = QAction("A1", None)
        a2 = QAction("A2", None)
        action_manager.register("act.1", a1, "Ctrl+K")
        action_manager.register("act.2", a2, "Ctrl+K")

        conflicts = action_manager.find_conflicts()
        assert "Ctrl+K" in conflicts


# ============================================================
# 完整工作流
# ============================================================
class TestFullWorkflow:
    """完整工作流"""

    def test_open_multiple_save_close(self, qapp, tmp_path):
        """打开多个文件，编辑，保存，关闭"""
        from core.document import DocumentModel

        # 准备文件
        files = []
        for i in range(3):
            p = tmp_path / f"workflow{i}.txt"
            p.write_text(f"content {i}\n", encoding="utf-8")
            files.append(str(p))

        model = DocumentModel()
        try:
            # 打开
            for f in files:
                model.open_document(f)

            # 编辑所有
            for doc in model.get_all_documents():
                doc.set_text(doc.get_text() + "edited\n")
                assert doc.is_modified

            # 保存所有
            success, failed = model.save_all()
            assert success == 3
            assert failed == 0

            # 验证无修改
            assert len(model.get_modified_documents()) == 0

        finally:
            model.close_all()

        # 验证磁盘上的内容
        for f in files:
            with open(f, encoding='utf-8') as fp:
                content = fp.read()
            assert "edited" in content