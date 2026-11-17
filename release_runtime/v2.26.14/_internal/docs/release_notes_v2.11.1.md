# 青草编辑器 v2.11.1 发布说明

> 发布日期：2026-10-27 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.11.1`）
> 维护版本：包含 v2.11.0 全部内容。

---

## 一句话概括

v2.11.1 为工程收尾版本：发布日志可诊断性、测试稳定性工具、
自托管 Runner 服务化文档与实测结论进入正式发布。

---

## 改进

### 发布链路可诊断性

- CI 发布步骤输出改为 **UTF-8 独立日志**（`D:\actions-runner\publish_utf8.log`），
  失败时可直接定位到具体 API/上传错误，不再受 PowerShell 混编码干扰。

### 测试稳定性

- 新增 `tools/verify_test_stability.py`：
  - 支持多轮重复运行（`--runs`）与核心子集快速检查（`--quick`）
  - 自动识别偶发崩溃并标注 `CRASH`
- 新增 `docs/test_stability.md`：已知偶发点、处理方式、CI 策略。

### 自托管 Runner 服务化（实测）

- 已安装并验证 Windows 服务：
  `actions.runner.TomJerryGit-qingcao.qingcao-local-runner`
  - Automatic（Delayed Auto Start），以 `Administrator` 账户运行
  - 实测服务接管 `test` / `test-py312` 任务成功
- 旧的 Startup/HKCU 自启项已清理；
- 操作手册：`docs/runner_service.md`。

---

## 测试

全量 pytest 通过；ruff 0；`tools/check_version` 通过。

---

## 升级注意事项

1. v2.11.0 → v2.11.1 无数据迁移、无接口破坏；
2. 仅工程/CI/文档层面改进，功能与 v2.11.0 相同。

---

## 已知限制

- 跨屏 DPI 与系统高对比度仍需真机人工验证；
- Python 3.12 为软矩阵（不阻塞发布）；
- 全量 offscreen 测试仍存在极低概率偶发崩溃（已提供稳定性复跑工具）。

---

## 包校验

发布包由自托管 Runner 构建：

* `QingCaoEditor-v2.11.1-windows.zip`
* `QingCaoEditor-v2.11.1-windows.zip.sha256.txt`
