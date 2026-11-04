# 插件市场公网化：GitHub Releases 静态托管（v2.21 P1-3）

> ✅ **已上线（2026-11-04）**：Release `plugin-registry`，13 个插件包，SHA256/Ed25519 抽查通过。

零域名/零证书方案：用 GitHub Release 资产提供 HTTPS 注册表与插件包。

## 发布
```powershell
python tools/publish_registry_release.py --dry-run          # 构建校验
$env:GITHUB_TOKEN = "<token>"
python tools/publish_registry_release.py --token $env:GITHUB_TOKEN
```
专用 Release（tag `plugin-registry`）产物：registry.json + 插件 zip。
公网 URL：https://github.com/TomJerryGit/qingcao/releases/download/plugin-registry/registry.json
客户端常量：`ui/plugin_store.py::GITHUB_REGISTRY_URL`。

## 客户端
插件市场 → 注册表 URL 填入上述地址；公钥沿用 QINGCAO_PLUGIN_PUBKEYS。

## 回滚 / 安全
删除或替换 Release 资产即可回滚；客户端有缓存与离线回退。
私钥仅存 CI secret；签名覆盖 zip 原始字节；发布前 dry-run 校验。

## 一键配置（需 GitHub 认证）

`powershell
gh auth login                       # 或 $env:GH_TOKEN = "..."
powershell -File tools/setup_registry_secret.ps1
`

脚本会：设置 secret QINGCAO_PLUGIN_SIGN_KEY → 触发 Publish Plugin Registry → 打印公网 URL。

## 签名公钥（客户端信任锚）

`
1f32f745a66e5b1782f974580f1f919b9970aa26e3be7f8d87b17dff5c2370c0
`

客户端设置：` $env:QINGCAO_PLUGIN_PUBKEYS = "1f32f745a66e5b1782f974580f1f919b9970aa26e3be7f8d87b17dff5c2370c0" `（或写入配置），
然后插件市场注册表 URL 填：
https://github.com/TomJerryGit/qingcao/releases/download/plugin-registry/registry.json
## 上线验证记录

- workflow run `41798754204`：success；
- Release 资产 14 个（registry.json + 13 zip）；
- 抽查 3 个插件包：SHA256 3/3、Ed25519 3/3 通过。


## 更新插件（发布新版本）

1. 修改插件并提升 `plugins/<name>/plugin.json` 的 `version`（可加 `changelog`）；
2. 提交后运行发布（secret 已配置，无需再设）：

```powershell
powershell -File D:\QingCaoEditor\tools\setup_registry_secret.ps1
```

脚本会重设 secret 并触发 `Publish Plugin Registry`；完成后市场刷新即可看到新版本。

## 更新验证记录（2026-11-04）

- workflow run `41799677718`：success；
- registry 中 `wordcount_sandbox` = **1.0.1**；
- `wordcount_sandbox-1.0.1.zip`：SHA256 匹配、Ed25519 验签通过。
