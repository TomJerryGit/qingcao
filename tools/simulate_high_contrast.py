# -*- coding: utf-8 -*-
"""高对比度模拟工具（单机可验证）

用法：
    python tools/simulate_high_contrast.py --status
    python tools/simulate_high_contrast.py --on --yes   # 临时开启
    python tools/simulate_high_contrast.py --off         # 关闭
注意：--on/--off 会修改当前用户的 Windows 高对比度显示设置。
"""
import argparse
import ctypes
import json
import sys


SPI_GETHIGHCONTRAST = 0x0042
SPI_SETHIGHCONTRAST = 0x0043
HCF_HIGHCONTRASTON = 0x00000001
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02


class HIGHCONTRASTW(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint),
                ("dwFlags", ctypes.c_uint),
                ("lpszDefaultScheme", ctypes.c_wchar_p)]


def get_high_contrast():
    try:
        hc = HIGHCONTRASTW()
        hc.cbSize = ctypes.sizeof(HIGHCONTRASTW)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETHIGHCONTRAST, hc.cbSize, ctypes.byref(hc), 0)
        if not ok:
            return None
        return bool(hc.dwFlags & HCF_HIGHCONTRASTON)
    except Exception:
        return None


def set_high_contrast(enabled: bool) -> bool:
    try:
        hc = HIGHCONTRASTW()
        hc.cbSize = ctypes.sizeof(HIGHCONTRASTW)
        hc.dwFlags = HCF_HIGHCONTRASTON if enabled else 0
        hc.lpszDefaultScheme = None
        return bool(ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETHIGHCONTRAST, hc.cbSize, ctypes.byref(hc),
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE))
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="高对比度模拟")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--on", action="store_true")
    ap.add_argument("--off", action="store_true")
    ap.add_argument("--yes", action="store_true",
                    help="确认修改系统显示设置")
    args = ap.parse_args()
    if args.status or (not args.on and not args.off):
        print(json.dumps({"high_contrast": get_high_contrast()}))
        return 0
    if not args.yes:
        print("需要 --yes 确认（会临时修改系统高对比度设置）")
        return 2
    target = bool(args.on)
    old = get_high_contrast()
    if set_high_contrast(target):
        print("已%s高对比度（原状态: %s）"
              % ("开启" if target else "关闭", old))
        return 0
    print("设置失败")
    return 1


if __name__ == "__main__":
    sys.exit(main())