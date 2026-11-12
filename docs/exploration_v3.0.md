# v3.0 探索与建设提案

> 基线：v2.24.6 之后的主线（阶段 1–3 已完成）· 制定：2026-11-11

## 结论先行

| 方向 | 建议优先级 | 预估 | 风险 | 决策 |
|---|---|---|---|---|
| 密钥轮换 | **P0（已完成实现）** | 5–6d | 低（可向后兼容） | ✅ 已实现（`docs/key_rotation.md`） |
| 性能看板 | **P0（先做）** | 2–3d | 低 | 进入 v2.25.x |
| Authenticode 签名 | P1（依赖证书） | 1–2d 接入 + 采购 | 中（成本/流程） | 先做资格评估/申请 |
| 插件沙箱 | P1（研究 + 分阶段） | 设计 3d，实装 8–12d | 高（兼容性/性能） | 先做威胁模型与阶段 A |
| macOS 支持 | P2（评估后） | 构建/测试 5–8d + CI 成本 | 中高 | 先做 1–2d 可行性 spike |

## 1. Authenticode 签名（Windows 安装包/可执行文件）

现状：安装包 ZIP + **Ed25519 分离签名**（`.sig`）；未做 Authenticode → SmartScreen 可能拦截。

| 方案 | 成本 | 适用 |
|---|---|---|
| OV/EV 代码签名证书（硬件令牌/HSM） | $200–500/年 + 令牌 | 长期、需线下流程 |
| Azure Trusted Signing | 低价订阅 | 需组织/历史条件 |
| SignPath（开源项目计划） | 免费（需审核） | 开源首选 |

接入设计：
1. CI 构建后调用 `signtool sign /fd sha256 /tr <rfc3161> /td sha256` 对 `.exe`/安装器签名；
2. `signtool verify /pa` 作为发布门禁（失败不出包）；
3. 保留现有 Ed25519 `.sig`（更新链路继续使用），两者互补。

验收：`Get-AuthenticodeSignature` = Valid；发布资产含已签名安装器；SmartScreen 信誉逐步建立。

下一步 spike（2d）：评估 SignPath/Azure 资格并申请；无证书前不写签名流水线。

## 2. 插件沙箱（权限模型 → 隔离执行）

现状：`permissions` 声明 + `PluginAPI` 运行时权限门控 + 高风险安装确认（plugin_risk）。插件仍**同进程**执行，理论上可用 `ctypes`/`subprocess` 绕过。

分阶段：
- **阶段 A（低风险，3–4d）**：强化进程内门控（import 审计钩子、危险 API 警告、可信插件允许列表、`ctypes` 告警）；
- **阶段 B（隔离，8–10d）**：插件宿主子进程 + JSON-RPC 能力代理（崩溃隔离、权限集中校验；文件系统仍同用户，需配合权限白名单）；
- **阶段 C（OS 级，长期）**：Windows AppContainer/低完整性令牌 或 WASM（wasmtime）用于纯逻辑插件。

验收（阶段 A）：高风险 API 使用可审计；阶段 B：插件崩溃不带走主进程；能力调用全部过代理。

风险：兼容性（现有 13 插件需回归）、性能（跨进程调用延迟）。

## 3. 签名密钥轮换（P0）

现状：单 Ed25519 密钥；公钥通过 `QINGCAO_PLUGIN_PUBKEYS` 列表配置；无 key id、无轮换/吊销流程。

设计：
1. **key_id**：公钥 hex 前 8 位，签名 payload 增加 `key_id` 字段（旧客户端忽略，新客户端校验）；
2. **信任清单**：`trusted_keys.json`（key_id、公钥、生效/过期时间、吊销状态），用离线 **root key** 签名；客户端只信 root 签名的清单；
3. **双签过渡**：轮换期 90 天内新旧 key 同时签（`signatures: [{key_id, sig}, ...]`）；
4. **流程**：`tools/rotate_sign_keys.py` 生成新 key + 清单 + 双签资产；发布说明记录。

工作项：schema（2d）、签名工具 key_id（1d）、客户端校验（2d）、流程文档（1d）。
验收：旧客户端仍可验旧签；新客户端识别 key_id 与吊销；双签资产可发布。

## 4. 性能看板（P0）

现状：CI 写入 `perf_history.jsonl`；`tools/perf_trend_report.py` 生成 Markdown；无可视化看板。

设计：
1. CI 性能 job 上传 `perf_latest.json` artifact（已有 gate）；
2. `tools/perf_dashboard.py`：从历史 JSONL 生成**单文件 HTML**（内联 SVG 折线图 + 阈值线），零服务端；
3. 发布到 GitHub Pages（或 Release 资产），README 链接；
4. 回归告警：超过阈值时在 CI summary 标红，可选自动开 Issue。

工作项 2–3d；验收：看板 URL + 最近 30 天趋势 + 阈值线。

## 5. macOS 评估（P2）

现状：`build_macos.py` 存在；PyQt5/QScintilla 有 macOS wheel；**终端依赖 `pywinpty`（Windows）**，需 POSIX `pty` 适配；无 macOS CI。

差距清单：
- PTY：`ui/pty_session.py` 增加 POSIX `pty.fork` 实现（或 `ptyprocess`）；
- 打包：PyInstaller `.app` + `codesign` + `notarization`（需 Apple Developer 账号 $99/年）；
- CI：GitHub 托管 macOS runner 跑 offscreen 测试子集（不含全局快捷键/托盘等平台相关）。

Spike（1–2d）：在 macOS runner 安装依赖 → 跑 `pytest tests/test_v224_architecture_split.py` 等离屏子集 → 记录失败面。
决策门：spike 通过且有人力维护 → 立 v3.x 里程碑；否则保持 Windows/Linux。

## 建议的两周执行顺序

1. **密钥轮换**：key_id + 信任清单 + 双签（P0）；
2. **性能看板**：单文件 HTML + Pages（P0）；
3. **Authenticode**：申请 SignPath/Azure（并行，采购周期）；
4. **插件沙箱**：威胁模型 + 阶段 A 门控（研究）；
5. **macOS**：1 天 spike 评估。

## 风险与依赖

| 风险 | 缓解 |
|---|---|
| 轮换破坏旧客户端 | 双签 + 90 天过渡 + 版本兼容矩阵测试 |
| 沙箱拖慢插件/破坏兼容 | 分阶段 + 13 插件回归套件 |
| Authenticode 证书周期长 | 提前申请；无证书前继续 Ed25519 链路 |
| macOS 维护成本 | 先 spike，按采用率决策 |
| 单 runner CI | 已落地超时/watchdog/托管兜底（阶段 1） |
