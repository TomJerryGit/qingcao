# -*- coding: utf-8 -*-
"""v2.19 M1：mmap 增量保存（等长补丁/journal/回退/恢复）"""

import io
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _mod():
    import core.mmap_save as m

    return m


def _write_lines(path, lines):
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        for line in lines:
            f.write(line + "\n")


def test_can_incremental_conditions(tmp_path, monkeypatch):
    monkeypatch.setenv("QINGCAO_MMAP_SAVE_MIN_MB", "0")
    m = _mod()
    old = b"aaa\nbbb\nccc\n"
    new = b"aaa\nBXB\nccc\n"  # 等长、换行位置一致
    assert m.can_incremental_save(old, new) is True
    assert m.can_incremental_save(old, b"aaa\nbb\nccc\n") is False  # 长度不同
    assert m.can_incremental_save(old, b"aaa\nbbbccc\n") is False  # 换行位置不同


def test_patch_and_journal_success(tmp_path, monkeypatch):
    m = _mod()
    monkeypatch.setenv("QINGCAO_MMAP_SAVE", "1")
    monkeypatch.setenv("QINGCAO_MMAP_SAVE_MIN_MB", "0")
    monkeypatch.setenv("QINGCAO_EDIT_JOURNAL_DIR", str(tmp_path / "journal"))
    path = tmp_path / "big.txt"
    lines = ["row %06d abcdefghij" % i for i in range(2000)]
    _write_lines(path, lines)
    new_lines = list(lines)
    new_lines[1000] = new_lines[1000].replace("abcdefghij", "ABCDEFGHIJ")
    old = path.read_bytes()
    new = ("\n".join(new_lines) + "\n").encode("utf-8")
    assert len(old) == len(new)

    calls = {"dirty": 0}

    def _clear():
        calls["dirty"] += 1

    ok = m.maybe_incremental_save(str(path), new, clear_dirty=_clear)
    assert ok is True
    assert path.read_bytes() == new
    assert calls["dirty"] == 1
    assert os.listdir(tmp_path / "journal") == []


def test_fallback_on_length_change(tmp_path, monkeypatch):
    m = _mod()
    monkeypatch.setenv("QINGCAO_MMAP_SAVE", "1")
    monkeypatch.setenv("QINGCAO_MMAP_SAVE_MIN_MB", "0")
    path = tmp_path / "f.txt"
    _write_lines(path, ["aaaa", "bbbb"])
    old = path.read_bytes()
    assert m.maybe_incremental_save(str(path), b"aaaa\nb\n", None) is None
    assert path.read_bytes() == old


def test_failure_restores_original(tmp_path, monkeypatch):
    m = _mod()
    monkeypatch.setenv("QINGCAO_MMAP_SAVE", "1")
    monkeypatch.setenv("QINGCAO_MMAP_SAVE_MIN_MB", "0")
    monkeypatch.setenv("QINGCAO_EDIT_JOURNAL_DIR", str(tmp_path / "journal"))
    path = tmp_path / "f2.txt"
    _write_lines(path, ["aaaa", "bbbb", "cccc"])
    old = path.read_bytes()
    new = old.replace(b"bbbb", b"BBBB")

    def boom(*args, **kwargs):
        raise RuntimeError("patch fail")

    monkeypatch.setattr(m, "_apply_patch", boom)
    ok = m.maybe_incremental_save(str(path), new, None)
    assert ok is None
    assert path.read_bytes() == old  # 已从 journal 恢复
    assert os.listdir(tmp_path / "journal") == []


def test_recover_pending_journal(tmp_path, monkeypatch):
    m = _mod()
    jdir = tmp_path / "journal"
    jdir.mkdir()
    target = tmp_path / "recover_me.txt"
    original = b"original content\n"
    target.write_bytes(b"half written")
    monkeypatch.setenv("QINGCAO_EDIT_JOURNAL_DIR", str(jdir))
    jpath = m._write_journal(str(target), original, [(0, len(original))])
    assert m.recover_pending_journals(str(tmp_path)) == 1
    assert target.read_bytes() == original
    assert not os.path.exists(jpath)


def test_document_and_main_wiring_static():
    doc = io.open(os.path.join(ROOT, "core", "document.py"), encoding="utf-8").read()
    assert "maybe_incremental_save" in doc
    main = io.open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    assert "recover_pending_journals" in main
