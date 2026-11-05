# 青草编辑器 v2.22.0 发布说明

> 发布日期：2026-11-05 · 版本：2.22.0
> 主题：**稳定性专项（启动期崩溃修复）**

## 修复
### 启动期 Windows fatal exception 0x8001010d
- 根因：更新检查后台线程 DNS（requests/getaddrinfo）与每日技巧模态对话框并发触发 COM/RPC 限制；
- 修复：
  - 更新检查改为**界面空闲后延迟启动**（默认 15s，模态窗口存在时重试）；
  - **迁移 QNetworkAccessManager 主线程异步**（彻底移除后台 DNS 线程）；
  - 15s 超时自动取消；关闭窗口时 `cancel()`；
  - 修正更新仓库 URL 为 `TomJerryGit/qingcao`；
- 新增网络超时审计 `tools/audit_network_threads.py`（AST，0 违规）；
- 崩溃根因文档 `docs/crash_root_cause_0x8001010d.md`。

## 新增
- **应用内反馈入口**：帮助 → 💬 反馈与建议（本机 JSONL，不上传；含体验反馈分类）；
- **P2 体验冒烟**：`tools/smoke_check.py` 自动冒烟（10/10）+ `docs/smoke_checklist_v2.22.md` 人工清单；
- **v2.22 优先级报告**：`docs/v2.22_prioritization.md`。

## 验证
- 修复回归测试 8 项；
- 分片并行全量：144 个测试文件全绿；
- 冒烟会话：启动→正常退出（exit 0），无新崩溃；
- CI：全量测试 + i18n（中/英/繁中/日韩试点）+ 性能/主题/无障碍门禁全绿。

## 升级
v2.21.2 → v2.22.0 无数据迁移；更新检查在启动 15s 后空闲时执行属预期。
