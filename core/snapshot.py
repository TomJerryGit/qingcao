# -*- coding: utf-8 -*-
"""会话快照管理器"""
import datetime
import json
import os
from typing import Any, Dict, List, Optional


# 基于应用根目录的**绝对路径**（相对路径会随工作目录变化）
#
# ★ 修复（接线时发现）：原实现是 `SNAPSHOT_DIR = "data/snapshots"` ——
#   相对路径，取决于进程工作目录。
#   打包后的应用从快捷方式/其他目录启动时（实测 cwd=C:\），快照会被写到
#   `C:\data\snapshots`；下次从别处启动又变成另一个目录 →
#   **用户保存的快照"凭空消失"**。
#   这与本仓库已修复的 `Document._draft_dir`、`CRASH_DIR` 是同一类缺陷，
#   统一改为从 `app_root_dir()` 派生。
try:
    from infrastructure.plugin_loader import app_root_dir as _app_root
    SNAPSHOT_DIR = os.path.join(_app_root(), "data", "snapshots")
except Exception:  # pragma: no cover - 仅在基础设施不可用时
    SNAPSHOT_DIR = "data/snapshots"


class SnapshotManager:
    """会话快照管理器"""

    def __init__(self):
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    def save_snapshot(self, name, tabs, main_window=None) -> bool:
        """保存快照"""
        try:
            data = {
                'name': name,
                'created_at': datetime.datetime.now().isoformat(),
                'files': [],
                'geometry': {},
            }

            # 文件列表
            for i in range(tabs.count()):
                widget = tabs.widget(i)
                if not hasattr(widget, 'proxy'):
                    continue
                proxy = widget.proxy
                if not proxy or not proxy.document:
                    continue

                info = {
                    'filepath': proxy.document.filepath or '',
                    'encoding': proxy.document.encoding or 'utf-8',
                    'cursor_line': 0,
                    'cursor_col': 0,
                    'first_line': 0,
                    'is_current': i == tabs.currentIndex(),
                }

                try:
                    if proxy.sc:
                        line, col = proxy.sc.getCursorPosition()
                        info['cursor_line'] = line
                        info['cursor_col'] = col
                        info['first_line'] = proxy.sc.SendScintilla(
                            proxy.sc.SCI_GETFIRSTVISIBLELINE
                        )
                except Exception:
                    pass

                data['files'].append(info)

            # 窗口几何
            if main_window:
                try:
                    geo = main_window.geometry()
                    data['geometry'] = {
                        'x': geo.x(), 'y': geo.y(),
                        'w': geo.width(), 'h': geo.height(),
                        'maximized': main_window.isMaximized(),
                    }
                except Exception:
                    pass

            # 保存
            filepath = self._get_snapshot_path(name)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            return True
        except Exception as e:
            print("[Snapshot] 保存失败: %s" % e)
            return False

    def load_snapshot(self, name) -> Optional[Dict[str, Any]]:
        """加载快照"""
        filepath = self._get_snapshot_path(name)
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def restore_snapshot(self, name, tabs, main_window=None) -> int:
        """恢复快照"""
        data = self.load_snapshot(name)
        if not data:
            return 0

        # 关闭当前所有标签
        for i in range(tabs.count() - 1, -1, -1):
            try:
                tabs.close_tab(i)
            except Exception:
                pass

        # 打开文件
        count = 0
        current_idx = -1
        for i, finfo in enumerate(data.get('files', [])):
            fpath = finfo.get('filepath', '')
            if not fpath or not os.path.exists(fpath):
                continue

            try:
                proxy = tabs.open_file(fpath)
                if proxy and proxy.sc:
                    # 恢复光标
                    proxy.sc.setCursorPosition(
                        finfo.get('cursor_line', 0),
                        finfo.get('cursor_col', 0)
                    )
                    # 恢复滚动
                    if finfo.get('first_line', 0) > 0:
                        proxy.sc.SendScintilla(
                            proxy.sc.SCI_SETFIRSTVISIBLELINE,
                            finfo['first_line']
                        )
                if finfo.get('is_current'):
                    current_idx = i
                count += 1
            except Exception as e:
                print("[Snapshot] 恢复 %s 失败: %s" % (fpath, e))

        # 恢复活动标签
        if current_idx >= 0 and current_idx < tabs.count():
            tabs.setCurrentIndex(current_idx)

        # 恢复窗口几何
        if main_window and data.get('geometry'):
            g = data['geometry']
            try:
                main_window.setGeometry(g['x'], g['y'], g['w'], g['h'])
                if g.get('maximized'):
                    main_window.showMaximized()
            except Exception:
                pass

        return count

    def list_snapshots(self) -> List[Dict[str, Any]]:
        """列出所有快照"""
        result = []
        if not os.path.isdir(SNAPSHOT_DIR):
            return result

        for fname in os.listdir(SNAPSHOT_DIR):
            if not fname.endswith('.json'):
                continue
            filepath = os.path.join(SNAPSHOT_DIR, fname)
            try:
                with open(filepath, encoding='utf-8') as f:
                    data = json.load(f)
                result.append({
                    'name': data.get('name', fname[:-5]),
                    'created_at': data.get('created_at', ''),
                    'file_count': len(data.get('files', [])),
                    'filepath': filepath,
                })
            except Exception:
                pass

        result.sort(key=lambda x: x['created_at'], reverse=True)
        return result

    def delete_snapshot(self, name) -> bool:
        """删除快照"""
        filepath = self._get_snapshot_path(name)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                return True
            except Exception:
                pass
        return False

    def _get_snapshot_path(self, name):
        # 清理文件名
        safe_name = "".join(
            c if c.isalnum() or c in '_-' else '_'
            for c in name
        )
        return os.path.join(SNAPSHOT_DIR, safe_name + '.json')