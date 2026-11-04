# -*- coding: utf-8 -*-
"""插件本地评分 MVP（v2.20 P1-3）

仅本机保存，不上传；JSON 存储，可被未来远端评分替代。
环境变量 QINGCAO_PLUGIN_RATINGS_FILE 可覆盖路径（测试用）。
"""

import io
import json
import os
import tempfile
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(ROOT, "data", "plugin_ratings.json")


def ratings_path():
    return os.environ.get("QINGCAO_PLUGIN_RATINGS_FILE") or DEFAULT_PATH


def rating_text(stars):
    n = max(0, min(5, int(stars or 0)))
    return "★" * n + "☆" * (5 - n) + (" 本地评分" if n else " 未评分")


class LocalRatings:
    def __init__(self, path=None):
        self.path = path or ratings_path()

    def _load(self):
        try:
            data = json.load(io.open(self.path, encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("plugins"), dict):
                return data
        except Exception:
            pass
        return {"version": 1, "plugins": {}}

    def _save(self, data):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=".ratings_", suffix=".json", dir=os.path.dirname(self.path)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass

    def get(self, name):
        return self._load().get("plugins", {}).get(name)

    def set_rating(self, name, stars, comment=""):
        stars = max(1, min(5, int(stars)))
        data = self._load()
        data.setdefault("plugins", {})[name] = {
            "stars": stars,
            "comment": str(comment or "")[:500],
            "updated": time.time(),
        }
        self._save(data)
        return data["plugins"][name]

    def remove(self, name):
        data = self._load()
        if name in data.get("plugins", {}):
            del data["plugins"][name]
            self._save(data)
            return True
        return False

    def export_data(self, path):
        data = self._load()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        io.open(path, "w", encoding="utf-8", newline="\n").write(
            json.dumps(data, ensure_ascii=False, indent=2)
        )
        return len(data.get("plugins", {}))

    def import_data(self, path, merge=True):
        data = json.load(io.open(path, encoding="utf-8"))
        incoming = data.get("plugins") if isinstance(data, dict) else None
        if not isinstance(incoming, dict):
            raise ValueError("无效的评分文件")
        current = self._load()
        if not merge:
            current = {"version": 1, "plugins": {}}
        count = 0
        for name, rec in incoming.items():
            if not isinstance(rec, dict):
                continue
            try:
                stars = max(1, min(5, int(rec.get("stars", 0))))
            except Exception:
                continue
            current.setdefault("plugins", {})[name] = {
                "stars": stars,
                "comment": str(rec.get("comment") or "")[:500],
                "updated": float(rec.get("updated") or time.time()),
            }
            count += 1
        self._save(current)
        return count

    def all(self):
        return dict(self._load().get("plugins", {}))
