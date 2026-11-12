# -*- coding: utf-8 -*-
"""插件宿主 B0：JSON-RPC 2.0 行协议编解码。"""
import json


ERROR_METHOD_NOT_FOUND = -32601
ERROR_PERMISSION_DENIED = -32001
ERROR_TIMEOUT = -32002
ERROR_LIMIT = -32003


class RpcError(Exception):
    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def encode(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"


def request(method, params=None, req_id=1):
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}


def response(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def error(req_id, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def notification(method, params=None):
    return {"jsonrpc": "2.0", "method": method, "params": params or {}}


def decode(line):
    try:
        obj = json.loads(line)
    except Exception as e:
        raise RpcError(-32700, "parse error: %s" % e)
    if not isinstance(obj, dict) or obj.get("jsonrpc") != "2.0":
        raise RpcError(-32600, "invalid request")
    return obj
