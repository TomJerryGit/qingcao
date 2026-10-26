# -*- coding: utf-8 -*-
"""P1：多实例无头冒烟 —— 两个进程验证保存广播"""
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = os.path.join(ROOT, "tools", "multi_instance_probe.py")


def _read_expect(stream, token, limit=30):
    lines = []
    for _ in range(limit):
        line = stream.readline()
        if line == "":
            break
        line = line.strip()
        lines.append(line)
        if token in line:
            return line, lines
    return "", lines


def main() -> int:
    name = "qingcao-smoke-%d" % os.getpid()
    path = os.path.join(ROOT, "data", "smoke_%d.txt" % os.getpid())
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONIOENCODING"] = "utf-8"
    hub = subprocess.Popen([sys.executable, PROBE, "hub", name, path],
                           cwd=ROOT, env=env, stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8", errors="replace")
    client = None
    try:
        line, _ = _read_expect(hub.stdout, "HUB")
        if not line:
            print("[smoke] hub 启动失败")
            return 1
        print("[smoke] hub ready")
        client = subprocess.Popen([sys.executable, PROBE, "client", name,
                                   path],
                                  cwd=ROOT, env=env,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True,
                                  encoding="utf-8", errors="replace")
        line, _ = _read_expect(client.stdout, "CLIENT")
        if not line:
            print("[smoke] client 连接失败")
            return 1
        print("[smoke] client ready")
        hub.stdin.write("go\n")
        hub.stdin.flush()
        line, _ = _read_expect(hub.stdout, "ANNOUNCED")
        print("[smoke] hub:", line)
        line, _ = _read_expect(client.stdout, "RECEIVED")
        print("[smoke] client:", line)
        received = line.startswith("RECEIVED") and line.endswith(path)
        hub_rc = hub.wait(timeout=15)
        client_rc = client.wait(timeout=15)
        ok = bool(received and hub_rc == 0 and client_rc == 0)
        print("[smoke] hub_rc=%s client_rc=%s" % (hub_rc, client_rc))
        print("[smoke] PASS" if ok else "[smoke] FAIL")
        return 0 if ok else 1
    finally:
        for proc in (hub, client):
            try:
                if proc is not None and proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())