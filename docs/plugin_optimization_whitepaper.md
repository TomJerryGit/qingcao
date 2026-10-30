# 青草编辑器 插件优化白皮书

> 版本：v1.0（整理于 2026-10-30，覆盖 v2.13.0 → v2.17.0 进行中）
> 范围：14 个内置插件、插件运行时（加载/沙箱/市场）、配套工具链与 CI 门禁
> 适用读者：插件作者、维护者、发布/CI 维护人员

---

## 1. 摘要

v2.13 起，插件体系从"能加载能运行"升级为**可分析、可度量、可防护、可回归**的工程化体系：

- 14 个插件完成 AST 级全景分析，建立性能/安全/主题/沙箱四类基线；
- 5 批次专项优化：主题统一、启动性能、安全收敛、沙箱试点、市场元数据；
- 新增 2 个沙箱插件（wordcount_sandbox / whitespace_sandbox），沙箱插件达 4 个；
- 插件导入性能从"误报 713ms"校正为真实 **ai_assistant ≈5ms、
  python_debugger ≈27ms（负载相关）**，并设 CI 预算防回退；
- 插件市场从只读列表升级为**带签名校验、安全筛选、来源徽章、依赖预检、
  失败回滚**的可信安装体验；
- CI 增加 5 道插件专项门禁（一致性/审计/RPC 白名单/市场元数据/性能预算）。

---

## 2. 背景与目标

### 问题

1. 插件面板硬编码深色 QSS，浅色/护眼主题下显示不一致；
2. ai_assistant 顶层 `import requests`，拖慢插件激活；
3. 部分插件权限声明与实际行为不匹配（python_debugger）；
4. 无统一性能/安全基线，回归只能靠人眼；
5. 插件市场只有列表，缺少来源/签名/安装安全提示。

### 目标

- **一致性**：插件 UI 跟随宿主主题（深/浅/护眼/高对比）；
- **性能**：插件加载与激活可度量、有预算、CI 防回退；
- **安全**：权限声明收敛、调试器求值受限、市场安装验签；
- **可维护**：分析/基准/审计工具化，文档与基线入库。

---

## 3. 方法论

```
全景分析（AST/依赖/样式/线程/IO）
   ↓
建立基线（导入耗时、审计结论、主题表现）
   ↓
分批优化（Batch 1~5 + 后续版本迭代）
   ↓
工具化（analyze/bench/audit/sign/market-check）
   ↓
CI 门禁 + 文档/基线入库
```

关键原则：

1. **先测量再优化**：所有"优化"必须有前后数据；
2. **宿主统一治理优先**：能在宿主层统一解决的（主题递归适配）不逐个改插件；
3. **失败关闭（fail closed）**：验签/依赖/白名单不满足即拒绝；
4. **防御性修复**：消息循环/读取上限等防御逻辑同时入库。

---

## 4. 插件全景（14 个）

| 插件 | 版本 | 沙箱 | 分类 | 主要优化 |
|---|---|---|---|---|
| ai_assistant | 1.0.0 | – | editor | requests 惰性化、自递归修复、主题适配、市场元数据 |
| python_debugger | 2.0.0 | – | integration | process 权限、受限求值、求值模式可配置、RPC 层校验 |
| spell_check | 1.0.0 | ✅ | tool | 沙箱诊断/忽略词 RPC、主题适配 |
| wordcount | 1.0.0 | – | tool | 精准 refresh_theme |
| todo_panel | 1.0.0 | – | tool | 精准 refresh_theme |
| logtail | 1.0.0 | – | tool | 精准 refresh_theme |
| markdown_preview | 1.0.0 | – | editor | 精准 refresh_theme |
| wordcount_sandbox | 1.0.0 | ✅ | tools | 沙箱试点：状态栏字数/字符/行 |
| whitespace_sandbox | 1.0.0 | ✅ | tools | 只读沙箱 linter（行尾空白/Tab/超长行） |
| sandbox_demo | 1.0.0 | ✅（禁用） | tool | 沙箱协议示例 |
| git_deep / json_formatter / demo / my_plugin | 1.0.0 | – | 各自 | 市场元数据、审计基线 |

