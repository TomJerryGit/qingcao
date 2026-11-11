# 青草编辑器 v2.25+ 建设与优化路线图

> 基线：v2.24.6（审计 8.4/10，见 `docs/audit_v2.24.6.md`）· 制定：2026-11-11

## 总目标（3 个月）

| 目标 | 从 | 到 |
|---|---|---|
| 综合评分 | 8.4 | **8.8+** |
| CI 可靠性 | 单 runner、卡死阻塞 5h | 卡死 <15 分钟自动恢复；发布不排队 >30 分钟 |
| 架构长尾 | 6 个 1.5–1.57k 文件 | 0 个 >1,300 行业务文件 |
| 生态评分 | 16 条 / count=1 | ≥50 条、≥3 位评分用户 |
| 安全门禁 | 扫描偏旧 | 发布前置强制安全扫描 + 签名全链路 |

## 阶段 1：CI 可靠性 + 安全门禁（v2.25.0，1–2 周）

| # | 任务 | 验收标准 | 工作量 |
|---|---|---|---|
| 1.1 ✅ | 所有 workflow job 加 `timeout-minutes`（test 45 / release 60 / security 20 / lint 30 / linux 40 / publish 20） | 卡死任务自动失败 | 0.5d |
| 1.2 ✅ | `tools/ci_watchdog.py` + `.github/workflows/ci-watchdog.yml`（hosted runner，每 30 分钟检测/取消超 120 分钟运行） | 卡死自动取消 | 1d |
| 1.3 ✅ | release.yml 新增 `gates` job：`tools/ci_release_gate.py` 等待该 SHA 的 Test/Security/Lint 成功（最多 35 分钟），`build-release` 依赖 `needs: gates` | 失败/超时则不构建发布 | 1d |
| 1.4 ✅ | GitHub 托管 Windows 兜底测试工作流 `test-fallback.yml`；watchdog 检测到 Test 排队 >90 分钟且无兜底运行时自动派发（按 SHA 去重） | 卡死/长队列时自动兜底 | 1d |
| 1.5 ✅ | security.yml 每日 03:00 UTC 定时 + 汇总/归档（security-reports，保留 30 天）；watchdog 检测最近成功扫描 >26h 自动派发 | 扫描新鲜度自动维持 | 0.5d |

**里程碑 M1（v2.25.0）**：CI 不再阻塞发布；安全扫描新鲜；评分 8.5。

## 阶段 2：架构长尾 + flaky 崩溃治理（v2.25.1–.2，2–3 周）

| # | 任务 | 验收标准 | 工作量 |
|---|---|---|---|
| 2.1 ✅ | `icon_manager.py` 1,568 → **609**（common 152 / cache 87 / providers 686），对外导入兼容 | 主文件 <900，测试通过 | 1d |
| 2.2 ✅ | `welcome_widget.py` 1,537 → **504**（common 176 / cards 194 / recent 310 / stats 386），`C`/`WelcomeWidget` 导出兼容 | 主文件 <900，测试通过 | 1d |
| 2.3 ✅ | `capability_wiring_mixin.py` 1,537 → **75**（keyseq 275 / plugins 326 / panels 553 / commands 292），MRO 兼容 | 主文件 <160，测试通过 | 1d |
| 2.4 ✅ | global_search **1,514→986**、keymap_editor **1,503→676**、lsp_client **1,501→1,217**；新增 `test_phase24_splits` 门禁 | 全部 <1,300，测试通过 | 2d |
| 2.5 ✅ | `tools/crash_triage.py`：聚合 faulthandler 转储 + CI flaky 历史，输出 `docs/crash_triage_report.md` / `data/crash_triage.json`（当前基线：9 dumps / 8 flaky / 3 组） | 聚合可用，flaky 下降持续跟踪 | 2d |
| 2.6 | 架构门禁加严：业务文件 ≤1,300、全局 ≤1,800 | CI 强制 | 0.5d |

**里程碑 M2（v2.25.2）**：全仓业务文件 ≤1,300；flaky 有数据可见；评分 8.6。

## 阶段 3：生态 + 用户体验（v2.26，3–4 周）

| # | 任务 | 验收标准 | 工作量 |
|---|---|---|---|
| 3.1 | 评分运营：应用内邀请 → Issue 模板 → 自动收集 → 聚合发布（含 count 门禁） | ≥50 条评分、≥3 用户 | 2d（+运营） |
| 3.2 | 插件开发文档 + 模板生成器 `tools/new_plugin.py` | 新插件 10 分钟内可跑通 | 1d |
| 3.3 | 市场体验：评分筛选、详情对比、更新公告 | 用户验收通过 | 2d |
| 3.4 | 终端 P7：滚动条缓冲可视、vim 真机验证清单 | vim/top 可用（真机） | 1.5d |
| 3.5 | 真机首帧 QA：测量工具基线 + 目测清单 | 首帧 P95 < 0.8s（真机） | 1d |

**里程碑 M3（v2.26.0）**：生态指标达标；评分 8.7。

## 阶段 4：v3.0 探索（按季度评估）

- Windows Authenticode 代码签名（安装包/更新）；
- 插件沙箱强化（进程级隔离/权限最小化）；
- 更新密钥轮换与多密钥信任链；
- 性能回归看板（自动对比历史、异常告警）；
- 托管 CI/多平台（Linux AppImage 已有，补齐 macOS 可行性评估）。

## 本周立即行动（Top 3）

1. 给 `test.yml`/`release.yml`/`security.yml` 加 `timeout-minutes`（0.5d）；
2. 提交 `tools/ci_watchdog.py` + 队列告警（1d）；
3. 重跑 security.yml 并归档报告（0.5d）。

## 风险与依赖

| 风险 | 缓解 |
|---|---|
| self-hosted runner 单点 | 加超时/看守 + 备用 runner/托管兜底 |
| 拆分回归 | 每文件拆分后跑对应测试 + 架构门禁 + 全量 CI |
| 生态冷启动 | 评分邀请 + 插件模板 + 征集活动 |
| 原生崩溃难复现 | faulthandler/minidump 数据聚合，优先定位 top crash |
