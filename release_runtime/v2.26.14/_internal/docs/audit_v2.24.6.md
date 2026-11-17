# 青草编辑器 v2.24.6 审计与评价

> 审计时间：2026-11-11 · 版本：2.24.6 · HEAD：65fafb1

## 总评：**8.4 / 10**（较 v2.23.0 的 8.0 提升）

| 维度 | 评分 | 依据 |
|---|---|---|
| 功能完整度 | **8.6** | 编辑器/终端(P1–P6)/LSP/插件市场/主题/宏/会话/对比/代码操作齐备；终端 alt-screen/鼠标/真彩完整 |
| 架构设计 | **8.4** | 5 批巨石拆分完成，main 115 行薄入口；插件 API 分模块；6 个业务文件 1,500–1,568 行（无 >2,000） |
| 代码质量 | **8.3** | ruff + ruff format 全绿；188 个测试文件；版本 SSOT 一致；仍有原生 Qt 崩溃需 flaky 回退 |
| 性能工程 | **8.6** | CI 实测 mainwindow **0.298s**、plugin_ready **0.490s**；50MB 视口默认开启（首屏 16×）；门禁收紧 |
| 安全性 | **8.2** | 插件风险分级确认、ratings/安装包 Ed25519 签名、pip-audit；插件权限门控；但安全扫描最近一次为 11-09（偏旧） |
| 用户体验 | **8.4** | ja/ko 语料 **100%**、首启向导、快捷键参考(F1)/覆盖 54.5%、设置分层、命令面板最近使用/分类、市场评分邀请 |
| 生态与扩展 | **8.2** | 插件市场/注册表/真实评分聚合管线；社区评分仅 16 条（count=1），生态规模仍小 |
| 工程与发布 | **8.0** | 发布流程可复现、资产含签名/SHA256；**单台 self-hosted runner 是瓶颈**，本次曾因卡死任务阻塞 Test 队列约 5h |

## 关键证据

- 代码：553 个 Python 文件、158,233 行（不含 tools/_archive）；188 测试文件；docs 146 份；
- 质量门禁：ruff ✅、format ✅、check_version ✅、ja/ko 覆盖率 100% ✅；
- 发布：v2.24.6 资产 ZIP(61.65MB)+SHA256+`.sig`，SHA256 PASS；注册表 17 资产含签名 ratings.json；
- 性能历史：`plugin_ready_after` 1.21s（11-02）→ **0.49s**（11-11）；
- 安全：security workflow 最近成功 2026-11-09（需重跑）。

## 主要风险

1. **CI 单点**：self-hosted 单 runner；一次卡死 Test job（42952449800）阻塞约 5 小时，v2.24.6 发布排队 1.5h；已通过重启 runner 缓解，仍需超时/取消策略或第二 runner。
2. **原生 Qt 崩溃 flaky**：依赖逐文件回退放行，长期应定位崩溃根因。
3. **架构长尾**：6 个业务文件 1.5–1.57k（icon_manager/welcome/capability_wiring/global_search/keymap/lsp_client）。
4. **生态薄弱**：社区评分样本少（16 条、count=1），插件数量有限。
5. **安全扫描陈旧**：security.yml 需定期运行并纳入发布门禁。

## 建议优先级

1. CI 可靠性：job `timeout-minutes`、卡死自动取消、第二 runner 或托管 runner；
2. 安全：发布前强制 security workflow（pip-audit + 权限矩阵）；
3. 架构：icon_manager/welcome_widget/capability_wiring 三文件拆到 <1,300；
4. 生态：邀请评分（count≥3）、插件征集；
5. 体验：真机首帧人工目测（工具已备）+ 终端 vim 真机验证。
