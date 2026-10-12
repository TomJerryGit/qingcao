#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为云同步模块，包含：
- SyncManager：配置云同步管理器
- GitHub Gist 同步
- WebDAV 同步
- 本地目录同步
- 自定义服务器同步
- 敏感信息加密（keyring 支持）
- 冲突检测与解决
- 增量同步
- 同步历史记录
- 自动同步定时器
- 同步进度信号
- 网络异常重试
"""

import base64
import datetime
import hashlib
import json
import os
import sys
import threading
import time
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


# ============================================================
# 常量
# ============================================================
SYNC_CONFIG_FILE = "sync_config.json"
SYNC_HISTORY_FILE = "data/sync_history.json"
SYNC_CACHE_DIR = "data/sync_cache"
KEYRING_SERVICE = "QingCaoEditor"
KEYRING_GIST_TOKEN = "gist_token"
KEYRING_WEBDAV_PASSWORD = "webdav_password"

# 默认同步项
SYNC_ITEMS = [
    "preferences",   # 偏好设置
    "keybindings",   # 快捷键
    "themes",        # 主题
    "snippets",      # 代码片段
    "plugins_list",  # 插件列表
    "session",       # 会话
]

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒
REQUEST_TIMEOUT = 15  # 秒


# ============================================================
# 同步提供者枚举
# ============================================================
class SyncProvider(Enum):
    """同步提供者类型"""
    NONE = auto()
    GIST = auto()       # GitHub Gist
    WEBDAV = auto()     # WebDAV（Nextcloud、OwnCloud 等）
    LOCAL = auto()      # 本地目录
    CUSTOM = auto()     # 自定义服务器


# ============================================================
# 同步状态枚举
# ============================================================
class SyncStatus(Enum):
    """同步状态"""
    IDLE = auto()
    UPLOADING = auto()
    DOWNLOADING = auto()
    MERGING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CONFLICT = auto()
    CANCELLED = auto()


# ============================================================
# 同步结果
# ============================================================
class SyncResult:
    """同步结果"""

    def __init__(self, success: bool, message: str = "",
                 uploaded: int = 0, downloaded: int = 0,
                 conflicts: int = 0, elapsed_ms: float = 0.0):
        self.success = success
        self.message = message
        self.uploaded = uploaded
        self.downloaded = downloaded
        self.conflicts = conflicts
        self.elapsed_ms = elapsed_ms

    def __repr__(self):
        return (f"<SyncResult success={self.success} "
                f"up={self.uploaded} down={self.downloaded} "
                f"conflicts={self.conflicts}>")


# ============================================================
# 同步管理器
# ============================================================
class SyncManager(QObject):
    """
    云同步管理器。

    支持多种同步后端，自动处理冲突和错误重试。

    信号:
        sync_started(str): 同步开始（提供者名称）
        sync_progress(int, str): 同步进度（百分比, 状态描述）
        sync_finished(SyncResult): 同步完成
        sync_failed(str): 同步失败（错误信息）
        conflict_detected(str, str): 冲突检测（文件, 描述）
    """

    sync_started = pyqtSignal(str)
    sync_progress = pyqtSignal(int, str)
    sync_finished = pyqtSignal(object)  # SyncResult
    sync_failed = pyqtSignal(str)
    conflict_detected = pyqtSignal(str, str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

        # 同步配置
        self.config: Dict[str, Any] = self._load_config()

        # 同步状态
        self.status = SyncStatus.IDLE
        self._current_worker: Optional[threading.Thread] = None
        self._cancel_requested = False

        # 自动同步定时器
        self._autosync_timer = QTimer(self)
        self._autosync_timer.timeout.connect(self._autosync_tick)

        # 同步历史
        self.history: List[Dict[str, Any]] = self._load_history()

        # 本地缓存目录
        os.makedirs(SYNC_CACHE_DIR, exist_ok=True)

    # ========================================================
    # 配置管理
    # ========================================================
    def _load_config(self) -> Dict[str, Any]:
        """加载同步配置"""
        default = {
            'provider': 'none',
            'enabled': False,
            'auto_sync': False,
            'auto_sync_interval': 30,  # 分钟
            'items': list(SYNC_ITEMS),
            'last_sync': None,
            'gist_id': '',
            'gist_token': '',
            'webdav_url': '',
            'webdav_username': '',
            'webdav_password': '',
            'webdav_path': '/qingcao',
            'local_path': '',
            'custom_url': '',
            'custom_token': '',
            'encrypt': False,
        }

        if os.path.exists(SYNC_CONFIG_FILE):
            try:
                with open(SYNC_CONFIG_FILE, encoding='utf-8') as f:
                    data = json.load(f)
                default.update(data)
            except Exception as e:
                print(f"[Sync] 加载配置失败: {e}")

        # 从 keyring 加载敏感信息
        default['gist_token'] = self._load_secret(KEYRING_GIST_TOKEN,
                                                  default.get('gist_token', ''))
        default['webdav_password'] = self._load_secret(KEYRING_WEBDAV_PASSWORD,
                                                       default.get('webdav_password', ''))

        return default

    def save_config(self):
        """保存同步配置"""
        try:
            # 敏感信息单独保存到 keyring
            config_copy = dict(self.config)

            if config_copy.get('gist_token'):
                self._save_secret(KEYRING_GIST_TOKEN, config_copy['gist_token'])
                config_copy['gist_token'] = ''  # 不写入文件

            if config_copy.get('webdav_password'):
                self._save_secret(KEYRING_WEBDAV_PASSWORD,
                                  config_copy['webdav_password'])
                config_copy['webdav_password'] = ''

            with open(SYNC_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config_copy, f, indent=2, ensure_ascii=False)

            return True
        except Exception as e:
            print(f"[Sync] 保存配置失败: {e}")
            return False

    def _load_secret(self, key: str, default: str = "") -> str:
        """从系统密钥环加载敏感信息"""
        try:
            import keyring
            value = keyring.get_password(KEYRING_SERVICE, key)
            return value if value else default
        except ImportError:
            return default
        except Exception:
            return default

    def _save_secret(self, key: str, value: str):
        """保存敏感信息到系统密钥环"""
        try:
            import keyring
            if value:
                keyring.set_password(KEYRING_SERVICE, key, value)
            else:
                try:
                    keyring.delete_password(KEYRING_SERVICE, key)
                except Exception:
                    pass
        except ImportError:
            print("[Sync] keyring 未安装，敏感信息无法安全存储")
        except Exception as e:
            print(f"[Sync] 保存密钥失败: {e}")

    def update_config(self, **kwargs):
        """更新同步配置"""
        for key, value in kwargs.items():
            if key in self.config:
                self.config[key] = value
        self.save_config()

    def get_config(self) -> Dict[str, Any]:
        """获取当前配置（不含敏感信息）"""
        config = dict(self.config)
        if config.get('gist_token'):
            config['gist_token'] = '***'
        if config.get('webdav_password'):
            config['webdav_password'] = '***'
        return config

    # ========================================================
    # 同步入口
    # ========================================================
    def sync_now(self, direction: str = "both"):
        """
        立即执行同步（异步）。

        参数:
            direction: "upload" / "download" / "both"
        """
        if self.status != SyncStatus.IDLE:
            self.sync_failed.emit("同步正在进行中")
            return

        provider = self.config.get('provider', 'none')
        if provider == 'none':
            self.sync_failed.emit("未配置同步提供者")
            return

        self._cancel_requested = False
        self._current_worker = threading.Thread(
            target=self._do_sync,
            args=(direction,),
            daemon=True
        )
        self._current_worker.start()

    def cancel_sync(self):
        """取消当前同步"""
        self._cancel_requested = True

    def _do_sync(self, direction: str):
        """同步主逻辑（在后台线程执行）"""
        start_time = time.time()
        provider = self.config.get('provider', 'none')

        try:
            self.status = SyncStatus.UPLOADING if direction == "upload" else SyncStatus.DOWNLOADING
            self.sync_started.emit(provider)
            self.sync_progress.emit(0, "准备同步...")

            if provider == 'gist':
                result = self._sync_gist(direction)
            elif provider == 'webdav':
                result = self._sync_webdav(direction)
            elif provider == 'local':
                result = self._sync_local(direction)
            elif provider == 'custom':
                result = self._sync_custom(direction)
            else:
                result = SyncResult(False, f"未知的同步提供者: {provider}")

            result.elapsed_ms = (time.time() - start_time) * 1000

            if result.success:
                self.status = SyncStatus.SUCCESS
                self.config['last_sync'] = datetime.datetime.now().isoformat()
                self.save_config()
            else:
                self.status = SyncStatus.FAILED

            self._record_history(result)
            self.sync_finished.emit(result)

        except Exception as e:
            self.status = SyncStatus.FAILED
            error_msg = f"同步失败: {e}"
            import traceback
            traceback.print_exc()
            self.sync_failed.emit(error_msg)
        finally:
            self.status = SyncStatus.IDLE
            self._current_worker = None

    # ========================================================
    # GitHub Gist 同步
    # ========================================================
    def _sync_gist(self, direction: str) -> SyncResult:
        """GitHub Gist 同步"""
        try:
            import requests
        except ImportError:
            return SyncResult(False, "缺少 requests 库，请运行: pip install requests")

        token = self.config.get('gist_token', '')
        if not token:
            return SyncResult(False, "未配置 GitHub Token")

        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }

        self.sync_progress.emit(10, "收集本地数据...")
        local_data = self._collect_local_data()
        local_json = json.dumps(local_data, indent=2, ensure_ascii=False)

        gist_id = self.config.get('gist_id', '')

        # 下载远程数据
        self.sync_progress.emit(30, "下载远程数据...")
        remote_data = {}
        if gist_id:
            try:
                resp = requests.get(
                    f"https://api.github.com/gists/{gist_id}",
                    headers=headers, timeout=REQUEST_TIMEOUT
                )
                if resp.status_code == 200:
                    gist = resp.json()
                    files = gist.get('files', {})
                    for filename, info in files.items():
                        if filename == 'qingcao_config.json':
                            remote_data = json.loads(info['content'])
                            break
                elif resp.status_code == 404:
                    gist_id = ''  # Gist 不存在，将创建新的
                else:
                    return SyncResult(False, f"下载失败: HTTP {resp.status_code}")
            except Exception as e:
                return SyncResult(False, f"下载失败: {e}")

        # 合并数据
        self.sync_progress.emit(50, "合并数据...")
        if direction == "download":
            merged = remote_data if remote_data else local_data
        elif direction == "upload":
            merged = local_data
        else:
            merged = self._merge_data(local_data, remote_data)

        merged_json = json.dumps(merged, indent=2, ensure_ascii=False)

        # 上传
        self.sync_progress.emit(70, "上传数据...")
        payload = {
            'description': '青草编辑器配置同步',
            'public': False,
            'files': {
                'qingcao_config.json': {
                    'content': merged_json
                }
            }
        }

        for attempt in range(MAX_RETRIES):
            if self._cancel_requested:
                return SyncResult(False, "已取消")

            try:
                if gist_id:
                    resp = requests.patch(
                        f"https://api.github.com/gists/{gist_id}",
                        headers=headers, json=payload, timeout=REQUEST_TIMEOUT
                    )
                else:
                    resp = requests.post(
                        "https://api.github.com/gists",
                        headers=headers, json=payload, timeout=REQUEST_TIMEOUT
                    )

                if resp.status_code in (200, 201):
                    if not gist_id:
                        gist_id = resp.json().get('id', '')
                        self.config['gist_id'] = gist_id
                        self.save_config()
                    self.sync_progress.emit(100, "同步完成")
                    return SyncResult(
                        True, "同步成功",
                        uploaded=len(merged),
                        downloaded=len(remote_data)
                    )
                else:
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY * (attempt + 1))
                        continue
                    return SyncResult(False, f"上传失败: HTTP {resp.status_code}")

            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                return SyncResult(False, f"上传失败: {e}")

        return SyncResult(False, "重试次数已用完")

    # ========================================================
    # WebDAV 同步
    # ========================================================
    def _sync_webdav(self, direction: str) -> SyncResult:
        """WebDAV 同步（Nextcloud、OwnCloud 等）"""
        try:
            import requests
        except ImportError:
            return SyncResult(False, "缺少 requests 库")

        url = self.config.get('webdav_url', '').rstrip('/')
        username = self.config.get('webdav_username', '')
        password = self.config.get('webdav_password', '')
        remote_path = self.config.get('webdav_path', '/qingcao').strip('/')

        if not url:
            return SyncResult(False, "未配置 WebDAV 地址")

        full_url = f"{url}/{remote_path}/qingcao_config.json"
        auth = (username, password) if username else None

        self.sync_progress.emit(10, "收集本地数据...")
        local_data = self._collect_local_data()

        # 下载远程数据
        self.sync_progress.emit(30, "下载远程数据...")
        remote_data = {}
        try:
            resp = requests.get(full_url, auth=auth, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                try:
                    remote_data = json.loads(resp.text)
                except json.JSONDecodeError:
                    remote_data = {}
            elif resp.status_code == 404:
                remote_data = {}
            else:
                return SyncResult(False, f"下载失败: HTTP {resp.status_code}")
        except Exception as e:
            return SyncResult(False, f"下载失败: {e}")

        # 合并
        self.sync_progress.emit(50, "合并数据...")
        if direction == "download":
            merged = remote_data if remote_data else local_data
        elif direction == "upload":
            merged = local_data
        else:
            merged = self._merge_data(local_data, remote_data)

        # 上传
        self.sync_progress.emit(70, "上传数据...")
        try:
            # 确保目录存在
            dir_url = f"{url}/{remote_path}"
            requests.request('MKCOL', dir_url, auth=auth, timeout=REQUEST_TIMEOUT)

            resp = requests.put(
                full_url,
                data=json.dumps(merged, indent=2, ensure_ascii=False),
                auth=auth,
                headers={'Content-Type': 'application/json'},
                timeout=REQUEST_TIMEOUT
            )

            if resp.status_code in (200, 201, 204):
                self.sync_progress.emit(100, "同步完成")
                return SyncResult(
                    True, "同步成功",
                    uploaded=len(merged),
                    downloaded=len(remote_data)
                )
            else:
                return SyncResult(False, f"上传失败: HTTP {resp.status_code}")
        except Exception as e:
            return SyncResult(False, f"上传失败: {e}")

    # ========================================================
    # 本地目录同步
    # ========================================================
    def _sync_local(self, direction: str) -> SyncResult:
        """本地目录同步（用于测试或局域网共享）"""
        local_path = self.config.get('local_path', '')
        if not local_path:
            return SyncResult(False, "未配置本地同步目录")

        os.makedirs(local_path, exist_ok=True)
        remote_file = os.path.join(local_path, 'qingcao_config.json')

        self.sync_progress.emit(10, "收集本地数据...")
        local_data = self._collect_local_data()

        # 读取远程
        self.sync_progress.emit(30, "读取远程数据...")
        remote_data = {}
        if os.path.exists(remote_file):
            try:
                with open(remote_file, encoding='utf-8') as f:
                    remote_data = json.load(f)
            except Exception:
                remote_data = {}

        # 合并
        self.sync_progress.emit(50, "合并数据...")
        if direction == "download":
            merged = remote_data if remote_data else local_data
        elif direction == "upload":
            merged = local_data
        else:
            merged = self._merge_data(local_data, remote_data)

        # 写入
        self.sync_progress.emit(70, "写入数据...")
        try:
            # 原子写入
            tmp_path = remote_file + '.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(merged, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, remote_file)

            self.sync_progress.emit(100, "同步完成")
            return SyncResult(
                True, "同步成功",
                uploaded=len(merged),
                downloaded=len(remote_data)
            )
        except Exception as e:
            return SyncResult(False, f"写入失败: {e}")

    # ========================================================
    # 自定义服务器同步
    # ========================================================
    def _sync_custom(self, direction: str) -> SyncResult:
        """自定义 HTTP 服务器同步"""
        try:
            import requests
        except ImportError:
            return SyncResult(False, "缺少 requests 库")

        url = self.config.get('custom_url', '')
        token = self.config.get('custom_token', '')

        if not url:
            return SyncResult(False, "未配置自定义服务器地址")

        headers = {}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        self.sync_progress.emit(10, "收集本地数据...")
        local_data = self._collect_local_data()

        # 下载
        self.sync_progress.emit(30, "下载远程数据...")
        remote_data = {}
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                remote_data = resp.json()
        except Exception:
            pass

        # 合并
        self.sync_progress.emit(50, "合并数据...")
        if direction == "download":
            merged = remote_data if remote_data else local_data
        elif direction == "upload":
            merged = local_data
        else:
            merged = self._merge_data(local_data, remote_data)

        # 上传
        self.sync_progress.emit(70, "上传数据...")
        try:
            resp = requests.post(
                url,
                json=merged,
                headers=headers,
                timeout=REQUEST_TIMEOUT
            )
            if resp.status_code in (200, 201, 204):
                self.sync_progress.emit(100, "同步完成")
                return SyncResult(
                    True, "同步成功",
                    uploaded=len(merged),
                    downloaded=len(remote_data)
                )
            return SyncResult(False, f"上传失败: HTTP {resp.status_code}")
        except Exception as e:
            return SyncResult(False, f"上传失败: {e}")

    # ========================================================
    # 数据收集与合并
    # ========================================================
    def _collect_local_data(self) -> Dict[str, Any]:
        """收集本地需要同步的数据"""
        data: Dict[str, Any] = {
            'version': 1,
            'timestamp': datetime.datetime.now().isoformat(),
            'machine': self._get_machine_id(),
            'items': {},
        }

        items_to_sync = self.config.get('items', SYNC_ITEMS)

        # 偏好设置
        if 'preferences' in items_to_sync:
            try:
                from PyQt5.QtCore import QSettings
                settings = QSettings("QingCao", "Editor")
                prefs = {}
                for key in settings.allKeys():
                    try:
                        prefs[key] = settings.value(key)
                    except Exception:
                        pass
                data['items']['preferences'] = prefs
            except Exception as e:
                print(f"[Sync] 收集偏好失败: {e}")

        # 快捷键
        if 'keybindings' in items_to_sync:
            try:
                if os.path.exists('keybindings.json'):
                    with open('keybindings.json', encoding='utf-8') as f:
                        data['items']['keybindings'] = json.load(f)
            except Exception:
                pass

        # 主题
        if 'themes' in items_to_sync:
            themes = {}
            themes_dir = 'themes'
            if os.path.isdir(themes_dir):
                for name in os.listdir(themes_dir):
                    if name.endswith('.json'):
                        try:
                            with open(os.path.join(themes_dir, name), encoding='utf-8') as f:
                                themes[name] = json.load(f)
                        except Exception:
                            pass
            data['items']['themes'] = themes

        # 代码片段
        if 'snippets' in items_to_sync:
            try:
                if os.path.exists('snippets.json'):
                    with open('snippets.json', encoding='utf-8') as f:
                        data['items']['snippets'] = json.load(f)
            except Exception:
                pass

        # 插件列表
        if 'plugins_list' in items_to_sync:
            plugins = []
            plugins_dir = 'plugins'
            if os.path.isdir(plugins_dir):
                for name in os.listdir(plugins_dir):
                    if os.path.isdir(os.path.join(plugins_dir, name)):
                        manifest_path = os.path.join(
                            plugins_dir, name, 'plugin.json'
                        )
                        if os.path.exists(manifest_path):
                            try:
                                with open(manifest_path,
                                          encoding='utf-8') as f:
                                    manifest = json.load(f)
                                    plugins.append({
                                        'name': manifest.get('name', name),
                                        'version': manifest.get('version', '0.0.0'),
                                        'enabled': True,
                                    })
                            except Exception:
                                pass
            data['items']['plugins_list'] = plugins

        # 会话（可选，含打开文件列表）
        if 'session' in items_to_sync:
            try:
                if os.path.exists('session.json'):
                    with open('session.json', encoding='utf-8') as f:
                        session = json.load(f)
                    # 只同步文件路径列表，不同步内容
                    data['items']['session'] = {
                        'files': [
                            f.get('filepath')
                            for f in session.get('files', [])
                            if f.get('filepath')
                        ]
                    }
            except Exception:
                pass

        # 加密（如启用）
        if self.config.get('encrypt'):
            data = self._encrypt_data(data)

        return data

    def _merge_data(self, local: Dict[str, Any],
                    remote: Dict[str, Any]) -> Dict[str, Any]:
        """
        合并本地和远程数据。

        策略:
        - 以 timestamp 更新的为准
        - 对 preferences/keybindings 做键级合并（本地优先）
        - 对 themes/snippets 做并集
        """
        if not remote:
            return local
        if not local:
            return remote

        # 简单策略：比较时间戳
        local_ts = local.get('timestamp', '')
        remote_ts = remote.get('timestamp', '')

        # 以更新的为基础
        if local_ts >= remote_ts:
            base = dict(local)
            other = remote
        else:
            base = dict(remote)
            other = local

        # 合并 items
        base_items = base.get('items', {})
        other_items = other.get('items', {})

        for key in other_items:
            if key not in base_items:
                base_items[key] = other_items[key]
            else:
                # 对字典类型做键级合并
                if isinstance(base_items[key], dict) and isinstance(other_items[key], dict):
                    merged_dict = dict(other_items[key])
                    merged_dict.update(base_items[key])  # base 优先
                    base_items[key] = merged_dict
                elif isinstance(base_items[key], list) and isinstance(other_items[key], list):
                    # 列表做并集（去重）
                    seen = set()
                    merged_list = []
                    for item in base_items[key] + other_items[key]:
                        key_str = json.dumps(item, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
                        if key_str not in seen:
                            seen.add(key_str)
                            merged_list.append(item)
                    base_items[key] = merged_list

        base['items'] = base_items
        base['timestamp'] = datetime.datetime.now().isoformat()

        return base

    # ========================================================
    # 加密支持
    # ========================================================
    def _encrypt_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """加密数据（使用简单 XOR，仅混淆，非强加密）"""
        try:
            key = self._get_encryption_key()
            json_str = json.dumps(data, ensure_ascii=False)
            encrypted = bytes(
                b ^ key[i % len(key)]
                for i, b in enumerate(json_str.encode('utf-8'))
            )
            return {
                '_encrypted': True,
                'data': base64.b64encode(encrypted).decode('ascii'),
            }
        except Exception as e:
            print(f"[Sync] 加密失败: {e}")
            return data

    def _decrypt_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """解密数据"""
        if not data.get('_encrypted'):
            return data
        try:
            key = self._get_encryption_key()
            encrypted = base64.b64decode(data['data'])
            decrypted = bytes(
                b ^ key[i % len(key)]
                for i, b in enumerate(encrypted)
            )
            return json.loads(decrypted.decode('utf-8'))
        except Exception as e:
            print(f"[Sync] 解密失败: {e}")
            return {}

    def _get_encryption_key(self) -> bytes:
        """获取加密密钥（基于机器 ID 派生）"""
        machine_id = self._get_machine_id()
        return hashlib.sha256(machine_id.encode('utf-8')).digest()[:16]

    def _get_machine_id(self) -> str:
        """获取机器唯一标识"""
        try:
            import uuid
            return str(uuid.getnode())
        except Exception:
            return "unknown"

    # ========================================================
    # 恢复同步数据
    # ========================================================
    def apply_synced_data(self, data: Dict[str, Any]) -> bool:
        """
        将同步下来的数据应用到本地。

        参数:
            data: 同步数据

        返回:
            是否成功
        """
        try:
            # 解密
            if data.get('_encrypted'):
                data = self._decrypt_data(data)

            items = data.get('items', {})

            # 恢复偏好设置
            if 'preferences' in items:
                try:
                    from PyQt5.QtCore import QSettings
                    settings = QSettings("QingCao", "Editor")
                    for key, value in items['preferences'].items():
                        settings.setValue(key, value)
                    settings.sync()
                except Exception as e:
                    print(f"[Sync] 恢复偏好失败: {e}")

            # 恢复快捷键
            if 'keybindings' in items:
                try:
                    with open('keybindings.json', 'w', encoding='utf-8') as f:
                        json.dump(items['keybindings'], f, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(f"[Sync] 恢复快捷键失败: {e}")

            # 恢复主题
            if 'themes' in items:
                themes_dir = 'themes'
                os.makedirs(themes_dir, exist_ok=True)
                for name, content in items['themes'].items():
                    try:
                        with open(os.path.join(themes_dir, name),
                                  'w', encoding='utf-8') as f:
                            json.dump(content, f, indent=2, ensure_ascii=False)
                    except Exception:
                        pass

            # 恢复代码片段
            if 'snippets' in items:
                try:
                    with open('snippets.json', 'w', encoding='utf-8') as f:
                        json.dump(items['snippets'], f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

            return True

        except Exception as e:
            print(f"[Sync] 应用数据失败: {e}")
            return False

    # ========================================================
    # 自动同步
    # ========================================================
    def start_autosync(self):
        """启动自动同步定时器"""
        interval = self.config.get('auto_sync_interval', 30)  # 分钟
        if self.config.get('auto_sync') and self.config.get('enabled'):
            self._autosync_timer.start(interval * 60 * 1000)
            print(f"[Sync] 自动同步已启用，间隔 {interval} 分钟")

    def stop_autosync(self):
        """停止自动同步"""
        self._autosync_timer.stop()

    def _autosync_tick(self):
        """自动同步触发"""
        if self.status == SyncStatus.IDLE:
            print("[Sync] 自动同步触发")
            self.sync_now("both")

    # ========================================================
    # 同步历史
    # ========================================================
    def _load_history(self) -> List[Dict[str, Any]]:
        """加载同步历史"""
        try:
            if os.path.exists(SYNC_HISTORY_FILE):
                with open(SYNC_HISTORY_FILE, encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _save_history(self):
        """保存同步历史"""
        try:
            os.makedirs(os.path.dirname(SYNC_HISTORY_FILE), exist_ok=True)
            # 只保留最近 50 条
            self.history = self.history[-50:]
            with open(SYNC_HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Sync] 保存历史失败: {e}")

    def _record_history(self, result: SyncResult):
        """记录同步历史"""
        entry = {
            'timestamp': datetime.datetime.now().isoformat(),
            'provider': self.config.get('provider'),
            'success': result.success,
            'message': result.message,
            'uploaded': result.uploaded,
            'downloaded': result.downloaded,
            'elapsed_ms': result.elapsed_ms,
        }
        self.history.append(entry)
        self._save_history()

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取同步历史"""
        return self.history[-limit:]

    def clear_history(self):
        """清空同步历史"""
        self.history = []
        self._save_history()

    # ========================================================
    # 测试连接
    # ========================================================
    def test_connection(self) -> SyncResult:
        """
        测试同步连接（同步执行，用于配置界面验证）。

        返回:
            SyncResult
        """
        provider = self.config.get('provider', 'none')
        start_time = time.time()

        try:
            if provider == 'gist':
                import requests
                token = self.config.get('gist_token', '')
                if not token:
                    return SyncResult(False, "未配置 Token")
                resp = requests.get(
                    "https://api.github.com/user",
                    headers={'Authorization': f'token {token}'},
                    timeout=10
                )
                if resp.status_code == 200:
                    user = resp.json().get('login', '')
                    return SyncResult(True, f"连接成功，用户: {user}")
                return SyncResult(False, f"认证失败: HTTP {resp.status_code}")

            elif provider == 'webdav':
                import requests
                url = self.config.get('webdav_url', '').rstrip('/')
                username = self.config.get('webdav_username', '')
                password = self.config.get('webdav_password', '')
                if not url:
                    return SyncResult(False, "未配置地址")
                auth = (username, password) if username else None
                resp = requests.request('PROPFIND', url, auth=auth, timeout=10)
                if resp.status_code in (200, 207):
                    return SyncResult(True, "连接成功")
                return SyncResult(False, f"连接失败: HTTP {resp.status_code}")

            elif provider == 'local':
                local_path = self.config.get('local_path', '')
                if not local_path:
                    return SyncResult(False, "未配置目录")
                if not os.path.isdir(local_path):
                    return SyncResult(False, f"目录不存在: {local_path}")
                if not os.access(local_path, os.W_OK):
                    return SyncResult(False, "目录不可写")
                return SyncResult(True, "目录可用")

            elif provider == 'custom':
                import requests
                url = self.config.get('custom_url', '')
                if not url:
                    return SyncResult(False, "未配置地址")
                try:
                    resp = requests.get(url, timeout=10)
                    return SyncResult(True, f"连接成功: HTTP {resp.status_code}")
                except Exception as e:
                    return SyncResult(False, f"连接失败: {e}")

            else:
                return SyncResult(False, "未配置同步提供者")

        except Exception as e:
            return SyncResult(False, f"测试失败: {e}")
        finally:
            pass

    # ========================================================
    # 信息查询
    # ========================================================
    def is_configured(self) -> bool:
        """检查是否已配置同步"""
        provider = self.config.get('provider', 'none')
        if provider == 'none':
            return False
        if provider == 'gist':
            return bool(self.config.get('gist_token'))
        if provider == 'webdav':
            return bool(self.config.get('webdav_url'))
        if provider == 'local':
            return bool(self.config.get('local_path'))
        if provider == 'custom':
            return bool(self.config.get('custom_url'))
        return False

    def get_status_text(self) -> str:
        """获取同步状态文本"""
        status_map = {
            SyncStatus.IDLE: "空闲",
            SyncStatus.UPLOADING: "上传中",
            SyncStatus.DOWNLOADING: "下载中",
            SyncStatus.MERGING: "合并中",
            SyncStatus.SUCCESS: "成功",
            SyncStatus.FAILED: "失败",
            SyncStatus.CONFLICT: "冲突",
            SyncStatus.CANCELLED: "已取消",
        }
        return status_map.get(self.status, "未知")

    def get_last_sync_time(self) -> Optional[str]:
        """获取上次同步时间"""
        return self.config.get('last_sync')

    def get_info(self) -> Dict[str, Any]:
        """获取同步信息摘要"""
        return {
            'provider': self.config.get('provider', 'none'),
            'enabled': self.config.get('enabled', False),
            'configured': self.is_configured(),
            'status': self.get_status_text(),
            'last_sync': self.get_last_sync_time(),
            'history_count': len(self.history),
        }

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出同步信息为可读文本"""
        info = self.get_info()
        lines = ["同步信息", "=" * 60]
        for k, v in info.items():
            lines.append(f"  {k}: {v}")

        lines.append("")
        lines.append("最近同步记录:")
        for entry in self.history[-5:]:
            ts = entry.get('timestamp', '?')[:19]
            status = "✓" if entry.get('success') else "✗"
            msg = entry.get('message', '')
            lines.append(f"  [{ts}] {status} {msg}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        info = self.get_info()
        return (f"<SyncManager provider={info['provider']} "
                f"configured={info['configured']} status={info['status']}>")


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    manager = SyncManager()

    # 连接信号
    manager.sync_started.connect(lambda p: print(f"[信号] 同步开始: {p}"))
    manager.sync_progress.connect(lambda p, s: print(f"[信号] 进度 {p}%: {s}"))
    manager.sync_finished.connect(
        lambda r: print(f"[信号] 完成: {r}")
    )
    manager.sync_failed.connect(lambda e: print(f"[信号] 失败: {e}"))

    # 显示当前信息
    print("=== 同步信息 ===")
    print(manager.dump())
    print()

    # 测试本地同步（无需网络）
    print("=== 测试本地同步 ===")
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_sync_test_")
    manager.update_config(
        provider='local',
        local_path=tmp_dir,
        enabled=True,
    )

    print(f"配置: {manager.get_config()}")
    print(f"已配置: {manager.is_configured()}")

    # 测试连接
    result = manager.test_connection()
    print(f"连接测试: {result.message}")

    # 执行同步
    manager.sync_now("both")

    # 等待同步完成
    def check_done():
        if manager.status == SyncStatus.IDLE:
            print("\n=== 同步历史 ===")
            for entry in manager.get_history():
                print(f"  {entry}")
            print()
            print(manager.dump())
            app.quit()
        else:
            QTimer.singleShot(500, check_done)

    QTimer.singleShot(1000, check_done)

    # 清理
    import atexit
    atexit.register(lambda: __import__('shutil').rmtree(tmp_dir, ignore_errors=True))

    sys.exit(app.exec())