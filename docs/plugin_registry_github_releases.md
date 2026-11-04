# 插件市场公网化：GitHub Releases 静态托管（v2.21 P1-3）

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
