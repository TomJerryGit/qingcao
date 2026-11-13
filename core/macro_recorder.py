# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""宏录制器（v2.25 从 macro 拆出）。"""

from core.macro_common import *  # noqa: F401,F403


class MacroRecorder(QObject):
    """
    宏录制器。

    监听编辑器的命令记录回调，将命令序列保存为宏。
    支持：
    - 开始/停止录制
    - 命令合并
    - 录制计数
    - 录制时长
    - 录制后保存为宏
    - 快捷键绑定

    信号:
        recording_started(): 开始录制
        recording_stopped(int): 停止录制（命令数量）
        command_recorded(int): 记录一条命令（累计数量）
        macro_saved(str): 宏已保存（文件路径）
        error_occurred(str): 错误
    """

    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal(int)
    command_recorded = pyqtSignal(int)
    macro_saved = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        undo_manager=None,
        parent: Optional[QObject] = None,
        undo_manager_provider: Optional[Callable[[], Any]] = None,
    ):
        """
        参数:
            undo_manager: 撤销管理器（用于注册命令记录回调）
            parent: 父 QObject
            undo_manager_provider: 无参回调，返回**当前**的撤销管理器

        关于 `undo_manager_provider`（P0-1 修复的核心）:
            缺陷背景（实测确认：录制后命令数为 0）:
                `ui/main_window.py` 构造的是 `MacroRecorder()`，
                没有传 `undo_manager`；而 `_register_hook()` 在
                `not self.undo_manager` 时**直接 return**，
                于是 `record_hook` 永不设置 —— 录制器挂在半空中，
                录到 0 条，回放必然提示"没有可回放的宏"。

                更关键的是：proxy 与其 `UndoManager` 是**每个标签一个**
                （`core/editor.py` 的 `EditorProxy.__init__` 里
                `self.undo_manager = UndoManager()`），标签随时可切换。
                所以正确的做法不是"构造时传一个固定引用"，而是在
                **开始录制的瞬间**解析出当前标签的 undo_manager
                （见 `bind_current_undo_manager()`）。
        """
        super().__init__(parent)

        self.undo_manager = undo_manager
        # 当前撤销管理器的解析回调（可为 None：退回 self.undo_manager）
        self._undo_manager_provider = undo_manager_provider
        # 已经挂上钩子的管理器。
        # 与 self.undo_manager 可能不同：录制中用户切了标签时，
        # stop() 必须解绑**当初挂钩的那个**，否则会在错误的对象上
        # 覆盖 record_hook（把别人的回调改掉 / 留下悬挂闭包）。
        self._hooked_manager: Optional[Any] = None

        # 状态
        self._state: MacroState = MacroState.IDLE
        self._recording: bool = False

        # 当前宏
        self.current_macro: Macro = Macro()

        # 录制时间
        self._start_time: float = 0.0
        self._last_command_time: float = 0.0

        # 命令计数
        self._command_count: int = 0

        # 是否启用命令合并
        self.merge_enabled: bool = True
        self.merge_interval_ms: int = DEFAULT_MERGE_INTERVAL

        # 保留原始的 record_hook（用于链式调用）
        self._original_hook: Optional[Callable] = None

    # --------------------------------------------------------
    # 属性
    # --------------------------------------------------------
    @property
    def state(self) -> MacroState:
        return self._state

    @property
    def recording(self) -> bool:
        """是否正在录制"""
        return self._recording

    @property
    def command_count(self) -> int:
        """当前录制的命令数量"""
        return self._command_count

    @property
    def has_hook(self) -> bool:
        """是否已把录制钩子挂到某个 UndoManager 上（P0-1）

        用途：调用方（如 `MainWindow._toggle_macro`）据此给出**可见**提示
        ——"开始了但没绑上编辑器"应当立刻告诉用户，
        而不是等他录完才发现是个空宏。
        """
        return self._hooked_manager is not None

    @property
    def duration(self) -> float:
        """录制时长（秒）"""
        if self._start_time <= 0:
            return 0.0
        return time.time() - self._start_time

    # --------------------------------------------------------
    # 开始/停止录制
    # --------------------------------------------------------
    def start(self, name: str = "", clear: bool = True):
        """
        开始录制宏。

        参数:
            name: 宏名称（留空则自动生成）
            clear: 是否清空当前宏
        """
        if self._recording:
            return

        # 初始化宏
        if clear or self.current_macro.is_empty:
            if not name:
                name = self._generate_macro_name()
            self.current_macro = Macro(
                name=name,
                author=self._get_default_author(),
            )

        # 重置时间
        # 修复 B3：_last_command_time 统一为 offset
        # （相对 _start_time 的秒数），而不是绝对时间戳。
        # 原实现初始化为 _start_time（绝对），而比较时用 offset
        # （相对），永远为负，导致所有连续命令被合并。
        self._start_time = time.time()
        self._last_command_time = 0.0
        self._command_count = 0

        # 设置状态
        self._recording = True
        self._state = MacroState.RECORDING

        # 注册命令记录回调
        #
        # P0-1 修复：不再直接 `_register_hook()`（它只看构造时传入的
        # undo_manager，而 main_window 构造时并没有传）——改为在开始录制的
        # 这一刻解析"当前标签"的 undo_manager 并挂钩。
        if not self.bind_current_undo_manager():
            # 录不到命令时必须**可见**（信号由 MainWindow 转成状态栏提示）
            self.error_occurred.emit("没有可录制的编辑器（当前标签无 undo_manager）")

        # 发射信号
        self.recording_started.emit()
        self.command_recorded.emit(0)

        # 事件总线
        try:
            bus.emit_event(
                MacroStartedEvent(
                    command_count=0,
                    macro_name=self.current_macro.name,
                )
            )
        except Exception:
            pass

    def stop(self) -> Macro:
        """
        停止录制。

        返回:
            录制的宏对象
        """
        if not self._recording:
            return self.current_macro

        # 更新状态
        self._recording = False
        self._state = MacroState.IDLE

        # 计算时长
        duration = time.time() - self._start_time

        # 取消注册回调
        self._unregister_hook()

        # 更新宏元数据
        self.current_macro.updated_at = datetime.datetime.now().isoformat()
        self.current_macro.metadata["duration"] = round(duration, 3)
        self.current_macro.metadata["recorded_at"] = datetime.datetime.now().isoformat()

        # 发射信号
        self.recording_stopped.emit(self._command_count)

        # 事件总线
        try:
            bus.emit_event(
                MacroStoppedEvent(
                    command_count=self._command_count,
                    macro_name=self.current_macro.name,
                    duration_seconds=duration,
                )
            )
        except Exception:
            pass

        return self.current_macro

    def toggle(self):
        """切换录制状态"""
        if self._recording:
            self.stop()
        else:
            self.start()

    def cancel(self):
        """取消录制并清空当前宏"""
        if self._recording:
            self._recording = False
            self._state = MacroState.IDLE
            self._unregister_hook()

        self.current_macro.clear()
        self._command_count = 0

    # --------------------------------------------------------
    # 命令记录回调
    # --------------------------------------------------------
    def set_undo_manager_provider(self, provider: Optional[Callable[[], Any]]):
        """设置"当前撤销管理器"的解析回调（P0-1）

        供运行期替换绑定来源（例如主窗口在标签系统就绪后才注册）。
        """
        self._undo_manager_provider = provider

    def _resolve_undo_manager(self):
        """解析当前应当绑定的 UndoManager

        优先走 `undo_manager_provider`（每标签动态解析），
        回调不可用/返回 None 时退回构造时传入的 `self.undo_manager`。
        任何异常都吞掉并退回 —— 宏录制绝不能把主流程带崩。
        """
        provider = self._undo_manager_provider
        if callable(provider):
            try:
                um = provider()
            except Exception as e:
                print(f"[Macro] 解析 undo_manager 失败: {e}")
                um = None
            if um is not None:
                return um
        return self.undo_manager

    def bind_current_undo_manager(self) -> bool:
        """把录制钩子挂到"当前"undo_manager 上，返回是否成功（P0-1）

        为什么需要这个方法:
            * 构造 `MacroRecorder()` 时主窗口还**没有**标签
              （`self.tabs` 在 `_build_central` 里才创建），
              所以只能在用的时候解析；
            * proxy 是每标签一个，用户录制中可以切标签 ——
              每次 `start()` 都重新解析并重新挂钩；
            * 若解析出的管理器与已挂钩的是同一个，则复用（幂等），
              避免重复包裹 `record_hook` 造成命令被记两次。
        """
        um = self._resolve_undo_manager()
        if um is None:
            return False
        if um is self._hooked_manager:
            return True
        # 先解绑旧的（可能是别的标签的管理器）
        self._unregister_hook()
        self.undo_manager = um
        self._register_hook()
        return self._hooked_manager is um

    def _register_hook(self):
        """注册命令记录回调到 undo_manager"""
        target = self._hooked_manager or self.undo_manager
        if not target:
            return

        # 保存原始回调（可能被其他模块使用）
        self._original_hook = getattr(target, "record_hook", None)

        # 注册我们的回调
        def combined_hook(command):
            # 先调用原始回调
            if self._original_hook:
                try:
                    self._original_hook(command)
                except Exception:
                    pass

            # 再记录到宏
            self._on_command_recorded(command)

        target.record_hook = combined_hook
        self._hooked_manager = target

    def _unregister_hook(self):
        """取消注册（解绑**当初挂钩的那个**管理器，而非当前的）"""
        target = self._hooked_manager or self.undo_manager
        if not target:
            return

        # 恢复原始回调
        target.record_hook = self._original_hook
        self._hooked_manager = None
        self._original_hook = None

    def _on_command_recorded(self, command: Command):
        """
        命令记录回调。

        参数:
            command: 记录的命令对象
        """
        if not self._recording:
            return

        try:
            # 计算时间偏移
            now = time.time()
            offset = now - self._start_time

            # 检查是否需要合并
            if (
                self.merge_enabled
                and self.current_macro.commands
                and offset - self._last_command_time < self.merge_interval_ms / 1000.0
            ):
                # 尝试与上一条命令合并
                last_macro_cmd = self.current_macro.commands[-1]

                try:
                    last_cmd = Command.from_dict(last_macro_cmd.command_data)
                    if last_cmd.can_merge(command):
                        merged = last_cmd.merge_with(command)
                        if merged is not None:
                            # 更新最后一条命令
                            last_macro_cmd.command_data = merged.to_dict()
                            self._last_command_time = offset
                            return
                except Exception:
                    pass

            # 添加新命令
            self.current_macro.add_command(command, offset)
            self._command_count += 1
            self._last_command_time = offset

            # 发射信号
            self.command_recorded.emit(self._command_count)

        except Exception as e:
            self.error_occurred.emit(f"记录命令失败: {e}")

    # --------------------------------------------------------
    # 回放
    # --------------------------------------------------------
    def replay(
        self,
        proxy,
        macro: Optional[Macro] = None,
        repeat: int = 1,
        show_progress: bool = True,
        check_cancel: bool = True,
    ) -> bool:
        """
        回放宏。

        参数:
            proxy: 编辑器代理
            macro: 要回放的宏（None 则使用当前宏）
            repeat: 重复次数
            show_progress: 是否显示进度对话框
            check_cancel: 是否允许取消

        返回:
            是否成功完成
        """
        if macro is None:
            macro = self.current_macro

        if macro.is_empty:
            self.error_occurred.emit("宏为空")
            return False

        if proxy is None or not hasattr(proxy, "sc"):
            self.error_occurred.emit("编辑器代理无效")
            return False

        # 检查命令数量
        total_commands = len(macro.commands) * repeat
        if total_commands > MAX_REPLAY_COMMANDS:
            self.error_occurred.emit(f"回放命令数量过多 ({total_commands})")
            return False

        # 记录状态
        old_state = self._state
        self._state = MacroState.PLAYING

        # 保存旧的 record_hook 并禁用录制
        was_recording = self._recording
        if was_recording:
            self._unregister_hook()

        start_time = time.time()

        # 回放前的缓冲区快照
        #
        # 用途见下方"写入单条整体回滚命令"：回放期间关闭了 Scintilla 通知
        # （性能考虑），`_on_scintilla_modified` 收不到事件，自研撤销栈
        # 不会有任何回放命令 —— 若不管，Ctrl+Z 会弹出回放**之前**的旧命令
        # 并按旧位置执行，直接损坏内容。
        text_before_replay = ""
        try:
            text_before_replay = proxy.sc.text()
        except Exception:
            pass

        try:
            # 禁用 Scintilla 通知（提高性能）
            self._disable_scintilla_notifications(proxy)

            # 进度对话框
            progress = None
            if show_progress and total_commands > 100:
                progress = QProgressDialog("正在回放宏...", "取消", 0, repeat, None)
                progress.setWindowModality(Qt.WindowModal)
                progress.setMinimumDuration(300)
                progress.show()

            # 执行回放
            cancelled = False
            executed = 0

            for r in range(repeat):
                if check_cancel and progress and progress.wasCanceled():
                    cancelled = True
                    break

                # 回放单次
                for macro_cmd in macro.commands:
                    try:
                        cmd = Command.from_dict(macro_cmd.command_data)
                        cmd.execute(proxy.sc)
                        executed += 1
                    except Exception as e:
                        print(f"[Macro] 回放命令失败: {e}")

                # 更新进度
                if progress:
                    progress.setValue(r + 1)
                    QApplication.processEvents()

            # 关闭进度
            if progress:
                progress.close()

            elapsed = (time.time() - start_time) * 1000

            # 标记修改
            #
            # 修复（INV-M3，审计用例复现）：原先只改 `proxy._modified`，
            # 不调用 `document.mark_modified()` —— 于是
            # `proxy.is_modified` 与 `document.is_modified` 出现分歧
            # （标签页显示 '*' 但文档认为干净，自动保存/关闭提示据此误判）。
            proxy.sc.setModified(True)
            if hasattr(proxy, "_modified"):
                proxy._modified = True
            try:
                doc = getattr(proxy, "document", None)
                if doc is not None and hasattr(doc, "mark_modified"):
                    doc.mark_modified()
            except Exception:
                pass
            if hasattr(proxy, "modified_changed"):
                try:
                    proxy.modified_changed.emit(True)
                except Exception:
                    pass

            # 写入一条**整体回滚命令**，让一次 Ctrl+Z 回到回放前
            #
            # 修复（INV-M1/INV-M2，审计用例复现）：
            #   回放用 `SCI_SETMODEVENTMASK(0)` 关闭了修改通知（第 577 行），
            #   `EditorProxy._on_scintilla_modified` 因此不会触发，
            #   `UndoManager.record()` 从未被调用 —— 回放改变了缓冲区却
            #   在撤销栈里**没有任何记录**。于是用户按 Ctrl+Z 时弹出的是
            #   回放**之前**的旧命令，按旧位置执行 → 内容损坏且不可预期。
            #
            #   这里把"回放前 → 回放后"的整段变化作为**一个原子命令**补记
            #   进撤销栈：undo 恢复回放前的全文，redo 恢复回放后的全文。
            #   使用 `CompoundCmd`（带显式逆操作），它能被 UndoManager
            #   正确 undo/redo（不像 GroupCmd 那样在 redo 时会再次执行正向）。
            try:
                if executed and text_before_replay != proxy.sc.text():
                    from core.commands import CompoundCmd as _Compound

                    text_after = proxy.sc.text()

                    def _restore(text):
                        def _fn(sc):
                            # 注意：不能用 `SCI_SETTEXT` + str —— 该消息的
                            # lParam 需要 bytes，传 str 会抛
                            # "argument 3 has unexpected type 'str'"，
                            # 命令因此静默失败（看起来像"撤销没反应"）。
                            # QScintilla 的 `setText()` 接受 str 并处理编码。
                            try:
                                sc.setText(text)
                            except Exception:
                                try:
                                    data = text.encode("utf-8")
                                    sc.SendScintilla(sc.SCI_SETTEXT, 0, data)
                                except Exception:
                                    pass

                        return _fn

                    rollback = _Compound(
                        forward_fn=_restore(text_after),
                        backward_fn=_restore(text_before_replay),
                        pos=0,
                        description="宏回放",
                    )
                    um = getattr(proxy, "undo_manager", None)
                    if um is not None:
                        # 清空回放前的撤销历史：回放是一次"批量替换"，
                        # 旧的命令位置相对新内容已失效（INV-M2 要求
                        # 一次 Ctrl+Z 就回到回放前，而不是先执行旧命令）。
                        try:
                            um.undo_stack.clear()
                        except Exception:
                            pass
                        try:
                            um.redo_stack.clear()
                        except Exception:
                            pass
                        um.record(rollback)
            except Exception as e:
                print(f"[Macro] 记录回放回滚命令失败: {e}")

            # 恢复状态
            self._enable_scintilla_notifications(proxy)
            self._state = old_state

            # 恢复录制（如果之前在录制）
            if was_recording:
                self._recording = True
                # P0-1: 回放前 _unregister_hook() 已把 _hooked_manager 清空，
                # 这里重新解析"当前"管理器再挂钩（不能假设还是回放前那个）。
                self.bind_current_undo_manager()

            # 发射信号
            try:
                bus.emit_event(
                    MacroReplayedEvent(
                        command_count=executed,
                        macro_name=macro.name,
                        elapsed_ms=elapsed,
                    )
                )
            except Exception:
                pass

            if cancelled:
                self.error_occurred.emit("回放已取消")
                return False

            return True

        except Exception as e:
            self._state = MacroState.ERROR
            self._enable_scintilla_notifications(proxy)
            self.error_occurred.emit(f"回放失败: {e}")
            traceback.print_exc()
            return False

    def replay_with_offsets(self, proxy, macro: Optional[Macro] = None):
        """
        按录制时的时间偏移回放（模拟真实时间）。

        参数:
            proxy: 编辑器代理
            macro: 宏对象
        """
        if macro is None:
            macro = self.current_macro

        if macro.is_empty:
            return False

        # 禁用通知
        self._disable_scintilla_notifications(proxy)

        try:
            last_offset = 0.0
            for macro_cmd in macro.commands:
                # 等待时间差
                delay = macro_cmd.timestamp_offset - last_offset
                if delay > 0:
                    time.sleep(delay)
                last_offset = macro_cmd.timestamp_offset

                # 执行命令
                try:
                    cmd = Command.from_dict(macro_cmd.command_data)
                    cmd.execute(proxy.sc)
                except Exception as e:
                    print(f"[Macro] 回放失败: {e}")

            proxy.sc.setModified(True)
            return True

        except Exception as e:
            self.error_occurred.emit(f"回放失败: {e}")
            return False
        finally:
            self._enable_scintilla_notifications(proxy)

    def _disable_scintilla_notifications(self, proxy):
        """禁用 Scintilla 通知以提高回放性能"""
        try:
            proxy.sc.SendScintilla(proxy.sc.SCI_SETMODEVENTMASK, 0)
        except Exception:
            pass

    def _enable_scintilla_notifications(self, proxy):
        """恢复 Scintilla 通知"""
        try:
            from PyQt5.Qsci import QsciScintilla

            mask = QsciScintilla.SC_MOD_INSERTTEXT | QsciScintilla.SC_MOD_DELETETEXT
            proxy.sc.SendScintilla(proxy.sc.SCI_SETMODEVENTMASK, mask)
        except Exception:
            pass

    # --------------------------------------------------------
    # 保存/加载
    # --------------------------------------------------------
    def save_current(self, filepath: Optional[str] = None) -> bool:
        """
        保存当前宏。

        参数:
            filepath: 文件路径（None 则自动生成）

        返回:
            是否成功
        """
        if self.current_macro.is_empty:
            self.error_occurred.emit("宏为空，无法保存")
            return False

        if not filepath:
            filepath = os.path.join(
                MACROS_DIR, f"{self._sanitize_filename(self.current_macro.name)}{MACRO_FILE_EXT}"
            )

        success = self.current_macro.save(filepath)
        if success:
            self.macro_saved.emit(filepath)
        return success

    def load(self, filepath: str) -> bool:
        """
        加载宏文件。

        参数:
            filepath: 宏文件路径

        返回:
            是否成功
        """
        macro = Macro.load(filepath)
        if macro is None:
            self.error_occurred.emit(f"加载宏失败: {filepath}")
            return False

        self.current_macro = macro
        self._command_count = len(macro.commands)
        return True

    # --------------------------------------------------------
    # 查询
    # --------------------------------------------------------
    def has_commands(self) -> bool:
        """当前宏是否包含命令"""
        return not self.current_macro.is_empty

    def get_commands(self) -> List[MacroCommand]:
        """获取当前宏的所有命令"""
        return list(self.current_macro.commands)

    def get_info(self) -> Dict[str, Any]:
        """获取录制器信息"""
        return {
            "state": self._state.name,
            "recording": self._recording,
            "command_count": self._command_count,
            "duration": round(self.duration, 2),
            "macro_name": self.current_macro.name,
            "macro_empty": self.current_macro.is_empty,
            # P0-1: 是否真的挂上了撤销管理器（录不到命令时最先看这个）
            "hooked": self._hooked_manager is not None,
            "undo_manager": repr(self._hooked_manager or self.undo_manager),
        }

    # --------------------------------------------------------
    # 辅助
    # --------------------------------------------------------
    def _generate_macro_name(self) -> str:
        """生成默认宏名称"""
        now = datetime.datetime.now()
        return f"宏_{now.strftime('%Y%m%d_%H%M%S')}"

    def _get_default_author(self) -> str:
        """获取默认作者名"""
        try:
            settings = QSettings("QingCao", "Editor")
            return settings.value("author_name", "", type=str)
        except Exception:
            return ""

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """清理文件名中的非法字符"""
        invalid_chars = '<>:"/\\|?*'
        for c in invalid_chars:
            name = name.replace(c, "_")
        return name.strip() or "macro"

    # --------------------------------------------------------
    # 调试
    # --------------------------------------------------------
    def dump(self) -> str:
        """导出录制器信息"""
        info = self.get_info()
        lines = ["MacroRecorder", "=" * 60]
        lines.append(f"状态: {info['state']}")
        lines.append(f"录制中: {info['recording']}")
        lines.append(f"命令数: {info['command_count']}")
        lines.append(f"时长: {info['duration']} 秒")
        lines.append(f"宏名称: {info['macro_name']}")
        lines.append(f"宏为空: {info['macro_empty']}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"<MacroRecorder state={self._state.name} "
            f"commands={self._command_count} "
            f"recording={self._recording}>"
        )


# ============================================================
# 宏管理器
# ============================================================
