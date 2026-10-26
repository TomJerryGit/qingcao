# -*- coding: utf-8 -*-
"""P2 真机验证辅助：显示环境自检（跨屏 DPI / 高对比度）

用法：
    python tools/verify_display_env.py          # 人类可读
    python tools/verify_display_env.py --json   # 机器可读（CI/记录用）
"""
import argparse
import ctypes
import json
import os
import sys


def high_contrast_enabled():
    """读取 Windows 高对比度开关（SPI_GETHIGHCONTRAST=0x0042）"""
    try:
        class HIGHCONTRASTW(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint),
                        ("dwFlags", ctypes.c_uint),
                        ("lpszDefaultScheme", ctypes.c_wchar_p)]
        hc = HIGHCONTRASTW()
        hc.cbSize = ctypes.sizeof(HIGHCONTRASTW)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            0x0042, hc.cbSize, ctypes.byref(hc), 0)
        if not ok:
            return None
        return bool(hc.dwFlags & 0x00000001)  # HCF_HIGHCONTRASTON
    except Exception:
        return None


def monitors():
    """枚举显示器：数量/分辨率（坐标可判断多屏）"""
    out = []
    try:
        user32 = ctypes.windll.user32
        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_int), ctypes.c_double)
        rects = []

        def _cb(hmon, hdc, lprect, data):
            rects.append((lprect[0], lprect[1], lprect[2], lprect[3]))
            return 1

        user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(_cb), 0)
        for i, (l, t, r, b) in enumerate(rects):
            out.append({"index": i, "left": l, "top": t,
                        "width": r - l, "height": b - t})
    except Exception:
        pass
    return out


def dpi_scale():
    """主屏 DPI（每 96 DPI = 100% 缩放）"""
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        try:
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        finally:
            ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi
    except Exception:
        return None


def collect():
    ms = monitors()
    dpi = dpi_scale()
    return {
        "platform": sys.platform,
        "monitor_count": len(ms),
        "monitors": ms,
        "primary_dpi": dpi,
        "primary_scale_percent": round(dpi / 96.0 * 100) if dpi else None,
        "high_contrast": high_contrast_enabled(),
        "qt_scale_factor": os.environ.get("QT_SCALE_FACTOR"),
        "qt_screen_scale_factors": os.environ.get(
            "QT_SCREEN_SCALE_FACTORS"),
    }


def main():
    ap = argparse.ArgumentParser(description="显示环境自检（P2）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    data = collect()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    print("=== 显示环境自检 ===")
    print("平台:", data["platform"])
    print("显示器数量:", data["monitor_count"])
    for m in data["monitors"]:
        print("  #%d 位置=(%d,%d) 分辨率=%dx%d"
              % (m["index"], m["left"], m["top"],
                 m["width"], m["height"]))
    if data["monitor_count"] > 1:
        xs = {m["left"] for m in data["monitors"]}
        print("多屏布局:", "横向/混合" if len(xs) > 1 else "镜像/重叠")
    else:
        print("多屏布局: 单屏（跨屏 DPI 验证需连接第二台显示器）")
    print("主屏 DPI:", data["primary_dpi"],
          "→ 缩放", data["primary_scale_percent"], "%")
    hc = data["high_contrast"]
    print("高对比度模式:", "未知" if hc is None else ("开启" if hc else "关闭"))
    print("QT_SCALE_FACTOR:", data["qt_scale_factor"] or "未设置")
    return 0


if __name__ == "__main__":
    sys.exit(main())