> 沙箱插件 4 个（3 个启用 + 1 个示例禁用）；全部插件具备
> category/license/homepage/keywords 市场元数据。

---

## 5. 六大优化维度

### 5.1 性能

| 项 | 优化前 | 优化后 |
|---|---|---|
| ai_assistant 导入 | 顶层 `import requests`（~0.9s 潜在开销） | 函数级惰性导入 |
| 基准方法 | 宿主预热失败 → 数字虚高（713ms） | 修 sys.path + 2 轮取最小 + 冷启动预算 |
| 真实增量导入 | 不可信 | ai_assistant ≈5ms、python_debugger ≈27ms、其余 ≤2ms |
| CI 防回退 | 无 | `bench_plugins.py --check --factor 2.0`（ai 200ms / debugger 120ms / 默认 60ms） |

### 5.2 UI / 主题

- 宿主启动主题路径统一调用 `adapt_widget_styles` → 插件面板**启动即适配**；
- wordcount/todo_panel/logtail/markdown_preview/ai_assistant 实现 `refresh_theme`；
- 修复主题应用顺序：先 `adapt_widget_styles`，后 `notify_widgets`；
- 插件面板按主题类型/真实配色生成 QSS（含护眼绿 eye_protect）；
- 关键子控件（工具栏/表头/搜索框/下拉/列表）直接设样式，避免被全局 QSS 覆盖；
- 多主题 E2E 截图基线（dark/light/eye/high_contrast × 窗口+面板）。

### 5.3 安全

- **python_debugger**：
  - manifest 补 `process` 权限；
  - eval 表达式长度限制 4000；
  - `_safe_eval`：仅表达式、拒绝 dunder/危险内建；
  - `QINGCAO_DEBUGGER_EVAL_MODE=restricted|developer`；
  - 宿主 RPC 层 `validate_eval_expression` 二次校验；
  - 复核文档 `docs/security_review_python_debugger_v2.15.md`。
- **沙箱 RPC**：`tools/audit_sandbox_rpc.py` 审计白名单/worker/manager 一致性，
  基线 `tools/baselines/sandbox_rpc.json` 入库，CI 比对变更。

### 5.4 沙箱

- 协议扩展 `status_text(text)`：宿主传入当前文本，插件只回状态串；
- spell_check（忽略词 RPC/菜单代理）→ wordcount_sandbox 试点 → whitespace_sandbox；
- 沙箱诊断**按文件聚合**：多标签页分别诊断，问题面板按文件分组；
- 问题面板支持来源列 + 按 `sandbox:<插件>` 动态过滤 + 一键清除。

### 5.5 市场

- 元数据：14 插件补齐 category/license/homepage/keywords，CI `--strict` 校验；
- 离线目录 MVP：远程不可用时从本地 manifest 构建市场目录；
- **签名校验**：SHA256 + HMAC（fail closed）→ Ed25519 非对称（公钥轮换/吊销）；
- 签名工具 `tools/sign_plugin.py` + 密钥轮换手册；
- UI：安全状态筛选、来源徽章（官方/本地/第三方）、依赖状态、失败回滚、重载提示。

### 5.6 工程能力

| 工具 | 用途 | CI |
|---|---|---|
| analyze_plugins.py | AST 全景分析（结构/依赖/QSS/线程/IO/网络） | – |
| bench_plugins.py | 导入基准 + 预算检查 | ✅ |
| audit_plugins.py | 安全审计（权限/危险调用） | ✅ |
| audit_sandbox_rpc.py | 沙箱 RPC 白名单审计 + 基线 | ✅ |
| check_plugin_market.py | 市场元数据完整性 | ✅ |
| sign_plugin.py | Ed25519 签名/验签 | – |
| smoke_plugin_theme.py / theme_e2e_screenshots.py | 主题 GUI 冒烟/基线对比 | ✅（基线检查） |

---

## 6. 回归防线

- **测试**：121 个测试文件（分片并行 + 重试），插件相关覆盖：
  主题自适应、性能基准、沙箱协议/菜单/配置/诊断、市场安全/UI、
  多实例广播、调试器求值安全；
