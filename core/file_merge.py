# -*- coding: utf-8 -*-
"""外部文件变更合并"""
import difflib
import os
from typing import Any, Dict, List, Optional, Tuple


class FileMergeDetector:
    """检测文件外部变更"""

    def __init__(self, provider):
        self.provider = provider
        self._last_mtime = 0.0
        self._last_size = 0

    def check_change(self) -> Optional[Dict[str, Any]]:
        """检查是否有外部变更"""
        if not self.provider or not self.provider.filepath:
            return None

        try:
            stat = os.stat(self.provider.filepath)
            current_mtime = stat.st_mtime
            current_size = stat.st_size

            # 首次调用
            if self._last_mtime == 0:
                self._last_mtime = current_mtime
                self._last_size = current_size
                return None

            # 检查是否变更
            if (abs(current_mtime - self._last_mtime) > 0.5 or
                    current_size != self._last_size):
                # 尝试读取
                try:
                    with open(self.provider.filepath, 'rb') as f:
                        new_content = f.read()
                    new_text = new_content.decode(
                        self.provider.encoding or 'utf-8',
                        errors='replace'
                    )
                except Exception as e:
                    return {
                        'type': 'deleted_or_error',
                        'message': str(e),
                    }

                old_mtime = self._last_mtime
                old_size = self._last_size
                self._last_mtime = current_mtime
                self._last_size = current_size

                return {
                    'type': 'modified',
                    'new_text': new_text,
                    'old_mtime': old_mtime,
                    'new_mtime': current_mtime,
                    'old_size': old_size,
                    'new_size': current_size,
                }
        except FileNotFoundError:
            return {'type': 'deleted'}
        except Exception:
            pass

        return None

    def update_baseline(self):
        """更新基准（保存后调用）"""
        if not self.provider or not self.provider.filepath:
            return
        try:
            stat = os.stat(self.provider.filepath)
            self._last_mtime = stat.st_mtime
            self._last_size = stat.st_size
        except Exception:
            pass


