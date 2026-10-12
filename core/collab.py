# -*- coding: utf-8 -*-
"""极简协作编辑（基于 OT）"""
import json
import socket
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, pyqtSignal

from core.commands import DeleteCmd, InsertCmd, ReplaceCmd


DEFAULT_PORT = 52000


class CollabMessage:
    """协作消息"""

    OP_INSERT = "insert"
    OP_DELETE = "delete"
    OP_REPLACE = "replace"
    OP_SYNC = "sync"
    OP_HELLO = "hello"
    OP_ROSTER = "roster"
    OP_LEAVE = "leave"

    def __init__(self, op, **kwargs):
        self.op = op
        self.data = kwargs
        self.timestamp = time.time()
        self.user_id = kwargs.get('user_id', '')

    def to_dict(self):
        d = {'op': self.op, 'ts': self.timestamp,
             'user_id': self.user_id}
        d.update(self.data)
        return d

    @classmethod
    def from_dict(cls, d):
        op = d.pop('op', '')
        ts = d.pop('ts', time.time())
        uid = d.pop('user_id', '')
        msg = cls(op, user_id=uid, **d)
        msg.timestamp = ts
        return msg


class CollabSession(QObject):
    """协作会话"""

    message_received = pyqtSignal(object)  # CollabMessage
    user_joined = pyqtSignal(str, str)     # user_id, user_name
    user_left = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    connected = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, user_id="", user_name="", parent=None):
        super().__init__(parent)
        self.user_id = user_id or self._gen_user_id()
        self.user_name = user_name or ("用户" + self.user_id[:4])
        self.room = ""
        self.sock = None
        self.connected_flag = False
        self._reader_thread = None
        self._stop_flag = False

    @staticmethod
    def _gen_user_id():
        import uuid
        return uuid.uuid4().hex[:8]

    def start_host(self, port=DEFAULT_PORT, room="default"):
        """作为主机启动"""
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('0.0.0.0', port))
            server.listen(5)

            self.room = room
            print("[Collab] 主机启动，端口 %d" % port)

            def accept_loop():
                while not self._stop_flag:
                    try:
                        server.settimeout(1.0)
                        client, addr = server.accept()
                        print("[Collab] 客户端连接: %s" % str(addr))
                        threading.Thread(
                            target=self._handle_client,
                            args=(client, addr), daemon=True
                        ).start()
                    except socket.timeout:
                        continue
                    except Exception:
                        break

            threading.Thread(target=accept_loop, daemon=True).start()
            return True
        except Exception as e:
            self.error_occurred.emit("主机启动失败: %s" % e)
            return False

    def _handle_client(self, client, addr):
        """处理客户端消息"""
        try:
            buf = b''
            while not self._stop_flag:
                data = client.recv(4096)
                if not data:
                    break
                buf += data
                # 简单协议：每条消息以 \n 分隔
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    try:
                        d = json.loads(line.decode('utf-8'))
                        msg = CollabMessage.from_dict(d)
                        self.message_received.emit(msg)
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            try:
                client.close()
            except Exception:
                pass
            self.user_left.emit(addr[0])

    def join(self, host, port=DEFAULT_PORT, room="default"):
        """加入协作"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((host, port))
            self.room = room
            self.connected_flag = True

            # 发送 hello
            self.send(CollabMessage(
                CollabMessage.OP_HELLO,
                user_id=self.user_id,
                user_name=self.user_name,
                room=room,
            ))

            # 启动读取线程
            self._reader_thread = threading.Thread(
                target=self._read_loop, daemon=True
            )
            self._reader_thread.start()

            self.connected.emit()
            return True
        except Exception as e:
            self.error_occurred.emit("连接失败: %s" % e)
            return False

    def _read_loop(self):
        """读取消息"""
        try:
            buf = b''
            while not self._stop_flag and self.sock:
                data = self.sock.recv(4096)
                if not data:
                    break
                buf += data
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    try:
                        d = json.loads(line.decode('utf-8'))
                        msg = CollabMessage.from_dict(d)
                        if msg.user_id != self.user_id:
                            self.message_received.emit(msg)
                            if msg.op == CollabMessage.OP_HELLO:
                                self.user_joined.emit(
                                    msg.user_id, msg.data.get('user_name', '')
                                )
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            self.connected_flag = False
            self.disconnected.emit()

    def send(self, msg):
        """发送消息"""
        if not self.sock or not self.connected_flag:
            return False
        try:
            line = json.dumps(msg.to_dict(), ensure_ascii=False) + '\n'
            self.sock.sendall(line.encode('utf-8'))
            return True
        except Exception as e:
            self.error_occurred.emit("发送失败: %s" % e)
            return False

    def broadcast_insert(self, position, text):
        """广播插入"""
        return self.send(CollabMessage(
            CollabMessage.OP_INSERT,
            user_id=self.user_id,
            position=position,
            text=text,
        ))

    def broadcast_delete(self, position, length, deleted_text=b''):
        """广播删除"""
        return self.send(CollabMessage(
            CollabMessage.OP_DELETE,
            user_id=self.user_id,
            position=position,
            length=length,
            text=deleted_text.decode('utf-8', errors='replace')
                if isinstance(deleted_text, bytes) else deleted_text,
        ))

    def leave(self):
        """离开"""
        self._stop_flag = True
        if self.connected_flag:
            self.send(CollabMessage(
                CollabMessage.OP_LEAVE,
                user_id=self.user_id,
            ))
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.connected_flag = False