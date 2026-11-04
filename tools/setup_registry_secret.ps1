# 一键配置 GitHub secret 并发布插件注册表（v2.21 P1-3）
# 前置：gh auth login（需 repo + workflow 权限）或设置 GH_TOKEN 环境变量。
$ErrorActionPreference = "Stop"
$gh = "D:\Programs\gh\bin\gh.exe"
$repo = "TomJerryGit/qingcao"
$keyFile = Join-Path $env:USERPROFILE ".qingcao\plugin_sign_key.hex"
if (-not (Test-Path $keyFile)) {
    throw "缺少密钥：$keyFile（先运行 python tools/sign_plugin.py --keygen）"
}
$oldEap = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
& $gh auth status 2>&1 | Out-Null
$authed = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $oldEap
if (-not $authed) {
    Write-Output "gh 未登录：请先运行 gh auth login（或设置 GH_TOKEN），然后重新运行本脚本。"
    exit 2
}
$key = (Get-Content $keyFile -Raw).Trim()
& $gh secret set QINGCAO_PLUGIN_SIGN_KEY --repo $repo --body $key
if ($LASTEXITCODE -ne 0) { throw "设置 secret 失败" }
& $gh workflow run publish_registry.yml --repo $repo
if ($LASTEXITCODE -ne 0) { throw "触发工作流失败" }
Start-Sleep -Seconds 8
& $gh run list --repo $repo --workflow publish_registry.yml --limit 1
Write-Output "已触发发布；完成后公网注册表："
Write-Output "https://github.com/$repo/releases/download/plugin-registry/registry.json"