class ThreeWayMerger:
    """三方合并（原 / 本地 / 远程）

    实现说明（已重写，修复 F1/F2）：

    **F1 —— 末尾追加被静默丢弃**
        原实现先算出 local/remote 各自的改动区间，然后**只遍历
        `original_lines`**。当某方在文件末尾**追加**内容时，改动区间是
        `(len(original), len(new))`，起点等于原文长度 —— 而循环条件
        `while i < len(original_lines)` 让这些区间**永远不会被访问**：
        内容丢失且不记入 conflicts。

        实测 `merge("a\\nb\\n", "a\\nb\\nLOCAL_NEW\\n", "a\\nb\\nREMOTE_NEW\\n")`
        返回 `'a\\nb'`，两侧追加全丢、conflicts 为空。

    **F2 —— 末尾换行丢失**
        `splitlines()` 吃掉行尾，`'\\n'.join()` 再拼回来 —— 原文的末尾
        换行必然消失，导致每次合并都产生"无意义 diff"。

    现在改用标准的**逐区间三方合并**：分别对齐 original→local 与
    original→remote，把两者改动区间按原文坐标归并，逐区间决策
    （单侧改动采用该侧；双侧相同采用之；双侧不同记为冲突并插入标记）。
    归并循环的边界取自**两侧区间并集**，末尾追加因此不会被漏掉。
    """

    @staticmethod
    def _changes(matcher) -> List[Tuple[int, int, List[str]]]:
        """把 opcodes 里非 equal 的部分转成 (原文起点, 原文终点, 新内容)"""
        real = matcher.get_opcodes()
        seq = matcher.b
        out = []
        for tag, i1, i2, j1, j2 in real:
            if tag != 'equal':
                out.append((i1, i2, list(seq[j1:j2])))
        # 同一原文起点只保留覆盖更长的一个，避免重复决策
        dedup: Dict[int, Tuple[int, int, List[str]]] = {}
        for s, e, lines in out:
            prev = dedup.get(s)
            if prev is None or (e - s) > (prev[1] - prev[0]):
                dedup[s] = (s, e, lines)
        return [dedup[k] for k in sorted(dedup)]

    @staticmethod
    def merge(original: str, local: str, remote: str) -> Dict[str, Any]:
        """
        三方合并。

        参数:
            original: 最后保存的版本
            local: 编辑器当前内容
            remote: 磁盘新版

        返回:
            {
                'merged': str,
                'conflicts': [{'line', 'local', 'remote'}],
                'auto_merged': bool,
                'strategy': str,
            }
        """
        # 单侧未改动：直接采用另一侧（原样返回，保留其末尾换行语义）
        if local == original:
            return {
                'merged': remote,
                'conflicts': [],
                'auto_merged': True,
                'strategy': 'take_remote',
            }
        if remote == original:
            return {
                'merged': local,
                'conflicts': [],
                'auto_merged': True,
                'strategy': 'keep_local',
            }

        original_lines = original.splitlines()
        local_lines = local.splitlines()
        remote_lines = remote.splitlines()

        local_changes = ThreeWayMerger._changes(
            difflib.SequenceMatcher(None, original_lines, local_lines)
        )
        remote_changes = ThreeWayMerger._changes(
            difflib.SequenceMatcher(None, original_lines, remote_lines)
        )

        merged_lines: List[str] = []
        conflicts: List[Dict[str, Any]] = []
        n_orig = len(original_lines)

        li = ri = 0
        i = 0
        guard = 0
        max_steps = (n_orig + len(local_changes) + len(remote_changes)) * 4 + 32

        while (li < len(local_changes) or ri < len(remote_changes)
               or i < n_orig):
            guard += 1
            if guard > max_steps:      # 防御：绝不死循环
                break

            lc = local_changes[li] if li < len(local_changes) else None
            rc = remote_changes[ri] if ri < len(remote_changes) else None

            # 1) 先原样输出到"下一个改动区间起点"
            starts = [n_orig]
            if lc is not None:
                starts.append(lc[0])
            if rc is not None:
                starts.append(rc[0])
            nxt = min(starts)
            while i < nxt:
                merged_lines.append(original_lines[i])
                i += 1

            # 2) 处理起点等于 i 的改动（含两端都有的并列改动）
            took = False
            if lc is not None and lc[0] <= i:
                if rc is not None and rc[0] <= i:
                    if lc[2] == rc[2]:
                        merged_lines.extend(lc[2])          # 相同改动
                    else:
                        conflicts.append({
                            'line': i,
                            'local': lc[2],
                            'remote': rc[2],
                        })
                        merged_lines.append("<<<<<<< LOCAL")
                        merged_lines.extend(lc[2])
                        merged_lines.append("=======")
                        merged_lines.extend(rc[2])
                        merged_lines.append(">>>>>>> REMOTE")
                    i = max(i, lc[1], rc[1])
                    li += 1
                    ri += 1
                else:
                    merged_lines.extend(lc[2])
                    i = max(i, lc[1])
                    li += 1
                took = True
            elif rc is not None and rc[0] <= i:
                merged_lines.extend(rc[2])
                i = max(i, rc[1])
                ri += 1
                took = True

            if took:
                continue

            # 3) 剩下的情况：原文还有行就输出一行；否则说明有"纯追加"
            #    区间落在原文末尾之外，直接采用
            if i < n_orig:
                merged_lines.append(original_lines[i])
                i += 1
            elif li < len(local_changes):
                merged_lines.extend(local_changes[li][2])
                i = max(i, local_changes[li][1])
                li += 1
            elif ri < len(remote_changes):
                merged_lines.extend(remote_changes[ri][2])
                i = max(i, remote_changes[ri][1])
                ri += 1
            else:
                break

        merged = '\n'.join(merged_lines)

        # F2：恢复末尾换行
        # 只要原文（或任一侧）以换行结尾，结果也应带末尾换行 ——
        # 否则每次合并都会吃掉文件末尾的 LF/CRLF，产生无意义 diff。
        if merged and not merged.endswith('\n') and (
            original.endswith('\n') or local.endswith('\n')
            or remote.endswith('\n')
        ):
            merged += '\n'

        return {
            'merged': merged,
            'conflicts': conflicts,
            'auto_merged': len(conflicts) == 0,
            'strategy': 'three_way',
        }
