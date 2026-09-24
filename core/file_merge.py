# -*- coding: utf-8 -*-
"""外部文件变更合并"""
import os
import time
import difflib
from typing import Optional, Dict, Any, List, Tuple


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
    """三方合并（原 / 本地 / 远程）"""

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
                'conflicts': [(line, local_text, remote_text)],
                'auto_merged': bool,
            }
        """
        original_lines = original.splitlines()
        local_lines = local.splitlines()
        remote_lines = remote.splitlines()

        # 简单策略：如果只有一方修改，直接用那一方
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

        # 双方都改了：尝试逐行合并
        merged_lines = []
        conflicts = []

        matcher = difflib.SequenceMatcher(
            None, original_lines, local_lines
        )
        local_ops = matcher.get_opcodes()

        matcher2 = difflib.SequenceMatcher(
            None, original_lines, remote_lines
        )
        remote_ops = matcher2.get_opcodes()

        # 建立修改映射
        local_changes = {}
        for tag, i1, i2, j1, j2 in local_ops:
            if tag != 'equal':
                local_changes[(i1, i2)] = local_lines[j1:j2]

        remote_changes = {}
        for tag, i1, i2, j1, j2 in remote_ops:
            if tag != 'equal':
                remote_changes[(i1, i2)] = remote_lines[j1:j2]

        # 逐行合并
        i = 0
        while i < len(original_lines):
            local_change = None
            remote_change = None

            for (s, e), lines in local_changes.items():
                if s <= i < e:
                    local_change = (s, e, lines)
                    break

            for (s, e), lines in remote_changes.items():
                if s <= i < e:
                    remote_change = (s, e, lines)
                    break

            if local_change and remote_change:
                # 双方都改：冲突
                if local_change[2] == remote_change[2]:
                    # 相同修改，直接用
                    merged_lines.extend(local_change[2])
                    i = max(local_change[1], remote_change[1])
                else:
                    # 真冲突
                    conflicts.append({
                        'line': i,
                        'local': local_change[2],
                        'remote': remote_change[2],
                    })
                    # 默认取本地，加冲突标记
                    merged_lines.append("<<<<<<< LOCAL")
                    merged_lines.extend(local_change[2])
                    merged_lines.append("=======")
                    merged_lines.extend(remote_change[2])
                    merged_lines.append(">>>>>>> REMOTE")
                    i = max(local_change[1], remote_change[1])
            elif local_change:
                merged_lines.extend(local_change[2])
                i = local_change[1]
            elif remote_change:
                merged_lines.extend(remote_change[2])
                i = remote_change[1]
            else:
                merged_lines.append(original_lines[i])
                i += 1

        return {
            'merged': '\n'.join(merged_lines),
            'conflicts': conflicts,
            'auto_merged': len(conflicts) == 0,
            'strategy': 'three_way',
        }