# 青草编辑器 v2.8.0 发布说明

> 发布日期：2026-10-26 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.8.0`）
> 功能版本：包含 v2.7.0 全部内容。

---

## 一句话概括

v2.8.0 完成多实例协作闭环（保存广播 + 自动化冒烟）、性能门禁接入 CI、
spell_check 沙箱二阶段；日常编辑更稳，插件隔离更彻底。

---

## 新增 / 改进

### 多实例文件保存广播（P0）

- 同一用户下首个实例监听 `QLocalServer` 成为 hub，其它实例作为
  client 连接；任一实例保存文件后广播
  `{"type":"file_saved","path","mtime","pid"}`，hub 转发给所有 client；
- 收到广播的实例：**未修改→自动重载**，已修改→弹窗询问是否重载；
- 事件只含路径/时间戳，不传文件内容；无法连接时静默降级为单实例行为。

### 多实例无头冒烟（P1）

- `tools/smoke_multi_instance.py`：启动 hub+client 两个进程，
  验证广播链路（握手 → 广播 → 接收 → 退出码）；
- 已接入自托管 CI（Multi-instance smoke 步骤），并纳入 pytest。

### spell_check 沙箱二阶段（P2）

- 沙箱协议新增受限 `add_ignore_word`（RPC 白名单 + worker 校验）；
- 宿主新增「工具 → 忽略沙箱诊断中的可疑词」，逐词写忽略表后重跑诊断；
- spell_check 重新标记 `sandbox: true`：诊断与忽略词全部经子进程 RPC，
  主进程不再导入该插件。

### 性能门禁（P3）

- `tools/bench_optimization.py` 新增 `--factor` 容忍度参数；
- CI 以 `--check --factor 4.0` 运行，拦截数量级性能回退。

---

## 测试

新增：
- `tests/test_instance_broadcast.py`（3 项）
- `tests/test_multi_instance_smoke.py`
- `tests/test_sandbox_ignore_words.py`（2 项）
- `tools/multi_instance_probe.py` / `tools/smoke_multi_instance.py`

全量 pytest 通过；ruff 0；`tools/check_version` 通过；多实例冒烟连续 3 次稳定通过。

---

## 升级注意事项

1. v2.7.0 → v2.8.0 无数据迁移、无接口破坏；
2. 多实例广播只在各进程启动后生效；同一文件双实例编辑仍建议先后保存；
3. 沙箱仍需在插件 manifest 显式声明 `"sandbox": true`。

---

## 已知限制

- 多实例广播不包含"打开/关闭文件"事件，仅保存事件；
- 沙箱只支持只读扩展点（symbols/hover/completion/describe/diagnostics/
  add_ignore_word）；
- 真实双显示器 / 跨屏 DPI 变化未物理验证。

---

## 包校验

发布包由自托管 Runner 构建：

* `QingCaoEditor-v2.8.0-windows.zip`
* `QingCaoEditor-v2.8.0-windows.zip.sha256.txt`
