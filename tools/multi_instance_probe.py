# -*- coding: utf-8 -*-
"""多实例冒烟子进程：hub 或 client（带连接握手）"""
import os
import sys
import threading
import time


sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

from PyQt5.QtCore import QCoreApplication, QTimer  # noqa: E402
from PyQt5.QtNetwork import QLocalSocket  # noqa: E402

from infrastructure.instance_broadcast import InstanceBroadcaster  # noqa: E402


def main() -> int:
    role, name, path = sys.argv[1], sys.argv[2], sys.argv[3]
    app = QCoreApplication([])
    b = InstanceBroadcaster(server_name=name)
    ok = b.start(force_client=(role != "hub"))
    received = []

    def on_saved(p, mtime, pid):
        received.append(p)
        print("RECEIVED", p, flush=True)

    b.file_saved.connect(on_saved)

    if role == "hub":
        print("HUB", flush=True)
        QTimer.singleShot(10000, app.quit)

        def wait_go():
            sys.stdin.readline()
            time.sleep(0.5)  # 等 hub 登记 client 连接
            b.announce(path, 123.0)
            print("ANNOUNCED", flush=True)

        threading.Thread(target=wait_go, daemon=True).start()
    else:
        def wait_connected():
            sock = getattr(b, "_socket", None)
            if sock is not None and \
                    sock.state() == QLocalSocket.ConnectedState:
                # 给 hub 一点时间登记连接，避免"已连上但广播没人收"
                QTimer.singleShot(
                    500, lambda: print("CLIENT", flush=True))
            else:
                QTimer.singleShot(50, wait_connected)

        wait_connected()
        QTimer.singleShot(8000, app.quit)
    app.exec_()
    b.stop()
    if role == "client":
        return 0 if received else 2
    return 0


if __name__ == "__main__":
    sys.exit(main())