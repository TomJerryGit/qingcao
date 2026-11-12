# -*- coding: utf-8 -*-
"""B1 试点验证：通过超级进程启动指定插件（默认 plugins/demo）。

QINGCAO_PLUGIN_ISOLATION=demo python tools/verify_plugin_isolation.py
"""

import argparse
import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.plugin_sandbox_policy import SandboxPolicy  # noqa: E402
from core.plugin_supervisor import PluginHostError, PluginProcess  # noqa: E402


class StubHostAPI:
    def __init__(self):
        self.menus = []

    def get_current_text(self):
        return "sample text"

    def set_current_text(self, text):
        return True

    def log(self, message, level="info"):
        print("[plugin-log]", message)
        return True

    def show_message(self, title, text):
        print("[message]", title, text)
        return True

    def add_menu(self, path, callback_id):
        self.menus.append((path, callback_id))
        print("[menu]", path, callback_id)
        return True

    def add_status_item(self, text):
        return True

    def get_config(self, key, default=None):
        return default

    def set_config(self, key, value):
        return True

    def register_settings_schema(self, schema):
        return True

    def run_command(self, command):
        raise RuntimeError("run_command denied in B1 demo")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugin", default=os.path.join(ROOT, "plugins", "demo"))
    ap.add_argument("--timeout", type=float, default=15)
    args = ap.parse_args()
    policy = SandboxPolicy([os.path.abspath(args.plugin)])
    host = StubHostAPI()
    proc = PluginProcess(args.plugin, host, timeout=args.timeout, policy=policy)
    try:
        proc.start()
        time.sleep(0.5)
        print("[B1] 插件已隔离激活：", os.path.basename(args.plugin))
        print("[B1] 菜单回调：", host.menus)
        if host.menus:
            proc.invoke_callback(host.menus[0][1])
            time.sleep(0.3)
        for level, msg in proc.logs:
            print("[B1][%s] %s" % (level, msg))
        return 0
    except PluginHostError as e:
        print("[B1] FAIL:", e)
        return 1
    finally:
        proc.stop()


if __name__ == "__main__":
    sys.exit(main())
