# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""从 core/editor.py 拆出的 loading 职责（v2.23 D1）。"""

from core.editor_common import *  # noqa: F401,F403
from core.editor_common import (  # noqa: F401
    _EOL_SPLIT_RE,
    _normalize_bytes,
    _trim_trailing_ws_keep_eol,
)


class EditorLoadingMixin:
    # ========================================================
    # 打开与保存
    # ========================================================
    def open_file(self, filepath: Optional[str] = None) -> bool:
        """
        打开文件。

        参数:
            filepath: 文件路径（None 则使用 document 中已打开的）

        返回:
            是否成功
        """
        try:
            self._restoring = True

            if filepath:
                if not self.document.open(filepath):
                    return False

            # 清空编辑器
            self.sc.clear()

            # 设置语法高亮
            self._apply_lexer(filepath or self.document.filepath)

            # 加载内容（分块流式）
            self._load_content()

            # 检测缩进风格
            self._detect_indent()

            # 恢复书签和折叠
            self._restore_bookmarks()
            self._restore_folds()

            # 清空撤销栈
            self.undo_manager.clear()

            # 更新状态
            self._modified = False
            self.sc.setModified(False)

            self._restoring = False

            # 发射事件
            try:
                bus.emit_event(
                    FileEvent(
                        path=self.document.filepath or "",
                        encoding=self.document.encoding,
                    )
                )
            except Exception:
                pass

            return True

        except Exception as e:
            self._restoring = False
            print(f"[EditorProxy] 打开文件失败: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _load_content(self):
        """分块加载内容

        ★ 修复（真实 UI 压测发现）：大文件加载既慢又可能崩

            原实现：>10MB 先同步加载 20 块（1.25MB），其余用
            `QTimer.singleShot(10, ...)` **逐块**（每块 64KB）延迟加载。

            实测后果（10MB = 约 160 块）：

            * 每块之间固定等 10ms → 至少 **1.6 秒**纯等待；
            * 关闭标签/窗口时若 timer 仍挂着，回调会操作已销毁的控件
              → 实测**段错误**（0xC0000005）——已由 `abort_loading` 修复；
            * 加载期间界面是**不完整**的，用户做"全选列编辑"只作用于
              已加载部分，且没有任何提示。

        ★ 第二次修复（量化后）：**QScintilla 的 `append()` 本身是超线性的**

            实测 161 块 × 64KB（约 10MB）逐块 append：

                第 1~5 块   0.0008 ~ 0.0040s
                第 157~161 块 0.117 ~ 0.134s     ← 慢 40 倍以上
                总计 **10.85 秒**

            而同样内容**一次 `setText` 仅 0.132 秒**（快 82 倍）。
            原因：每次 append 都要在已增长的文档上做行索引/位置维护，
            成本随文档增大而上升 → 逐块 append 累积成 O(n²)。

            因此改为**两级策略**：

              1. ≤ `_SYNC_LOAD_LIMIT`（32MB）：一次性 decode 全文 +
                 单次 `setText`。实测 10MB 仅 0.13s，也最省心；
              2. > 32MB：**几何递增批量** append（64KB → 128KB → 256KB …，
                 上限 `_APPEND_BATCH_MAX`），把 append 次数从 O(n/64KB)
                 降到 **O(log n)**（100MB 约 15 次），同时用时间片让出事件循环，
                 峰值内存仍受控。
        """
        if not self.document.provider:
            return

        provider = self.document.provider
        total = provider.total_blocks
        self._load_aborted = False
        self._load_cursor = 0
        self._load_total = total
        self._viewport_ready = False
        self._deferred_loading = False
        self._viewport_prefix_blocks = 0

        # ---- 策略 0：视口优先加载（v2.24.x 默认自动开启）----
        # QINGCAO_VIEWPORT_LOAD=0 可禁用；默认对 >32MB 文件启用。
        _vflag = os.environ.get("QINGCAO_VIEWPORT_LOAD", "auto")
        try:
            _vmb = int(os.environ.get("QINGCAO_VIEWPORT_THRESHOLD_MB", "32"))
        except ValueError:
            _vmb = 32
        if _vflag != "0" and provider.size > _vmb * 1024 * 1024:
            self._load_viewport_prefix(provider, total)
            return

        # ---- 策略 1：中小文件一次性 setText（最快）----
        if provider.size <= self._SYNC_LOAD_LIMIT:
            try:
                text = provider.read_text()
                if getattr(self, "_load_aborted", False):
                    return
                # ★ 性能（cProfile 实测）：一次性 setText 会触发约
                #   **50 万次** `SCN_MODIFIED`（10MB/58 万行场景），
                #   每次回调虽然因 `_restoring=True` 立刻 return，
                #   纯 Python 调用开销合计仍有 **0.4 秒**。
                #   加载期间内容完全来自 provider，不需要撤销记录，
                #   因此临时断开信号，加载后接回。
                _disconnected = False
                try:
                    self.sc.SCN_MODIFIED.disconnect(self._on_scintilla_modified)
                    _disconnected = True
                except (TypeError, RuntimeError):
                    pass
                try:
                    self.sc.setText(text)
                finally:
                    if _disconnected:
                        try:
                            self.sc.SCN_MODIFIED.connect(self._on_scintilla_modified)
                        except (TypeError, RuntimeError):
                            pass
                self._load_cursor = total
                self._viewport_ready = True
                self.load_progress.emit(total, total)
                return
            except Exception as e:
                print(f"[EditorProxy] 一次性加载失败，回退分片: {e}")

        # ---- 策略 2：超大文件几何递增批量 append（O(log n) 次）----
        self._load_batch_blocks = 1  # 以"块数"为批量单位
        QTimer.singleShot(0, self._load_chunk_slice)

    _VIEWPORT_PREFIX_BYTES = 2 * 1024 * 1024

    def _load_viewport_prefix(self, provider, total):
        """视口优先：只同步加载前 N 块立即显示，其余后台补齐（原型）。"""
        try:
            _pmb = int(os.environ.get("QINGCAO_VIEWPORT_PREFIX_MB", "2"))
        except ValueError:
            _pmb = 2
        target = max(1, _pmb) * 1024 * 1024
        bs = max(1, int(getattr(provider, "block_size", 65536)))
        n = max(1, min(int(total), (target + bs - 1) // bs))
        parts = [provider.decode(provider.read_block(i)) for i in range(n)]
        text = "".join(parts)
        _disc = False
        try:
            self.sc.SCN_MODIFIED.disconnect(self._on_scintilla_modified)
            _disc = True
        except (TypeError, RuntimeError):
            pass
        try:
            self.sc.setText(text)
        finally:
            if _disc:
                try:
                    self.sc.SCN_MODIFIED.connect(self._on_scintilla_modified)
                except (TypeError, RuntimeError):
                    pass
        self._load_cursor = n
        self._viewport_prefix_blocks = n
        self._viewport_ready = True
        self._deferred_loading = True
        self.load_progress.emit(n, int(total))
        QTimer.singleShot(0, self._finish_viewport_load)

    def _finish_viewport_load(self):
        """视口首屏后一次性补齐剩余内容（原型）。"""
        try:
            provider = self.document.provider
            total = int(getattr(self, "_load_total", 0) or 0)
            current = int(getattr(self, "_load_cursor", 0) or 0)
            if not total or current >= total:
                self._deferred_loading = False
                return
            parts = [provider.decode(provider.read_block(i)) for i in range(current, total)]
            _disc = False
            try:
                self.sc.SCN_MODIFIED.disconnect(self._on_scintilla_modified)
                _disc = True
            except (TypeError, RuntimeError):
                pass
            try:
                self.sc.append("".join(parts))
            finally:
                if _disc:
                    try:
                        self.sc.SCN_MODIFIED.connect(self._on_scintilla_modified)
                    except (TypeError, RuntimeError):
                        pass
            self._load_cursor = total
            self._deferred_loading = False
            self._modified = False
            try:
                self.sc.setModified(False)
            except Exception:
                pass
            self.load_progress.emit(total, total)
        except Exception as e:
            self._deferred_loading = False
            print("[viewport] 补齐失败:", e)

    def _load_chunk_slice(self):
        """时间片 + **几何递增批量** append（超大文件专用）

        为什么批量要递增（实测数据）：QScintilla 的 `append()` 成本随文档
        增长而上升 —— 161 次 64KB append 共 10.85s（末尾单次 0.13s），
        而同样内容一次 `setText` 仅 0.132s。

        因此这里每轮把"批量块数"翻倍（1 → 2 → 4 → …，上限
        `_APPEND_BATCH_MAX_BLOCKS`），append 次数降到 O(log n)：
        100MB 文件约 15 次 append，而不是 1600 次。

        每片仍受 `_LOAD_SLICE_SECONDS` 约束，到点让出事件循环保持 UI 可响应。
        """
        if getattr(self, "_load_aborted", False):
            return
        provider = getattr(self.document, "provider", None)
        if provider is None:
            return

        total = getattr(self, "_load_total", 0)
        current = getattr(self, "_load_cursor", 0)
        batch = max(1, int(getattr(self, "_load_batch_blocks", 1)))
        slice_start = time.perf_counter()

        try:
            while current < total:
                if getattr(self, "_load_aborted", False):
                    return
                n = min(batch, total - current)
                parts = []
                for i in range(current, current + n):
                    parts.append(provider.decode(provider.read_block(i)))
                chunk = "".join(parts)
                if getattr(self, "_deferred_loading", False):
                    _disc = False
                    try:
                        self.sc.SCN_MODIFIED.disconnect(self._on_scintilla_modified)
                        _disc = True
                    except (TypeError, RuntimeError):
                        pass
                    try:
                        self.sc.append(chunk)
                    finally:
                        if _disc:
                            try:
                                self.sc.SCN_MODIFIED.connect(self._on_scintilla_modified)
                            except (TypeError, RuntimeError):
                                pass
                else:
                    self.sc.append(chunk)
                current += n
                self._load_cursor = current
                # 下一轮批量翻倍（上限见常量），把 append 次数压到 O(log n)
                batch = min(batch * 2, self._APPEND_BATCH_MAX_BLOCKS)
                if time.perf_counter() - slice_start >= self._LOAD_SLICE_SECONDS:
                    break
            self.load_progress.emit(current, total)
            if current >= total and getattr(self, "_deferred_loading", False):
                self._deferred_loading = False
                self._modified = False
                try:
                    self.sc.setModified(False)
                except Exception:
                    pass
            if current < total:
                QTimer.singleShot(0, self._load_chunk_slice)
        except Exception as e:
            print(f"[EditorProxy] 加载块 {current} 失败: {e}")

    def _load_next_chunk(self, current: int, total: int):
        """【已废弃】延迟加载下一块

        ★ 保留此方法只为**外部兼容**（若仍有调用点），内部改为一次性
        委托给时间片加载器 `_load_chunk_slice`。

        原实现逐块 `QTimer.singleShot(10, ...)`，10MB 文件需 1.6 秒以上的
        **纯空等**，且关闭标签时回调会操作已销毁控件导致段错误 ——
        详见 `_load_content` 的说明。
        """
        self._load_cursor = max(0, int(current))
        self._load_total = max(0, int(total))
        self._load_aborted = False
        self._load_chunk_slice()

    def _prefs(self):
        """获取全局 Preferences 单例（P8: 统一偏好读取）。

        修复说明:
            本文件原先有 4 处裸 ``QSettings("QingCao", "Editor")``，而
            ``ui/editor_view.py`` 全部走 ``Preferences``。两者底层虽然
            是同一个 QSettings 存储（``app/preferences.py`` 的
            ``ORG_NAME="QingCao"`` / ``APP_NAME="Editor"``），但裸读
            绕过了 Preferences 的类型转换与变更通知，也没有"单一
            入口"可维护性 —— 例如同一个开关在两处用不同的默认值
            （``settings.value(k, True, type=bool)`` vs
            ``DEFAULTS[k]``）就会读出不一致的结果。
            现在统一走 Preferences 单例。

        返回:
            Preferences 实例；不可用时返回 None（调用方回退默认值）
        """
        try:
            from app.preferences import get_preferences

            return get_preferences()
        except Exception:
            return None
