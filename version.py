# -*- coding: utf-8 -*-
"""青草编辑器版本号（单一来源 / single source of truth）

C4 修复：所有脚本（main.py / build.py / build_linux.py /
build_macos.py / build_installer.py / installer.iss / release.py）
统一从这里读取版本号，避免多处硬编码导致版本漂移。

P1-1 修复（版本漂移）：
    修复前 CHANGELOG 已发布 [2.1.0]，但 version.py / VERSION /
    installer.iss / 各 build 脚本 / 7 处运行时代码全部仍是
    "2.0.0"，且这 30 余处是**各自硬编码**的字符串。

    现在统一规则：
      1. 本文件的 __version__ 是唯一权威值；
      2. ``VERSION`` 文件与本文件保持同步（由 release.py 写入）；
      3. 运行时代码一律 ``from version import __version__``，
         不再写字面量；
      4. 用 ``python -m tools.check_version`` 校验全仓一致性。

更新版本只需修改此文件的 __version__，然后：
    python release.py bump patch   # 同步 VERSION 文件
"""

__version__ = "2.12.0"

# 打包/安装器读取的别名（部分脚本历史上叫 APP_VERSION / VERSION）
APP_VERSION = __version__
