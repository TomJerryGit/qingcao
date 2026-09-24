#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P1-1 字符/字节偏移修复
============================
修复含中文文件的搜索/高亮/替换错位问题。

问题:
    core/search.py 的 iter_matches 把"字节偏移 + 字符偏移"混用:
        global_start = combined_offset + m.start()
                        ^^^^^^^^^^^^^^   ^^^^^^^^^^
                        字节偏移          字符偏移

    纯 ASCII 下偶然正确，含中文时所有匹配位置错误。

方案:
    SearchMatch 增加 char_start / char_end 字段。
    start / end        字节偏移（Scintilla 用）
    char_start/char_end 字符偏移（Python 字符串索引用）

    同时修复 ReplaceEngine / SearchEngine.replace_all /
    _replace_range 用错索引的问题。

特性:
    - 幂等
    - 每项独立处理
    - 修改前备份 *.bak.p1cb
    - 修改后 compile() 验证

用法:
    python fix_p1_char_byte.py --dry-run
    python fix_p1_char_byte.py
    python fix_p1_char_byte.py --no-backup
"""

import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple, List

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.p1cb"


# ============================================================
# 输出
# ============================================================
def print_header(t): print(f"\n{'=' * 60}\n{t}\n{'=' * 60}")
def print_ok(m):   print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")


# ============================================================
# 工具
# ============================================================
def backup(path: Path) -> bool:
    bak = Path(str(path) + BACKUP_SUFFIX)
    if bak.exists():
        return True
    try:
        shutil.copy2(path, bak)
        print_info(f"已备份: {bak.name}")
        return True
    except Exception as e:
        print_fail(f"备份失败: {e}")
        return False


def write_back(path: Path, content: str, no_backup: bool) -> bool:
    if not no_backup and not backup(path):
        return False
    try:
        path.write_text(content, encoding='utf-8', newline='\n')
        return True
    except Exception as e:
        print_fail(f"写回失败: {e}")
        return False


def validate_python(content: str, filepath: str) -> Tuple[bool, str]:
    try:
        compile(content, filepath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"


def apply_multi(path: Path,
                sections: List[Tuple[str, str, str]],
                no_backup: bool) -> str:
    """
    多段替换。

    sections: [(marker, old, new), ...]
    返回: applied / skipped / failed
    """
    if not path.exists():
        print_fail(f"{path.relative_to(ROOT)}: 文件不存在")
        return 'failed'

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"{path.relative_to(ROOT)}: 读取失败 ({e})")
        return 'failed'

    # 幂等：所有 marker 都命中 → 视为已修复
    if all(m in content for m, _, _ in sections):
        print_skip(f"{path.relative_to(ROOT)}: 已修复")
        return 'skipped'

    # 逐段应用
    new_content = content
    for i, (marker, old, new) in enumerate(sections, 1):
        if marker in new_content:
            print_info(f"  段 {i}: 已应用，跳过")
            continue

        cnt = new_content.count(old)
        if cnt == 0:
            print_fail(f"  段 {i}: 锚点未找到")
            print_info("  期望锚点前 3 行：")
            for line in old.split('\n')[:3]:
                print(f"      | {line}")
            return 'failed'
        if cnt > 1:
            print_fail(f"  段 {i}: 锚点重复 {cnt} 次")
            return 'failed'

        new_content = new_content.replace(old, new, 1)
        print_info(f"  段 {i}: 已替换")

    # 语法验证
    ok, err = validate_python(new_content, str(path))
    if not ok:
        print_fail(f"{path.relative_to(ROOT)}: 语法错误 ({err})")
        return 'failed'

    if not write_back(path, new_content, no_backup):
        return 'failed'

    print_ok(f"{path.relative_to(ROOT)}: 已修复")
    return 'applied'


# ============================================================
# 段 1: SearchMatch 数据类
# ============================================================
M1 = "char_start: int = 0           # 字符偏移（Python 索引）"

OLD1 = '''@dataclass
class SearchMatch:
    """
    单个匹配结果。

    包含匹配的位置信息、文本内容和上下文。
    """

    start: int                    # 起始字符位置
    end: int                      # 结束字符位置（不含）
    text: str = ""                # 匹配的文本
    line: int = 0                 # 行号（1 开始）
    col: int = 0                  # 列号（0 开始）
    line_text: str = ""           # 所在行的完整文本
    context: str = ""             # 上下文预览
    groups: Tuple[str, ...] = ()  # 正则捕获组

    @property
    def length(self) -> int:
        """匹配长度"""
        return self.end - self.start

    def contains(self, pos: int) -> bool:
        """检查指定位置是否在匹配范围内"""
        return self.start <= pos < self.end

    def overlaps(self, other: 'SearchMatch') -> bool:
        """检查是否与另一匹配重叠"""
        return not (self.end <= other.start or other.end <= self.start)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            'start': self.start,
            'end': self.end,
            'text': self.text,
            'line': self.line,
            'col': self.col,
            'line_text': self.line_text,
            'context': self.context,
            'groups': list(self.groups),
        }'''

NEW1 = '''@dataclass
class SearchMatch:
    """
    单个匹配结果。

    位置说明（P1-1）:
        start / end           字节偏移（Scintilla 用）
        char_start / char_end 字符偏移（Python 字符串索引用）

        纯 ASCII 文本两者相等；含中文时字节偏移 > 字符偏移。
    """

    start: int                    # 字节偏移（Scintilla）
    end: int                      # 字节偏移（不含）
    char_start: int = 0           # 字符偏移（Python 索引）
    char_end: int = 0             # 字符偏移（不含）
    text: str = ""                # 匹配的文本
    line: int = 0                 # 行号（1 开始）
    col: int = 0                  # 列号（0 开始）
    line_text: str = ""           # 所在行的完整文本
    context: str = ""             # 上下文预览
    groups: Tuple[str, ...] = ()  # 正则捕获组

    @property
    def length(self) -> int:
        """匹配长度（字节）"""
        return self.end - self.start

    def contains(self, pos: int) -> bool:
        """检查指定字节位置是否在匹配范围内"""
        return self.start <= pos < self.end

    def overlaps(self, other: 'SearchMatch') -> bool:
        """检查是否与另一匹配重叠"""
        return not (self.end <= other.start or other.end <= self.start)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            'start': self.start,
            'end': self.end,
            'char_start': self.char_start,
            'char_end': self.char_end,
            'text': self.text,
            'line': self.line,
            'col': self.col,
            'line_text': self.line_text,
            'context': self.context,
            'groups': list(self.groups),
        }'''


# ============================================================
# 段 2: iter_matches 重写
# ============================================================
M2 = "P1-1 修复：原分块逻辑把"

OLD2 = '''    def iter_matches(self) -> Iterator[SearchMatch]:
        """
        迭代所有匹配（生成器）。

        适用于流式处理，避免一次性加载所有结果。
        """
        if not self._regex:
            return

        # 逐块读取
        block_size = self.provider.block_size
        total_blocks = self.provider.total_blocks

        # 跨块缓冲
        carry_over = b''
        carry_offset = 0

        count = 0

        for bid in range(total_blocks):
            if self.is_cancelled():
                return

            if count >= self.options.max_results:
                return

            # 读取块
            try:
                block_data = self.provider.read_block(bid)
            except Exception:
                continue

            # 合并跨块数据
            combined = carry_over + block_data
            combined_offset = carry_offset

            # 解码
            try:
                text = combined.decode(self.provider.encoding, errors='replace')
            except Exception:
                continue

            # 匹配
            for m in self._regex.finditer(text):
                if self.is_cancelled():
                    return
                if count >= self.options.max_results:
                    return

                # 计算全局位置
                global_start = combined_offset + m.start()
                global_end = combined_offset + m.end()

                # 检查范围
                if global_start < self.options.start_pos:
                    continue
                if (self.options.end_pos >= 0 and
                        global_start >= self.options.end_pos):
                    return

                # 构建匹配对象
                match = self._build_match(global_start, global_end, m, text)
                yield match
                count += 1

            # 保留最后一部分作为跨块缓冲（防止跨块匹配丢失）
            if len(block_data) > 0:
                overlap_size = max(256, block_size // 4)
                if len(combined) > overlap_size:
                    carry_over = combined[-overlap_size:].encode(
                        self.provider.encoding, errors='replace'
                    )
                    carry_offset = combined_offset + len(combined) - overlap_size
                else:
                    carry_over = b''
                    carry_offset = 0'''

NEW2 = '''    def iter_matches(self) -> Iterator[SearchMatch]:
        """
        迭代所有匹配（生成器）。

        P1-1 修复：原分块逻辑把"字节偏移 + 字符偏移"混用，
        导致含中文文件搜索位置错误。改为一次性读取全文，
        匹配位置统一换算：字节偏移 + 字符偏移双写。

        性能：O(N) 正则扫描，大文件也能接受。
        """
        if not self._regex:
            return

        # 一次性读取全文（避免分块的偏移换算问题）
        try:
            text = self.provider.read_text()
        except Exception:
            return

        if not text:
            return

        encoding = self.provider.encoding or 'utf-8'
        count = 0

        # 缓存上一次匹配的字节位置，避免每次重算前缀
        last_char_end = 0
        last_byte_end = 0

        for m in self._regex.finditer(text):
            if self.is_cancelled():
                return
            if count >= self.options.max_results:
                return

            char_start = m.start()
            char_end = m.end()

            # 字符偏移 -> 字节偏移（增量计算）
            if char_start >= last_char_end:
                byte_start = last_byte_end + len(
                    text[last_char_end:char_start].encode(
                        encoding, errors='replace'
                    )
                )
            else:
                # finditer 是顺序的，正常不会走这里
                byte_start = len(
                    text[:char_start].encode(
                        encoding, errors='replace'
                    )
                )

            byte_end = byte_start + len(
                text[char_start:char_end].encode(
                    encoding, errors='replace'
                )
            )

            last_char_end = char_end
            last_byte_end = byte_end

            # 范围过滤（用字节偏移）
            if byte_start < self.options.start_pos:
                continue
            if (self.options.end_pos >= 0 and
                    byte_start >= self.options.end_pos):
                return

            match = self._build_match(
                byte_start, byte_end,
                char_start, char_end,
                m, text,
            )
            yield match
            count += 1'''


# ============================================================
# 段 3: _search_multi_threaded 简化
# ============================================================
M3 = "P1-1: 已废弃多线程分块"

OLD3 = '''    def _search_multi_threaded(self, result: SearchResult):
        """多线程搜索"""
        total_blocks = self.provider.total_blocks
        threads = min(self.options.threads, MAX_THREADS, total_blocks)

        if threads <= 1:
            self._search_single_threaded(result)
            return

        # 分配块范围给各线程
        chunk_size = max(1, total_blocks // threads)
        chunks = []
        for i in range(threads):
            start = i * chunk_size
            end = min(start + chunk_size, total_blocks) if i < threads - 1 else total_blocks
            if start < end:
                chunks.append((start, end))

        # 并行搜索
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {
                executor.submit(self._search_range, start, end): (start, end)
                for start, end in chunks
            }

            all_matches: Dict[int, List[SearchMatch]] = {}

            for future in as_completed(futures):
                if self.is_cancelled():
                    result.cancelled = True
                    break

                start, end = futures[future]
                try:
                    matches = future.result()
                    all_matches[start] = matches
                except Exception as e:
                    print(f"[SearchEngine] 线程失败: {e}")

        # 按块顺序合并结果
        for start in sorted(all_matches.keys()):
            for match in all_matches[start]:
                if not result.add_match(match):
                    return'''

NEW3 = '''    def _search_multi_threaded(self, result: SearchResult):
        """多线程搜索（P1-1: 已废弃多线程分块）

        说明:
            原实现把文件分块并行搜索，但匹配位置需要"全局字
            节偏移"，分块后跨块偏移换算极其复杂且容易出错。
            改为单线程一次性搜索；正则扫描本身是 O(N)，
            分块对性能提升有限。
        """
        self._search_single_threaded(result)'''


# ============================================================
# 段 4: _search_range 简化
# ============================================================
M4 = "P1-1: _search_range 已废弃"

OLD4 = '''    def _search_range(self, start_block: int,
                       end_block: int) -> List[SearchMatch]:
        """搜索指定块范围"""
        matches = []

        if not self._regex:
            return matches

        block_size = self.provider.block_size
        carry_over = b''
        carry_offset = 0

        for bid in range(start_block, end_block):
            if self.is_cancelled():
                return matches

            try:
                block_data = self.provider.read_block(bid)
            except Exception:
                continue

            combined = carry_over + block_data
            combined_offset = carry_offset

            try:
                text = combined.decode(self.provider.encoding, errors='replace')
            except Exception:
                continue

            for m in self._regex.finditer(text):
                if self.is_cancelled():
                    return matches

                global_start = combined_offset + m.start()
                global_end = combined_offset + m.end()

                if global_start < self.options.start_pos:
                    continue
                if (self.options.end_pos >= 0 and
                        global_start >= self.options.end_pos):
                    return matches

                match = self._build_match(global_start, global_end, m, text)
                matches.append(match)

            # 保留跨块缓冲
            if len(block_data) > 0:
                overlap_size = max(256, block_size // 4)
                if len(combined) > overlap_size:
                    carry_over = combined[-overlap_size:].encode(
                        self.provider.encoding, errors='replace'
                    )
                    carry_offset = combined_offset + len(combined) - overlap_size
                else:
                    carry_over = b''
                    carry_offset = 0

        return matches'''

NEW4 = '''    def _search_range(self, start_block: int,
                       end_block: int) -> List[SearchMatch]:
        """P1-1: _search_range 已废弃。

        保留方法名以兼容外部可能的调用，但不再使用。
        """
        return []'''


# ============================================================
# 段 5: _build_match 双写偏移
# ============================================================
M5 = "P1-1: 双写字节/字符偏移"

OLD5 = '''    def _build_match(self, start: int, end: int,
                      re_match, text: str) -> SearchMatch:
        """构建 SearchMatch 对象"""
        # 计算行号列号
        line, col = self._position_to_line_col(start)

        # 获取所在行文本
        line_text = self._get_line_text(line)

        # 上下文预览
        context = self._make_context(text, re_match.start(), re_match.end())

        # 捕获组
        groups = tuple(g for g in re_match.groups()) if re_match.groups() else ()

        return SearchMatch(
            start=start,
            end=end,
            text=re_match.group(0),
            line=line,
            col=col,
            line_text=line_text,
            context=context,
            groups=groups,
        )'''

NEW5 = '''    def _build_match(self, byte_start: int, byte_end: int,
                      char_start: int, char_end: int,
                      re_match, text: str) -> SearchMatch:
        """构建 SearchMatch 对象（P1-1: 双写字节/字符偏移）"""
        # 用字符偏移计算行列
        line, col = self._position_to_line_col(char_start)

        line_text = self._get_line_text(line)

        # 上下文预览（text 内部是字符偏移）
        context = self._make_context(text, char_start, char_end)

        groups = (tuple(g for g in re_match.groups())
                  if re_match.groups() else ())

        return SearchMatch(
            start=byte_start,
            end=byte_end,
            char_start=char_start,
            char_end=char_end,
            text=re_match.group(0),
            line=line,
            col=col,
            line_text=line_text,
            context=context,
            groups=groups,
        )'''


# ============================================================
# 段 6: SearchEngine.replace_all 用字符偏移
# ============================================================
M6 = "self._replace_range(match.char_start, match.char_end"

OLD6 = '''                # 更新提供者内容
                self._replace_range(match.start, match.end, new_text)
                count += 1'''

NEW6 = '''                # 更新提供者内容（P1-1: 用字符偏移）
                self._replace_range(
                    match.char_start, match.char_end, new_text
                )
                count += 1'''


# ============================================================
# 段 7: ReplaceEngine.replace_one 用字符偏移
# ============================================================
M7 = "text[:match.char_start] + replacement +"

OLD7 = '''        try:
            # 读取全文
            text = self.provider.read_text()

            # 执行替换
            new_text = text[:match.start] + replacement + text[match.end:]

            # 写回
            self._write_back(new_text)
            return True

        except Exception as e:
            print(f"[ReplaceEngine] 替换失败: {e}")
            return False'''

NEW7 = '''        try:
            # 读取全文
            text = self.provider.read_text()

            # 执行替换（P1-1: 用字符偏移索引 str）
            new_text = (text[:match.char_start] + replacement +
                        text[match.char_end:])

            # 写回
            self._write_back(new_text)
            return True

        except Exception as e:
            print(f"[ReplaceEngine] 替换失败: {e}")
            return False'''


# ============================================================
# 段 8: ReplaceEngine.replace_all 用字符偏移
# ============================================================
M8 = "original = text[match.char_start:match.char_end]"

OLD8 = '''            # 从后往前替换
            new_text = text
            for match in reversed(result.matches):
                try:
                    if is_regex and regex:
                        # 正则替换
                        original = text[match.start:match.end]
                        re_match = regex.fullmatch(original)
                        if re_match:
                            repl = re_match.expand(replacement)
                        else:
                            repl = replacement
                    else:
                        repl = replacement

                    new_text = (new_text[:match.start] + repl +
                                new_text[match.end:])
                    count += 1

                except Exception:
                    continue

            # 写回
            self._write_back(new_text)'''

NEW8 = '''            # 从后往前替换（P1-1: 用字符偏移索引 str）
            new_text = text
            for match in reversed(result.matches):
                try:
                    if is_regex and regex:
                        original = text[match.char_start:match.char_end]
                        re_match = regex.fullmatch(original)
                        if re_match:
                            repl = re_match.expand(replacement)
                        else:
                            repl = replacement
                    else:
                        repl = replacement

                    new_text = (new_text[:match.char_start] + repl +
                                new_text[match.char_end:])
                    count += 1

                except Exception:
                    continue

            # 写回
            self._write_back(new_text)'''


# ============================================================
# 段 9: highlight_matches_in_text 用字符偏移
# ============================================================
M9 = "key=lambda m: m.char_start"

OLD9 = '''def highlight_matches_in_text(text: str, matches: List[SearchMatch],
                                left: str = "<<", right: str = ">>") -> str:
    """
    在文本中标记匹配位置（用于调试）。

    参数:
        text: 原始文本
        matches: 匹配列表
        left: 左标记
        right: 右标记

    返回:
        标记后的文本
    """
    if not matches:
        return text

    # 按位置排序
    sorted_matches = sorted(matches, key=lambda m: m.start)

    result = []
    last_pos = 0
    for m in sorted_matches:
        if m.start < last_pos:
            continue  # 跳过重叠
        result.append(text[last_pos:m.start])
        result.append(left + m.text + right)
        last_pos = m.end

    result.append(text[last_pos:])
    return ''.join(result)'''

NEW9 = '''def highlight_matches_in_text(text: str, matches: List[SearchMatch],
                                left: str = "<<", right: str = ">>") -> str:
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
        result.append(text[last_pos:m.char_start])
        result.append(left + m.text + right)
        last_pos = m.char_end

    result.append(text[last_pos:])
    return ''.join(result)'''


# ============================================================
# 主流程
# ============================================================
SECTIONS = [
    (M1, OLD1, NEW1, "SearchMatch 数据类（加 char_start/char_end）"),
    (M2, OLD2, NEW2, "iter_matches（一次性读取 + 双写偏移）"),
    (M3, OLD3, NEW3, "_search_multi_threaded（改为单线程）"),
    (M4, OLD4, NEW4, "_search_range（废弃）"),
    (M5, OLD5, NEW5, "_build_match（双写偏移）"),
    (M6, OLD6, NEW6, "SearchEngine.replace_all（用字符偏移）"),
    (M7, OLD7, NEW7, "ReplaceEngine.replace_one（用字符偏移）"),
    (M8, OLD8, NEW8, "ReplaceEngine.replace_all（用字符偏移）"),
    (M9, OLD9, NEW9, "highlight_matches_in_text（用字符偏移）"),
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="P1-1 字符/字节偏移修复"
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("P1-1 字符/字节偏移修复")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")
    print(f"  备份:     {'禁用' if args.no_backup else '启用'}")

    target = ROOT / "core" / "search.py"

    if args.dry_run:
        print()
        print_info(f"目标文件: {target.relative_to(ROOT)}")
        print_info(f"将替换 {len(SECTIONS)} 段：")
        for i, (_, _, _, desc) in enumerate(SECTIONS, 1):
            print_info(f"  {i}. {desc}")

        # 检测当前状态
        if not target.exists():
            print()
            print_fail("文件不存在")
            return 1

        content = target.read_text(encoding='utf-8')
        print()
        print_info("锚点匹配检测：")
        all_ok = True
        for i, (marker, old, _, _) in enumerate(SECTIONS, 1):
            if marker in content:
                print_ok(f"  段 {i}: 已应用（幂等）")
            elif old in content:
                print_ok(f"  段 {i}: 锚点就绪")
            else:
                print_fail(f"  段 {i}: 锚点未找到")
                all_ok = False

        print()
        if all_ok:
            print_info("去掉 --dry-run 即可应用")
            return 0
        else:
            print_fail("有锚点未就绪，请检查")
            return 1

    print()
    result = apply_multi(
        target,
        [(m, o, n) for (m, o, n, _) in SECTIONS],
        args.no_backup,
    )

    print()
    print("=" * 60)
    if result == 'failed':
        print("✗ 修复失败")
        print("=" * 60)
        return 1
    if result == 'skipped':
        print("✓ 已是最新（无需修复）")
        print("=" * 60)
        return 0

    print("✓ 修复完成")
    print("=" * 60)
    print()
    print("验证步骤:")
    print("  1. 语法:")
    print("     python -c \"import ast; "
          "ast.parse(open('core/search.py', encoding='utf-8').read()); "
          "print('OK')\"")
    print("  2. 跑测试: python tests/run_all.py")
    print("  3. 手工验证:")
    print("     python main.py")
    print("     打开含中文的文件，Ctrl+F 搜索中文，")
    print("     点'全部高亮'和'下一个'应正确定位")
    print()
    print("清理备份:")
    print("  Windows:     del core\\search.py.bak.p1cb")
    print("  Linux/macOS: rm core/search.py.bak.p1cb")

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n脚本异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)