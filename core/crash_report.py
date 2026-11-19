# -*- coding: utf-8 -*-
"""崩溃报告（opt-in）：本地摘要，不自动上传，不含隐私内容。"""

import io
import json
import os
import struct
import time


EXCEPTION_STREAM = 6


def _exception_code(path):
    try:
        with open(path, "rb") as f:
            head = f.read(32)
            if head[:4] != b"MDMP":
                return None
            count, rva = struct.unpack_from("<II", head, 20)
            f.seek(rva)
            entries = f.read(count * 12)
            for i in range(count):
                stype, _size, srva = struct.unpack_from("<III", entries, i * 12)
                if stype == EXCEPTION_STREAM:
                    f.seek(srva + 8)
                    code = struct.unpack("<I", f.read(4))[0]
                    return "0x%08X" % code
    except Exception:
        return None
    return None


def build_report(dump_dir="data/crashes", exception=""):
    """返回可导出的摘要；只含文件名/大小/时间/版本，不含路径或文本。"""
    dumps = []
    if os.path.isdir(dump_dir):
        for name in sorted(os.listdir(dump_dir)):
            if not name.lower().endswith(".dmp"):
                continue
            path = os.path.join(dump_dir, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            dumps.append(
                {
                    "name": name,
                    "size": st.st_size,
                    "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
                    "exception_code": _exception_code(path),
                }
            )
    version = ""
    try:
        version = (
            io.open(
                os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION"
                ),
                encoding="utf-8",
            )
            .read()
            .strip()
        )
    except OSError:
        pass
    return {
        "schema": 1,
        "version": version,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "exception": str(exception or ""),
        "dumps": dumps,
        "privacy": "仅本地生成；不自动上传；不含用户文本/路径/身份信息",
    }


def write_report(out_path, report):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    io.open(out_path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    return out_path
