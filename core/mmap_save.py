# -*- coding: utf-8 -*-
"""mmap 增量保存（v2.19 M1）：等长字节替换 + 区间级 journal 备份/恢复

默认关闭（灰度）：
    环境变量 QINGCAO_MMAP_SAVE=1 或 QSettings("QingCao","Editor")
    .mmap_incremental_save = true 时启用；
    QINGCAO_MMAP_SAVE_MIN_MB 可覆盖最小文件阈值（默认 10MB，测试用）。
"""
import io
import os
import struct
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MIN_MB = 10.0
JOURNAL_REL = os.path.join("data", "edit_journal")
MAGIC = b"QCJ1"
_CHUNK = 1 << 16


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
    return os.environ.get("QINGCAO_EDIT_JOURNAL_DIR") or os.path.join(
        ROOT, JOURNAL_REL)


def diff_spans(old: bytes, new: bytes, chunk: int = _CHUNK):
    """返回 [(start, end)] 差异区间（按 64KB 块比较，避免逐字节循环）"""
    if old == new:
        return []
    spans = []
    n = len(old)
    pos = 0
    while pos < n:
        end = min(pos + chunk, n)
        if old[pos:end] != new[pos:end]:
            # 在块内找首/尾差异，减少 Python 循环
            lo = pos
            hi = end
            a = old
            b = new
            while lo < hi and a[lo] == b[lo]:
                lo += 1
            while hi > lo and a[hi - 1] == b[hi - 1]:
                hi -= 1
            spans.append((lo, hi))
        pos = end
    return spans


def plan_incremental_save(old: bytes, new: bytes, min_size: int = None):
    """规划等长补丁：返回 spans 或 None（行结构必须不变）"""
    if min_size is None:
        min_size = min_bytes()
    if len(old) != len(new) or len(old) < min_size:
        return None
    if old.count(b"\n") != new.count(b"\n"):
        return None
    spans = diff_spans(old, new)
    for start, end in spans:
        # 差异区间不得改变换行符位置（否则行结构变化）
        if b"\n" in old[start:end] or b"\n" in new[start:end]:
            return None
    return spans


def can_incremental_save(old: bytes, new: bytes,
                         min_size: int = None) -> bool:
    return plan_incremental_save(old, new, min_size) is not None


def _write_journal(path: str, old: bytes, spans) -> str:
    """只记录差异区间的旧字节（小 journal，崩溃可恢复）"""
    d = journal_dir()
    os.makedirs(d, exist_ok=True)
    jpath = os.path.join(
        d, "%s.%d.journal" % (os.path.basename(path), int(time.time() * 1000)))
    buf = bytearray()
    buf += MAGIC
    buf += struct.pack("<I", len(spans))
    for start, end in spans:
        buf += struct.pack("<QI", start, end - start)
        buf += old[start:end]
    with io.open(jpath, "wb") as f:
        f.write(buf)
        f.flush()
        os.fsync(f.fileno())
    return jpath


def _read_journal(jpath: str):
    data = io.open(jpath, "rb").read()
    if not data.startswith(MAGIC):
        return None
    pos = len(MAGIC)
    (count,) = struct.unpack_from("<I", data, pos)
    pos += 4
    records = []
    for _ in range(count):
        start, length = struct.unpack_from("<QI", data, pos)
        pos += 12
        records.append((start, data[pos:pos + length]))
        pos += length
    return records


def _restore_records(target: str, records):
    with io.open(target, "r+b") as f:
        for start, old_bytes in records:
            f.seek(start)
            f.write(old_bytes)
        f.flush()
        os.fsync(f.fileno())


def _apply_patch(path: str, new: bytes, spans):
    import mmap
    with io.open(path, "r+b") as f:
        mm = mmap.mmap(f.fileno(), 0)
        try:
            for start, end in spans:
                mm[start:end] = new[start:end]
            mm.flush()
        finally:
            mm.close()


def _verify_patch(path: str, new: bytes, spans) -> bool:
    size = os.path.getsize(path)
    if size != len(new):
        return False
    with io.open(path, "rb") as f:
        for start, end in spans:
            f.seek(start)
            if f.read(end - start) != new[start:end]:
                return False
    return True


def maybe_incremental_save(target: str, new_bytes: bytes,
                           clear_dirty=None):
    """尝试 mmap 增量保存。

    返回 True  → 已增量保存（调用方跳过全量写盘）
    返回 None  → 不满足条件/失败，调用方回退全量保存
    """
    if not enabled() or not target or not os.path.isfile(target):
        return None
    try:
        old = io.open(target, "rb").read()
    except Exception:
        return None
    spans = plan_incremental_save(old, new_bytes)
    if spans is None:
        return None
    if not spans:
        try:
            if clear_dirty:
                clear_dirty()
        except Exception:
            pass
        return True
    jpath = _write_journal(target, old, spans)
    try:
        _apply_patch(target, new_bytes, spans)
        if not _verify_patch(target, new_bytes, spans):
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
            records = _read_journal(jpath)
            if records:
                _restore_records(target, records)
            else:
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
    """从 journal 恢复原文件（文件名格式: <basename>.<ts>.journal）"""
    name = os.path.basename(journal_path)
    base = name.rsplit(".", 2)[0]
    root = repo_root or ROOT
    target = os.path.join(root, base)
    if not os.path.exists(target):
        print(f"[mmap-save] 恢复跳过（目标不存在）: {target}")
        return False
    records = _read_journal(journal_path)
    if records is None:
        # 兼容旧版全文 journal
        import shutil
        with io.open(journal_path, "rb") as f, io.open(target, "wb") as out:
            shutil.copyfileobj(f, out)
    else:
        _restore_records(target, records)
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
