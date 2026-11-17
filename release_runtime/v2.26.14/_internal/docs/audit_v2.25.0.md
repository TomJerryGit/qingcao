# 青草编辑器 v2.25.0 审计与评价

> 审计时间：2026-11-12 · HEAD：81659d1 · 版本：2.25.0（最新 release）

## 总评：**8.6 / 10**（v2.24.6 为 8.4）

| 维度 | 评分 | 依据 |
|---|---|---|
| 功能完整度 | **8.7** | 编辑器/终端 P1–P7/LSP/插件市场/主题/宏/会话/对比/沙箱隔离齐备 |
| 架构设计 | **8.5** | 8 批拆分 + 棘轮门禁；10 个历史文件 1.3–1.5k 在允许列表（达标即移除） |
| 代码质量 | **8.4** | ruff/format/version 全绿；200 个测试文件；原生 Qt 崩溃仍 flaky（逐文件回退放行） |
| 性能工程 | **8.8** | 最新 CI 样本：mainwindow **0.405s**、plugin_ready **0.629s**、open_50mb **1.76s**；性能看板+阈值线 |
| 安全性 | **8.7** | **P0 已修复**（PR 不再跑 self-hosted）；密钥轮换；沙箱 A/B0/B1/B1.5；Authenticode 条件签名（待证书） |
| 用户体验 | **8.5** | ja/ko 100%、市场评分邀请/筛选、终端 P7、首帧 QA P95 0.772s、快捷键参考 |
| 生态与扩展 | **8.3** | 插件开发指南+脚手架、评分运营闭环；评分样本仍少（16 条，count=1） |
| 工程与发布 | **8.4** | release 前置门禁 + watchdog + 托管兜底；单 self-hosted runner 队列仍有排队风险 |

## 关键证据

- 代码：449 个 Python 文件（app/core/ui/infrastructure/plugins/tests），127,111 行；200 测试文件；
- 门禁：ruff ✅、format ✅、check_version ✅、ja/ko 覆盖率 100% ✅；
- 测试：**1,254** 个测试节点（pytest collect）；
- 发布：最新 **v2.25.0**，资产 ZIP+SHA256+Ed25519 .sig，SHA256 已验证；
- 性能（2026-11-12 14:45 样本）：mainwindow 0.4048、plugin_ready_after 0.6293、open_50mb 1.7642、theme_reapply 0.0001；
- macOS spike：macos-latest arm64 离屏 **27/27 通过**；
- 崩溃聚合基线：9 dumps / 8 flaky / 3 组；TODO/FIXME **45** 处；
- 签名 Secrets：WINDOWS_SIGN_CERT_* **MISSING**（需证书）。

## 主要风险

1. **CI 单点与排队**：self-hosted 单 runner；Test 偶发排队，本次审计时仍有 queued 运行（watchdog/兜底已就绪）；
2. **原生 Qt 崩溃 flaky**：靠逐文件回退放行，存在掩盖真实回归的风险；
3. **沙箱默认关闭**：B1.5 仅 demo 灰度，ll 未逐插件验证；
4. **Authenticode 未生效**：证书/Secrets 缺失，SmartScreen 信誉未建立；
5. **架构长尾**：10 个 1.3–1.5k 文件仍在允许列表；
6. **macOS 仅离屏验证**：PTY/打包/公证未完成；
7. **TODO 45 处**：需按 docs/todo_cleanup_v2.25.md 清理。

## 结论与建议

软件已从“高质量可发布”（8.4）提升到 **8.6**：安全 P0 修复、CI 可靠性、沙箱隔离、密钥轮换与性能可观测性均落地。

建议优先级：
1. 证书到位 → 配置 Secrets → 验证 Authenticode 发布；
2. 沙箱 ll 模式逐插件灰度（先低风险 3 个）；
3. 架构长尾再拆 3 个（directory_tree/macro/plugin_store）→ 移除白名单；
4. flaky 根因定位（crash_triage 持续跟踪）；
5. 发 **v2.25.1** 固化本轮增量。
