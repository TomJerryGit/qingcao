# QingCao Editor v2.25.2 发布说明

> 2026-11-13 · 上一版本：v2.25.1

## 安全（沙箱 B2.1 系列）
- 远程面板协议：wordcount 子进程运行、宿主 QDockWidget 渲染刷新；
- 设置 schema：隔离插件动态配置对话框 + 工具菜单入口 + 按插件持久化；
- 网络 broker：manifest 域名白名单、60/min 限流、拒绝审计、1MB 上限；
- provider 接线：hover / code-action / 右键菜单跨进程代理；json_formatter 灰度；
- demo 灰度：demo、wordcount、json_formatter。

## 架构（R2）
- directory_tree → 1,072、macro → 610、plugin_store → 1,081；
- 架构白名单 10 → 7。

## 工程/稳定性（R3）
- 崩溃聚合支持空 dump / WER minidump / 无异常行；
- 每日技巧改非原生 QMessageBox（缓解 0x8001010d）；
- CI job 队列统计（Test 队列 P95 ≈23min）；本地全量测试 3.9 分钟。

## 验证
- 沙箱/网络/provider/schema/架构/崩溃/队列测试通过；
- 资产 ZIP + SHA256 + Ed25519 `.sig`。
