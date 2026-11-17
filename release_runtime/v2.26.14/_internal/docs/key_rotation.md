# 签名密钥轮换（v2.25 实现）

## 现状与目标

- 现有：单 Ed25519 密钥，客户端通过 `QINGCAO_PLUGIN_PUBKEYS`（部分场景）验证裸 base64 签名；
- 目标：支持 **key_id + 信任清单 + 双签过渡 + 吊销**，旧客户端/旧签名继续可用。

## 信任清单

`resources/trusted_keys.json`（或 `QINGCAO_TRUST_STORE` 指定的文件）：

```json
{
  "version": 1,
  "keys": [
    {"key_id": "1f32f745", "public_key": "1f32...", "not_before": "2026-01-01",
     "not_after": "2027-12-31", "revoked": false}
  ]
}
```

- `key_id`：公钥 hex 前 8 位；
- 有效期与吊销在验证时检查；过期/吊销的 key 直接拒绝；
- 环境变量 `QINGCAO_PLUGIN_PUBKEYS` 仍作为兜底（无信任清单时）。

## 签名信封（双签）

新格式（`.sig` 文件为 JSON）：

```json
{
  "version": 1,
  "signatures": [
    {"key_id": "1f32f745", "signature": "<base64>"},
    {"key_id": "88b6626e", "signature": "<base64>"}
  ]
}
```

客户端 `core.plugin_signature.verify_signature_envelope`：
1. 若是信封 → 按 `key_id` 在信任清单中找 key，校验有效期/吊销后验签；
2. 若是旧裸 base64 → 走原有 `verify_ed25519`（环境变量公钥）；
3. 插件市场、更新资产验证均已切换到信封函数（自动兼容旧格式）。

## 轮换流程（90 天双签）

```powershell
# 1. 生成新密钥（私钥离线保存，勿提交）
python tools/key_rotation.py --keygen
# 2. 新公钥加入信任清单（生效日 = 今天）
python tools/key_rotation.py --make-trust-store --pub <new_pub_hex> --out resources/trusted_keys.json
# 3. 双签现有资产（旧 key + 新 key）
python tools/key_rotation.py --sign QingCaoEditor-vX.zip --key <old_priv> --key <new_priv>
# 4. 发布（客户端两个 key 都信任）
# 5. 90 天后：旧 key 置 revoked:true 或 not_after 过期，重新签名单签
# 6. 验证
python tools/key_rotation.py --verify QingCaoEditor-vX.zip --sig QingCaoEditor-vX.zip.sig
```

## 验收

- 信封签名验证 PASS；吊销/过期 key 验证 FAIL；
- 旧裸签名仍 PASS（兼容矩阵测试 `tests/test_v225_key_rotation.py`）；
- 生产公钥已写入 `resources/trusted_keys.json`（key_id `1f32f745`）。

## 后续

- 注册表/更新发布流水线切换到信封签名（发布工具已支持 `--sign`）；
- root key 离线签名信任清单（当前清单随仓库分发，后续可加 root 签名校验）；
- v3.0 完成密钥轮换演练并归档旧 key。
