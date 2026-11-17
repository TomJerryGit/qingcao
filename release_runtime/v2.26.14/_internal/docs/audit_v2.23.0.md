# 青草编辑器 v2.23.0 审计与评价报告

> 审计日期：2026-11-09 · 版本：2.23.0（RELEASE_OK）· 审计范围：代码/安全/测试/CI/性能/i18n/发布
> 方法：静态扫描 + 仓库自带审计工具 + CI/Release API 核验 + 测试收集统计

---

## 一、总体结论

**综合评分：8.0 / 10（较 v2.22.0 的 7.6 提升 0.4）**
**风险等级：低-中**（无 P0 缺陷；存在 5 项 P1 需优先处理）

本版本完成了 5 个巨型文件的拆分（最大文件从 3,920 降至 1,818，后又因新代码回潮至 2,028），
新增终端 PTY 交互模式、Linux AppImage 构建、CI flaky 面包屑与频率门禁、插件评分静态聚合闭环、
日韩翻译覆盖率 22.4%。发布流程完整（SHA256 校验通过），CI 三工作流全绿。

主要遗留风险：**性能门禁过宽**、**插件注册表未重发（评分聚合未上线）**、
**插件信任边界依赖来源**、**巨型文件回潮**、**CI 上传网络脆弱**。

---

## 二、关键指标（审计实测）

| 指标 | 数值 |
|---|---|
| Python 文件 / 总行数 | **449 / 154,160 行**（core 25,730 / ui 39,946 / app 11,942 / infra 10,687 / tests 24,268 / tools 19,836 / plugins 7,236） |
| 测试 | **156 个测试文件 / 448 个测试函数**；分片并行全绿 |
| 文档 | 138 个 docs 文件 |
| 版本一致性 | ✅ 2.23.0（`check_version` OK） |
| 编译 | ✅ `compileall` rc=0；核心模块导入 OK |
| 依赖 | ✅ `pip check` 无损坏依赖；`check_deps` 核心依赖就绪 |
| 发布 | ✅ v2.23.0 资产 2 个；SHA256 校验 **PASS** |
| CI（de34be7） | test / lint / linux-build **全部 success** |
| i18n | en 979（语料 100%）、zh_TW 5227（100%）、ja/ko 各 183（**22.4%**，门禁 15%） |
| 插件安全审计 | pass=11 / review=1 / warn=2（基线豁免） |
| 沙箱 RPC 审计 | ✅ 白名单 11 个受限方法，无危险执行方法 |
| 网络超时审计 | ✅ 0 违规 |
| 键盘无障碍 | ✅ 178 菜单项 / 无名称控件 0 |
| flaky 历史 | 3 次/7 天（阈值 3，临界通过） |
| 性能基线 | mainwindow 0.53s、open_50mb **4.35s**（阈值 3.0s）、plugin_ready 1.21s |

---

## 三、发现清单

### P0（阻断级）
无。

### P1（高优先）

| ID | 发现 | 证据 | 影响 | 建议 |
|---|---|---|---|---|
| P1-1 | **注册表未重发，ratings.json 缺失** | `plugin-registry` Release 15 个资产，无 `ratings.json`；最近 publish run 为旧提交 | 评分静态聚合"发布接线+客户端消费"已实现但**未上线** | 触发 `Publish Plugin Registry`（需 PAT）；验证含 ratings.json |
| P1-2 | **性能门禁过宽** | `bench_optimization.py --auto` 最低有效容差 **5×**；open_50mb 实测 4.35s > 3.0s 仍通过 | 无法拦截 2–5 倍性能退化；与 Roadmap KPI（≤3.0s）不一致 | 引入相对基线回归门禁（如较上次 +20% 失败），open_50mb 单独硬阈值 |
| P1-3 | **插件信任边界依赖来源** | python_debugger（process + eval/compile，in-process，`sandbox=None`）；ai_assistant/spell_check 在审计基线豁免 | 安装恶意插件可执行任意代码/命令（权限提示是唯一防线） | 强制高权限插件走沙箱子进程；或在安装界面显式风险分级确认 |
| P1-4 | **巨型文件回潮** | 9 个文件 >2,000 行：ai_assistant 3,258、plugin_api 2,294、editor_view 2,235、tabs 2,219、content_provider 2,190、document 2,072、editor 2,028、outline_panel 2,024、session 2,010 | 拆分收益被新代码抵消；维护成本回升 | 下一批拆分：ai_assistant / plugin_api / tabs / content_provider / document |
| P1-5 | **CI 发布上传网络脆弱** | v2.23.0 `build-release` 上传 ZIP 超时（人工重跑后成功） | 发布可能静默缺资产；需人工发现 | 上传加指数退避重试 + 失败后自动校验资产并告警 |

### P2（中优先）

| ID | 发现 | 证据 | 建议 |
|---|---|---|---|
| P2-1 | 宽泛异常过多 | 非测试代码 `except Exception:` **1,488 处** | 关键路径收窄异常类型，避免掩盖缺陷 |
| P2-2 | 更新包未签名 | 自动更新仅 HTTPS + SHA256（插件包有 Ed25519，安装包无） | 对更新 ZIP 增加签名校验 |
| P2-3 | 本地 Git 仓库曾损坏 | `.git/packed-refs` 损坏（已隔离修复，43 tags 恢复） | 定期 `git fsck` + 备份；CI 增加仓库健康检查 |
| P2-4 | Linux AppImage 验证有限 | 仅 x86_64；冒烟为"启动/超时"判定，未做真实桌面交互 | 增加 AppImage 内 Qt 平台插件加载验证 + 中文输入法冒烟 |
| P2-5 | 日韩仍为试点 | 覆盖率 22.4%，未达"正式语言"标准 | 按 key 驱动补到 ≥50% 再宣布正式 |
| P2-6 | 真实反馈样本少 | 本地反馈记录 6 条，功能使用数据缺失 | 发布说明内置反馈引导；每版收集 ≥3 条 |

