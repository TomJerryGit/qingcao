# -*- coding: utf-8 -*-
"""P1-1 回归测试：版本号单一来源

修复前 version.py / VERSION / installer.iss / 各 build 脚本 /
7 处运行时代码各自硬编码版本号，且 CHANGELOG 已发布 2.1.0 而
代码仍写 2.0.0。
"""
import os
import re
import subprocess
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(path):
    with open(os.path.join(ROOT, path), encoding='utf-8') as f:
        return f.read()


class TestSingleSourceOfTruth:
    """version.py 是唯一权威来源"""

    def test_version_py_parsable(self):
        m = re.search(
            r'^__version__\s*=\s*["\']([^"\']+)["\']',
            _read('version.py'), re.M,
        )
        assert m, "version.py 中找不到 __version__"
        assert re.match(r'^\d+\.\d+\.\d+$', m.group(1))

    def test_version_file_matches(self):
        from version import __version__
        assert _read('VERSION').strip() == __version__

    def test_installer_iss_matches(self):
        from version import __version__
        m = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"',
                      _read('installer.iss'))
        assert m, "installer.iss 中找不到 MyAppVersion"
        assert m.group(1) == __version__

    def test_readme_badge_matches(self):
        from version import __version__
        m = re.search(r'badge/version-([0-9]+\.[0-9]+\.[0-9]+)',
                      _read('README.md'))
        assert m, "README 中找不到版本徽章"
        assert m.group(1) == __version__


class TestRuntimeReadsSingleSource:
    """运行时代码必须从 version.py 读取，而不是硬编码"""

    def test_main_fallback_matches(self):
        import main
        from version import __version__
        assert main.__version__ == __version__

    def test_updater_default(self):
        from core.updater import UpdateChecker
        from version import __version__
        assert UpdateChecker().current_version == __version__

    def test_crash_reporter_default(self):
        from core.crash_reporter import CrashReporter
        from version import __version__
        assert CrashReporter().app_version == __version__

    def test_plugin_loader_app_version(self):
        from infrastructure.plugin_loader import CURRENT_APP_VERSION
        from version import __version__
        assert __version__ == CURRENT_APP_VERSION

    def test_api_version_is_independent(self):
        """插件 API 版本是独立契约，不应跟随应用版本"""
        from infrastructure.plugin_loader import CURRENT_API_VERSION
        assert re.match(r'^\d+\.\d+\.\d+$', CURRENT_API_VERSION)


class TestCheckVersionTool:
    """tools/check_version.py 必须报全票通过"""

    def test_checker_passes(self):
        result = subprocess.run(
            [sys.executable, os.path.join('tools', 'check_version.py')],
            cwd=ROOT, capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            "版本一致性检查失败:\n%s\n%s"
            % (result.stdout, result.stderr)
        )


class TestReleaseSyncsVersionPy:
    """release.py 的 bump 必须同时更新 version.py"""

    def test_write_version_updates_both(self, tmp_path, monkeypatch):
        import release

        fake_py = tmp_path / 'version.py'
        fake_py.write_text('__version__ = "1.0.0"\n', encoding='utf-8')
        fake_version = tmp_path / 'VERSION'
        fake_version.write_text('1.0.0\n', encoding='utf-8')

        monkeypatch.setattr(release, 'VERSION_PY', str(fake_py))
        monkeypatch.setattr(release, 'VERSION_FILE', str(fake_version))

        release.write_version('9.9.9')

        assert fake_version.read_text(encoding='utf-8').strip() == '9.9.9'
        assert '__version__ = "9.9.9"' in fake_py.read_text(encoding='utf-8')
