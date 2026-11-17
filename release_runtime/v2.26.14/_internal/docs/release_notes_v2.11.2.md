# 青草编辑器 v2.11.2 发布说明

> 发布日期：2026-10-27 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.11.2`）
> 维护版本：包含 v2.11.1 全部内容。

---

## 一句话概括

v2.11.2 为 CI 与测试稳定性加固版本：修复软矩阵 job 误报失败、
引入分片+重试+崩溃定位、隔离测试 QSettings，消除顺序敏感 flaky。

---

## 改进

### CI 软矩阵修复

- 根因：Runner 写出的 `.ps1` 为 UTF-8 无 BOM，Windows PowerShell 5.1
  按 GBK 解析，脚本内中文字符串导致 `ParserError` → job 误报失败；
- 修复：软矩阵脚本改纯 ASCII 输出，并增加**全工作流 run 块 ASCII 审计**；
- 现在 Python 3.12 缺失时 job 显示成功（静默跳过），不再污染 CI 观感。

### 测试稳定性：分片 + 重试 + 崩溃定位

- 新增 `tools/run_tests_sharded.py`：
  - 测试文件轮转分片（`--shards`）
  - 失败分片自动重试（`--retries`）
  - `--localize` 逐文件定位崩溃/失败点（日志 `data/test_shards/`）
- CI 全量测试改为分片运行（2 片 + 重试 1 次 + 自动定位）。

### 测试 QSettings 隔离（消除顺序敏感 flaky）

- 根因：测试通过 MainWindow 把布局/面板可见性写入**真实 QSettings**，
  同进程后序测试恢复该状态 → 顺序敏感失败（分片时暴露），并污染用户配置；
- 修复：`tests/conftest.py` 新增 session 级 autouse fixture
  `_isolated_qsettings`，把 QSettings 重定向到临时目录，结束后恢复。

---

## 测试

- 分片运行：96 个测试文件 → 2 片，**全部通过**；
- ruff 0；`tools/check_version` 通过。

---

## 升级注意事项

1. v2.11.1 → v2.11.2 无数据迁移、无接口破坏；
2. 功能与 v2.11.1 相同，改动集中在 CI/测试基础设施。

---

## 已知限制

- 跨屏 DPI 与系统高对比度仍需真机人工验证；
- 偶发 offscreen 崩溃已通过分片+重试缓解，根因仍在持续观察；
- Python 3.12 为软矩阵（不阻塞发布）。

---

## 包校验

发布包由自托管 Runner 构建：

* `QingCaoEditor-v2.11.2-windows.zip`
* `QingCaoEditor-v2.11.2-windows.zip.sha256.txt`
