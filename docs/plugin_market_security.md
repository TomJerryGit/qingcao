# 插件市场安全校验（v2.15.x P3）

> 目标：在线安装插件前验证**完整性**与**来源签名**，失败则拒绝安装（fail closed）。

## 校验链

1. **SHA256 校验和**（注册表 `file_hash`）
   - `verify_plugin_signature(data, expected_hash)`；
   - 不匹配 → 「文件哈希校验失败」，终止安装。
2. **HMAC 签名**（注册表 `signature`，可选）
   - 签名算法：`HMAC-SHA256(key, sha256_hex(plugin_bytes))`；
   - 密钥来自环境变量 `QINGCAO_PLUGIN_SIGNING_KEY`；
   - **未配置密钥时拒绝**带签名安装（防降级绕过）；
   - 使用 `hmac.compare_digest` 常量时间比较。
3. 解压前完成上述校验（`PluginStoreClient.install_plugin`）。

2b. **Ed25519 非对称签名**（v2.16）
   - 公钥：`QINGCAO_PLUGIN_PUBKEYS`（hex/base64，逗号分隔，支持轮换）；
   - 吊销：`QINGCAO_PLUGIN_REVOKED`（插件名列表）；
   - 签名算法：Ed25519（`cryptography`），失败回退 HMAC；
   - 入口：`core/plugin_signature.py::verify_ed25519`。

## 代码入口

- `ui/plugin_store.py::verify_plugin_signature`
- `ui/plugin_store.py::PluginStoreClient.install_plugin`
- 测试：`tests/test_p3_security_market_debugger.py`

## 已知限制 / 后续

- HMAC 为对称签名，适合官方注册表托管场景；去中心化市场需 Ed25519/RSA 非对称签名；
- 插件解压后的静态审计（权限越权）尚未自动化（见 `tools/audit_plugins.py`）。
