# 自托管 Runner 服务化操作手册

> 目标：让 GitHub Actions Runner 在**开机/登录后自动运行**，
> 并说明真正 Windows 服务化的条件与步骤。

---

## 当前状态（v2.11.0 基线）

| 项 | 状态 |
|---|---|
| Runner 目录 | `D:\actions-runner`（2.338.1） |
| 已注册 | `qingcao-local-runner`，连接正常（Listening for Jobs） |
| 包内服务脚本 | **无 `svc.cmd`**（该分发包只含 config/run/run-helper） |
| 当前权限 | 非管理员会话 |
| 已配置自启 | ✅ **Windows 服务** `actions.runner.TomJerryGit-qingcao.qingcao-local-runner`（延迟自动启动，以 Administrator 账户运行） |

`start-runner.vbs` 逻辑：隐藏窗口执行 `cmd /c run.cmd > runner.log 2>&1`，
保留当前用户环境（SSH key、Python 3.11、git）。

---

## 真·Windows 服务化（需管理员）

### 前提

1. 管理员权限 PowerShell；
2. 本地账户密码（服务以该账户运行，才能使用
   `C:\Users\Administrator\.ssh` 的 SSH key 与 Python 环境）；
3. Runner 注册 token（GitHub → Settings → Actions → Runners → New runner）。

### 步骤（推荐：用 config.cmd 重建）

```powershell
cd D:\actions-runner
# 1) 移除现有注册（会提示确认）
.\config.cmd remove

# 2) 以服务方式重新配置（<TOKEN> 为新的注册 token）
.\config.cmd --unattended --replace `
  --url https://github.com/TomJerryGit/qingcao `
  --token <TOKEN> `
  --name qingcao-local-runner `
  --work _work `
  --runasservice `
  --windowslogonaccount <本地账号> `
  --windowslogonpassword <密码>

# 3) 启动服务
Start-Service actions.runner.*
Get-Service actions.runner.*
```

### 备选：手动创建服务（若包内后来补回 svc.cmd）

```powershell
cd D:\actions-runner
.\svc.cmd install
.\svc.cmd start
.\svc.cmd status
```

---

## 注意事项

- **不要**把服务配成 `LocalSystem`：会丢失用户 SSH key/Python 路径，
  CI 检出与构建都会失败；
- 若坚持 LocalSystem，需要：
  - 为 LocalSystem 配置可用凭据（HTTPS token 检出 + 系统级 Python）；
  - 或改用 `actions/checkout`（需 github.com 可达，当前被网络阻断）；
- 服务化后 Startup/HKCU Run 自启项应移除，避免重复进程：
  ```powershell
  Remove-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name QingCaoActionsRunner
  Remove-Item "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\QingCaoActionsRunner.vbs"
  ```

---

## 验证

```powershell
Get-Service actions.runner.*          # Running
D:\actions-runner\runner.log           # Listening for Jobs
```

CI 侧：推送任意提交后 Actions 页面应看到该 Runner 接管任务。