#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成应用图标与启动画面（P2）

背景
----
README 与打包脚本引用了 ``resources/icons/qingcao.ico`` /
``qingcao.png`` 与 ``resources/splash.png``，但仓库里这几个文件
**都不存在**：

* ``installer.iss`` 的 ``SetupIconFile=resources\\icons\\qingcao.ico``
  → Inno Setup 编译必然失败；
* ``build.py`` 的图标/启动画面打包项缺失；
* ``main.py`` 的 ``set_app_icon`` 找不到任何图标，窗口没有图标。

本脚本用 Pillow 现场生成这些资源（深蓝渐变 + 青草绿标题），
不依赖任何外部素材。

用法::

    python tools/make_assets.py
"""
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_DIR = os.path.join(ROOT, 'resources', 'icons')
SPLASH_PATH = os.path.join(ROOT, 'resources', 'splash.png')

# 与 resources/qingcao_theme.qss / main.py 回退主题一致的配色
BG_TOP = (30, 58, 95)      # #1e3a5f
BG_BOTTOM = (13, 31, 51)   # #0d1f33
ACCENT = (126, 200, 80)    # #7ec850
SUBTITLE = (160, 160, 160)  # #a0a0a0


def _gradient(size):
    """生成竖向渐变背景"""
    from PIL import Image
    w, h = size
    img = Image.new('RGB', size, BG_TOP)
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    return img


def _font(size):
    """找一个能渲染中文的字体"""
    from PIL import ImageFont
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _center_text(draw, box, text, font, fill):
    """在 box=(x, y, w, h) 内居中绘制文字"""
    x, y, w, h = box
    try:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        tw, th = right - left, bottom - top
    except Exception:
        tw, th = draw.textsize(text, font=font)
    draw.text(
        (x + (w - tw) / 2 - left, y + (h - th) / 2 - top),
        text, font=font, fill=fill,
    )


def make_icon():
    """生成 resources/icons/qingcao.png 与 .ico"""
    from PIL import Image, ImageDraw

    os.makedirs(ICON_DIR, exist_ok=True)

    size = 256
    img = _gradient((size, size))
    draw = ImageDraw.Draw(img)

    # 圆角遮罩（让图标在小尺寸下更像应用图标）
    radius = 48
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=radius, fill=255
    )

    # 主字形
    font = _font(150)
    _center_text(draw, (0, -18, size, size), '青', font, ACCENT)
    # 底部细横线
    draw.rectangle((72, 206, size - 72, 212), fill=ACCENT)

    rgba = img.convert('RGBA')
    rgba.putalpha(mask)

    png_path = os.path.join(ICON_DIR, 'qingcao.png')
    rgba.save(png_path)
    print("[make_assets] 写出 %s" % os.path.relpath(png_path, ROOT))

    ico_path = os.path.join(ICON_DIR, 'qingcao.ico')
    rgba.save(
        ico_path,
        format='ICO',
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
               (128, 128), (256, 256)],
    )
    print("[make_assets] 写出 %s" % os.path.relpath(ico_path, ROOT))


def make_splash():
    """生成 resources/splash.png（480x260，与 main.py 回退绘制一致）"""
    from PIL import Image, ImageDraw

    w, h = 480, 260
    img = _gradient((w, h))
    draw = ImageDraw.Draw(img)

    _center_text(draw, (0, -30, w, h), '青草编辑器', _font(56), ACCENT)
    _center_text(draw, (0, 60, w, h), '青草枯荣 · 野火重生',
                 _font(22), SUBTITLE)
    draw.rectangle((180, 186, w - 180, 189), fill=ACCENT)

    os.makedirs(os.path.dirname(SPLASH_PATH), exist_ok=True)
    img.save(SPLASH_PATH)
    print("[make_assets] 写出 %s" % os.path.relpath(SPLASH_PATH, ROOT))


def main():
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("[make_assets] 需要 Pillow: pip install pillow")
        return 1

    make_icon()
    make_splash()
    print("[make_assets] 完成")
    return 0


if __name__ == '__main__':
    sys.exit(main())
