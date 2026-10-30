# 插件签名密钥轮换/吊销操作手册（v2.16）

## 1. 生成密钥对

```powershell
python tools/sign_plugin.py --keygen
# 输出 PRIVATE_KEY=...（离线保存，勿入库） PUBLIC_KEY=...
```

## 2. 签名插件包

```powershell
python tools/sign_plugin.py --sign QingCaoEditor-plugin-x.zip --key <私钥hex>
# 输出 SHA256=... SIGNATURE=...
```

把 `sha256` 填入插件注册表 `file_hash`，`SIGNATURE` 填入 `signature`，
并在条目中设 `signature_algo: "ed25519"`。

## 3. 客户端配置

```powershell
$env:QINGCAO_PLUGIN_PUBKEYS = "<pub1_hex>,<pub2_hex>"  # 支持多个（轮换期）
```

## 4. 轮换流程

1. 生成新密钥对；
2. 客户端环境变量**同时**配置旧公钥 + 新公钥；
3. 用新私钥重新签名插件并发布；
4. 观察一个发布周期后，从环境变量移除旧公钥。

## 5. 吊销流程

```powershell
$env:QINGCAO_PLUGIN_REVOKED = "bad_plugin,old_plugin"
```

- 被吊销插件在市场中显示「已吊销」，安装入口会被拒绝；
- 吊销是**客户端侧**即时生效，无需重新发布插件包。

## 6. 故障排查

| 现象 | 原因 |
|---|---|
| 「未配置公钥」 | 未设置 `QINGCAO_PLUGIN_PUBKEYS` |
| 「签名校验失败」 | 私钥/公钥不匹配，或包内容被修改 |
| 「未配置签名密钥」 | HMAC 回退路径缺少 `QINGCAO_PLUGIN_SIGNING_KEY` |

## 7. 相关文件

- `core/plugin_signature.py`（Ed25519 校验/吊销）
- `ui/plugin_store.py::verify_plugin_signature`（安装前校验）
- `tools/sign_plugin.py`（签名工具）
- `docs/plugin_market_security.md`
