# QingCao Editor v2.25.0 发布说明

> 2026-11-12 · 上一版本：v2.24.6 · 主题：CI 可靠性、架构长尾、生态与体验

## 阶段 1：CI 可靠性 + 安全门禁
- 全部 workflow 增加 `timeout-minutes`；
- `ci_watchdog.py` + 定时工作流：自动取消 >120 分钟卡死运行；
- **release 前置门禁**：Test/Security/Lint 全部成功才构建发布；
- Test 长队列自动派发 GitHub 托管 Windows 兜底（>90 分钟，按 SHA 去重）；
- security.yml 每日 03:00 UTC + 报告归档（30 天），watchdog 维持扫描新鲜度。

## 阶段 2：架构长尾 + flaky 治理
- icon_manager 1,568→609、welcome_widget 1,537→504、capability_wiring 1,537→75；
- global_search 1,514→986、keymap_editor 1,503→676、lsp_client 1,501→1,217；
- 崩溃聚合 `tools/crash_triage.py`（faulthandler + flaky 历史归组）；
- 架构门禁：业务 ≤1,300（10 个长尾白名单，达标即移除）、全局 ≤1,800。

## 阶段 3：生态与体验
- 评分运营闭环：邀请 → Issue → 每日自动收集（幂等加权）→ 触发签名发布；
- 插件开发指南 + `tools/new_plugin.py` 模板生成器；
- 市场：评分筛选、更新公告横幅、详情版本对比；
- 终端 P7：滚动缓冲可视 + vim 验证脚本；
- 真机首帧 QA：中位 0.489s、P95 0.772s（PASS）。

## 其他
- ja/ko 语料 100%、真实评分聚合（16 插件）、v3.0 探索提案（`docs/exploration_v3.0.md`）。

## 验证
- 定向测试 + CI 门禁（Test/Security/Lint）通过；
- 发布资产 ZIP + SHA256 + Ed25519 `.sig`。
