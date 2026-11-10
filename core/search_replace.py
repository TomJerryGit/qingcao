# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""替换引擎（v2.24 拆出）。"""

from core.search_common import *  # noqa: F401,F403,F405


class ReplaceEngine:
    """
    替换引擎。

    封装搜索与替换的完整流程，支持：
    - 单个替换
    - 全部替换
    - 预览替换结果
    - 批量替换多文件
    """

    def __init__(self, provider):
        """
        参数:
            provider: 内容提供者
        """
        self.provider = provider

    def replace_one(self, match: SearchMatch, replacement: str) -> bool:
        """
        替换单个匹配。

        参数:
            match: 匹配对象
            replacement: 替换文本

        返回:
            是否成功
        """
        try:
            # 读取全文
            text = self.provider.read_text()

            # 执行替换（P1-1: 用字符偏移索引 str）
            new_text = text[: match.char_start] + replacement + text[match.char_end :]

            # 写回
            self._write_back(new_text)
            return True

        except Exception as e:
            print(f"[ReplaceEngine] 替换失败: {e}")
            return False

    def replace_all(
        self, result: SearchResult, replacement: str, is_regex: bool = False, pattern: str = ""
    ) -> int:
        """
        替换所有匹配。

        参数:
            result: 搜索结果
            replacement: 替换文本
            is_regex: 是否使用正则替换
            pattern: 原始正则（用于反向引用）

        返回:
            替换的数量
        """
        if result.is_empty:
            return 0

        count = 0

        try:
            text = self.provider.read_text()
            regex = re.compile(pattern) if (is_regex and pattern) else None

            # 从后往前替换（P1-1: 用字符偏移索引 str）
            new_text = text
            for match in reversed(result.matches):
                try:
                    if is_regex and regex:
                        original = text[match.char_start : match.char_end]
                        re_match = regex.fullmatch(original)
                        if re_match:
                            repl = re_match.expand(replacement)
                        else:
                            repl = replacement
                    else:
                        repl = replacement

                    new_text = new_text[: match.char_start] + repl + new_text[match.char_end :]
                    count += 1

                except Exception:
                    continue

            # 写回
            self._write_back(new_text)

        except Exception as e:
            print(f"[ReplaceEngine] 全部替换失败: {e}")

        return count

    def preview_replace(
        self, result: SearchResult, replacement: str, max_preview: int = 5
    ) -> List[Tuple[str, str]]:
        """
        预览替换结果。

        返回:
            [(原文, 替换后), ...] 最多 max_preview 条
        """
        previews = []

        for match in result.matches[:max_preview]:
            original = match.text
            if result.pattern:
                try:
                    regex = re.compile(result.pattern)
                    re_match = regex.fullmatch(original)
                    if re_match:
                        new_text = re_match.expand(replacement)
                    else:
                        new_text = replacement
                except Exception:
                    new_text = replacement
            else:
                new_text = replacement

            previews.append((original, new_text))

        return previews

    def _write_back(self, new_text: str):
        """将新文本写回提供者"""
        encoded = self.provider.encode(new_text)
        block_size = self.provider.block_size
        total_blocks = max(1, (len(encoded) + block_size - 1) // block_size)

        self.provider.clear_dirty()

        for bid in range(total_blocks):
            start = bid * block_size
            end = min(start + block_size, len(encoded))
            self.provider.write_block(bid, encoded[start:end])

        if hasattr(self.provider, "_total_blocks"):
            self.provider._total_blocks = total_blocks
        if hasattr(self.provider, "_size"):
            self.provider._size = len(encoded)


# ============================================================
# 辅助函数
# ============================================================
