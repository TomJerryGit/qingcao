# 青草编辑器 v2.6.1 发布说明

> 发布日期：2026-10-23 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.6.1`）
> 维护版本：包含 v2.6.0 全部功能 + 以下基础设施修复。

---

## 一句话概括

v2.6.1 修复 v2.6.0 之后的 CI/发布链路问题：GitHub Actions 免费额度用尽
后的**自托管 Runner 迁移**、Release 发布的 **curl + UTF-8 payload** 方案、
以及遗漏提交的**拼写检查默认忽略词文件**；功能与 v2.6.0 一致。

---

## 修复

### CI 测试门禁失败

- 根因：`data/spell_ignore.txt` 被 `.gitignore` 的 `/data/` 规则忽略，
  未进入仓库 → 自托管 Runner 检出后缺文件，测试失败；
- 修复：显式提交该文件；CI 全量测试恢复绿色。

### Release 发布失败（422）

- 根因：PowerShell 5.1 将含中文的发布说明序列化为 `{"value": ...}`
  对象，GitHub API 返回 422；
- 修复：发布步骤改为 **curl + UTF-8 payload 文件**，并加
  重试（5 次指数退避）、上传结果校验、已存在资产跳过、结束前资产复核。

### Actions 免费额度用尽导致秒级失败

- 根因：私有仓库每月 2000 分钟用满，非自托管任务启动即失败；
- 修复：`test.yml` / `release.yml` 全部迁移到**自托管 Runner**，
  且**零外部 action**（SSH 检出 + 本地 Python + REST API），
  不再消耗额度。

---

## 基础设施

- 自托管工作流对 Runner 环境做兼容：显式 `powershell` shell、
  `$ErrorActionPreference="Continue"`（原生命令 stderr 不再误判失败）、
  PowerShell 执行策略 RemoteSigned（一次性配置）；
- 新增 `tools/release_local.py`：断网时本地一键构建 + 打包 + 生成
  网页发布清单；
- CI 关键步骤输出写入本地日志（`D:\actions-runner\release.log` /
  `test.log`），便于无 UI 环境诊断。

---

## 升级注意事项

1. v2.6.0 → v2.6.1 无数据迁移、无接口变化；
2. 仅 CI/数据文件修复，用户使用体验与 v2.6.0 相同。

---

## 已知限制

- 沙箱仅支持只读扩展点（symbols/hover/completion/describe/diagnostics）；
- 主题切换未覆盖所有独立顶层对话框（C-2 待做）；
- 真实双显示器 / 跨屏 DPI 变化未物理验证。

---

## 包校验

发布包由自托管 Runner 在 windows x64 构建：

* `QingCaoEditor-v2.6.1-windows.zip`
* `QingCaoEditor-v2.6.1-windows.zip.sha256.txt`

```powershell
Get-FileHash .\QingCaoEditor-v2.6.1-windows.zip -Algorithm SHA256
# 与 .sha256.txt 比对
```
