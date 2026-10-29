# -*- coding: utf-8 -*-
"""多实例文件保存广播（P0）

设计：同一用户下第一个实例监听 QLocalServer 成为 hub；其它实例作为
client 连接 hub。任一实例保存文件后广播 {"type":"file_saved","path",
"mtime","pid"}，hub 转发给所有 client。无法监听/连接时静默降级为
本地单实例行为。
"""
import getpass
import json
import os
import re

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtNetwork import QLocalServer, QLocalSocket


SERVER_NAME = "qingcao-instance-%s" % re.sub(
    r"[^A-Za-z0-9_-]", "_", getpass.getuser() or "user")

_singleton = None


def notify_file_saved(path: str) -> None:
    """保存成功后调用；未初始化/未启用时静默返回"""
    try:
        if _singleton is not None and path:
            _singleton.announce(path, os.path.getmtime(path))
    except Exception:
        pass


PROTOCOL_VERSION = 1


def make_payload(kind: str, path: str, mtime: float, pid: int) -> dict:
    """构造广播消息（带协议版本号，便于以后兼容旧实例）"""
    return {"v": PROTOCOL_VERSION, "type": kind, "path": path,
            "mtime": float(mtime), "pid": int(pid)}


class InstanceBroadcaster(QObject):
    file_saved = pyqtSignal(str, float, int)
    file_opened = pyqtSignal(str, float, int)
    file_closed = pyqtSignal(str, float, int)
    focus_requested = pyqtSignal()
    config_changed = pyqtSignal(str)
    peer_versions_changed = pyqtSignal(dict)

    def __init__(self, parent=None, server_name=None):
        super().__init__(parent)
        self._server_name = server_name or SERVER_NAME
        self.pid = os.getpid()
        self._server = None
        self._clients = []
        self._socket = None
        self._retry = None
        self._hub = False
        self._peer_versions = {}

    def start(self, force_client: bool = False) -> bool:
        """启动；force_client=True 时跳过 listen（测试/强制 client）"""
        if not force_client:
            server = QLocalServer(self)
            if server.listen(self._server_name):
                self._server = server
                self._hub = True
                server.newConnection.connect(self._on_new_connection)
                return True
        self._retry = QTimer(self)
        self._retry.setInterval(3000)
        self._retry.timeout.connect(self._connect_hub)
        self._retry.start()
        self._connect_hub()
        return False

    def stop(self) -> None:
        try:
            if self._retry is not None:
                self._retry.stop()
            for c in list(self._clients):
                c.abort()
            self._clients = []
            if self._socket is not None:
                self._socket.abort()
                self._socket = None
            if self._server is not None:
                self._server.close()
                QLocalServer.removeServer(self._server_name)
                self._server = None
        except Exception:
            pass

    def _on_new_connection(self):
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            self._clients.append(sock)
            sock.readyRead.connect(lambda s=sock: self._read_from(s))
            sock.disconnected.connect(
                lambda s=sock: self._drop_client(s))

    def _drop_client(self, sock):
        if sock in self._clients:
            self._clients.remove(sock)
        try:
            sock.deleteLater()
        except Exception:
            pass

    def _read_from(self, sock):
        try:
            while sock.canReadLine():
                line = bytes(sock.readLine()).decode("utf-8", "replace")
                self._dispatch(line, origin=sock)
        except Exception:
            pass

    def _connect_hub(self):
        if self._hub:
            return
        try:
            if self._socket is not None:
                return
            sock = QLocalSocket(self)
            sock.readyRead.connect(lambda: self._read_from(sock))
            sock.disconnected.connect(self._on_client_disconnect)
            sock.connectToServer(self._server_name)
            self._socket = sock
            try:
                QTimer.singleShot(300, self.announce_hello)
            except Exception:
                pass
        except Exception:
            self._socket = None

    def _on_client_disconnect(self):
        try:
            if self._socket is not None:
                self._socket.deleteLater()
        except Exception:
            pass
        self._socket = None

    def announce_config_changed(self, plugin_name: str) -> None:
        self._send_obj({"type": "config_changed", "name": str(plugin_name)},
                       )

    def announce_focus(self) -> None:
        self._send_obj({"type": "focus_request", "path": "",
                        "mtime": 0.0, "pid": self.pid})

    def announce(self, path: str, mtime: float) -> None:
        payload = json.dumps(
            make_payload("file_saved", path, mtime, self.pid),
            ensure_ascii=False) + "\n"
        data = payload.encode("utf-8")
        if self._hub:
            self.file_saved.emit(path, float(mtime), self.pid)
            for c in list(self._clients):
                try:
                    if c.state() == QLocalSocket.ConnectedState:
                        c.write(data)
                        c.flush()
                except Exception:
                    pass
        else:
            sock = self._socket
            if sock is not None and sock.state() == QLocalSocket.ConnectedState:
                try:
                    sock.write(data)
                    sock.flush()
                    return
                except Exception:
                    pass
            self.file_saved.emit(path, float(mtime), self.pid)

    def announce_event(self, kind: str, path: str) -> None:
        """广播 file_opened / file_closed（增量实现）"""
        if kind not in ("file_opened", "file_closed"):
            return
        try:
            mtime = os.path.getmtime(path)
        except Exception:
            mtime = 0.0
        obj = make_payload(kind, path, mtime, self.pid)
        val = (path, float(mtime), self.pid)
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        emit = (self.file_opened.emit if kind == "file_opened"
                else self.file_closed.emit)
        if self._hub:
            emit(*val)
            for c in list(self._clients):
                try:
                    if c.state() == QLocalSocket.ConnectedState:
                        c.write(data)
                        c.flush()
                except Exception:
                    pass
        else:
            sock = self._socket
            if sock is not None and sock.state() == QLocalSocket.ConnectedState:
                try:
                    sock.write(data)
                    sock.flush()
                    return
                except Exception:
                    pass
            emit(*val)



    def announce_hello(self) -> None:
        """协议版本协商：广播 hello（v2.15.x）"""
        self._write_raw({"v": PROTOCOL_VERSION, "type": "hello",
                         "pid": self.pid})

    def _write_raw(self, obj: dict, origin=None) -> None:
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        if self._hub:
            for c in list(self._clients):
                if c is origin:
                    continue
                try:
                    if c.state() == QLocalSocket.ConnectedState:
                        c.write(data)
                        c.flush()
                except Exception:
                    pass
        else:
            sock = self._socket
            if sock is not None and sock.state() == QLocalSocket.ConnectedState:
                try:
                    sock.write(data)
                    sock.flush()
                except Exception:
                    pass

    def _note_peer_version(self, pid, version) -> None:
        try:
            pid = int(pid or 0)
            version = int(version or 0)
        except Exception:
            return
        if pid <= 0 or pid == self.pid:
            return
        if self._peer_versions.get(pid) == version:
            return
        self._peer_versions[pid] = version
        try:
            self.peer_versions_changed.emit(dict(self._peer_versions))
        except Exception:
            pass

    def _dispatch(self, line: str, origin=None):
        try:
            obj = json.loads(line)
        except Exception:
            return
        kind = obj.get("type")
        if kind == "hello":
            self._note_peer_version(obj.get("pid"), obj.get("v"))
            if self._hub:
                self._write_raw(obj, origin)
                self._write_raw({"v": PROTOCOL_VERSION,
                                 "type": "hello_ack", "pid": self.pid,
                                 "peer_pid": obj.get("pid")}, origin)
            return
        if kind == "hello_ack":
            self._note_peer_version(
                obj.get("peer_pid") or obj.get("pid"), obj.get("v"))
            return
        if kind == "focus_request":
            self.focus_requested.emit()
            return
        if kind == "config_changed":
            self.config_changed.emit(str(obj.get("name") or ""))
            return
        if kind in ("file_opened", "file_closed"):
            try:
                val = (str(obj.get("path") or ""),
                       float(obj.get("mtime") or 0.0),
                       int(obj.get("pid") or 0))
            except Exception:
                return
            if not val[0]:
                return
            if kind == "file_opened":
                self.file_opened.emit(*val)
            else:
                self.file_closed.emit(*val)
            return
        if kind != "file_saved":
            return
        path = str(obj.get("path") or "")
        mtime = float(obj.get("mtime") or 0.0)
        pid = int(obj.get("pid") or 0)
        if not path:
            return
        if self._hub:
            data = (json.dumps(obj, ensure_ascii=False) + "\n").encode()
            for c in list(self._clients):
                if c is origin:
                    continue
                try:
                    if c.state() == QLocalSocket.ConnectedState:
                        c.write(data)
                        c.flush()
                except Exception:
                    pass
        self.file_saved.emit(path, mtime, pid)

    def _send_obj(self, obj: dict) -> None:
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        kind = obj.get("type")
        path = str(obj.get("path") or "")
        mtime = float(obj.get("mtime") or 0.0)
        pid = int(obj.get("pid") or 0)
        if kind == "config_changed":
            emit = self.config_changed.emit
            args = (str(obj.get("name") or ""),)
        elif kind == "focus_request":
            emit = self.focus_requested.emit
            args = ()
        elif kind == "file_opened":
            emit = self.file_opened.emit
            args = (path, mtime, pid)
        elif kind == "file_closed":
            emit = self.file_closed.emit
            args = (path, mtime, pid)
        else:
            emit = self.file_saved.emit
            args = (path, mtime, pid)
        if self._hub:
            emit(*args)
            for c in list(self._clients):
                try:
                    if c.state() == QLocalSocket.ConnectedState:
                        c.write(data)
                        c.flush()
                except Exception:
                    pass
            return
        sock = self._socket
        if sock is not None and \
                sock.state() == QLocalSocket.ConnectedState:
            try:
                sock.write(data)
                sock.flush()
                return
            except Exception:
                pass
        emit(*args)