### 安全专项结论

| 项 | 结论 |
|---|---|
| 插件签名/哈希 | ✅ Ed25519 + SHA256，fail-closed |
| 沙箱 RPC 白名单 | ✅ 11 个受限方法，无 `run_python/run_command/shell` 暴露 |
| 命令执行/动态执行 | ⚠️ `PluginAPI.run_command`（shell=True）与 `run_python`（exec）均需 `PERMISSION_PROCESS`；但高权限插件仍为 in-process |
| 数学表达式 eval | ✅ 严格字符白名单（数字/运算符/括号） |
| Python 控制台 eval/exec | 用户显式操作，属预期功能 |
| 网络安全 | ✅ 所有 requests/urlopen 显式 timeout（AST 审计 0 违规）；更新检查已迁移 QNetworkAccessManager |
| 遥测隐私 | ✅ telemetry 无网络代码（仅本地） |
| 仓库密钥 | ✅ 未发现 `verify=False`/pickle.load/yaml.load/硬编码 token |

### 测试与 CI 健康度

- 156 测试文件 / 448 测试函数；分片 2 片本地、CI 3 片；
- CI 门禁：i18n 覆盖率+QA、版本、ruff、插件安全（基线）、沙箱 RPC、性能、崩溃分析、a11y、主题基线、全量测试、flaky 频率；
- 原生 Qt 崩溃 fallback 仍偶发（本地 7 天 3 次，阈值 3 临界）；门禁可放行但需持续观察；
- Linux 构建工作流新引入（ubuntu-22.04），当前冒烟策略为"源码导入 + 启动/超时"。

### 性能评估

| 指标 | 实测 | 阈值 | 结论 |
|---|---|---|---|
| mainwindow | 0.53s | 2.5s | ✅ |
| open_50mb | 4.35s | 3.0s | ❌ 超阈值（门禁因 5× 容差放行） |
| plugin_ready | 1.21s | 2.0s | ✅ |
| 主题重应用 | 0.08s | 0.05s×容差 | ✅（容差内） |

---

## 四、评价与评分

| 维度 | v2.22 | v2.23 | 评价 |
|---|---|---|---|
| 功能完整度 | 8.0 | **8.3** | 终端 PTY、Linux AppImage、评分聚合（待上线） |
| 架构设计 | 7.5 | **8.0** | 5 个巨石拆分完成；但新文件回潮 |
| 代码质量 | 7.0 | **7.5** | ruff 0 违规；1,488 宽泛异常、9 个 >2,000 行文件 |
| 测试质量 | 8.5 | **8.7** | 156 文件/448 测试 + 多门禁；flaky 临界 |
| 性能工程 | 7.5 | **7.5** | 启动/主题良好；50MB 4.35s 未达 3.0 目标，门禁过宽 |
| 安全性 | 7.5 | **7.8** | 签名/沙箱/超时审计扎实；高权限插件 in-process 风险 |
| 用户体验 | 7.0 | **7.5** | PTY/多语言/Linux；真实反馈少 |
| 生态与扩展 | 6.5 | **7.2** | 13 插件、静态评分（未上线）；无服务端 |
| 发布工程 | 9.0 | **8.9** | RELEASE_OK、Linux 构建；上传超时需重试机制 |
| 文档 | 8.0 | **8.2** | 138 份；部分陈旧 |
| **综合** | **7.6** | **8.0** | 工程化成熟，产品化仍待生态与真实反馈 |

---

## 五、优先行动建议

### 立即（本周）
1. **重发插件注册表**（含 ratings.json），验证资产与客户端展示；
2. **性能门禁收紧**：open_50mb 硬阈值 + 相对基线回归（+20%）；
3. **发布上传重试**：`release_local/ci_publish` 增加 3 次退避重试与资产校验。

### 下一步（v2.23.x）
4. 拆分第二批巨石：`ai_assistant`、`plugin_api`、`tabs`、`content_provider`、`document`；
5. 高权限插件强制沙箱或安装风险分级提示；
6. 更新包签名（Ed25519）与自动校验；
7. 真实反馈收集（发布说明引导 + 每版 ≥3 条）。

### 中期（v2.24）
8. ja/ko 覆盖率 50%（key 驱动）；
9. Linux AppImage 正式发布（tag 自动上传）与 x86_64 冒烟增强；
10. 评分服务端阶段 2（只写服务）与反滥用。

---

## 六、审计方法附录

| 工具 | 结果 |
|---|---|
| `tools/audit_plugins.py --strict` | pass=11/review=1/warn=2（基线豁免） |
| `tools/audit_sandbox_rpc.py --strict` | ✅ 白名单 11 方法 |
| `tools/audit_network_threads.py --check` | ✅ 0 违规 |
| `tools/audit_keyboard_a11y.py --strict` | ✅ 通过（178 菜单/0 缺失名称） |
| `python -m tools.check_version` | ✅ 2.23.0 一致 |
| `tools/health_check.py` | 5 空包文件（正常）、9 超大文件、48 待处理项 |
| `tools/analyze_crash_dumps.py` | jobs=389 failed=57 crash=0 dumps=5 |
| `tools/ci_flaky_report.py` | 3 次/7 天（阈值临界） |
| API 核验 | v2.23.0 资产 SHA256 PASS；registry 缺 ratings.json；CI 三工作流绿 |
