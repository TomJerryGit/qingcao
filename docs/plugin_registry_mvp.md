# 插件市场在线服务化 MVP（v2.18）

> 目标：本地/内网起一个插件市场注册表服务，完成"发布 → 签名 → 市场拉取 →
> 验签安装"的完整闭环，为后续公网市场打基础。

## 1. 生成签名密钥

```powershell
python tools/sign_plugin.py --keygen
# 输出 PRIVATE_KEY=<hex> / PUBLIC_KEY=<hex>
```

## 2. 生成注册表（打包 + SHA256 + Ed25519 签名）

```powershell
python tools/build_plugin_registry.py ^
  --out data/registry ^
  --base-url http://127.0.0.1:8765 ^
  --key-hex <PRIVATE_KEY>
# 可选：--only wordcount_sandbox,whitespace_sandbox
```

产物：

- `data/registry/registry.json`
- `data/registry/plugins/<name>-<version>.zip`
- 每个插件条目含 `file_hash`（SHA256）、`signature`/`signature_algo=ed25519`

## 3. 启动注册表服务

```powershell
python tools/plugin_registry_server.py --registry data/registry --port 8765
# 自检（不启动服务）：
python tools/plugin_registry_server.py --registry data/registry --check
```

访问：`http://127.0.0.1:8765/registry.json`

## 4. 客户端配置

1. 设置环境变量（验签公钥）：

```powershell
$env:QINGCAO_PLUGIN_PUBKEYS = "<PUBLIC_KEY>"
```

2. 打开编辑器 → 工具 → 🧩 插件市场 → 「注册表 URL」填
   `http://127.0.0.1:8765/registry.json` → 应用并刷新；

3. 安装插件：下载 → SHA256 校验 → Ed25519 验签 → 解压安装 → 提示重载。

## 5. 失败路径（已验证）

| 场景 | 行为 |
|---|---|
| 插件包被篡改 | 哈希/签名校验失败，安装中止 |
| 未配置公钥 | 带签名插件拒绝安装（fail closed） |
| 被吊销插件 | 市场显示「已吊销」，安装被拒 |
| 服务不可用 | 回退本地目录/缓存，市场不空白 |

## 6. 测试

```powershell
python -m pytest tests/test_v218_registry.py -q
```

覆盖：注册表生成、HTTP 服务、客户端 schema 兼容、Ed25519 验签、
篡改拒绝、`--check` 自检。

## 7. 已知限制

- MVP 面向本地/内网，HTTP 无鉴权、无 HTTPS；
- 注册表为静态 JSON，发布需手动重新生成；
- 公网市场需要：HTTPS、签名密钥托管/轮换、审核与评分体系。
