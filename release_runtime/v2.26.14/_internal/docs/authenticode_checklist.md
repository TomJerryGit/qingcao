> **决策（2026-11-12）：本项目不再申请 Authenticode 证书**；发布完整性使用 SHA256 + Ed25519 `.sig`。以下内容仅作历史/备查。

﻿# Authenticode 接入 checklist（Windows）

> 目标：安装包/可执行文件签名，减少 SmartScreen 拦截；与现有 Ed25519 更新链路互补。

## 1. 证书获取（三选一）

| 方案 | 适用 | 成本/周期 |
|---|---|---|
| SignPath Foundation（开源计划） | 开源项目首选 | 免费，审核周期数天–数周 |
| Azure Trusted Signing | 组织账号 | 低价订阅，需资格审核 |
| OV/EV 代码签名证书（DigiCert/Sectigo 等） | 商业长期 | $200–500/年 + 硬件令牌/HSM |

## 2. GitHub Secrets（仓库 Settings → Secrets）

| Secret | 内容 |
|---|---|
| `WINDOWS_SIGN_CERT_BASE64` | PFX 证书文件的 Base64 |
| `WINDOWS_SIGN_CERT_PASSWORD` | PFX 密码 |

> 未配置时 release 工作流的签名步骤自动跳过，不影响现有发布（Ed25519 `.sig` 仍保留）。

## 3. 流水线（已内置）

`release.yml` → `Authenticode Sign (optional)`（Build 之后、Package 之前）：

- 解码 PFX 到 runner 临时目录；
- 查找 Windows SDK `signtool.exe`（x64）；
- 对 `dist/QingCaoEditor/**/*.exe` 逐个签名：
  `signtool sign /fd SHA256 /f pfx /p pass /tr http://timestamp.digicert.com /td SHA256 <exe>`
- 立即 `Get-AuthenticodeSignature` 校验，非 `Valid` 则构建失败；
- 清理临时 PFX。

## 4. 发布前人工验收

- [ ] `Get-AuthenticodeSignature .\QingCaoEditor.exe` → `Status = Valid`；
- [ ] 安装包/主程序属性 → 数字签名可见；
- [ ] 新机器首次运行 SmartScreen 提示减少（信誉需时间积累）；
- [ ] SHA256 + Ed25519 `.sig` 仍上传（双保险）。

## 5. 轮换与吊销

- 证书到期前 30 天更新 Secret；
- 私钥泄露：立即吊销证书 + 更换 Secret + 重发版本；
- 与 `docs/key_rotation.md` 的 Ed25519 轮换独立进行。

## 6. 后续

- 若采用 SignPath/Azure，可改为托管签名（无需在 runner 存 PFX）；
- 将 `AuthenticodeOK` 纳入发布门禁（当前已内联校验）。
