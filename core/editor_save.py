# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""从 core/editor.py 拆出的 save 职责（v2.23 D1）。"""

from core.editor_common import *  # noqa: F401,F403
from core.editor_common import (  # noqa: F401
    _EOL_SPLIT_RE,
    _normalize_bytes,
    _trim_trailing_ws_keep_eol,
)


class EditorSaveMixin:
    def save_file(self, filepath: Optional[str] = None) -> bool:
        """
        保存文件。

        参数:
            filepath: 另存为路径

        返回:
            是否成功
        """
        try:
            # 获取文本
            text = self.sc.text()

            # 应用偏好设置：清理行尾空白和末尾换行
            # P8: 统一走 Preferences（原先裸 QSettings("QingCao","Editor")
            #     绕过了偏好层，默认值可能与 DEFAULTS 不一致）
            prefs = self._prefs()
            trim_ws = True
            final_newline = True
            if prefs is not None:
                trim_ws = bool(prefs.get("trim_trailing_whitespace", True))
                final_newline = bool(prefs.get("insert_final_newline", True))

            if trim_ws:
                # ★ 修复（混合场景压测实测发现）：
                #   原实现 `[l.rstrip() for l in text.splitlines()]` +
                #   `'\n'.join(...)` 会**把每一行的行尾符统一改成 LF**：
                #     * `splitlines()` 把 CRLF / CR / LF 全部切开；
                #     * `'\n'.join()` 又全部用 LF 拼回。
                #   于是"打开一个混合换行（或 CRLF）文件、改一个字、保存"
                #   之后，**整个文件的行尾风格被悄悄改写**（实测
                #   `b'a\r\nb\nc\rd\r\n'` → `b'a\nb\nc\nd\n'`）。
                #   文本内容没错，但这是用户没要求的格式变更：
                #   git diff 会显示全文件改动，CRLF 项目会被整体污染。
                #
                #   现在只裁剪**行尾空白**，原样保留每行的行尾符号。
                text = _trim_trailing_ws_keep_eol(text)

            if final_newline:
                if text and not text.endswith(("\n", "\r")):
                    # 用文件当前的行尾风格补最后一个换行，避免造出混合换行
                    try:
                        eol = (
                            self.document.provider._eol if self.document.provider else "\n"
                        ) or "\n"
                    except Exception:
                        eol = "\n"
                    text += eol

            # 设置回编辑器（保持一致性）
            if text != self.sc.text():
                self.sc.setText(text)

            # 更新提供者内容
            self._sync_content_to_provider(text)

            # 保存
            success = self.document.save(filepath)

            if success:
                self._modified = False
                self.sc.setModified(False)

                # 注：另存为时 LSP URI 的更新由 `Document.filepath_changed`
                # 信号统一驱动（见 `_on_document_filepath_changed`），
                # 不在这里手动补 —— 这样无论从哪个入口保存都一致。

                # P0-2: 通知语言服务器已保存
                #
                # 修复（P0-7，实测确认）：这里原本**连着写了两遍**同一行
                # `self._notify_lsp_saved(filepath)`（连注释一起复制），
                # 于是每次 Ctrl+S 都会向语言服务器发**两次 didSave**。
                # 服务器可能因此重复触发保存钩子/重复诊断。
                self._notify_lsp_saved(filepath)

                # 删除草稿
                try:
                    self.document.delete_draft()
                except Exception:
                    pass

                self.modified_changed.emit(False)

                # 多实例（P0）：广播本次保存，让其它实例重载
                try:
                    from infrastructure.instance_broadcast import notify_file_saved

                    notify_file_saved(self.document.filepath or "")
                except Exception:
                    pass

                # 发射事件
                try:
                    bus.emit_event(
                        FileSavedEvent(
                            path=self.document.filepath or "",
                            size=self.document.meta.size,
                        )
                    )
                except Exception:
                    pass

            return success

        except Exception as e:
            print(f"[EditorProxy] 保存失败: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _sync_content_to_provider(self, text: str):
        """将编辑器内容同步到提供者"""
        if not self.document.provider:
            return

        provider = self.document.provider
        encoded = provider.encode(text)
        new_size = len(encoded)
        block_size = provider.block_size
        total_blocks = max(1, (new_size + block_size - 1) // block_size)

        # 清空旧脏块
        provider.clear_dirty()

        # 写入所有块（单块=小文件常见路径，直接写 block 0，省循环开销）
        if total_blocks == 1:
            provider.write_block(0, encoded)
        else:
            for bid in range(total_blocks):
                start = bid * block_size
                end = min(start + block_size, new_size)
                provider.write_block(bid, encoded[start:end])

        # 更新提供者元数据
        if hasattr(provider, "_total_blocks"):
            provider._total_blocks = total_blocks
        if hasattr(provider, "_size"):
            provider._size = new_size
        self._last_synced_text = text
