# Authenticode 申请与 Secrets 配置步骤（可执行清单）

## A. 申请（三选一）

### A1. SignPath Foundation（开源免费，推荐先试）
1. 打开 https://signpath.org/apply 提交项目（公开仓库、许可证、维护者信息）；
2. 审核通过后创建 Project/Artifact Configuration（Windows ZIP/EXE）；
3. 按 SignPath 文档在 GitHub Actions 集成（或导出证书给本地 signtool）。

### A2. Azure Trusted Signing
1. Azure 订阅 + 组织验证（需 3 年历史/域名邮箱等条件）；
2. 创建 Trusted Signing Account + Certificate Profile；
3. GitHub Actions 用 `azure/trusted-signing-action`（无需 PFX Secret）。

### A3. OV/EV 证书（DigiCert/Sectigo 等）
1. 提交企业/个人信息 + 电话验证；
2. 收到硬件令牌或 PFX；
3. 导出 PFX（含私钥）用于 CI Secret。

## B. 配置 GitHub Secrets（PFX 方案）

PowerShell（在证书文件所在机器执行；`GH_TOKEN` 需 repo admin）：

```powershell
$env:GH_TOKEN = "<管理员 PAT>"
$pfx = "C:\path\cert.pfx"
$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($pfx))
gh secret set WINDOWS_SIGN_CERT_BASE64 --body $b64 --repo TomJerryGit/qingcao
gh secret set WINDOWS_SIGN_CERT_PASSWORD --body "<pfx-password>" --repo TomJerryGit/qingcao
```

> 不要把 PFX/密码提交到仓库；配置后本地删除临时 PFX。

## C. 验证

```powershell
python tools/check_signing_secrets.py --repo TomJerryGit/qingcao
# 期望：WINDOWS_SIGN_CERT_BASE64: configured / WINDOWS_SIGN_CERT_PASSWORD: configured
```

下次打 tag 发布时 `release.yml` 的 `Authenticode Sign (optional)` 会自动：
1. 解码 PFX → signtool 签名 `dist/QingCaoEditor/**/*.exe`；
2. `Get-AuthenticodeSignature` 校验，失败即中止发布；
3. 清理临时 PFX。

## D. 发布后验收

- 下载安装包 → 右键 exe → 数字签名 → 证书主体 = 你的组织；
- `Get-AuthenticodeSignature` 显示 Valid；
- SmartScreen 信誉随下载量累积（EV 更快）。
