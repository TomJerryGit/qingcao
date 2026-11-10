# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""搜索聚合入口（v2.24 拆分：common/engine/replace + 顶层函数）。"""

from core.search_common import *  # noqa: F401,F403
from core.search_engine import *  # noqa: F401,F403
from core.search_replace import *  # noqa: F401,F403


def build_search_options(pattern: str, **kwargs) -> SearchOptions:
    """
    构建搜索选项的便捷函数。

    用法:
        options = build_search_options("hello", case_sensitive=True)
    """
    # P7：走 from_preferences()，让 search_threads / use_hyperscan /
    # search_timeout 三个偏好对便捷入口同样生效。
    options = SearchOptions.from_preferences(pattern=pattern)
    for key, value in kwargs.items():
        if hasattr(options, key):
            setattr(options, key, value)
    return options


def quick_search(provider, pattern: str, **kwargs) -> SearchResult:
    """
    快速搜索的便捷函数。

    用法:
        result = quick_search(provider, "hello", is_regex=True)
    """
    options = build_search_options(pattern, **kwargs)
    engine = SearchEngine(provider, options)
    return engine.search()


def find_in_files(root_dir: str, pattern: str, file_filter: str = "*.py", **kwargs) -> SearchResult:
    """
    在文件中搜索的便捷函数。

    用法:
        result = find_in_files("/path", "TODO", "*.py")
    """
    options = build_search_options(pattern, **kwargs)
    searcher = FileSearcher()
    return searcher.search_sync(root_dir, options, file_filter)


def highlight_matches_in_text(
    text: str, matches: List[SearchMatch], left: str = "<<", right: str = ">>"
) -> str:
    """
    在文本中标记匹配位置（用于调试）。

    P1-1: 改为用 char_start / char_end（字符偏移）索引 str。
    """
    if not matches:
        return text

    # 按位置排序
    sorted_matches = sorted(matches, key=lambda m: m.char_start)

    result = []
    last_pos = 0
    for m in sorted_matches:
        if m.char_start < last_pos:
            continue  # 跳过重叠
        result.append(text[last_pos : m.char_start])
        result.append(left + m.text + right)
        last_pos = m.char_end

    result.append(text[last_pos:])
    return "".join(result)


def count_matches_in_text(text: str, pattern: str, is_regex: bool = False) -> int:
    """统计文本中匹配数量（不构建 SearchMatch 对象）"""
    try:
        if not is_regex:
            pattern = re.escape(pattern)
        return len(re.findall(pattern, text))
    except Exception:
        return 0


def extract_lines(text: str, matches: List[SearchMatch]) -> Dict[int, str]:
    """提取所有包含匹配的行的文本"""
    lines = text.splitlines()
    result = {}
    for m in matches:
        if 1 <= m.line <= len(lines):
            result[m.line] = lines[m.line - 1]
    return result


# ============================================================
# 模块测试
# ============================================================
