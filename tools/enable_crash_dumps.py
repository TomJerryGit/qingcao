# -*- coding: utf-8 -*-
"""配置 Windows 错误报告本地转储（用于定位 CI Qt 原生崩溃，v2.17.x）

用法:
    python tools/enable_crash_dumps.py --folder D:\actions-runner\crash_dumps
    python tools/enable_crash_dumps.py --check
    python tools/enable_crash_dumps.py --remove
"""
import argparse
import os
import sys


BASE = r"SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps"
EXES = ("python.exe", "QingCaoEditor.exe")


def dump_folder(arg):
    if arg:
        return arg
    base = os.environ.get("QC_CRASH_DUMP_DIR")
    if base:
        return base
    if os.path.isdir(r"D:\actions-runner"):
        return r"D:\actions-runner\crash_dumps"
    return os.path.join(os.environ.get("TEMP", "."), "qc_crash_dumps")


def build_values(folder):
    return {"DumpFolder": os.path.abspath(folder), "DumpType": 1,
            "DumpCount": 5}


def apply_dump_config(folder):
    import winreg
    values = build_values(folder)
    os.makedirs(values["DumpFolder"], exist_ok=True)
    done = []
    for exe in EXES:
        key_path = BASE + "\\" + exe
        try:
            key = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, key_path,
                                     0, winreg.KEY_WRITE)
        except PermissionError:
            return (False, "需要管理员权限（HKLM）")
        try:
            winreg.SetValueEx(key, "DumpFolder", 0, winreg.REG_EXPAND_SZ,
                              values["DumpFolder"])
            winreg.SetValueEx(key, "DumpType", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "DumpCount", 0, winreg.REG_DWORD, 5)
        finally:
            winreg.CloseKey(key)
        done.append(exe)
    return (True, "已配置: " + ",".join(done))


def check_dump_config():
    import winreg
    report = {}
    for exe in EXES:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 BASE + "\\" + exe, 0, winreg.KEY_READ)
        except OSError:
            report[exe] = None
            continue
        try:
            report[exe] = winreg.QueryValueEx(key, "DumpFolder")[0]
        finally:
            winreg.CloseKey(key)
    return report


def remove_dump_config():
    import winreg
    for exe in EXES:
        try:
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE,
                             BASE + "\\" + exe)
        except OSError:
            pass
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default="")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--remove", action="store_true")
    args = ap.parse_args()
    if args.check:
        print(check_dump_config())
        return 0
    if args.remove:
        remove_dump_config()
        print("已移除 LocalDumps 配置")
        return 0
    folder = dump_folder(args.folder)
    ok, msg = apply_dump_config(folder)
    print("[crash-dump] " + msg)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
