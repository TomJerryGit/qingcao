from core.macro_common import *  # noqa: F401,F403
from core.macro_recorder import MacroRecorder  # noqa: E402,F401


# ruff: noqa: F401, F403, F405


class MacroManager(QObject):
    """
    宏管理器。

    管理多个宏，提供：
    - 宏列表
    - 宏的增删改查
    - 宏集合保存/加载
    - 快捷键绑定
    - 导入/导出

    信号:
        macro_added(str): 宏添加（名称）
        macro_removed(str): 宏移除（名称）
        macro_updated(str): 宏更新（名称）
        macros_changed(): 宏列表变更
    """

    macro_added = pyqtSignal(str)
    macro_removed = pyqtSignal(str)
    macro_updated = pyqtSignal(str)
    macros_changed = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

        # 宏字典：名称 -> Macro
        self._macros: Dict[str, Macro] = {}

        # 快捷键映射：快捷键 -> 宏名称
        self._shortcuts: Dict[str, str] = {}

    # --------------------------------------------------------
    # 增删改查
    # --------------------------------------------------------
    def add(self, macro: Macro, overwrite: bool = False) -> bool:
        """
        添加宏。

        参数:
            macro: 宏对象
            overwrite: 同名时是否覆盖

        返回:
            是否成功
        """
        if not macro.name:
            return False

        if macro.name in self._macros and not overwrite:
            return False

        self._macros[macro.name] = macro

        # 绑定快捷键
        if macro.shortcut:
            self._shortcuts[macro.shortcut] = macro.name

        self.macro_added.emit(macro.name)
        self.macros_changed.emit()
        return True

    def remove(self, name: str) -> bool:
        """移除宏"""
        if name not in self._macros:
            return False

        macro = self._macros.pop(name)

        # 移除快捷键
        if macro.shortcut and self._shortcuts.get(macro.shortcut) == name:
            del self._shortcuts[macro.shortcut]

        self.macro_removed.emit(name)
        self.macros_changed.emit()
        return True

    def get(self, name: str) -> Optional[Macro]:
        """获取宏"""
        return self._macros.get(name)

    def has(self, name: str) -> bool:
        """检查宏是否存在"""
        return name in self._macros

    def rename(self, old_name: str, new_name: str) -> bool:
        """重命名宏"""
        if old_name not in self._macros:
            return False
        if new_name in self._macros:
            return False

        macro = self._macros.pop(old_name)
        macro.name = new_name
        self._macros[new_name] = macro

        # 更新快捷键映射
        for shortcut, name in list(self._shortcuts.items()):
            if name == old_name:
                self._shortcuts[shortcut] = new_name

        self.macro_updated.emit(new_name)
        self.macros_changed.emit()
        return True

    def list_names(self) -> List[str]:
        """列出所有宏名称"""
        return sorted(self._macros.keys())

    def list_macros(self) -> List[Macro]:
        """列出所有宏"""
        return [self._macros[name] for name in self.list_names()]

    def count(self) -> int:
        """宏数量"""
        return len(self._macros)

    def clear(self):
        """清空所有宏"""
        self._macros.clear()
        self._shortcuts.clear()
        self.macros_changed.emit()

    # --------------------------------------------------------
    # 快捷键
    # --------------------------------------------------------
    def bind_shortcut(self, name: str, shortcut: str) -> bool:
        """绑定快捷键"""
        if name not in self._macros:
            return False

        macro = self._macros[name]

        # 解除旧的绑定
        if macro.shortcut and self._shortcuts.get(macro.shortcut) == name:
            del self._shortcuts[macro.shortcut]

        # 解除可能冲突的绑定
        if shortcut in self._shortcuts:
            old_name = self._shortcuts[shortcut]
            if old_name in self._macros:
                self._macros[old_name].shortcut = ""

        # 设置新绑定
        macro.shortcut = shortcut
        self._shortcuts[shortcut] = name

        self.macro_updated.emit(name)
        return True

    def unbind_shortcut(self, name: str) -> bool:
        """解除快捷键绑定"""
        if name not in self._macros:
            return False

        macro = self._macros[name]
        if macro.shortcut and self._shortcuts.get(macro.shortcut) == name:
            del self._shortcuts[macro.shortcut]

        macro.shortcut = ""
        self.macro_updated.emit(name)
        return True

    def get_macro_by_shortcut(self, shortcut: str) -> Optional[Macro]:
        """通过快捷键获取宏"""
        name = self._shortcuts.get(shortcut)
        if name:
            return self._macros.get(name)
        return None

    def list_shortcuts(self) -> Dict[str, str]:
        """列出所有快捷键绑定"""
        return dict(self._shortcuts)

    # --------------------------------------------------------
    # 批量保存/加载
    # --------------------------------------------------------
    def save_all(self, directory: str = MACROS_DIR) -> int:
        """
        保存所有宏到目录。

        返回:
            成功保存的数量
        """
        os.makedirs(directory, exist_ok=True)
        count = 0

        for name, macro in self._macros.items():
            filename = MacroRecorder._sanitize_filename(name) + MACRO_FILE_EXT
            filepath = os.path.join(directory, filename)
            if macro.save(filepath):
                count += 1

        return count

    def load_all(self, directory: str = MACROS_DIR) -> int:
        """
        从目录加载所有宏。

        返回:
            成功加载的数量
        """
        if not os.path.isdir(directory):
            return 0

        count = 0
        for filename in os.listdir(directory):
            if filename.endswith(MACRO_FILE_EXT) or filename.endswith(".json"):
                filepath = os.path.join(directory, filename)
                macro = Macro.load(filepath)
                if macro:
                    self.add(macro, overwrite=True)
                    count += 1

        return count

    def export_to_json(self, filepath: str) -> bool:
        """导出所有宏到单个 JSON 文件"""
        try:
            data = {
                "version": MACRO_FORMAT_VERSION,
                "exported_at": datetime.datetime.now().isoformat(),
                "count": self.count(),
                "macros": [m.to_dict() for m in self.list_macros()],
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[MacroManager] 导出失败: {e}")
            return False

    def import_from_json(self, filepath: str, overwrite: bool = False) -> int:
        """从单个 JSON 文件导入宏"""
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)

            macros_data = data.get("macros", [])
            count = 0
            for macro_data in macros_data:
                macro = Macro.from_dict(macro_data)
                if self.add(macro, overwrite=overwrite):
                    count += 1
            return count
        except Exception as e:
            print(f"[MacroManager] 导入失败: {e}")
            return 0

    # --------------------------------------------------------
    # 调试
    # --------------------------------------------------------
    def dump(self) -> str:
        """导出管理器信息"""
        lines = [f"MacroManager: {self.count()} 个宏", "=" * 60]
        for name in self.list_names():
            macro = self._macros[name]
            shortcut = f" [{macro.shortcut}]" if macro.shortcut else ""
            lines.append(f"  - {name}{shortcut} ({macro.command_count} 条命令)")
        return "\n".join(lines)

    def __len__(self) -> int:
        return self.count()

    def __contains__(self, name: str) -> bool:
        return self.has(name)

    def __iter__(self):
        return iter(self.list_macros())

    def __repr__(self) -> str:
        return f"<MacroManager macros={self.count()}>"


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import shutil
    import tempfile

    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    print("=== 测试 Macro ===")

    # 创建一个宏
    macro = Macro(name="测试宏", description="这是一个测试")
    macro.add_command(InsertCmd(0, "Hello "))
    macro.add_command(InsertCmd(6, "World"))
    macro.add_command(DeleteCmd(0, 5, b"Hello"))

    print(f"宏: {macro}")
    print(f"命令数: {macro.command_count}")
    print(f"序列化: {len(json.dumps(macro.to_dict()))} 字符")
    print()

    # 保存/加载
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_macro_test_")
    test_file = os.path.join(tmp_dir, "test.qingcao-macro.json")

    print(f"保存: {macro.save(test_file)}")
    loaded = Macro.load(test_file)
    print(f"加载: {loaded}")
    print(f"加载后命令数: {loaded.command_count}")
    print()

    # 测试 MacroRecorder
    print("=== 测试 MacroRecorder ===")

    class FakeUndoManager:
        def __init__(self):
            self.record_hook = None

        def record(self, cmd):
            if self.record_hook:
                self.record_hook(cmd)

    class FakeScintilla:
        def __init__(self):
            self.text_content = ""

        def SendScintilla(self, *args):
            return 0

        def setModified(self, m):
            pass

    class FakeProxy:
        def __init__(self):
            self.sc = FakeScintilla()

    undo_mgr = FakeUndoManager()
    recorder = MacroRecorder(undo_manager=undo_mgr)

    # 连接信号
    recorder.recording_started.connect(lambda: print("[信号] 录制开始"))
    recorder.recording_stopped.connect(lambda n: print(f"[信号] 录制停止: {n} 条命令"))
    recorder.command_recorded.connect(lambda n: print(f"[信号] 已记录 {n} 条命令"))

    # 开始录制
    recorder.start("我的测试宏")

    # 模拟记录命令
    undo_mgr.record(InsertCmd(0, "A"))
    undo_mgr.record(InsertCmd(1, "B"))
    undo_mgr.record(InsertCmd(2, "C"))

    # 停止
    result_macro = recorder.stop()
    print(f"录制的宏: {result_macro.name}")
    print(f"命令数: {result_macro.command_count}")
    print()

    print(recorder.dump())
    print()

    # 保存录制的宏
    output_path = os.path.join(tmp_dir, "recorded.qingcao-macro.json")
    print(f"保存录制宏: {recorder.save_current(output_path)}")
    print()

    # 测试回放（使用假代理）
    print("=== 测试回放 ===")
    proxy = FakeProxy()
    success = recorder.replay(proxy, repeat=1, show_progress=False, check_cancel=False)
    print(f"回放结果: {success}")
    print()

    # 测试 MacroManager
    print("=== 测试 MacroManager ===")
    manager = MacroManager()

    # 添加宏
    manager.add(Macro(name="宏A", description="测试A"))
    manager.add(Macro(name="宏B", description="测试B"))
    manager.add(Macro(name="宏C", description="测试C"))

    print(f"宏数量: {manager.count()}")
    print(f"宏列表: {manager.list_names()}")

    # 绑定快捷键
    manager.bind_shortcut("宏A", "Ctrl+Alt+1")
    manager.bind_shortcut("宏B", "Ctrl+Alt+2")

    print(f"快捷键: {manager.list_shortcuts()}")
    print()

    # 通过快捷键获取宏
    macro_a = manager.get_macro_by_shortcut("Ctrl+Alt+1")
    print(f"Ctrl+Alt+1 -> {macro_a.name if macro_a else '无'}")
    print()

    # 重命名
    manager.rename("宏C", "宏C_重命名")
    print(f"重命名后: {manager.list_names()}")
    print()

    print(manager.dump())
    print()

    # 测试批量保存/加载
    print("=== 测试批量保存/加载 ===")
    save_dir = os.path.join(tmp_dir, "macros")
    print(f"保存全部: {manager.save_all(save_dir)} 个")

    new_manager = MacroManager()
    print(f"加载全部: {new_manager.load_all(save_dir)} 个")
    print(f"加载后: {new_manager.list_names()}")
    print()

    # 测试导出/导入
    print("=== 测试导出/导入 ===")
    export_file = os.path.join(tmp_dir, "macros_export.json")
    print(f"导出: {manager.export_to_json(export_file)}")

    new_manager2 = MacroManager()
    print(f"导入: {new_manager2.import_from_json(export_file)} 个")
    print(f"导入后: {new_manager2.list_names()}")
    print()

    # 清理
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print("测试完成。")
    sys.exit(0)