def notify_file_event(kind: str, path: str) -> None:
    """广播打开/关闭事件；未初始化时静默返回"""
    try:
        if _singleton is not None and path:
            _singleton.announce_event(kind, path)
    except Exception:
        pass


def notify_focus_request() -> None:
    """请求现有实例聚焦窗口；未初始化时静默返回"""
    try:
        if _singleton is not None:
            _singleton.announce_focus()
    except Exception:
        pass


def try_focus_existing(timeout_ms: int = 400) -> bool:
    """尝试通知已运行的实例聚焦；成功返回 True（调用方应退出）"""
    try:
        import os as _os
        import time as _time

        from PyQt5.QtNetwork import QLocalSocket
        sock = QLocalSocket()
        sock.connectToServer(SERVER_NAME)
        deadline = _time.time() + timeout_ms / 1000.0
        while sock.state() != QLocalSocket.ConnectedState:
            if _time.time() > deadline:
                sock.abort()
                return False
            QCoreApplication_process()
        payload = '{"type": "focus_request"}\n'.encode("utf-8")
        sock.write(payload)
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        sock.waitForDisconnected(200)
        return True
    except Exception:
        return False


def QCoreApplication_process():
    try:
        from PyQt5.QtCore import QCoreApplication
        QCoreApplication.processEvents()
    except Exception:
        pass


def notify_config_changed(plugin_name: str) -> None:
    """广播插件配置变更到其它实例；未初始化时静默返回"""
    try:
        if _singleton is not None and plugin_name:
            _singleton.announce_config_changed(plugin_name)
    except Exception:
        pass


def start_broadcast() -> InstanceBroadcaster:
    global _singleton
    if _singleton is None:
        _singleton = InstanceBroadcaster()
        _singleton.start()
    return _singleton


def stop_broadcast() -> None:
    global _singleton
    if _singleton is not None:
        _singleton.stop()
        _singleton = None