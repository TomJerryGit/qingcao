# -*- coding: utf-8 -*-
"""mmap 增量保存（v2.19 M1）：等长字节替换 + journal 备份/恢复

默认关闭（灰度）：
    环境变量 QINGCAO_MMAP_SAVE=1 或 QSettings("QingCao","Editor")
    .mmap_incremental_save = true 时启用；
    QINGCAO_MMAP_SAVE_MIN_MB 可覆盖最小文件阈值（默认 10MB，测试用）。
"""
import hashlib
import io
import os
import shutil
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MIN_MB = 10.0
JOURNAL_REL = os.path.join("data", "edit_journal")


def min_bytes():
    try:
        mb = float(os.environ.get("QINGCAO_MMAP_SAVE_MIN_MB",
                                  DEFAULT_MIN_MB))
    except Exception:
        mb = DEFAULT_MIN_MB
    return int(max(0.0, mb) * 1024 * 1024)


def enabled():
    raw = os.environ.get("QINGCAO_MMAP_SAVE", "")
    if raw.strip().lower() in ("1", "true", "yes", "on"):
        return True
    try:
        from PyQt5.QtCore import QSettings
        return bool(QSettings("QingCao", "Editor").value(
            "mmap_incremental_save", False, type=bool))
    except Exception:
        return False


def journal_dir():
    path = os.environ.get("QINGCAO_EDIT_JOURNAL_DIR") or os.path.join(
        ROOT, JOURNAL_REL)
    return path


def newline_positions(data: bytes):
    return [i for i, b in enumerate(data) if b == 10]


def can_incremental_save(old: bytes, new: bytes,
                         min_size: int = None) -> bool:
    """等长且换行位置一致才可原地补丁（保证行结构不变）"""
    if min_size is None:
        min_size = min_bytes()
    if len(old) != len(new) or len(old) < min_size:
        return False
    if old.count(b"\n") != new.count(b"\n"):
        return False
    if newline_positions(old) != newline_positions(new):
        return False
    return True


def diff_spans(old: bytes, new: bytes, chunk=1 << 20):
    """返回 [(start, end)] 差异区间；按块比较，避免逐字节 Python 循环"""
    spans = []
    n = len(old)
    pos = 0
    while pos < n:
        end = min(pos + chunk, n)
        if old[pos:end] != new[pos:end]:
            sub = memoryview(new)[pos:end]
            first = next(i for i in range(len(sub)) if old[pos + i] != sub[i])
            last = len(sub) - 1
            while last > first and old[pos + last] == sub[last]:
                last -= 1
            spans.append((pos + first, pos + last + 1))
        pos = end
    return spans


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _apply_patch(path: str, old: bytes, new: bytes, spans):
    import mmap
    with io.open(path, "r+b") as f:
        mm = mmap.mmap(f.fileno(), 0)
        try:
            for start, end in spans:
                mm[start:end] = new[start:end]
            mm.flush()
        finally:
            mm.close()


def _write_journal(path: str, old: bytes) -> str:
    d = journal_dir()
    os.makedirs(d, exist_ok=True)
    jpath = os.path.join(
        d, "%s.%d.journal" % (os.path.basename(path), int(time.time() * 1000)))
    with io.open(jpath, "wb") as f:
        f.write(old)
        f.flush()
        os.fsync(f.fileno())
    return jpath


def maybe_incremental_save(target: str, new_bytes: bytes,
                           clear_dirty=None):
    """尝试 mmap 增量保存。

    返回 True  → 已增量保存（调用方应跳过全量写盘）
    返回 None  → 不满足条件/失败，调用方回退全量保存
    """
    if not enabled():
        return None
    if not target or not os.path.isfile(target):
        return None
    try:
        old = io.open(target, "rb").read()
    except Exception:
        return None
    if not can_incremental_save(old, new_bytes):
        return None
    if _sha256(old) == _sha256(new_bytes):
        try:
            if clear_dirty:
                clear_dirty()
        except Exception:
            pass
        return True
    jpath = _write_journal(target, old)
    try:
        spans = diff_spans(old, new_bytes)
        _apply_patch(target, old, new_bytes, spans)
        if _sha256(io.open(target, "rb").read()) != _sha256(new_bytes):
            raise OSError("mmap 校验失败")
        try:
            if clear_dirty:
                clear_dirty()
        except Exception:
            pass
        try:
            os.remove(jpath)
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"[mmap-save] 增量保存失败，回退全量: {e}")
        try:
            with io.open(target, "wb") as f:
                f.write(old)
        except Exception as restore_err:
            print(f"[mmap-save] journal 恢复失败: {restore_err}")
        try:
            os.remove(jpath)
        except Exception:
            pass
        return None


def pending_journals():
    d = journal_dir()
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, n) for n in sorted(os.listdir(d))
            if n.endswith(".journal")]


def recover_journal(journal_path: str, repo_root: str = None):
    """从 journal 恢复原文件（journal 名格式: <basename>.<ts>.journal）"""
    name = os.path.basename(journal_path)
    base = name.rsplit(".", 2)[0]   # 去掉 .<ts>.journal
    root = repo_root or ROOT
    target = os.path.join(root, base)
    if not os.path.exists(target):
        print(f"[mmap-save] 恢复跳过（目标不存在）: {target}")
        return False
    with io.open(journal_path, "rb") as f:
        shutil.copyfileobj(f, io.open(target, "wb"))
    os.remove(journal_path)
    print(f"[mmap-save] 已从 journal 恢复: {target}")
    return True


def recover_pending_journals(repo_root: str = None):
    done = 0
    for jp in pending_journals():
        try:
            if recover_journal(jp, repo_root):
                done += 1
        except Exception as e:
            print(f"[mmap-save] 恢复失败 {jp}: {e}")
    return done
