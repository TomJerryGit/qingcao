# 一键配置 GitHub secret 并发布插件注册表（v2.21 P1-3）
# 支持：环境变量 GH_TOKEN/GITHUB_TOKEN，或交互式安全输入（不回显）
$ErrorActionPreference = "Stop"
$gh = "D:\Programs\gh\bin\gh.exe"
$repo = "TomJerryGit/qingcao"
$keyFile = Join-Path $env:USERPROFILE ".qingcao\plugin_sign_key.hex"

if (-not (Test-Path $keyFile)) {
    throw "缺少密钥：$keyFile（先运行 python tools/sign_plugin.py --keygen）"
}

$token = $env:GH_TOKEN
if (-not $token) { $token = $env:GITHUB_TOKEN }
if (-not $token) {
    if ([Environment]::UserInteractive) {
        Write-Output "未检测到 GH_TOKEN；请输入 GitHub PAT（输入不回显，不会写入历史）"
        $secure = Read-Host "PAT" -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $token = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}
if (-not $token) {
    Write-Output "未提供 token。请设置 `$env:GH_TOKEN='<新PAT>'（勿粘贴到聊天），或交互运行本脚本。"
    exit 2
}
$env:GH_TOKEN = $token

$key = (Get-Content $keyFile -Raw).Trim()
& $gh secret set QINGCAO_PLUGIN_SIGN_KEY --repo $repo --body $key
if ($LASTEXITCODE -ne 0) { throw "设置 secret 失败（检查 PAT 是否含 repo/workflow 权限）" }
Write-Output "secret 已设置：QINGCAO_PLUGIN_SIGN_KEY"
& $gh workflow run publish_registry.yml --repo $repo
if ($LASTEXITCODE -ne 0) { throw "触发工作流失败" }
Write-Output "已触发发布工作流；等待完成后访问："
Write-Output "https://github.com/$repo/releases/download/plugin-registry/registry.json"
Start-Sleep -Seconds 8
& $gh run list --repo $repo --workflow publish_registry.yml --limit 1