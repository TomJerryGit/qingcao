# -*- coding: utf-8 -*-
"""插件沙箱 B1：文件路径与网络域名白名单策略。"""
import os


class SandboxPolicy:
    def __init__(self, allowed_roots=None, allowed_hosts=None):
        self.allowed_roots = [os.path.realpath(p) for p in (allowed_roots or [])]
        self.allowed_hosts = {h.lower() for h in (allowed_hosts or [])}

    def check_path(self, path):
        if not path:
            return False
        try:
            real = os.path.realpath(path)
        except Exception:
            return False
        for root in self.allowed_roots:
            try:
                if os.path.commonpath([real, root]) == root:
                    return True
            except Exception:
                continue
        return False

    def check_host(self, host):
        return (host or "").lower() in self.allowed_hosts