- **CI 门禁**（12 步）：
  Version check → Ruff → Plugin conformance → Plugin security audit →
  Sandbox RPC allowlist audit → Plugin market metadata →
  Plugin performance budget → Performance gate → Theme baseline check →
  Full test suite；
- 本地基线：`docs/theme_baseline/`（8 张）、`data/plugin_bench.json`、
  `tools/baselines/sandbox_rpc.json`。

---

## 7. 插件开发规范（提炼）

### manifest 必填/推荐字段

```json
{
  "name": "example",
  "display_name": "示例",
  "version": "1.0.0",
  "api_version": "2.0.0",
  "enabled": true,
  "sandbox": false,
  "category": "tool",
  "license": "MIT",
  "homepage": "https://...",
  "keywords": ["..."],
  "permissions": ["editor_read"]
}
```

### 主题规范

- 需要自定义样式的面板实现 `refresh_theme(theme)`，使用
  `adapt_qss_colors` 或按主题真实色板生成 QSS；
- 不要硬编码依赖深色；启动/切换主题均会调用 `notify_widgets`。

### 性能规范

- 禁止模块顶层导入重依赖（requests/openai/cryptography 等）；
- 大对象/网络/文件扫描延迟到实际调用；
- 新增插件导入预算：默认 ≤60ms（×2 容差）。

### 安全规范

- 权限声明必须与实际行为匹配；
- 禁止无限制 eval/exec；需要时使用 `_safe_eval` 模式并记录加固说明；
- 沙箱插件仅通过白名单 RPC 方法交互。

### 沙箱规范

- manifest `"sandbox": true` + `permissions` 最小化；
- 只返回数据（`diagnostics`/`symbols`/`status_text`），UI 由宿主创建；
- 新 RPC 方法必须同步更新 `ALLOWED_METHODS`、worker、manager 与审计基线。

---

## 8. 经验与教训（踩坑记录）

| 问题 | 教训 |
|---|---|
| 基准工具 sys.path 缺失导致预热失效 | 工具脚本必须显式加入仓库根路径 |
| 把宿主模块首启算进插件耗时 | 先预热宿主，再测增量 |
| `_requests_ok()` 自递归 | 惰性改造后必须单测激活路径 |
| ACK 中继造成读取回环 | 消息路由避免广播回环，加处理上限 |
| 主题适配顺序反了（刷新被覆盖） | adapt 在前、notify 在后 |
| 新沙箱插件破坏既有测试假设 | 发现逻辑需可环境变量隔离 |
| CI Qt 偶发原生崩溃 | 失败重试 + 后续 crash dump 治理 |

---

## 9. 后续路线（v2.17+）

- 大文件性能（>10MB 模式、50MB 打开预算）；
- 无障碍深化（键盘导航/焦点/字体缩放/Accessibility）；
- 市场在线安装 UI 继续完善（批量更新/更新日志）；
- CI Qt 原生崩溃根因治理（crash dump 采集）。

---

## 10. 附录

### 命令索引

```powershell
python tools/analyze_plugins.py
python tools/bench_plugins.py --check --factor 2.0
python -m tools.audit_plugins
python tools/audit_sandbox_rpc.py --strict --baseline tools/baselines/sandbox_rpc.json
python tools/check_plugin_market.py --strict
python tools/sign_plugin.py --keygen
python tools/smoke_plugin_theme.py
python tools/theme_e2e_screenshots.py --check
```

### 文档索引

- `docs/plugin_analysis_v2.13.md`（全景分析）
- `docs/plugin_market_security.md`（市场安全）
- `docs/plugin_market_key_rotation_playbook.md`（密钥轮换/吊销）
- `docs/security_review_python_debugger_v2.15.md`（调试器安全）
- `docs/roadmap_v2.17.0.md`（后续规划）

### 关键提交

- `f96ec4e` / `9eb21cc` / `4eb29f0` / `ce156ac` / `a3bc7c3`（Batch 1-5）
- `dc8f96a`（P3 RPC 审计/签名/求值校验）
- `d567004`（市场 UI 完善）
