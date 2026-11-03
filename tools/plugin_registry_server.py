# -*- coding: utf-8 -*-
"""本地/内网插件市场注册表服务（v2.18 MVP）

用法:
    python tools/plugin_registry_server.py --registry data/registry --port 8765
    python tools/plugin_registry_server.py --registry data/registry --check

客户端设置注册表 URL 为: http://127.0.0.1:8765/registry.json
"""

import argparse
import functools
import http.server
import io
import json
import os
import sys
import threading


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _Handler(http.server.SimpleHTTPRequestHandler):
    token = ""

    def _authorized(self):
        if not self.token:
            return True
        import hmac

        auth = self.headers.get("Authorization", "")
        expected = "Bearer %s" % self.token
        return hmac.compare_digest(auth, expected)

    def do_GET(self):
        if not self._authorized():
            self.send_error(401, "Unauthorized")
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


def make_server(registry_dir, host="127.0.0.1", port=8765, token="", certfile="", keyfile=""):
    handler_cls = type("Handler", (_Handler,), {"token": token or ""})
    handler = functools.partial(handler_cls, directory=os.path.abspath(registry_dir))
    srv = http.server.ThreadingHTTPServer((host, port), handler)
    if certfile and keyfile:
        import ssl

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile, keyfile)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    return srv


def check_registry(registry_dir):
    path = os.path.join(registry_dir, "registry.json")
    if not os.path.isfile(path):
        return (False, "registry.json 不存在")
    try:
        data = json.load(io.open(path, encoding="utf-8"))
    except Exception as e:
        return (False, "registry.json 解析失败: %s" % e)
    plugins = data.get("plugins") or []
    missing = []
    for p in plugins:
        url = str(p.get("download_url") or "")
        fname = os.path.basename(url)
        fpath = os.path.join(registry_dir, "plugins", fname)
        if not os.path.isfile(fpath):
            missing.append(fname)
    if missing:
        return (False, "缺少插件包: %s" % ",".join(missing[:5]))
    return (True, "注册表检查通过（%d 个插件）" % len(plugins))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="data/registry")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--token", default="")
    ap.add_argument("--cert", default="")
    ap.add_argument("--key", default="")
    args = ap.parse_args()
    registry_dir = (
        args.registry if os.path.isabs(args.registry) else os.path.join(ROOT, args.registry)
    )
    if args.check:
        ok, msg = check_registry(registry_dir)
        print("[registry-server] " + msg)
        return 0 if ok else 1
    srv = make_server(
        registry_dir, args.host, args.port, token=args.token, certfile=args.cert, keyfile=args.key
    )
    print("[registry-server] http://%s:%d/registry.json（Ctrl+C 停止）" % (args.host, args.port))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
