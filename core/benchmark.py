# -*- coding: utf-8 -*-
"""性能基准测试"""
import os
import tempfile
import time
from typing import Any, Callable, Dict


class Benchmark:
    """基准测试"""

    def __init__(self):
        self.results = {}

    def run_all(self) -> Dict[str, Any]:
        """运行所有基准"""
        self.results = {}

        self.results['open_file'] = self._bench_open_file()
        self.results['search'] = self._bench_search()
        self.results['commands'] = self._bench_commands()
        self.results['undo_redo'] = self._bench_undo_redo()
        self.results['event_bus'] = self._bench_event_bus()

        return self.results

    def _bench_open_file(self, size_kb=100) -> Dict[str, Any]:
        """打开文件性能"""
        try:
            from core.content_provider import LocalFileProvider

            # 创建临时文件
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.txt', delete=False,
                encoding='utf-8'
            ) as f:
                f.write("line content\n" * (size_kb * 30))
                path = f.name

            start = time.time()
            provider = LocalFileProvider()
            provider.open(path)
            text = provider.read_text()
            elapsed = time.time() - start

            provider.close()
            os.unlink(path)

            return {
                'size_kb': size_kb,
                'elapsed_ms': round(elapsed * 1000, 2),
                'chars': len(text),
                'throughput_mbps': round(
                    len(text) / elapsed / 1024 / 1024, 2
                ) if elapsed > 0 else 0,
            }
        except Exception as e:
            return {'error': str(e)}

    def _bench_search(self) -> Dict[str, Any]:
        """搜索性能"""
        try:
            from core.content_provider import MemoryProvider
            from core.search import SearchEngine, SearchOptions

            text = "hello world\n" * 10000
            provider = MemoryProvider()
            provider.open(initial_text=text)

            opts = SearchOptions(pattern="hello")
            engine = SearchEngine(provider, opts)

            start = time.time()
            result = engine.search()
            elapsed = time.time() - start

            return {
                'matches': result.count,
                'elapsed_ms': round(elapsed * 1000, 2),
                'matches_per_sec': round(
                    result.count / elapsed, 0
                ) if elapsed > 0 else 0,
            }
        except Exception as e:
            return {'error': str(e)}

    def _bench_commands(self) -> Dict[str, Any]:
        """命令操作性能"""
        try:
            from core.commands import CommandSerializer, DeleteCmd, InsertCmd

            cmds = []
            for i in range(1000):
                cmds.append(InsertCmd(i * 10, "hello "))

            # 序列化
            start = time.time()
            data = CommandSerializer.serialize(cmds)
            elapsed1 = time.time() - start

            # 反序列化
            start = time.time()
            restored = CommandSerializer.deserialize(data)
            elapsed2 = time.time() - start

            return {
                'count': 1000,
                'serialize_ms': round(elapsed1 * 1000, 2),
                'deserialize_ms': round(elapsed2 * 1000, 2),
                'restored': len(restored),
            }
        except Exception as e:
            return {'error': str(e)}

    def _bench_undo_redo(self) -> Dict[str, Any]:
        """撤销/重做性能"""
        try:
            from core.commands import InsertCmd
            from core.undo import UndoManager

            mgr = UndoManager()

            # 记录 1000 个命令
            start = time.time()
            for i in range(1000):
                mgr.record(InsertCmd(i, "x"))
            elapsed_record = time.time() - start

            # 撤销 1000 次
            start = time.time()
            for _ in range(1000):
                mgr.undo()
            elapsed_undo = time.time() - start

            # 重做 1000 次
            start = time.time()
            for _ in range(1000):
                mgr.redo()
            elapsed_redo = time.time() - start

            return {
                'record_1000_ms': round(elapsed_record * 1000, 2),
                'undo_1000_ms': round(elapsed_undo * 1000, 2),
                'redo_1000_ms': round(elapsed_redo * 1000, 2),
            }
        except Exception as e:
            return {'error': str(e)}

    def _bench_event_bus(self) -> Dict[str, Any]:
        """事件总线性能"""
        try:
            from PyQt5.QtWidgets import QApplication
            if not QApplication.instance():
                app = QApplication([])

            from app.event_bus import EventBus, StatusMessageEvent
            bus = EventBus()

            received = []
            bus.status_message.connect(
                lambda e: received.append(e)
            )

            start = time.time()
            for i in range(10000):
                bus.emit_event(StatusMessageEvent(
                    message="test %d" % i
                ))
            elapsed = time.time() - start

            return {
                'events': 10000,
                'received': len(received),
                'elapsed_ms': round(elapsed * 1000, 2),
                'events_per_sec': round(
                    10000 / elapsed, 0
                ) if elapsed > 0 else 0,
            }
        except Exception as e:
            return {'error': str(e)}

    def get_report(self) -> str:
        """生成报告"""
        lines = ["性能基准测试报告", "=" * 60, ""]
        for name, result in self.results.items():
            lines.append("【%s】" % name)
            if 'error' in result:
                lines.append("  错误: %s" % result['error'])
            else:
                for k, v in result.items():
                    lines.append("  %s: %s" % (k, v))
            lines.append("")
        return "\n".join(lines)