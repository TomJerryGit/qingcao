# -*- coding: utf-8 -*-
"""运行所有测试"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def run_all():
    """
    改用 pytest，fixture 自动生效。

    修复说明（P0-C5）:
        - 原实现用 unittest.TestLoader + TextTestRunner，
          会绕过 conftest.py 中的所有 fixture。
        - 特别是 _isolate_qsettings（autouse）不生效，
          test_smoke.py 里 new Preferences() 会写入
          用户真实配置（Windows 注册表 / macOS plist /
          Linux ~/.config）。
        - pytest 能识别 unittest.TestCase 风格，autouse
          fixture 同样对其生效。
    """
    import pytest

    start_dir = os.path.dirname(os.path.abspath(__file__))
    args = [
        start_dir,
        '-v',
        '--tb=short',
    ]
    return pytest.main(args)


if __name__ == "__main__":
    sys.exit(run_all())