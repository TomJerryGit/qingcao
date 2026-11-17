# QingCao Editor v2.25.1 发布说明

> 2026-11-12 · 上一版本：v2.25.0

## 安全
- 插件沙箱 B0/B1/B1.5：JSON-RPC 子进程宿主、能力 broker、路径白名单、菜单回调 id、真实 QMainWindow 菜单/状态栏接线；`QINGCAO_PLUGIN_ISOLATION=demo` 灰度 demo 插件；
- 签名密钥轮换：key_id + 信任清单 + 双签信封（兼容旧裸签名）；
- 插件沙箱阶段 A：静态审计 + 运行时告警 + 可信允许列表。

## 工程
- 性能看板：`perf_dashboard.html` + Pages 工作流；
- macOS spike：arm64 离屏 27/27 通过（决策 PASS）；
- Authenticode 流水线保留为 no-op（决策不申请证书）；
- TODO 指标复核：真实注释 0 处；
- CI：超时/watchdog/托管兜底/发布前置门禁继续生效。

## 验证
- 沙箱 B0/B1/B1.5、隔离 UI、密钥轮换、看板、架构门禁测试通过；
- 发布资产 ZIP + SHA256 + Ed25519 `.sig`。
