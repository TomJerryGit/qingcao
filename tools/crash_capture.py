# -*- coding: utf-8 -*-
"""P0：Windows WER 本地崩溃转储开关（python.exe）。"""

import argparse
import os
import sys


KEY = r"Software\Microsoft\Windows\Windows Error Reporting\LocalDumps\python.exe"


def enable(folder):
    import winreg

    os.makedirs(folder, exist_ok=True)
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY)
    winreg.SetValueEx(key, "DumpFolder", 0, winreg.REG_EXPAND_SZ, folder)
    winreg.SetValueEx(key, "DumpType", 0, winreg.REG_DWORD, 1)
    winreg.SetValueEx(key, "DumpCount", 0, winreg.REG_DWORD, 3)
    winreg.CloseKey(key)
    return True


def disable():
    import winreg

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, KEY)
    except FileNotFoundError:
        pass
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--enable", default="")
    ap.add_argument("--disable", action="store_true")
    args = ap.parse_args(argv)
    if args.disable:
        disable()
        print("[wer] disabled")
    elif args.enable:
        enable(args.enable)
        print("[wer] dumps ->", args.enable)
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
