## [Unreleased]

（下一版本开发中）

### 规划

- v2.17.0 roadmap：插件市场在线安装 UI 完善 / 大文件性能 / 无障碍深化（`docs/roadmap_v2.17.0.md`）。

### 修复

- CI 全量测试重试次数 1→2，缓解 Runner 偶发 Qt 原生崩溃（rc=0xC0000005）导致的假失败。

## [2.16.1] - 2026-10-30

### 修复

- 性能门禁 `--auto` 最低有效容差提升到 5×，避免空闲 Runner 误报；
- 沙箱插件目录支持 `QINGCAO_SANDBOX_PLUGIN_DIR` 覆盖（测试隔离）。

## [2.16.0] - 2026-10-30

### 新增

- 插件签名工具 `tools/sign_plugin.py`（keygen/sign/verify）与密钥轮换/吊销手册 `docs/plugin_market_key_rotation_playbook.md`；
- 新增只读沙箱插件 `whitespace_sandbox`（行尾空白/Tab/超长行诊断）；
- 主题 E2E 基线对比 `--check` 纳入 CI（像素差异阈值 24）；
- 多主题 E2E 截图基线：`tools/theme_e2e_screenshots.py`（dark/light/eye/high_contrast 主窗口+插件面板，产物 docs/theme_baseline/）；
- 问题面板支持按沙箱插件来源动态过滤（插件: sandbox:<name>）；
- 测试分片数自适应（按 CPU 数 2~4 片），CI 使用 `--auto-shards`；
- 问题面板新增「来源」列（sandbox:<插件> / LSP 等）；
- 广播 ACK 重试：file_saved 带 msg_id，500ms 未确认自动重发一次；
- 多屏高 DPI 手动验证清单 `docs/manual_validation_v2.16_multimonitor.md`；
- Ed25519 非对称签名：公钥可配置（QINGCAO_PLUGIN_PUBKEYS，支持轮换）+ 吊销名单（QINGCAO_PLUGIN_REVOKED），HMAC 回退；
- 插件市场详情展示签名安全状态（未签名/SHA256/HMAC/Ed25519/已吊销）；
- 沙箱 RPC 审计基线版本化（tools/baselines/sandbox_rpc.json），CI 比对白名单变更；
- 调试器求值模式可配置（QINGCAO_DEBUGGER_EVAL_MODE=restricted/developer）。

## [2.15.1] - 2026-10-30

### 新增

- 沙箱 RPC 白名单自动化审计：`tools/audit_sandbox_rpc.py`（校验白名单/worker/manager 一致性），纳入 CI；
- 插件市场签名校验：SHA256 + HMAC-SHA256（fail closed），文档 `docs/plugin_market_security.md`；
- 调试器求值 RPC 层校验：空/超长表达式宿主侧直接拒绝；
- 多实例广播协议版本协商：hello/hello_ack 交换协议版本，不同版本按兼容模式处理并在状态栏提示；
- 性能门禁智能降级：`bench_optimization.py --auto` 按 CPU/内存负载自动放大容差（1.0~4.0），CI 使用 `--auto --factor 3.0`。

## [2.15.0] - 2026-10-29

### 新增

- 问题面板支持来源过滤（全部/仅沙箱/仅非沙箱）与「清除沙箱诊断」；
- 设置 → 常规新增「多实例」：新窗口实例上限 1~10 可视化设置；
- 插件市场离线 MVP：`build_market_catalog` 从本地 manifest 构建目录，远程不可用时兜底展示；
- python_debugger 安全复核：新增受限表达式求值 `_safe_eval`（拒绝 dunder/危险内建、表达式模式、长度限制）；
- 沙箱诊断按文件聚合：对所有已打开文件分别运行沙箱子进程诊断，问题面板按文件分组展示；实时诊断仅计算当前文件。

## [2.14.2] - 2026-10-29

### 修复

- 插件面板支持**护眼绿（eye_protect）等变体主题真实配色**：
  `_theme_colors()` 改为优先读取主题 `background/panel_bg/foreground/
  border/selection`，缺失时按类型回退；浅色系前景过浅时自动回退深色。
- 主题冒烟工具扩展覆盖 eye 主题（三主题截图回归）。



（下一版本开发中）

## [2.14.1] - 2026-10-29

### 修复

- **AI 助手插件激活错误**：惰性依赖检查 `_requests_ok()` 自递归导致
  RecursionError（插件面板显示"错误"）；修复为返回 `_REQUESTS_OK`；
  并将 `refresh_theme` 移入 `Plugin` 类体内。
- **插件面板主题适配**：
  - 修复主题应用顺序：`adapt_widget_styles` 先于 `notify_widgets`，
    避免面板刷新后的样式被覆盖；
  - 面板改为按主题类型（light/dark/high_contrast）直接生成确定调色板 QSS，
    工具栏、表头、搜索框、下拉框、列表全部同步；
  - 修复浅色主题下文字被映射成近白（对比度差）的问题。
- 欢迎页与窗口调色板随主题同步（修复深色主题下欢迎页仍为浅色）。

### 测试与工具

- 新增 GUI 主题冒烟工具 `tools/smoke_plugin_theme.py`：
  真实窗口切换主题并截图对比（含插件面板独立截图）。
- 新增/更新相关断言；分片并行全量通过。



（下一版本开发中）

## [2.14.0] - 2026-10-29

### 插件全面提振（Batch 1-5）

- 全面分析 13 个插件（AST 扫描/导入基准/安全审计），报告
  `docs/plugin_analysis_v2.13.md`；
- 主题：宿主启动主题统一递归适配插件面板；wordcount/todo_panel/
  logtail/markdown_preview/ai_assistant 实现 `refresh_theme(theme)`；
- 性能：ai_assistant 可选依赖 requests 惰性化；真实增量导入
  ai_assistant 1.8ms / python_debugger 8.9ms；CI 性能预算门禁
  （150/60/30ms，×2 容差）；
- 安全：python_debugger 补 `process` 权限，eval 表达式限长；
- 沙箱：`status_text(text)` 支持文本；新增 wordcount_sandbox 试点；
- 市场：13 个插件补齐 homepage/keywords；`check_plugin_market.py --strict`
  纳入 CI。



（下一版本开发中）

## [2.13.0] - 2026-10-28

### 无障碍：高对比度自动适配

- 检测 Windows 高对比度（`system_high_contrast()`）；
- 开启时自动应用系统调色板 QSS（`build_high_contrast_qss()`）；
- 面板/控件自定义 QSS 在 HC 模式下让位系统调色板，关闭后完整恢复；
- 工具菜单「♿ 跟随系统高对比度」开关（默认开）。

### 多实例体验

- 配置变更广播 UI 增强：状态栏「配置已同步」提示 + 自动刷新菜单/诊断；
- 多实例上限可配置（`QINGCAO_MAX_INSTANCES` / QSettings，范围 1~10）；
- 崩溃恢复草稿/陈旧备份清理工具 `tools/clean_recovery_drafts.py`。

### 测试与验证

- 高对比度模拟工具 + 真机验证报告与截图（`docs/validation_results_v2.13.md`）；
- 测试 QSettings/session/备份目录三重隔离，分片并行全量通过。



（下一版本开发中）

## [2.12.1] - 2026-10-28

（下一版本开发中）

## [2.12.0] - 2026-10-28

### 多实例冲突检测与实例保护（v2.12.0 P0）

- 保存冲突检测：其它实例保存同一文件且本地有未保存修改时，弹「保存冲突」
  对话框（默认保留本地），可显式选择重载磁盘内容；冲突记录在
  `_last_remote_conflict` 便于排查；
- 打开事件重复抑制：同一路径只广播一次 `file_opened`；
- **单实例聚焦**：普通启动（不带 `--new-window`）先尝试通知已运行实例
  聚焦窗口并退出，避免误开大量实例；
- **`--new-window` 上限 3**：超过时提示并安全退出，防止实例过多拖垮机器；
- 修复 `Document.is_modified` 为 property 导致冲突分支被异常吞掉的问题；
- 测试：冲突保留/重载、无冲突自动重载、重复打开抑制、实例计数与接线。

## [Unreleased]

（下一版本开发中）

## [2.11.3] - 2026-10-27

### 开发者信息更新

- 开发者署名由 `hedongwei` 统一更新为 **TomJerry**（代码头注释、版权、
  About 对话框、安装器发布者、插件作者、README/LICENSE/Dockerfile 等，
  共 100+ 处；邮箱保持不变）。

## [Unreleased]

（下一版本开发中）

## [2.11.2] - 2026-10-27

（下一版本开发中）

## [2.11.1] - 2026-10-27

（下一版本开发中）

## [2.11.0] - 2026-10-27

（下一版本开发中）

## [2.10.0] - 2026-10-26

（下一版本开发中）

## [2.9.0] - 2026-10-26

### 发布质量（P3：Release 自动附加包报告）

- `tools/ci_publish_release.py` 新增 `compose_body()`：发布说明自动追加
  「包信息（自动生成）」章节（ZIP/哈希文件大小 + SHA256）；
- 发版时无需手工维护体积/哈希，Release 正文与资产一致；
- `tests/test_ci_publish_release.py` 2 项：报告拼接、payload 字段。

## [Unreleased]

（下一版本开发中）

## [2.8.0] - 2026-10-26

### 插件平台（P2：spell_check 沙箱二阶段）

- 沙箱协议新增受限 `add_ignore_word`（RPC 白名单 + worker 校验，
  单词长度上限 80，空词拒绝）；
- `SandboxedPlugin.add_ignore_word()` 只读代理（写文件仍由插件进程完成）；
- 宿主新增「工具 → 忽略沙箱诊断中的可疑词」：读取沙箱诊断、逐词
  调用 `add_ignore_word`，然后重跑诊断发布（来源 `sandbox:<插件>`）；
- spell_check 重新标记 `sandbox: true`：主进程不再导入，诊断与忽略词
  均经子进程 RPC；进程内菜单/右键入口保留给非沙箱场景；
- `tests/test_sandbox_ignore_words.py` 2 项：RPC 忽略词、spell_check
  沙箱标记与协议方法。

## [Unreleased]

（下一版本开发中）

## [2.7.0] - 2026-10-26

### 拼写检查增强（忽略本文件可疑词）

- 新增 `ignore_flagged_words()`：把当前文档全部可疑词一次性写入
  `data/spell_ignore.txt`（去重、保留已有词），随后清空诊断并更新状态栏；
- 菜单「工具 → 拼写检查 → 忽略本文件可疑词」+ **编辑器右键菜单**
  同名入口（`api.add_editor_context_menu`）；
- spell_check 恢复为进程内插件（沙箱试点已由 `plugins/sandbox_demo`
  验证；仍保留 `diagnostics()` 协议入口以便再次迁移）；
- 新增 `tests/test_spell_ignore_enhance.py` 2 项：追加+清诊断、
  无可疑词时零操作。

## [Unreleased]

### UI 修复（C-2：主题覆盖独立顶层对话框）

- 新增 `_TopLevelThemeFilter`（应用级事件过滤器）：**新创建**的独立顶层
  窗口显示时自动套用当前主题 QSS（QMenu/QToolTip 除外）；
- 新增 `_apply_theme_to_top_levels()`：主题切换时同步已存在的所有顶层
  窗口（含独立对话框），并递归适配其子控件内联 QSS；
- `_apply_theme_by_name()` 记录 `_current_theme_qss` 并接入上述两步；
- 新增 `tests/test_theme_toplevel.py` 3 项：已存在对话框套主题、
  新对话框经过滤器套主题、菜单不被误改。

## [Unreleased]

（下一版本开发中）

## [2.6.2] - 2026-10-26

（下一版本开发中）

## [2.6.1] - 2026-10-23

### 插件平台（C-1 落地：宿主诊断接线 + spell_check 沙箱试点）

- `MainWindow.run_sandboxed_diagnostics()`：调用沙箱插件的
  `diagnostics()`，以 `sandbox:<插件名>` 为来源发布到「问题」面板；
  重复运行覆盖本来源、不清除 LSP/其它插件诊断；
- 工具菜单新增「🧪 运行沙箱插件诊断」（无快捷键、不影响旧入口）；
- **spell_check 转为沙箱试点**：manifest 标记 `sandbox: true`，
  新增 `diagnostics(text)` 只读入口（原 `check_current`/菜单保留给
  非沙箱场景的测试与回溯）；
- 更新 B-3b 默认发现测试（spell_check 属试点，sandbox_demo 仍禁用）；
- `tests/test_sandbox_diagnostics_host.py` 2 项：宿主发布/覆盖、
  spell_check 沙箱标记与 diagnostics 入口。

## [Unreleased]

### 插件平台（C-1：沙箱受限诊断协议）

- RPC 白名单新增 `diagnostics`：插件只**返回诊断数据**，发布到问题面板
  仍由宿主完成（最小攻击面）；
- worker 侧校验并规范化字段（line/col/severity/message/code），
  过滤非法项、上限 500 条；
- `SandboxedPlugin.diagnostics(text)` 只读代理，异常自动降级为空列表；
- `tests/test_sandbox_diagnostics.py` 2 项：规范化/限量、缺方法返回空；
- 为后续把 spell_check 等诊断类插件迁移到沙箱铺路。

## [Unreleased]

（下一版本开发中）

## [2.6.0] - 2026-10-23

### 插件平台（B-4/B-5：沙箱示例插件 + 端到端验证）

- 新增 `plugins/sandbox_demo/` 示例插件：manifest `sandbox: true`、
  **默认 `enabled: false`**（安全交付），只实现只读 `symbols`；
  启用后 `.sdemo` 文件的 `## 标题` 会进入大纲（符号由子进程计算）；
- `discover_sandboxed_plugins()` 尊重 manifest `enabled`：禁用插件不参与
  沙箱发现；
- 宿主 `_get_sandboxed_plugins()` 支持注入插件目录
  （`_sandbox_plugin_dir`，便于测试与自定义部署）；
- 新增 `tests/test_sandbox_e2e.py`（3 项）：默认禁用不被发现、加载器
  导入级排除 + 宿主代理符号合并（非目标文件无噪声）、禁用插件不发现；
- 说明：spell_check 使用菜单/诊断/状态项等非只读 API，不适合纯只读
  沙箱代理；B-4 采用示例插件验证链路，后续再评估扩展 RPC（诊断类）。

## [Unreleased]

### 插件平台（B-3b：宿主侧沙箱注册表 + 符号合并）

- `MainWindow` 新增 `_get_sandboxed_plugins()`：按 manifest
  `sandbox: true` 惰性创建 `SandboxedPlugin` 代理（无声明时为空，
  对现有插件零影响）；
- `_close_sandboxed_plugins()` 在 `closeEvent` 调用，退出时关闭所有
  沙箱子进程（避免孤儿进程）；
- `collect_plugin_symbols()` 合并沙箱插件符号（只读代理，失败/降级
  自动跳过）；
- 新增 `tests/test_sandboxed_collectors.py`（3 项：符号合并、退出关闭、
  默认无沙箱插件为空）；
- 待办：`PluginManager.load_all` 的**导入级排除**需要
  `PluginLoader.load_all` 增加 `exclude_names` 参数（当前只在收集器
  侧隔离，沙箱插件仍会被进程内导入），列入下一轮。

## [Unreleased]

### 插件平台（B-3a：opt-in 只读沙箱管理）

- 新增 `infrastructure/plugin_sandbox_manager.py`：
  - `is_sandbox_enabled()` / `discover_sandboxed_plugins()`：
    仅 manifest 显式 `"sandbox": true` 的插件被隔离（**默认关闭**，
    现有插件零影响）；
  - `SandboxedPlugin`：只读代理 symbols/hover/completion/describe，
    惰性启进程、超时/崩溃自动降级（返回空结果 + `degraded` 标记，
    不阻塞、不抛异常到宿主）；
- `SandboxProcess` 增加**就绪握手**（worker 发 `{"ready": ...}`）：
  插件导入失败时启动即报错，消除"进程活着但不可用"的竞态；
- `tests/test_plugin_sandbox_manager.py` 4 项：开关默认值、扫描、
  只读代理往返、坏插件降级不抛异常。

## [Unreleased]

### 插件平台（B-1/B-2：子进程沙箱 RPC 协议 + 宿主）

- 新增 `infrastructure/plugin_sandbox_rpc.py`：JSON Lines over stdin/stdout；
  `SandboxProcess` 负责启动子进程、带超时调用、崩溃隔离与 `restart()`；
- 新增 `infrastructure/plugin_sandbox_worker.py`：子进程内导入插件并响应
  **只读**扩展点（symbols/hover/completion/describe），主进程永不导入
  插件代码；插件 print 被忽略，stdout 专用于协议；
- 方法白名单双重限制（客户端 + worker）；
- `tests/test_plugin_sandbox_rpc.py` 4 项：正常调用、超时隔离（不杀进程）、
  非法方法拦截、崩溃后 restart；
- 后续（B-3/B-4）：manifest `sandbox: true` 强制隔离、接入扩展点收集器、
  试点插件迁移。

## [Unreleased]

### 性能（主题切换 1s+ → 130-210ms）

- 根因实测：应用级 `QApplication.setStyleSheet` 会触发**全控件样式重算**
  （90-424ms）；且延后插件激活与切换撞车时可达 2.3s（AI 插件激活
  1937ms 叠加）；
- C-1：`PluginManager` 新增暂停/恢复延后插件激活，
  `_apply_theme_by_name()` 在应用 QSS 期间暂停，避免两件重活撞车；
- C-2：新增 `ThemeLoader.build_qss()`；主题切换改为 **窗口级**
  `self.setStyleSheet(qss)`（实测 35-49ms vs 应用级 90-424ms）+
  `apply_palette()` 兜底，子对话框随父控件继承样式；
- 实测真实切换：130/159/213ms（首次 363ms 含延后插件激活噪声）；
- 待人工验证：独立非子对话框（若存在）的主题覆盖。

## [Unreleased]

（下一版本开发中）

## [2.5.2] - 2026-10-23

### 性能（撤销栈惰性物化：typing 149 → 57 µs/键，达标 <100µs）

- `InsertCmd` 改为分片存储（`_parts` + 按需 join 缓存），连续输入时
  **原地追加**，不再每次 merge 重建命令对象、不再整篇字符串拼接；
- `UndoManager` 新增 `try_append_typing()` 打字快路径：单光标连续插入且
  位置相邻/合并窗口内时，直接追加到栈顶命令，**跳过 CommandPool 与命令
  对象分配**；新操作照常清空 redo 栈（与 record() 语义一致）；
- `core/editor.py` 的 SCN_MODIFIED 插入路径接入快路径（多光标/列模式
  仍走原逻辑）；
- 实测：**149 → 57.2 µs/键**（三次采样 56.2/57.2/72.8，2000 次
  insertAt 0.114s）；撤销语义 38 项定向测试通过；
- `bench_optimization.py` typing_2000 阈值 0.40 → **0.20s**（达标）。

## [Unreleased]

### 性能（输入路径优化，typing 211 → 149 µs/键）

- cProfile（2000 次 insertAt）显示热点在每键的 provider 同步：
  `sc.text()` 全文 + `provider.read_text()` 全文解码比较 + 逐块写入；
- `_sync_provider_now()` 改用**内存缓存** `_last_synced_text` 比较，
  去掉 provider 全文解码；
- `_sync_content_to_provider()` 增加单块快速路径（小文件常见）；
- 实测：211 µs/键 → **149 µs/键**（三次采样 143/149/160）；
- `bench_optimization.py` 的 typing_2000 阈值 0.9 → **0.40s**，
  锁定本阶段收益；目标 <0.20s（<100µs/键）需继续优化撤销栈路径。

## [Unreleased]

### 性能（主题切换遍历优化）

- `adapt_widget_styles()` 去掉了重复的 `findChildren` 遍历（原先
  先按 type(root) 再按 QWidget 扫两遍，实际只用第二次结果）；
- 增加主题/控件级缓存：同一主题重复套用（惰性面板反复 ensure 等）
  直接短路；切换主题时仍从**首次原始 QSS** 重新适配，不会叠加失真；
- 测试同步更新语义：同主题二次调用返回 0，换主题重新适配。

## [Unreleased]

（下一版本开发中）

## [2.5.1] - 2026-10-22

### UI 修复（主题切换崩溃 + 菜单选中对号）

- 修复「主题切换失败: cannot access local variable 'QApplication'」：
  `_apply_theme_by_name()` 后文局部 import 使 QApplication 成为整函数
  局部变量，提前使用抛 UnboundLocalError；改为函数最前面导入。
- 菜单选中对号（对齐 Notepad++）：「编码」勾选当前编码、
  「换行符」勾选当前 EOL、「语言」勾选当前语言包/自动（aboutToShow 同步）。
- 新增 tests/test_menu_checks.py（导入顺序回归 + 勾选当前项）。

## [Unreleased]

### UI 修复（浅色主题下面板仍为黑底）

- 根因：部分面板只在**内部子控件**（树/列表等）设置硬编码深色 QSS，
  dock 级 `refresh_theme` 覆盖不到；浅色主题下出现"黑块"
  （真实桌面截图确认：插件面板、全局搜索、性能诊断、目录树）。
- 新增 `adapt_widget_styles(root, theme)`：递归适配控件树内联 QSS，
  保存首次原始 QSS 并从原始值重适配（幂等，避免多次切换叠加失真）；
- 接入两处主题路径：`apply_theme_to_widget()`（惰性面板首次打开）与
  主题切换路径（`notify_widgets` 之后全窗口扫描）；
- 测试 `tests/test_panel_theme_adapt.py`（子控件深色被改写 + 幂等）。

## [2.5.0] - 2026-10-22

### 插件平台（P2：审计接入 CI + 基线）

- `tools/audit_plugins.py` 新增 `--baseline`：按基线校验，未登记的新插件
  必须 pass，已登记插件可放宽到指定 verdict；
- `plugin_sandbox.check_against_baseline()` 纯函数；
- 新增 `tools/plugin_audit_baseline.json`；
- CI `test.yml` 增加「Plugin security audit」步骤（windows + py3.11）；
- `docs/plugin_sandbox.md` 补 CI 接入说明。

### 插件平台（P2 第一阶段：安全沙箱静态审计）

- 新增 `infrastructure/plugin_sandbox.py`：AST 扫描危险 import/调用/
  动态执行/写文件，比对 manifest 权限声明，输出
  pass/warn/review/reject 判定；
- 新增 `tools/audit_plugins.py` CLI（默认/--json/--strict）；
- 新增 `docs/plugin_sandbox.md`（规则表、判定、内置插件现状、接入建议）；
- `spell_check` 补齐 `filesystem` 权限声明（写忽略词文件）；
- `tests/test_plugin_sandbox.py` 6 项：干净插件、网络/进程/文件系统
  能力检测、danger 人工评审、全量内置插件无 reject。

### 插件（拼写检查：状态栏计数）

- 激活时创建状态项「拼写: -」，检查后显示问题数量、清除后归零
  （惰性创建以兼容直接调用/测试）；
- FakeApi 行为测试：`check_current` 发布诊断并更新状态项、`clear`
  归零（不再只做静态检查）。

### 插件（拼写检查：忽略词 / 自定义词典）

- 新增 `data/spell_ignore.txt`（每行一词，`#` 注释，大小写不敏感）：
  忽略词与自定义词典合一，加载后直接参与判定；
- 插件新增「重新加载忽略词」「编辑忽略词…」菜单（文件不存在自动创建）；
- `load_ignore_words()` 模块函数便于复用/测试；
- 测试补 2 项：文件解析（注释/空行/大小写）、默认文件与菜单存在。

## [2.4.0] - 2026-10-22

### 插件（内置拼写检查，对标 NPP DSpellCheck）

- 新增内置插件 `plugins/spell_check/`：仅 `editor_read` 权限；
- 词典优先级：可选 `pyspellchecker`（已装则自动用）→ 内置常用词表 +
  技术词允许列表（零依赖可运行）；
- 只检查像英文单词的 token：跳过全大写/含数字/下划线/驼峰/URL/过短词，
  降低误报；结果发布到「问题」面板（SPELL001 warning），状态栏给数量；
- 设置项：启用、最短检查长度、最多报告数量；
- 菜单：工具 → 拼写检查 → 检查当前文档 / 清除结果；
- `tests/test_spell_check_plugin.py` 4 项（manifest/注册/误报过滤/限额）。

### UI（对齐 Notepad++：标签栏习惯）

- 双击标签栏空白处 **新建文档**（NPP 同名行为，可在标签栏设置中关闭——
  本项目直接实现，无额外开关）；
- 中键关闭标签确认已实现（早前版本）；新增 `tests/test_tab_bar_npp.py`
  覆盖两种交互（真实 QMouseEvent）。

### UI（对齐 Notepad++：窗口级拖放打开）

- 主窗口启用拖放：文件拖到窗口/欢迎页任意位置即可打开；
  目录拖入则作为项目打开（复用 `_open_folder`）；
- 新增 `_open_dropped_paths()` 与 `dragEnterEvent/dragMoveEvent/dropEvent`；
- 新增 `tests/test_drag_drop.py`（acceptDrops + 真实 QDropEvent 打开文件）。

## [2.3.0] - 2026-10-22

### 性能（实测驱动，`tools/bench_optimization.py` 可复跑）

- **大文件打开提速 10~30 倍**：10MB/58 万行 4.21s → **0.40s**；
  2MB `.py`/50 万行 2.60s → **0.23s**。根因不是 QScintilla（`setText` 仅 0.22s），
  而是 `_has_non_ascii_beyond` 用 Python 逐字节遍历（2080 万次生成器调用）。
  改为 `bytes.isascii()`（C 实现）。
- **会话保存 23 倍**：50 万行标签 `session.save()` 1.61s → **0.07s**。
  书签改用 `SCI_MARKERNEXT` 跳转；折叠状态在超大文档跳过扫描。
- **启动不再被网络阻塞**：AI 插件原在 UI 线程同步 HTTP 探测 Ollama（实测 4.1s），
  改为后台线程 + 信号桥；Ollama 等本地 provider 不再初始化 keyring（省 0.37s）。
- **新增「视图 → 大文件强制高亮」开关**：大文档（>20 万行或 >8MB）
  默认关闭语法高亮与缩略图渲染，用户可显式覆盖。
- **启动主题去重**：真实启动里 `main.load_theme()` 已应用过同主题，
  `apply_startup_theme()` 不再重复应用（实测 0.53~1.2s → **0.004s**）；
  隐藏面板改为"挂起 + 首次显示时应用"（`_LazyThemeApplier`），
  惰性构造面板与插件面板也统一套用当前主题（修复浅色主题下黑块）。
- **应用级事件过滤器零成本放行**：非按键事件不再走 weakref/getattr 链
  （实测主题 polish 期间 13,139 个事件白付 0.147s）。
- **重量级插件延后加载**：manifest 新增 `defer_activation`（ai_assistant
  导入占插件加载 0.535s/0.61s）；首轮插件就绪 2.18s → **1.07s**，
  AI 插件后台 600ms 后加载（`PluginLoader.load_deferred`，带关闭护栏）。
- **新增回归基准** `tools/bench_optimization.py`：覆盖启动/插件/事件/面板/
  输入/大文件/会话/主题，`--check` 超阈值退出码 1。

### 构建 / CI

- 修复 GitHub Actions 发版工作流：`artifact@v3` 已于 2025-01-30 停用、
  缺 `contents: write`、`action-gh-release@v1` 过时。
- 修复英文 Windows（cp1252）下 `build.py` / `main.py` 中文输出
  `UnicodeEncodeError` 导致构建失败（`PYTHONUTF8=1` + stdio reconfigure）。
- 版本兜底漂移：`main.py` / `build_linux.py` / `build_macos.py` /
  `build_installer.py` 中硬编码的 `"2.1.0"` 改为读 `VERSION`，
  避免 version.py 导入失败时静默产出过期版本号。

### 插件系统（计划第 2 周：扩展点 API v2.3）

- **补全提供者** `api.register_completion_provider(provider, language_ids=None)`：
  插件可参与编辑器补全，候选项合并进 `EditorWidget.local_completions()`
  （按语言/扩展名过滤；异常隔离；卸载自动注销）。
- **诊断发布** `api.publish_diagnostics(problems, filepath=None)` /
  `api.clear_diagnostics()`：插件诊断进入「问题」面板；
  **只替换本插件来源**，不误删 LSP/其它插件条目（实时校验语义）。
- **后台任务** `api.run_background(func, on_done, on_error, name)`：
  子线程执行、**回调回到主线程**（QObject 信号桥），
  插件卸载自动取消，避免窗口销毁后 emit 崩溃。
- 三个 API 均受权限门控（`editor_read`，缺失时抛 `PermissionError`）。
- 新增测试 `tests/test_plugin_extension_points.py`（4 项）：
  补全合并/注销、诊断合并且不误删、后台回调线程正确、
  权限拒绝。

### 插件系统（扩展点 API v2.4：第二批）

- **hover 悬浮提示**：`api.register_hover_provider()` → 编辑器 ToolTip；
- **代码操作**：`api.register_code_action_provider()` + 编辑器右键菜单
  「代码操作…」入口（quickfix 类）；
- **编辑器右键菜单**：`api.add_editor_context_menu()`；
- **状态栏项**：`api.add_status_item()`（QLabel/QWidget 常驻右侧）；
- **装饰/标记**：`api.add_decoration(start, end, color)`（Scintilla 指示器，
  不修改文本）；
- **设置界面 schema**：`api.register_settings_schema()` 自动生成
  「工具 → 插件设置」对话框并持久化（str/int/bool/choice/text）。
- 全部支持插件卸载自动清理；测试 `test_plugin_extension_points.py`
  扩展到 **7 项**（hover 过滤/清理、右键菜单+代码操作+状态栏、
  装饰+设置 schema）。

### 插件系统（真实插件迁移 + 测试稳定性）

- **json_formatter 迁移到扩展点 API**（端到端验证）：hover 显示 JSON
  键/值或语法错误、代码操作（按设置格式化/压缩/排序键）、编辑器右键菜单、
  设置 schema（缩进/排序键，自动生成对话框）、诊断（JSON 语法错误发布到
  「问题」面板，卸载清理）。
- 修复 `register_settings_schema` 未登记宿主的问题
  （新增 `MainWindow.register_plugin_settings_schema`）；
  且不再要求 `dialog` 权限（插件自有配置声明，宿主渲染）。
- **修复延迟插件加载竞态**：`__init__` 的
  `QTimer.singleShot(100, _load_plugins)` 在窗口已关闭时仍会执行
  → 弹权限框/创建面板（测试中造成模态阻塞与偶发崩溃）；
  `_load_plugins` 入口增加 `_closing` 守卫。
- **测试稳定性**：
  * 真实子进程 LSP 握手用例标记 `@pytest.mark.isolated`，默认跳过，
    `QC_RUN_ISOLATED=1` 显式运行（`tests/conftest.py`）；
  * 修复测试会话污染：新测试关闭窗口时会写真实用户会话文件，
    导致后续 `test_default_panels_visible` 恢复出空面板布局；
    现统一 `_close_without_session()` 防止写会话。
- 新增 `tests/test_json_formatter_plugin.py`（真实插件端到端）通过。

### 测试基础设施：插件 conformance 骨架

- 新增 `tests/test_plugin_conformance.py`（三层契约，自动扩展）：
  1. **扩展点契约**：9 个 v2.3/v2.4 扩展点各自验证
     `注册 → 生效 → 卸载清理`（新增 API 只需加一条 `@contract`）；
  2. **插件清单契约**：扫描 `plugins/*/plugin.json`，验证必填字段、
     权限必须在 `ALL_PERMISSIONS` 内、`api_version` 可解析、
     入口模块存在 `Plugin` 类且实现 `on_activate/on_deactivate`
     （用 AST 静态检查，**不 import 插件** —— 插件模块顶层有 QObject
     副作用，导入会污染测试进程）；
  3. **API 面自检**：防止扩展点被误删/改名。
- 契约测试不写真实用户会话（`_close()` 屏蔽 session.save），
  避免测试间污染。

### 插件系统（更多内置插件迁移）

- **markdown_preview**：新增「工具 → Markdown → 检查并报告到问题面板」，
  把 Markdown 结构问题发布为诊断（空图片 alt = warning MD001、
  代码围栏未闭合 = error MD002）；设置 schema 控制是否检查 alt、
  最多报告条数；卸载清理诊断。
- **todo_panel**：设置 schema（最多扫描条数 max_items、状态栏计数开关）；
  新增状态栏常驻项显示 TODO 数量；扫描时应用 max_items 上限。
- 新增 `tests/test_builtin_plugin_migrations.py`：加载真实插件模块验证
  诊断/设置/状态栏注册、行为与清理。

### 插件系统（更多内置插件迁移 + CI 契约）

- **wordcount**：状态栏常驻项显示字数/词数（0.5s 节流、>2MB 大文件
  显示"大文件"保护），设置 schema（show_status、统计口径 chars/words）。
- **ai_assistant**：设置 schema（status_refresh_seconds、enable_inline，
  实际驱动状态刷新间隔与内联补全开关）；菜单状态检查改用宿主
  `api.run_background`（不再自行 threading）。
- 修复 `run_background` 清理顺序：卸载时**不再 deleteLater 桥对象**
  （工作线程可能仍在 emit → Qt 访问违例段错误），改为置 cancelled +
  断开信号。
- **CI 契约**：`.github/workflows/test.yml` 增加
  「Plugin conformance contracts」步骤（windows-latest + Py3.11）。
- 新增 `tests/test_builtin_plugin_migrations.py`（wordcount 行为 +
  ai_assistant 静态迁移校验；AI 自带 QThread 生命周期在 pytest 直接
  activate/deactivate 会偶发段错误，故行为层由应用内加载覆盖）。

### 插件系统（10/10 内置插件迁移完成 + AI 线程清理债）

- 剩余 5 个内置插件迁移扩展点：
  demo（设置 schema + 状态栏问候）、my_plugin（设置 schema）、
  git_deep（设置 schema + 状态栏）、logtail（设置 schema + 监视状态栏）、
  python_debugger（设置 schema + 状态栏）。conformance 新增
  `test_all_builtin_plugins_migrated`（10 插件设置契约 + 7 插件状态栏契约）。
- **修复 ai_assistant QThread 清理债**（pytest 段错误根因）：
  对话框持有 AIWorker(QThread)（parent=dlg），worker 运行中销毁对话框会
  让 QThread 析构 qFatal → 段错误。卸载时 cancel() → wait(3000) →
  超时 terminate()+wait(1000)，线程停稳后才 close/销毁对话框；
  新增状态栏常驻项显示 Ollama 状态。
- python_debugger 扩展点调用改为防御式（FakeApi 测试桩缺少新 API 时
  不影响菜单注册）。

### 插件 SDK（Notepad++ 对比借鉴：能力探测 + 事件目录）

- 新增 `api.get_api_capabilities()`：借鉴 NPP 插件"函数表"思路，插件可
  在激活时探测宿主支持的扩展点/事件/权限，避免在旧宿主上盲试 API。
- 新增 `api.list_events()`：可枚举 15 个可订阅事件（等价 NPP 的
  `NPPN_*` 通知清单）。
- conformance 增加 `test_api_capabilities_and_event_catalog`，锁定
  能力清单与事件目录下限。
- 新增 `docs/npp_plugin_benchmark_v2.3.md`：NPP 插件体系逐项对比、
  8 条可借鉴项与 P0/P1/P2 排期（声明式语言定义/插件 symbol provider/
  商店兼容性 + 全部更新/插件模板/事件生命周期保证/子进程沙箱）。

### 编辑器（声明式语言包：Notepad++ UDL 等价物）

- 新增 `core/language_pack.py`：扫描 `data/language_packs/` 与
  `plugins/*/languages/` 下的 `*.qingcao-lang.json`，按扩展名索引，
  **语言包优先于内置映射表**；含格式校验与错误提示。
- 新增 `ui/generic_lexer.py`：`QsciLexerCustom` 解释语言包，支持
  关键字/注释（行+块）/字符串/数字/标识符 6 种样式，颜色跟随当前主题；
  文档 >1MB 自动退化为默认样式（与「大文档模式」一致）。
- `create_lexer_for_extension()` 接入语言包：新增语言不再需要写
  Python 词法器类，只需投放 JSON。
- 示例 `docs/examples/mylang.qingcao-lang.json` + 文档
  `docs/language_packs.md`；新增 `tests/test_language_pack.py`（4 项：
  校验/发现注册/工厂命中/样式分类）。

### 插件系统（P0-2：symbol provider 接入大纲面板）

- 新增 `api.register_symbol_provider(provider, language_ids=None)`
  （等价 Notepad++ 的 `functionList.xml`）：插件/语言包可为新语言贡献
  符号，合并进「大纲」面板；权限 `editor_read`，卸载自动清理。
- 大纲面板修复两个真实缺陷：
  * 定时器可能在文件**加载中途**解析并缓存空符号，之后同文件不再
    重解析 → 增加内容就绪兜底补解析；
  * 插件 **symbol provider 数量变化**（晚激活/卸载）不会反映到大纲 →
    现在 provider 数量变化即重解析。
- `markdown_preview` 实际使用：把 Markdown 标题（`#`~`######`）贡献为
  大纲符号。
- conformance 新增 `symbol-provider` 契约与 markdown 迁移覆盖；
  `docs/npp_plugin_benchmark_v2.3.md` 标记 P0-1/P0-2 完成；
  `docs/plugin_api_v2.3.md` 追加 symbol provider 用法。
- 新增 `tests/test_symbol_provider.py`（3 项：规范化收集、语言/扩展名
  过滤、大纲合并与卸载移除；capabilities 含 symbol_provider）。

### 插件 SDK（P1：插件模板脚手架）

- 新增 `tools/new_plugin.py`：一键生成半成品插件（manifest + PluginBase
  子类 + 生命周期 + 所选扩展点示例），生成的清单默认满足 conformance
  清单契约；支持权限/扩展点选择、参数校验、`--force`。
- 新增 `docs/plugin_scaffold.md`、`tests/test_plugin_scaffold.py`（3 项）。
- 对应 `docs/npp_plugin_benchmark_v2.3.md` P1-6（NPP pluginTemplate）。

### 插件 SDK（P1：事件生命周期保证）

- 新增 `docs/event_lifecycle.md`：15 个事件的触发时机、主线程派发保证、
  顺序保证（`file_saved` 在落盘后、`theme_changed` 在 QSS 后）、
  订阅/退订规则与后台线程禁忌。
- 新增 `tests/test_event_lifecycle.py`（3 项）：**文档与代码一致性**
  （新增事件漏文档会失败）、全部事件可订阅/退订、未知事件被拒绝。
- 对应 `docs/npp_plugin_benchmark_v2.3.md` P1-7。

### 插件系统（P1：商店兼容性门控基础）

- `infrastructure/plugin_updater.py`：
  * `UpdateInfo` 新增 `max_app_version`；
  * 新增 `get_app_version()` 与
    `is_app_version_compatible(min, max, app_version)`：空约束不限，
    支持 `1.2`/`1.2.3`/`1.2.3-beta`，**非法版本字符串直接拒绝**
    （防止 SemVer 宽松解析成 0.0.0 误判兼容）；
  * `PluginUpdater.check_compatibility(info)` 便捷包装。
- 新增 `tests/test_plugin_compatibility.py`（3 项）；
- 新增 `docs/plugin_store_benchmark.md`：现状/缺口/改造方案
  （NPP Plugins Admin 对标；下一步：更新入口强制门控、商店兼容性
  徽章、全部更新 UI、changelog 展示）。

### UI（对齐 Notepad++：状态栏交互 + 对齐方案）

- 状态栏新增 NPP 式交互：**「行/列」标签可点击跳转到行**
  （`_ClickableLabel`，`Ctrl+G` 等价入口）；行列/编码/EOL/模式标签
  补齐说明性 tooltip 与指针光标。
- 新增 `docs/npp_ui_feature_alignment.md`：UI 骨架逐项对照
  （菜单/工具栏/标签栏/状态栏/面板/欢迎页/主题）、功能清单对照与
  P0/P1/P2 排期（P0 菜单重组 + 状态栏分段点击；P1 工具栏图标模式/
  标签右键菜单/欢迎页开关/商店兼容性徽章；P2 打印预览/多实例/拼写检查）。
- 新增 `tests/test_status_bar_ui.py`（2 项）；
  修复 `test_default_panels_visible` 的顺序相关 flaky：
  用例先删除会话文件，避免恢复前序测试写入的"无可见面板"状态。

### UI（对齐 Notepad++：状态栏长度段 + 统计摘要）

- 状态栏新增「长度」段（NPP `Length` 段等价）：显示文档字节长度，
  **点击弹出统计摘要**（行数/字符数/单词数/UTF-8 字节数）；
  >4MB 文档跳过统计并提示（避免卡顿）。
- 既有「编码」「EOL」标签的点击切换菜单确认可用（NPP 同款交互）。
- 测试补充 `test_length_label_and_stats`（tooltip/长度文本/统计正确）。

### UI（对齐 Notepad++：菜单重组第一批）

- 新增 **「搜索」「宏」「运行」「窗口」** 四个顶级菜单（通过
  `insertMenu` 插到「帮助」前，符合 NPP 习惯顺序）：
  * 搜索：查找 / 在文件中查找 / 跳转到行 / 命令面板 / 模糊打开文件 /
    跳转到符号；
  * 宏：开始-停止录制 / 回放；
  * 运行：运行当前文件 / 调试运行；
  * 窗口：面板切换项（复用现有 QAction）+ 无干扰模式 / 全屏。
- **非破坏式**：新菜单项不绑定快捷键（原 QAction 仍是唯一快捷键入口，
  避免 ambiguous shortcut），旧菜单与命令面板入口全部保留。
- 新增 `tests/test_npp_menus.py`（2 项意图：四个菜单存在、旧菜单未破坏、
  新菜单项无快捷键绑定）。
- 编码/语言收拢为「编码」菜单列为下一步。

### UI（对齐 Notepad++：编码 / 语言菜单）

- 新增「编码(&C)」菜单：编码列表（复用状态栏 ENCODINGS，切换走
  `_on_encoding_changed`）+「换行符」子菜单（LF/CRLF/CR）。
- 新增「语言(&L)」菜单：「自动（按扩展名）」+ 所有声明式语言包
  （`core.language_pack`，点击即对当前编辑器应用通用词法器）；
  实现 v2.3 语言包的首个 UI 入口。
- 仍保持非破坏式：新菜单项不绑定快捷键，旧入口不变。
- `tests/test_npp_menus.py` 增加编码/语言菜单用例。

### UI（对齐 Notepad++：设置菜单收拢）

- 新增「设置(&O)」菜单，集中 NPP `Settings` 类入口：
  首选项 / 快捷键一览 / 快捷键编辑器（方案）/ 主题编辑器 / 主题市场 /
  导入-导出主题包 / 打开主题目录 / 导入-导出配置 / 打开语言包目录。
- 新增 `_open_language_packs_dir()`：直接打开 `data/language_packs/`
  方便投放声明式语言包。
- 仍为非破坏式（无新快捷键、旧入口保留）；
  `tests/test_npp_menus.py` 增加设置菜单用例。

### UI（对齐 Notepad++：欢迎页可关闭）

- 「视图」菜单新增可勾选动作 **显示欢迎页**（默认开，持久化到
  `show_welcome_page` 偏好）：关闭后启动直接进入空白编辑区（NPP 习惯），
  随时可恢复。
- 新增 `tests/test_welcome_toggle.py`（开关状态/偏好写入/堆叠切换，
  结束时恢复默认偏好避免污染真实配置）。
- 已知范围：关闭后若手动关闭全部标签，仍会显示欢迎页（不影响启动体验）。

### 插件系统（P0：更新路径兼容性门控）

- `PluginUpdater.update_plugin()`：下载前校验 `min/max_app_version`，
  不兼容直接返回失败 `UpdateResult`（不下载、不安装、不备份）；
- `PluginUpdater.update_all()`：逐项门控，跳过不兼容项并在汇总中给出
  "跳过：需要应用 >= x"；进度回调也会显示跳过原因；
- 测试：`test_update_plugin_rejects_incompatible_before_download`
  （不触网）、`test_update_all_skips_incompatible`（批量跳过）；
- 文档 `docs/plugin_store_benchmark.md` 标记 P0 完成。

### 插件商店（P1：兼容性徽章 + 全部更新）

- 新增 `check_plugin_compatibility()`（复用更新器唯一判定）：
  安装、更新、详情页、批量更新共用同一套 min/max 兼容规则。
- 安装/更新入口加门控：不兼容弹「不兼容」并取消，不再下载。
- 详情页新增「最高版本」与兼容性徽章（✅ 兼容当前版本 /
  ⚠️ 不兼容: 原因）。
- 新增「⬆ 全部更新」按钮（检查更新 → 确认 → 批量更新），
  `_update_all()` 自动跳过不兼容项并列出跳过原因。
- 新增 `tests/test_store_compatibility.py`（3 项）。
- docs/plugin_store_benchmark.md P1 关键项完成。

### 插件商店（P1：changelog / update_url 展示）

- `PluginInfo` 新增 `changelog` 字段（可选，注册表可下发）；
- 详情页技术信息新增「更新地址」（可点击链接）与「更新日志」；
- 新增 `tests/test_store_metadata.py`（字段存在 + 详情 HTML 含两项）。

### UI（对齐 Notepad++：工具栏图标模式）

- 「视图」菜单新增可勾选 **工具栏图标模式**（默认关，持久化
  `toolbar_icon_mode`）：开启后工具栏切换为 `ToolButtonIconOnly`，
  动作文本用 **emoji 动态生成 QIcon**（QPainter 绘制，无需图片资源），
  原文本转为 tooltip；关闭恢复文字。
- 新增 `tests/test_toolbar_icon_mode.py`（模式切换/图标生成/文字恢复，
  结束时恢复默认偏好）。
- `docs/npp_ui_feature_alignment.md` 工具栏行标记完成。

### UI（对齐 Notepad++：打印 / 打印预览）

- 文件菜单新增「🖨 打印…」（Ctrl+P）与「👁 打印预览…」；
- 实现 `_build_print_document()`：把当前编辑器文本构建为
  QTextDocument（Consolas 等宽 10pt），打印与预览共用；
- 打印：QPrintDialog + QPrinter.HighResolution；
  预览：QPrintPreviewDialog（900×700，实时重排）；
- 新增 `tests/test_print_support.py`（菜单项/方法存在/文档内容正确）。

### 插件商店（P1：列表行内兼容性徽章）

- `PluginCard` 标题行新增兼容性徽章：✅ 兼容 / ⚠️ 不兼容（tooltip 原因），
  与详情页共用 `check_plugin_compatibility()`；
- 不兼容时安装/更新按钮变为「不兼容」并置灰（卸载/启用不受限），
  `_on_action_clicked` 兜底拦截；
- `tests/test_store_card_compat.py`（源码契约 + 判定函数；卡片在
  offscreen 实例化会 Qt 崩溃 0xC0000409，故不实例化 GUI）。

## [2.2.0] - 2026-10-20

> **v2.2.0 摘要**（详见 `docs/release_notes_v2.2.0.md`）
>
> * **新增能力接线**：项目（工作区/项目配置/任务面板）、会话快照、
>   从模板新建、多键快捷键序列、本地代码片段库、性能剖析、
>   崩溃统计、LSP 状态面板、撤销历史面板、格式化、导出 PDF/HTML。
> * **数据安全修复**：保存静默失败（WinError 5）、UTF-16 文件打不开、
>   编辑后丢 BOM、行尾风格被静默改写、草稿恢复永远为空、
>   快照/片段库相对路径导致"数据消失"。
> * **界面修复**：面板不跟随主题（全黑）、状态栏白字白底不可见、
>   搜索结果树不跟随主题、目录树空状态像坏掉、多屏窗口几何跑丢、
>   200% 缩放下编辑器只剩 3 行。
> * **性能**：列编辑 100k 行 22 分钟 → 3.68 秒；10MB 文件打开
>   34.9 秒 → 0.00 秒。
> * **移除**：实时协作（裸 TCP 无认证/无加密，属高风险未接线功能）。
> * **技术债**：孤立模块 17 → **0**（棘轮上限 0）。

### 高 DPI / 多显示器验证（QT_SCALE_FACTOR 1.0/1.25/1.5/2.0 + 几何恢复）

本轮验证了两个此前完全空白的场景，并修掉 2 个真实缺陷。

#### 环境限制（如实说明）

本机只有**一台显示器**（物理 1920x1080，系统缩放 125%），且 Windows 的
系统级缩放改动需要注销/重启才生效。因此：

* **高 DPI**：用 Qt 官方 `QT_SCALE_FACTOR` 模拟 1.0 / 1.25 / 1.5 / 2.0
  四档。这会真实改变 `devicePixelRatio`、字体度量与布局计算，
  等价于用户在不同缩放档下运行；
* **多显示器**：无法接第二块屏。改为验证**多屏相关代码路径**：
  会话保存的窗口坐标在"显示器被拔掉 / 换到小屏 / 尺寸超出屏幕"时
  是否正确夹回可见区域 —— 这几条正是多显示器下最常见的真实故障。

#### 高 DPI 结论：Qt 缩放本身工作正常

四档实测（`tools/verify_hidpi_multimonitor.py`，56 项全通过）：

| 缩放 | dpr | 逻辑窗口 | 抓图物理像素 | 状态栏逻辑高 | 状态栏物理高 |
|---|---|---|---|---|---|
| 100% | 1.00 | 1920×1001 | 1920×1001 | 26px | 26px |
| 125% | 1.25 | 1536×801 | 1920×1001 | 26px | 32px |
| 150% | 1.50 | 1280×667 | 1920×1001 | 26px | 39px |
| 200% | 2.00 | 960×501 | 1920×1002 | 26px | 52px |

关键不变量全部成立：**逻辑尺寸不变、物理像素按 dpr 放大、
抓图尺寸 = 逻辑×dpr（无裁切）、字体逻辑字号不变、
标签/菜单文字不裁切**。`AA_EnableHighDpiScaling` / `AA_UseHighDpiPixmaps`
也确实在 `QApplication` 创建**之前**设置（顺序错了会完全失效）。

#### 修复 7（P0，多显示器）：窗口几何恢复不感知多屏、且从不缩尺寸

`app/session.py::_restore_geometry` 原实现只拿 `primaryScreen()` 的
可用区域夹 `x/y`，导致三个真实问题：

1. **窗口永远回主屏**：保存在第二块显示器（主屏右侧 x=2200）的窗口，
   下次启动被强行拉回主屏，用户每次都要重新拖；
2. **尺寸从不夹取**：在大屏（2560×1440）保存的窗口换到小屏（1366×768）
   后仍是 2560×1440，**底部和右侧大半在屏幕外**，保存按钮/状态栏看不到；
3. **只夹左上角**：条件是 `x > right-100`，窗口宽 1000 放在 `right-950`
   时仍会越界。

修复：新增 `_pick_screen_for_geometry()` —— 用**窗口中点**调
`QApplication.screenAt()` 找对应屏幕（中点比左上角更能代表"用户把窗口
放在哪块屏"）；中点不在任何屏（显示器被拔）时取最近屏幕
（>2000px 视为无效，退回主屏）；然后先把 `w/h` 夹到 `availableGeometry`
尺寸，再把 `x/y` 夹到 `[left, right-w]` / `[top, bottom-h]`，
保证**整个窗口可见**。

#### 修复 8（P0，高 DPI 可用性）：200% 缩放下默认面板把编辑器挤成 3 行

真实桌面 200% 截图暴露：1920×1080 物理屏在 200% 下只有 **960×540 逻辑
像素**，而默认仍铺开 4 个面板（左目录树 + 底全局搜索 + 右插件 +
底性能监控）→ 编辑器只剩 3 行文本，全局搜索的单选项还被裁掉一半。

修复：新增 `_default_panels_for_screen()` —— 逻辑可用区域不足
**1280×720** 时只默认打开目录树，其余面板由用户从「视图 → 面板」按需
打开（各自记住可见性；会话恢复仍按用户上次布局覆盖）。
实测：150%/200% 下编辑器获得几乎全部空间，100%/125% 保持原 4 面板布局。

#### 验证结果

* `tools/verify_hidpi_multimonitor.py`：**56 项全通过**
  （四档缩放语义 + 几何恢复 12 项 + 静态设置 3 项 + 自适应面板 4 项）
* 全量套件：**779 项，0 失败，0 错误，2 skipped**；ruff 0 告警
* 打包版真实桌面截图：150% / 200% 下菜单、工具栏、标签、状态栏
  （`行 7, 列 0 · UTF-8 · CRLF · 插入 · 内存`）全部正常，
  自适应面板策略生效
* `tests/test_p1_features.py` 的默认面板测试改为按
  `_default_panels_for_screen()` 断言（原写死 4 个名字，策略变化后必然失败）

#### 仍未覆盖（如实说明）

* **真实双显示器**：无法在本机物理验证（单屏）。已验证的是
  "显示器变化时的窗口恢复"代码路径 + `screenAt` 选择逻辑，
  以及单屏下"多屏分支不触发"的正确性；
* **运行时跨屏拖动（DPI 变化事件）**：需要第二块不同 DPI 的屏幕才能
  触发 `QEvent.ScreenChangeInternal`；Qt 5.15 会自行处理缩放，
  但本机无法实测；
* **Windows 系统级缩放 150%/200% 的真实生效**：需要注销；
  已用 `QT_SCALE_FACTOR` 等效验证 Qt 侧布局与字号行为，
  但"系统 DPI 变化 → 进程重建布局"的完整链路未测。


### 真实混合场景压测 + 打包产物真实桌面验证（发现并修复 6 个缺陷）

两项验证都不是"再跑一遍单元测试"，而是走**真实用户动作序列**
（切编码→编辑→保存、混合换行文件→编辑→保存）和**真实桌面渲染**
（打包 exe + Windows 窗口截图）。一共抓出 6 个此前看不到的缺陷。

#### 一、混合场景压测（`tools/stress_mixed.py`，58 项全通过）

覆盖编码（UTF-8/BOM/GBK/UTF-16 LE/BE）、换行（LF/CRLF/CR/混合）、
编辑、保存的**组合动作**，每步都读回磁盘字节做断言。

**修复 1（P0，保存会静默失败）：`os.replace` 遇瞬态占用直接失败**

连续"打开→编辑→保存"时会间歇性抛
`PermissionError: [WinError 5] 拒绝访问`，保存直接返回 False。
实测频率不低（6 轮里 1~4 轮失败），且**与文件监视器、自动保存无关**
（两者都关掉仍复现）——属于 Windows 上临时性共享冲突
（杀毒/索引服务在文件刚写入时短暂持有句柄）。

数据没丢（脏块保留、返回 False），但用户按 Ctrl+S **静默失败**不可接受。
修复：`_replace_with_retry()` —— 10 次短退避重试（约 1.1 秒），
只吸收毫秒级瞬态占用；真正的权限问题仍会失败并返回 False。

**修复 2（P0，UTF-16 文件打不开）：二进制判定"见 NUL 即二进制"**

`app/tabs.py` 用 `b'\x00' in chunk` 判二进制并弹
「文件可能包含二进制内容，确定要打开吗？」。
但 **UTF-16/UTF-32 文本必然含 NUL**（ASCII 字符是 `61 00`，换行是 `0A 00`）。
实测：正常的 UTF-16 文本被拦下，用户选「否」后**根本无法打开**。

修复：新增 `is_binary_sample()` 多级判断 —— 有文本 BOM → 文本；
可严格 UTF-8 解码 → 文本；像无 BOM 的 UTF-16（NUL 集中单侧 +
可打印比例高）→ 文本；否则看 NUL 比例（>5% 才判二进制）。

**修复 3（P1，丢 BOM）：编辑 UTF-16/32 文件保存后 BOM 消失**

`BOMS` 把 BOM 映射成裸端序编码（`utf-16-le` 等）以保字节保真，
而这类编码的 `str.encode()` **不补 BOM**。于是"不改直接保存"字节不变
（保存被跳过），一旦编辑过就丢 BOM —— 记事本/Excel/部分编译器
靠 BOM 判断端序，丢 BOM 后可能被当成 ANSI 或二进制。

修复：`encode()` 在 `_has_bom` 且编码为裸端序时把对应 BOM 补回
（`utf-8-sig`/`utf-16` 自带 BOM 的不重复补）。

**修复 4（P1，静默改写行尾风格）：保存把混合换行统一成 LF**

`save_file()` 原用 `[l.rstrip() for l in text.splitlines()]` +
`'\n'.join(...)` —— `splitlines()` 把 CRLF/CR/LF 全切开，再全用 LF 拼回。
实测 `b'a\r\nb\nc\rd\r\n'` 保存后变成 `b'a\nb\nc\nd\n'`：
用户只改一个字，**整个文件的行尾风格被悄悄改写**（git diff 全文件变动，
CRLF 项目被整体污染）。

修复：`_trim_trailing_ws_keep_eol()` 按行尾符切分、只裁行内容尾部空白，
原样保留每行行尾符号；末尾补换行也用文件当前的行尾风格。
**注**：显式切换行尾（状态栏 LF↔CRLF）仍会整篇转换（这是用户明确要求）。

#### 二、打包产物真实桌面验证（新截图流程）

真实桌面截图暴露出 4 个**只有真机才看得见**的界面缺陷
（offscreen 测试全部通过、源码级断言也全部通过）：

**修复 5（P0，面板永远深色）：启动时主题没应用到面板**

启动时编辑器是浅色护眼主题，而所有停靠面板（目录树、全局搜索、
性能监控）却是**纯黑**，左侧目录树更只是一块黑矩形。

根因：`main.load_theme()` 只对 `QApplication` 设 QSS，而各面板在
`_apply_style()` 里**写死深色 QSS 会覆盖 app 级 QSS**；
能把面板 QSS 按主题换算的 `ThemeLoader.notify_widgets()`
**只在用户手动切换主题时调用，启动时从不调用**。

修复：新增 `MainWindow.apply_startup_theme()` 并在 `main.py`
主窗口构造后调用（打开文件之前），应用保存的 `theme_name` +
`notify_widgets(self, theme)`。

**修复 6（P0，状态栏关键信息不可见）：白字白底**

状态栏里"行/列、编码、行尾符"等**都是 QLabel**，而主题 QSS 顶部有
全局 `QWidget { background-color: ... }`（浅色主题下纯白），
QLabel 继承成白底；状态栏文字色又是白色 →
**白色方块 + 白色文字 = 完全看不见**。
实测 1000×700 窗口里状态栏底部只有一排白块 ——
而这些信息恰恰是"切换编码/换行后最需要确认的反馈"。

修复：主题 QSS 的 `QStatusBar QLabel` 增加 `background: transparent;`
并去掉 `QStatusBar::item` 边框。

**附带修复**：
* **目录树空状态**：未打开文件夹时原本是一块纯黑空矩形（看不出"还没打开"），
  现在显示禁用提示「（未打开文件夹）」+ 工具提示；
* **搜索结果树不跟随主题**：`SearchResultTree` 写死深色且**没有
  `refresh_theme` 方法**，而主题刷新只调用拥有该方法的控件 →
  "文件 / 匹配内容"永远黑块。已补 `refresh_theme`。

**附带新增**：`QINGCAO_STARTUP_DIAG=1` 环境变量门控的启动诊断
（写 `startup_diag.txt`：窗口尺寸、状态栏可见性/几何、主题名、
各停靠面板可见性与区域）。用于排查**只在打包产物中出现**的 UI 问题 ——
本次正是靠它确认"状态栏其实存在，只是文字不可见"。

#### 三、验证结果

* `tools/stress_mixed.py`：**58 项全通过**
  （2MB 文件：打开 0.26s，切 EOL+保存 0.11s）
* 全量套件：**779 项，0 失败，0 错误，2 skipped**；ruff 0 告警
* 打包冒烟（cwd=`C:\`）：插件 10/10；UTF-16 与混合换行文件均正常打开
* 真实桌面截图（DPI 感知、`PrintWindow` 抗遮挡）确认：
  面板主题一致、目录树空状态可见、
  状态栏显示「行 7, 列 0 · UTF-8 · CRLF · 插入 · 内存 22.8 MB」


### 技术债 2 → 0：实时协作删除 + 片段市场改造为本地片段库

上一条把最后两个孤立模块转成了"待产品决策"。本轮**决策并执行完毕**，
仓库里不再有「完整实现但零引用」的模块。

#### 实时协作 → **删除**

`ui/collab_dialog.py`(193 行) + `core/collab.py`(206 行) 已删除。

为什么不是接线：该实现是**裸 TCP 监听 `0.0.0.0:52000`**，
**无加密、无认证、无 NAT 穿透**。接上 UI 等于把"局域网内任意人可加入的
无密码共享编辑端口"暴露给用户，且用户看不出风险。而要做对，需要
加密 + 认证 + 可达性（中继/WebRTC）+ 冲突语义 + 真实双端联调环境 ——
本环境无网络，连联调都做不到，任何"已接线"的声明都不可信。

同时清理 `build.py` hiddenimports 里的 `'core.collab'`。

#### 代码片段市场 → **改造为本地片段包库**

原 `MARKET_API` 指向
`api.github.com/repos/qingcao-editor/snippets/contents` ——
**实测 HTTP 404，仓库不存在**。接上 UI 也只会显示 4 条硬编码示例，
"市场"是假的。

改造：

* `core/snippet_market.py` 重写为 `SnippetLibrary`：扫描**本地片段包目录**
  （默认 `<应用根>/data/snippet_packs`，可自选目录，选择被记住）；
* 片段包格式简单可手写/可版本控制：
  `{"snippets": [{"name","language","description","body"}]}` 或裸数组；
  坏 JSON 逐文件容错，不影响其它片段包；
* 入口 **工具 → 📚 代码片段库…**；「导入选中」登记进本地
  `SnippetManager`（纯本地写入、零网络请求、零第三方代码执行风险）；
* 目录为空时展示**内置示例**，让用户知道片段包长什么样；
* 保留 `SnippetMarketClient` 类名别名，避免外部 import 断裂。

**顺手修的同类缺陷**：`core/snippets.py` 存储路径原为相对路径
`"snippets.json"` —— 打包后从快捷方式启动会写到 `C:\snippets.json`，
换目录启动就读不到，用户导入的片段"消失"。改为从 `app_root_dir()`
派生绝对路径（与 `Document._draft_dir` / `crash_stats.CRASH_DIR` /
`snapshot.SNAPSHOT_DIR` 同一模式）。

**额外改进**：同名不同内容的片段导入时自动加 `_2` 后缀
（不静默覆盖已有片段）；无 `body` 的片段被拒绝。

#### 顺手修的一个 flaky 测试

`tests/test_wiring_audit.py::test_default_panels_visible` 原实现
`win.show()` 后只调一次 `processEvents()` 就断言面板可见。offscreen 下
dock 映射依赖事件循环处理布局/显示事件，**机器负载高时单次处理不完**
→ 可见集合为 `[]` → 假失败（实测：单跑通过、整文件跑偶尔失败）。
改为**轮询等待**（最多 2 秒 / 每 20ms 泵一次），既消除 flaky
又保留真实回归防线（面板真不显示则 2 秒后仍失败）。

#### 验证

新增 `tools/verify_snippet_library.py` —— **35 项全通过**：
两种片段包格式、坏文件容错、空目录兜底、目录切换与记忆、导入落库、
同名不覆盖、对话框语言/关键词过滤、菜单接线、
**协作模块已删除且全仓无 `import core.collab` 残留**、
**片段库代码里确实没有网络请求**（按 import/赋值/调用检查，
不按文本出现 —— 文档字符串会解释历史原因）。

全部验证脚本：35 / 39 / 26 / 34 / 78 / 13 / 34 / 16 项，
全量套件 **779 项，0 失败，0 错误，2 skipped**，ruff 0 告警。

#### 债务棘轮

```
17 → 12 → 10 → 8 → 6 → 5 → 2 → 0
```

```
[技术债体量] 孤立模块 0 个 / 0 行；棘轮上限 0
```


### 技术债 8 → 2：接线 6 个孤立模块（批次 A / B / C）+ 剩余 2 个转产品决策

此前调查结论：剩下的 8 个孤立模块**都是可运行的完整代码，不是空壳**
（逐个实例化 + 核心 API 实跑验证）。本轮按风险从低到高接线了 6 个，
并把剩下 2 个（协作 / 片段市场）**从"待接线"转为"待产品立项"** ——
因为它们卡的是产品成立条件，不是工程量。

#### 批次 A：会话快照 + 代码模板（8 → 6）

**会话快照** —— 「文件 → 📸 会话快照…」
把当前所有打开的文件 + 光标位置 + 窗口布局存成快照，一键恢复。

接线时修的 2 个真实缺陷：
1. **`SNAPSHOT_DIR` 是相对路径** `data/snapshots`：打包后从快捷方式启动
   （cwd=`C:\`）会写到 `C:\data\snapshots`，换目录启动又变成另一个位置
   → 用户保存的快照"凭空消失"。改为从 `app_root_dir()` 派生绝对路径
   （与 `Document._draft_dir` / `crash_stats.CRASH_DIR` 同一模式）。
2. **恢复会关闭所有标签但无未保存保护**：`restore_snapshot()` 逐个
   `close_tab()`，每个已修改标签都会弹一次模态确认框；用户中途点"取消"
   会留下"前面已关、后面还在"的半恢复状态。现在先统一提示
   保存全部 / 放弃 / 取消，保存失败则中止恢复。

**代码模板** —— 「文件 → 🧩 从模板新建…」
新增 `ui/template_picker_dialog.py`：模板下拉 + 按模板**动态生成**占位符
输入框 + 实时预览 + 建议文件名；生成的标签标记为未保存新文档。

接线时修的 2 个真实缺陷：
1. **`format_template` 参数冲突**：形参名 `name` 与模板占位符 `{name}` 冲突，
   `format_template("py_class", name="MyClass")` 直接抛
   `TypeError: got multiple values for argument 'name'` ——
   "给类名赋值"这个最基本用法不可用。形参改名 `template_name`（位置调用兼容）。
2. **占位符缺失时原样返回坏代码**：`except KeyError: return code` 会把
   `{docstring}` 原样留在生成的 `.py` 里（语法错误）。现在缺失项填空串。

#### 批次 C：多键快捷键序列（6 → 5）

接线 `core/key_sequence_manager.py`（190 行，此前零引用）。
6 条 VSCode 风格序列（前缀键 `Ctrl+K` 全仓无单键绑定，已 grep 确认）：
`Ctrl+K Ctrl+S/W/C/F/T/D` → 保存全部 / 关闭全部 / 注释 / 格式化 /
会话快照 / 对比文件。

**安全设计（三道闸，缺一不可）**：只处理带 Ctrl/Alt 的键、只在事件目标
是编辑器时处理、有模态窗口时不处理 —— 绝不吞普通输入。

接线时修的 2 个真实缺陷：
1. **★ 事件过滤器导致进程崩溃（0xC0000005）**：第一版
   `app.installEventFilter(self)` 把 MainWindow 当过滤器，QApplication
   持有其 C++ 指针；窗口销毁后 Qt 仍在事件派发时调用它 → **访问违例**。
   实测：`pytest tests/test_p1_features.py` 单跑必崩（6 个测试全通过后
   在 teardown 段错误）；临时注释掉初始化则完整通过 —— 因果已确认。
   修复：改用独立 `_KeySequenceAppFilter`（模块级单例 + **weakref**），
   窗口没了就安全返回 False；`closeEvent` 里在 `_closing` 置位后立即卸载。
2. **焦点判断错误导致序列完全不触发**：第一版用
   `app.activeWindow().focusWidget()` —— headless 或焦点在浮动面板时
   取不到编辑器，序列根本不触发。改用事件过滤器收到的 `obj`。

#### 批次 B：项目概念（5 → 2）—— 三个模块共享同一个「项目根」

接线 `core/workspace.py`(116) + `core/project_config.py`(133) +
`ui/task_panel.py`(189) + `core/project_tasks.py`(131)，新增
`ui/mixins/project_mixin.py` 统一定义「项目根」。

**为什么必须一起做**：三者共享「项目根」这一个概念 ——
没项目根，项目配置不知道读哪个目录、任务不知道在哪跑、工作区只是一堆路径。
分开接必然各造一套定义。

**产品定义（最小可用）**：
* 「项目 → 📁 打开项目…」选目录 → 该目录即项目根；
* 项目根记进 `Workspace` 并持久化到 `data/workspace.json`，
  「🕘 最近项目」可一键切回；
* `.qingcao/settings.json` 覆盖编辑设置（tab 宽度 / 缩进方式 / 换行符）；
* `.qingcao/tasks.json` 定义任务，「任务」面板双击运行、看输出。

接线时修的 1 个真实缺陷：
* **任务文件路径两套约定不一致**：`project_config` 约定配置在
  `.qingcao/` 目录下（`tasks.json`），而 `ProjectTaskManager` 只读根目录的
  `.qingcao-tasks.json` —— 用户按项目配置约定写任务时**列表为空且无提示**。
  现两者都支持（新版优先）。

**诚实标注**：项目设置只让 4 个键真正生效
（`tab_width` / `use_spaces` / `eol` / `encoding`）；
`font_size` / `word_wrap` 等只保存在文件里、当前版本不应用 ——
因为改字号/换行要动主题与编辑器构造参数，属另一个改动面。
设置对话框里已明确写出这一点，避免"看起来能配实际没用"。

#### 批次 D：剩余 2 个转产品决策（2 个 / 453 行）

新增 `docs/product_decision_pending.md`，把事实与选项写清楚：

| 模块 | 卡在哪 |
|---|---|
| `ui/collab_dialog.py` + `core/collab.py` | **裸 TCP 监听 `0.0.0.0:52000`，无加密、无认证、无 NAT 穿透**。当前形态相当于"在局域网开放一个无密码共享编辑端口"。缺安全模型与可达性，且本会话无网络环境**无法双端联调** |
| `ui/snippet_market_dialog.py` + `core/snippet_market.py` | 市场 API 指向 `api.github.com/repos/qingcao-editor/snippets/contents` —— **实测返回 HTTP 404，仓库不存在**。没有内容源，接上 UI 也只会是空列表 |

建议：协作若要做得先加密码 + 明确"仅局域网、无加密"，否则移除 UI；
片段市场建议改为**本地片段库导入**（零运维、零信任风险，
且 `core/snippets.py` 的片段功能本身可用）。

#### 验证

新增 3 个验证脚本，全部通过：

* `tools/verify_snapshot_templates.py` —— **39 项**：
  模板参数冲突回归、缺参无残留、动态占位符、快照 save/list/load/restore
  往返（真实 TabManager，含光标位置恢复）、未保存检测、菜单接线。
* `tools/verify_key_sequences.py` —— **26 项**，重点是**负向**验证：
  普通字母/数字/退格/回车都不被消费、非序列 Ctrl 组合放行、
  焦点在 QLineEdit 时不拦截、有模态窗口时不拦截、超时后不误触发。
* `tools/verify_project.py` —— **34 项**：
  菜单位置、打开项目、设置生效到编辑器（tab 宽度真的变了）、
  Workspace 持久化、任务面板加载两种任务文件、
  **真实执行任务并捕获到 `HELLO_FROM_TASK` 输出**、关闭项目清理。

全量套件：**779 项，0 失败，0 错误，2 skipped**（junit xml 核对）

#### 债务棘轮

```
17 → 12 → 10 → 8 → 6 → 5 → 2
```

剩余 2 个在台账里标为 `owner=product`、`due=待产品立项` ——
棘轮上限已是 2，任何新增孤立模块都会让 CI 直接失败。


### 新增：UI 层真实压力测试，修掉 2 个真实性能/稳定性缺陷

新增 `tools/stress_ui.py`（可独立跑，`--quick` 缩小规模）。上一轮
`tools/stress_test.py` 只压 Document 层（无 GUI），本轮压**真实 UI 层**：
QScintilla 渲染、撤销栈、对话框、标签切换、窗口关闭。

| 场景 | 规模 | 实测 |
|---|---|---|
| 真实 MainWindow + 打开大文件 | 10.0 MB / 147,687 行 | 打开 1.0~6.1s，内容完整 |
| 整列编辑（插入文本） | 40,000 行 | **0.8s**，一次撤销完整回退 |
| 整列编辑（数字序列） | 40,000 行 | **0.9s**，一次撤销完整回退 |
| 大文件对比 | 6 MB × 2（>5MB 阈值） | 0.24s，正确进入摘要模式 |
| 多标签循环切换 | 9 标签 × 3 轮 | 0.06s |
| 关窗清理 | 9 标签 | 未崩溃，0.7~6.7s |

#### ★ 缺陷 1：列编辑是 O(n²)，10 万行需约 22 分钟

实测原始实现（逐行 `SCI_INSERTTEXT`）：

    n=1,000  → 0.115s        n=8,000  → 8.635s

**规模翻倍、耗时约 4 倍** → O(n²)。外推 10 万行 ≈ **22 分钟**。
而"在 10 万行上插入行号"正是列编辑的核心场景（对标 Notepad++），
等于该功能在大文件上不可用。

根因量化（同一文档，161 块 × 64KB）：

* 逐条 `SCI_INSERTTEXT`：**10.85s**（第 1 块 0.0008s，第 161 块 0.13s —— 慢 160 倍）
* 一次性 `setText`：**0.132s**（快 82 倍）

修复：`apply_column_edit` 与 `ColumnInsertCmd` 全部改为
**Python 侧单次重建全文 + 一次 `setText`**，新增
`_byte_to_char_index` / `_apply_inserts_to_text` / `_remove_inserts_from_text`
三个辅助函数处理「UTF-8 字节位置 ↔ Python 字符索引」换算
（插入点落在多字节字符中间时钳到字符起点，绝不产生 U+FFFD）。

`to_dict`/`from_dict` 格式**保持不变**，宏回放继续兼容。

实测结果：

    10 万行列编辑 **3.68s**（此前外推约 22 分钟）
    撤销 2.91s / 重做 2.10s，均完整正确

#### ★ 缺陷 2：大文件分片加载又慢又没提示

原实现 >10MB 时先同步加载 20 块，其余逐块 `QTimer.singleShot(10ms)` 续跑：

* 每块固定等 10ms → 10MB 至少 1.6s **纯空等**，100MB 要 16s+；
* 加载期间界面只有**部分内容**，用户此时"全选列编辑"只作用于已加载部分，
  **且没有任何提示**；
* 关标签/关窗口时若 timer 仍挂着，回调会操作已销毁的 QScintilla 控件
  → **段错误（0xC0000005）**，用户看到"关窗口时闪退"。

修复分两层：

1. `EditorProxy.abort_loading()`：关标签（`close_tab`）与关窗
   （`TabManager.dispose`）时**先**置位中止标志，让挂起的定时器回调立即退出；
2. 加载策略改为两级：
   * ≤ 32MB：**一次性** `read_text()` + 单次 `setText`（实测 10MB 0.13s）；
   * > 32MB：**几何递增批量** append（1→2→4→…→1024 块），
     把 append 次数从 O(n/64KB) 降到 **O(log n)**（100MB 约 15 次）。

实测：10MB 分片加载从 **34.9s → 0.00s**（走一次性路径）。

#### 测试自身的两个假失败（如实记录）

* 第一版压测把"无选区时的列编辑"当成缺陷 —— 实际 `source="caret"`
  只作用于光标行是**正确语义**（Notepad++ 同样如此），压测改用显式 `lines=`；
* 数字序列断言写死 4 位宽，而序列到 40000 是 **5 位数**、
  按最大宽度补零得到 `00001` —— 引擎行为正确，是断言错了。

#### 关于 headless 下的"关窗段错误"

隔离实验（4 个变体，各起独立进程）：

    A 普通修改 + 真实模态框 → 崩溃
    B 普通修改 + 拦截模态框 → 正常
    B2 列编辑  + 拦截模态框 → 正常
    C 无修改（不弹框）      → 正常

即崩溃**与列编辑器无关**，只取决于 `closeEvent` 里是否弹**真实模态框**
（offscreen 平台插件在模态事件循环 + 析构组合下的限制）。真实 GUI 下这是
标准做法、不会崩，**不是产品缺陷**；但 headless 压测必须拦截模态框，
否则只能测到这一个假崩溃。压测脚本已统一拦截并注明原因。

#### 回归测试

新增 `tests/test_column_edit_performance.py`（4 项）：

* 批量插入正确性 + 一次撤销完整回退；
* **多字节安全**：含中文/emoji 的行插入后不得出现 U+FFFD，撤销逐行精确还原；
* **缩放断言**：规模 1000→4000（4 倍），耗时不得超过 8 倍
  （线性约 4 倍、二次方约 16 倍，阈值可稳定区分，避免机器抖动导致假失败）；
* **10 万行预算**：必须在 60s 内完成（可用性底线）。


### 技术债：删除 2 个确认无用的孤立模块（10 → 8）

| 模块 | 行数 | 判定依据 |
|---|---|---|
| `core/benchmark.py` | 160 | 生产代码无用途；对应 UI（`ui/benchmark_dialog.py`）早已删除。性能基准应由 pytest-benchmark 承担 |
| `core/refactor_session.py` | 132 | 配套 UI（`ui/refactor_dialog.py`）早已删除；`docs/audit_concurrency.md` 也标注二者"零调用点" |

同步清理：
* `build.py` 与 `QingCaoEditor.spec` 的 `hiddenimports` 移除这两个名字
  （**不删会被 PyInstaller 静默跳过**，属于"打包配置腐化"）；
* `tests/audit_concurrency_probe.py` 里原本用 `RefactorSession` 现场复现
  "worker 线程直接回调 UI"的探针，改为**静态防回归检查**：
  扫描生产代码中是否同时出现 `threading.Thread(` 与
  `QApplication.processEvents()`（那是"在别的线程为 UI 派发事件"的铁证），
  并断言这两个模块确实已不存在。教训被保留，而不是随代码一起删掉。

`DEBT_CEILING_HISTORY` 新增：`17 → 12 → 10 → **8**`。

### 新增：真实压力测试，并修掉 3 个实测缺陷

新增 `tools/stress_test.py`（可独立跑）：不是"按规格工作吗"，而是
"**在真实世界的极端输入下还能不能用、快不快**"。

| 场景 | 规模 | 实测结果 |
|---|---|---|
| 大文件打开 | 10.0 MB / 163,029 行 | **0.43s**，内容逐字符一致 |
| 超大文件 | 32.4 MB / 1,000,000 行 | **7.99s**，行数正确 |
| 超长单行 | 100,001 字符一行 | **0.02s**，保真 |
| 编码矩阵 | UTF-8 / UTF-8-BOM / GBK / UTF-16LE | 全部保真 |
| 换行矩阵 | LF / CRLF / CR | 行数与内容全部正确 |
| 草稿恢复 | 模拟崩溃 | 未保存内容完整找回 |
| 边界输入 | 空文件/纯换行/无尾换行/二进制 | 均不崩溃 |

**压测发现并修复的 3 个真实缺陷**：

1. **UTF-16/UTF-32 文件的 BOM 被当成正文读入**
   `BOMS` 把 UTF-16 的 BOM 映射到**裸端序编码**（`utf-16-le`），
   而这类编码**不剥离 BOM** —— 解出来第一个字符就是不可见的 `U+FEFF`。
   对比之下 UTF-8 BOM 走 `'utf-8-sig'`（自动剥离），所以这是**不对称**缺陷。

   实测：32 字符的 UTF-16LE 文件被读成 **33** 字符。文本"看起来没坏"，
   但搜索/替换/正则的首字符位置全偏移；若是 JSON/XML 会让解析器报错；
   行级 diff 会把首行判为已修改。
   修复：`decode()` 后剥离**开头**的 BOM（不动正文里合法的同码位字符）。
   `encode()` 用同一裸端序编码不会再补 BOM，因此**保存字节仍保真**（已测）。

2. **纯 CR（老式 Mac）换行文件被算成 1 行**
   `build_line_index()` 只认 `'\n'`，`"line1\rline2\rline3\r"` 的索引是
   `[0]`。文本没丢，但「跳转到行」失效，行级 diff / 列编辑器 / 书签 /
   LSP 行列位置**全部错位**，状态栏行号永远是 1。
   修复：`\r\n` 算一个换行、单独 `\r` 也算换行（不重复断行）。
   只改索引不改文本，保存仍保真（已测）。

3. **CRLF 行的 `get_line_text()` 返回多余的 `'\r'`**
   `get_line_end()` 对非末行返回 `index[line+1] - 1`，对 CRLF 文件这个位置
   落在 `\n` 上，切片排除了 `\n` 却**留下了 `\r`** —— 返回 `'b\r'` 而非 `'b'`。
   后果：按"行文本"工作的逻辑（行尾匹配、列位置）会把 `\r` 当正文。
   修复：仅当末尾确为 `\r` 时剥掉**一个**。

**回归测试**：新增 `tests/test_stress_regressions.py`（14 项），
参数化覆盖 UTF-16 LE/BE、三种换行符、CRLF 不重复计数、混合换行，
并断言"修行索引不得改变文本内容"（防止修复本身引入数据损坏）。


### 技术债继续递减：孤立模块 12 → 10（另发现一个更严重的根因）

本轮又接线 3 个零引用模块，并顺带**挖出一个让两个功能同时失效的根因**。

#### ★ 根因：`MainWindow` 从不把动作注册进 `ActionManager`

实测：全仓对 `act_mgr.register(` 的调用处数为 **0**（插件除外）。
`ActionManager.actions` 因此**一个核心动作都没有**，连带后果：

* **「⌨ 快捷键编辑器」是一张空表** —— 它遍历 `self.act_mgr.actions`，
  而那里什么都没有（用户打开只看到空白）；
* **`core/keymap_profiles.py` 的 4 个方案全部无效** —— overrides 引用的
  `file.save` / `edit.find` / `edit.duplicate_line` … 全部"不存在"，
  `set_shortcut()` **返回 False 且不抛异常**（静默忽略），
  用户以为切了 VSCode 方案、实际一个快捷键都没变；
* `reset_to_defaults()` 因 `defaults` 为空，会对动作执行
  `setShortcut(QKeySequence())` —— 即**把快捷键清空**
  （`app/actions.py:353-358`）。也就是说"套用方案"会先把用户
  原有快捷键全抹掉，再套上一堆不存在的覆盖。

修复：`_add_action()` 现在顺带 `act_mgr.register(name, action,
default_shortcut=shortcut)`。名字策略两级：
`ACTION_NAME_BY_TEXT` 映射表给出方案直接引用的 canonical 名
（必须逐字一致），其余带快捷键的项自动生成 `misc.<hash>`。
实测注册动作数 **0 → 55**，快捷键编辑器不再是空表。

#### 交付 1：快捷键方案预设可用（`core/keymap_profiles.py`，102 行）

* `ui/keymap_editor.py` 顶部新增「方案」下拉 + 「套用」按钮；
* 方案经 `QSettings("QingCao","Editor")` 持久化，
  `main.py` 启动路径（`_load_plugins()` 收尾）调用 `apply_saved_scheme()`
  自动恢复 —— 否则用户重启后快捷键会**悄悄回到默认**；
* 新增 `validate_scheme(name, action_manager=None) -> (ok, problems)`。

**同时修掉 2 个真实缺陷**：

1. **vscode 方案自相矛盾**：`edit.duplicate_line` 与 `view.column_mode`
   都写成 `Shift+Alt+Down`。应用后全仓出现重复快捷键 →
   Qt 报 `ambiguous shortcut overload` → **两个动作都失效**。
   改为 `Ctrl+Shift+Alt+Down`（VSCode 的备用列选绑定）。
   `apply_scheme()` 现在**先校验再动手**，发现重复就拒绝并保持原状 ——
   原实现是"先 `reset_to_defaults()` 再逐条失败"，会把用户快捷键
   清掉一半、留下半坏状态且毫无提示。
2. **方案引用不存在的动作名**：`edit.replace` 在本项目没有对应
   QAction（替换是全局搜索面板内部的输入框，不是 QAction）。
   原来这条会被静默忽略。现按事实移除并在注释说明。

#### 交付 2：性能剖析（`core/profiler.py` 67 行 + `ui/profiler_panel.py` 166 行）

「工具 → ⏱ 性能剖析…」（紧邻「📊 性能监控」，**不绑快捷键**）。

**如实标注局限**（菜单 tooltip + 方法 docstring）：
`cProfile` 只统计 **Python 帧**，Qt 的 C++ 事件循环与 Scintilla 的
绘制/排版耗时**不在报告里**。因此它适合排查*插件的 Python 回调慢 /
搜索正则慢 / 大文件解析慢*，**不适合**测"编辑器滚动卡不卡"——
后者看「📊 性能监控」。不写清楚用户一定会误读报告。

#### 新增验证

* `tools/verify_keymap_profiles.py` —— **39 项全通过**：
  逐方案校验、重复方案被拒且不留半坏状态、真实 ActionManager 上
  overrides 真的落到 QAction、套用后全仓无重复快捷键、
  default 恢复默认而非清空、QSettings 往返、编辑器下拉可用。
* `tools/verify_profiler.py` —— **34 项全通过**：
  状态机边界（重复 start / 未 start 就 stop / 无报告不写文件）、
  pstats 列名与自有函数出现在报告里、GUI 按钮与状态流转、
  菜单项位置/文本/无快捷键/tooltip。

#### 债务棘轮

`DEBT_LEDGER` 与 `KNOWN_DEAD_MODULES` 同步收缩（已接线条目**必须从
台账删除**，由 `test_ledger_matches_baseline` 强制），
`DEBT_CEILING_HISTORY` 新增一条：

    17 → 12 → **10**


### 工程治理（P0-11）：技术债门禁从"可豁免基线"改为"必须递减"

**改造前的问题**：只有 `KNOWN_DEAD_MODULES`（一个 frozenset 基线）+ "不得新增"断言。
它能防**新增**，却对**存量零压力** —— 基线一旦写死，孤立模块可以永远躺在那里。
测试源码里甚至写着「把死模块计数从 17 降到 3 属于指标好看，不是工程收益」，
等于用基线把指标洗白了。

**改造后（三件套）**：

1. `DEBT_LEDGER` —— 每条债务必须有 `owner` / 动作（`wire` 接线 或 `delete` 删除）
   / `due` 期限 / `note` 原因。键集合与基线**强制一一对应**
   （`test_ledger_matches_baseline`），消灭"有基线无台账"的幽灵条目；
2. `DEBT_CEILING_HISTORY` —— 只增不减的**棘轮**历史。当前孤立模块数
   **不得超过历史最低值**（`test_dead_module_count_is_decreasing`）。
   想把上限调高，必须在历史里追加一条并写明原因 ——
   让"放宽门槛"成为**显式的、要评审的动作**，而不是悄悄改个数字；
3. `test_debt_volume_report` —— 把债务体量（模块数 + 总行数 + 逐条处置计划）
   打进 CI 输出，避免"债务只存在于某个人的记忆里"。

**棘轮自检（负向测试）**：人为把上限压到 5 后重跑，
`test_dead_module_count_is_decreasing` **确实失败**并报
「孤立模块数**回升**了：当前 12 个 > 棘轮上限 5 个」—— 证明门禁不是摆设。

**当前基线**：孤立模块 **17 → 12**（本轮接线 5 个：
`core/formatter.py`、`core/exporter.py`、`ui/lsp_panel.py`、
`ui/problems_panel.py`、`ui/undo_history_panel.py`），共 2,094 行。

### 入口重排（P1-7）：把差异化能力提升为一级可见

**新菜单「⭐ 特色功能」**（位于「编辑」与「视图」之间）：

* 🤖 AI 助手（ai_assistant）→ 子菜单列出该插件**真实注册**的 12 个命令
  （解释代码 / 修复 Bug / 性能优化 / 重构 / Code Review / 生成 Docstring /
  生成单元测试 / 代码摘要 / 添加注释 / 快速解释 / 缓存统计 / 清空缓存）；
* 🔀 Git（git_deep）→ 子菜单列出 Git 状态等命令；
* ▶ 运行当前文件（复用工具菜单的 F5 动作）、⚙ 切换断点；
* 🧠 LSP 状态 / 安装向导、📊 问题（LSP 诊断）。

**与命令面板同源**：直接从 `act_mgr.actions` 里按 `plugin.<插件>.<命令>`
前缀取（`PluginAPI.register_command` 的注册键），因此不会出现
"菜单里有、命令面板里没有"的偏差。实测菜单 13 项 == 面板 13 项。

**诚实占位**：插件尚未加载时显示**禁用**的「（该插件未注册命令，或未启用）」
并提示去「工具 → 插件管理」，而不是放一个点了没反应的菜单项。

### 修复（P1-7 过程中实测发现的三个新缺陷）

1. **★ 首次运行时 13 个插件命令全部注册失败（隐蔽且 100% 复现）**

   `app/actions.py::ActionManager` 定义了 `__len__`（返回已注册动作数），
   因此**空的 ActionManager 是 falsy**。而插件正是在**激活时**注册命令 ——
   那一刻 `act_mgr` 里几乎还是空的，于是原来的

       if hasattr(self.win, 'act_mgr') and self.win.act_mgr:

   直接短路，命令一个都没注册。后果：

   * 命令面板的「插件」分类**永远是空的**；
   * 「⭐ 特色功能」只能显示"未注册命令"。

   第二次启动（动作已被上一次填过）反而正常 —— 这类"只在首次运行出现"
   的缺陷靠人工点测极难发现。改为 `mgr is not None` 判定。
   已加 `tests/test_plugin_command_registration.py` 锁住根因与场景。

2. **`QMenuBar.insertMenu()` 返回的是 QAction，不是 QMenu**

   原实现把返回值赋给 `self.feature_menu`，随后 `addSeparator()` 抛
   `AttributeError: 'QAction' object has no attribute 'addSeparator'`，
   **整个 MainWindow 构造失败**（实测崩溃）。改为先建 QMenu 再 insert。

3. **`_add_action(slot=None)` 会 `connect(None)` 抛 TypeError**

   一个禁用占位项就能让整个主窗口构造失败
   （`TypeError: argument 1 has unexpected type 'NoneType'`）。
   现在 slot 为 None 时产出**禁用**动作。

**同族风险一并修掉**：

* **F5 被绑成两个动作**：特色功能菜单里新建了带 F5 的 QAction，
  导致 `tests/test_shortcuts.py` 两条断言失败、Qt 报 ambiguous shortcut
  → F5 彻底失效。改为**复用**工具菜单里已存在的那个 QAction
  （同一动作可出现在多个菜单）。
* **按文本查找动作不能用 `menuBar().findChildren(QAction)`**：
  菜单里 QAction 的 parent 是**主窗口**而非 QMenuBar，
  该调用**一个都找不到**（静默返回 None，于是又新建一个动作）。
  改为遍历 QMenu 树，并**优先返回带快捷键的那个**（同名动作可能有两个）。

### 新增（验证脚本）

* `tools/verify_feature_menu.py` —— P1-7 聚合入口验证（13 项，全部通过）：
  覆盖菜单位置、未加载时的诚实占位、加载后自动刷新、
  与命令面板同源、点击链路有真实接收者、F5 唯一且复用同一对象。

* `tests/test_plugin_command_registration.py` —— 6 项回归测试，
  锁住"空 ActionManager 为假"这一根因、"空 manager 上注册命令必须成功"、
  以及 `insertMenu` / `slot=None` 两个 Qt 陷阱。


### 新增（两大核心功能：列编辑器 · 对比合并）

#### 📊 列编辑器（对标 Notepad++ Edit → Column Editor…）

`ui/column_editor_dialog.py`（新建，1400+ 行）+ 编辑器右键菜单 +
「编辑 → 📊 列编辑器…」（`Alt+Shift+I`）。

* **插入文本**：在矩形选区 / 多光标 / 选区覆盖的每一行、指定列位置插入同一段文本；
* **插入数字**：起始值 / 步长（含负步长）/ 进制（Dec/Hex/Oct/Bin）/
  **前导零填充**（按最大宽度）/ **前导空格对齐** / 最小位数 / 进制前缀；
* **一次编辑 = 一条撤销命令**（关键）：编辑前把矩形/多光标收成单一流式选区，
  编辑期间 `UndoManager.disable()`，结束后用一条 `ColumnInsertCmd` 入栈 ——
  按一次 Ctrl+Z 即完整回退，不会"只退一行"；
* **刻意不用 `GroupCmd`**：它的 `can_merge` 对任何 GroupCmd 都返回 True 且无时间窗，
  连续两次列编辑会被静默合并（一次 Ctrl+Z 回退两次编辑）；
* 位置按 **UTF-8 字节**（与 `_lsp_pos_to_scintilla` 同约定），中文/emoji 不错位；
* 命令注册进 `CommandFactory`，**宏回放**可识别该类型。

#### 🔀 对比合并（diff / merge）

`ui/file_merge_dialog.py`（新建，1900+ 行）复用 `core/file_merge.py` 的算法
（**未重写算法**），入口「工具 → 🔀 对比文件…」。

* **并排双栏 diff**：行级对齐 + 三色高亮（新增/删除/修改）、只显示差异/显示全部、
  同步滚动、字符级高亮开关、底部「新增 N / 删除 M / 修改 K」、纯文本报告导出；
* **三方合并**：`ThreeWayMergeDialog` 展示 `<<<<<<< LOCAL / ======= / >>>>>>> REMOTE`
  冲突标记，提供 保留本地 / 采用远程 / 手动编辑，含"下一个冲突"导航；
* **大文件三级保护**：≥5MB 不做行级对齐也不渲染正文；`from_files`/`pick_files`
  对超大文件**连读取都跳过**（只 `os.stat`）；差异行 >2000 自动关闭字符级高亮。

**算法修复（实测复现）**：原 `compute_diff` 在 `replace` 块里按**下标配对**并在
第一对不相似时 `break`，导致两类错误 —— ①该对之后的真实"修改"行被算成
1 删 + 1 增；②两侧行数不等时后续配对整体错位。改为**打分式最优配对**
（DP 最大权匹配），实测修复"修改/新增/删除计数"与"对齐序列/左右行号"等断言。

### 新增（P0 接线：把已实现但零引用的能力交付出去）

| 能力 | 此前状态 | 现在入口 |
|---|---|---|
| **本地格式化**（Black/autopep8/clang-format） | `core/formatter.py` **零引用** | 工具 → 🪄 格式化文档 |
| **LSP 面板 + 安装向导** | `ui/lsp_panel.py`（548 行）零实例化 | 视图 → 面板 → LSP 状态 |
| **撤销历史面板** | `ui/undo_history_panel.py`（229 行）零实例化 | 视图 → 面板 → 撤销历史 |
| **崩溃统计** | `core/crash_stats.py`（240 行）零引用 | 帮助 → 📉 崩溃统计 |
| **导出 PDF/HTML/Markdown** | `core/exporter.py` 零引用，而 `requirements.txt` 已承诺 | 文件 → 📤 导出 |
| **书签导航** | `next/prev/clear` 引擎已实现且会话已持久化，**无菜单无快捷键** | 编辑 → 🔖 书签（Ctrl+F2 / F2 / Shift+F2） |

* **格式化写回是一次原子撤销**：实测 `proxy.set_text()` 会触发**多条**撤销命令，
  按一次 Ctrl+Z 只回退一半（实测把内容清空，比不格式化更糟）。改用 `CompoundCmd`
  包成单条命令，undo/redo 均正确。
* **面板属性名必须等于 `_LAZY_PANELS` 里的名字**（`_ensure_panel` 用
  `getattr(self, name)`）：`lsp` / `undo_history`，否则懒加载判定为失败。

### 修复（三个已实测确认的缺陷）

1. **宏录制录到 0 条**
   `ui/main_window.py` 构造 `MacroRecorder()` 时**未传 `undo_manager`** →
   `_register_hook()` 在 `not self.undo_manager` 时直接 return →
   `record_hook` 永不设置 → 实测录制后 `commands == 0`，回放必提示"没有可回放的宏"。
   修复：新增 `undo_manager_provider` 回调，`start()` 时动态解析**当前标签**的
   `undo_manager`（proxy 是每标签一个，不能只绑一次），`stop()` 精确解绑当初挂钩的
   那个；录制中切标签会自动重绑；错误经 `error_occurred` **可见**（此前零接收者）。

2. **草稿只写不读 —— 且修复后发现读取端本身也是坏的**
   `app/session.py::check_and_recover_drafts()` 此前**零调用点**；
   接线到 `main.py` 后又实测发现 `find_recoverable_drafts()` 调的是
   `DocumentModel.list_drafts()`，而该方法**定义在 `Document` 上**
   （`DocumentModel` 没有）→ `AttributeError` 被自身 `except` 吞掉并 `return []`
   → **草稿恢复恒为空**，等于没接。现已修正为 `Document.list_drafts()`，
   并用真实 SessionManager + 真实标签页实测恢复出草稿正文。
   另补 `_render_recovered_drafts()`：恢复出的标签此前是**空白**的
   （`EditorWidget(provider=MemoryProvider(...))` 不会把正文灌进 QScintilla）。

3. **全局替换静默丢选项**
   `_on_global_replace` 用 `SearchOptions(pattern=pattern)` 重建选项，无视面板勾选 →
   正则搜索后"全部替换"按字面量、忽略大小写替换，且**重新搜索得到的匹配集与用户
   看到的结果不是同一批**，替换位置随之错乱。修复：`replace_requested` 信号携带
   `SearchOptions`，搜索与替换共用同一对象（`build_options()` 成为唯一构造点）。

### 修复（编码语义混合 → 静默数据损坏）

**实测复现**：UTF-8 文件「中文内容测试」→ 用户切到 GBK"看一眼"（界面显示乱码）
→ 顺手 Ctrl+S → **磁盘被改写**，原字节永久丢失（读回变成乱码）。

不保存则无损 —— 危险恰恰藏在"看一眼 + 保存"这个最自然的动作里。根因是
`change_encoding` 把 Notepad++ 明确区分的两种语义（"改解释" vs "转码"）混成一个动作。

修复：
* `Document.change_encoding(mode=..., require_lossless=...)` 显式区分两种语义；
* 新增 `Document.would_lose_text()`：判断新编码能否无损解码现有字节，含**例外**
  —— 若当前显示已是乱码/为空（说明编码本就判错），本次切换属于**修正**、不拦截；
* 状态栏切换走 **fail-closed**：有损时弹确认框并明确告知"保存会改写文件"，
  取消则不切换。实测四种场景全部正确。

### 修复（其他实测确认的问题）

* **双重 `didSave`**：`core/editor.py` 里 `_notify_lsp_saved(filepath)`
  **连着写了两遍**（连注释一起复制），每次 Ctrl+S 向语言服务器发两次 didSave。
* **字符统计口径**：`app/tabs.py`、`ui/perf_monitor.py` 把 Scintilla 的**字节数**
  当"字符数"（中文差约 3 倍）。现区分 `char_count` 与 `byte_count`。
* **列编辑后修改标记**：除 `document.mark_modified()` 外还需置 QScintilla 侧标记，
  否则标签页不显示 `*`、关窗不提示保存。实测坑：`QScintilla.setModified(True)`
  在本项目配置下**不生效**（`EditorProxy` 执行过 `SCI_SETUNDOCOLLECTION, 0`），
  需同时用 `SCI_SETMODIFY`。
* **十六进制前缀大小写**：`_radix_prefix` 把 `uppercase` 也作用到前缀字母 x 上，
  生成 `0X01`；标准写法是 `0x01`（数字才受大小写影响）。
* **测试脚本输出编码**：`tools/verify_column_editor.py` 打印含 emoji 的 QAction
  文本（`📊`）时，在 Windows 中文环境（stdout 默认 GBK）抛 `UnicodeEncodeError`
  导致整个验证在最后一步崩掉。已强制 UTF-8。

### 新增（分析工具，可复现）

* `tools/audit_reachability.py` —— 可达性普查：**123 个生产模块中 80 可达、
  30 真孤立（约 9,200 行完整实现零引用）**；
* `tools/verify_user_journeys.py` —— 端到端功能旅程实跑（**16/16 通过**）；
* `tools/verify_diff_semantics.py` —— diff 引擎真实代码场景验证（**30/30 通过**）；
* `tools/verify_file_merge.py` / `tools/verify_column_editor.py` /
  `tools/verify_p0_defects.py` —— 特性独立验证（82 / 78 / 17 项，全部通过）；
* `docs/cross_analysis_v2.1.0.md` —— 全量交叉分析报告。


### 新增

- **Ollama 本地模型管理（完整）**
  编辑器原本已支持 `ollama` provider（OpenAI 兼容端点），但模型下拉框用的是
  **硬编码列表**，用户本地装了哪些模型界面上看不到，只能手工输入名称。

  本次补齐：

  * `core/ollama_client.py` —— Ollama **原生 REST** 客户端（纯标准库，
    不新增依赖），封装 `/api/tags`、`/api/ps`、`/api/pull`（流式）、
    `/api/delete`、`/api/show`、`/api/version`。所有方法**不抛异常**，
    统一返回 `(ok, msg)`，便于 UI 直接展示。
  * **独立停靠面板**「Ollama 管理」（工具 → AI 助手 → 🦙 Ollama 管理面板）：
    服务状态与版本、模型列表（名称/大小/参数量/量化/修改时间）、
    内存中已加载模型、拉取模型（实时进度）、删除模型、连通性测试、
    双击复制模型名、一键写入 AI 配置。
  * **配置对话框动态拉取**：选中 Ollama 时从本机 `/api/tags` 读取真实
    模型填入下拉框，并显示探测结果提示（未启动 / 无模型 / 已读取 N 个）。
  * **状态栏常驻指示**：每 60 秒刷新一行 `🦙 Ollama: 运行中 vX · N 个模型`。

  **实测**（本机 Ollama v0.34.4）：
  ```
  状态   : 运行中 v0.34.4
  模型   : llama3.2:latest  [1.9 GB]  3.2B/Q4_K_M  2026-09-21
  摘要   : Ollama: 运行中 v0.34.4 · 1 个模型
  下拉框 : ['llama3.2:latest']   ← 由 /api/tags 动态获取
  ```

### 修复（插件全部不加载 · 根因是相对路径依赖工作目录）

**这是"每次打包都丢菜单"的真正根因。**

**现象**：用户的自检报告显示

    plugin_manager: <PluginManager total=0 active=0>
    插件目录存在: True          <-- 目录明明存在，却一个插件都发现不到

**根因**：插件目录写成**相对路径**

    PluginManager(main_window=self, plugin_dir="plugins")   # 相对！
    self.plugin_dir = os.path.abspath(plugin_dir)           # 相对当前工作目录

相对路径的含义取决于**当前工作目录**：

    cwd = exe 所在目录   -> total=10 active=10   （我此前一直这样测，所以复现不到）
    cwd = C:\           -> total=0  active=0    （用户通过快捷方式/其他目录启动）

为什么极难排查：报告里"插件目录存在: True"是用**绝对路径**判断的，
与真正用于发现的相对路径不是同一个东西 —— 两个判断互相矛盾，
看起来像"目录在、插件却找不到"。

**修复**：新增插件目录的绝对解析，并在所有相关入口使用：

    infrastructure/plugin_loader.py:
        app_root_dir()        -> 冻结时为 _internal，源码时为仓库根
        resolve_plugin_dir()  -> 兼容相对/绝对；依次尝试
                                 应用根目录 / exe 目录 / 绝对化 / cwd，
                                 取第一个真实存在的

    plugin_loader.PluginLoader.__init__ / discover  -> resolve_plugin_dir
    app/plugin_manager.PluginManager.__init__       -> resolve_plugin_dir
    ui/main_window.py                               -> 传入绝对路径
    ui/plugins_panel.py                             -> 兜底绝对解析

**顺带修正同类的"工作目录依赖"隐患**（同一根因，避免用户踩到别的）：

    core/crash_stats.py        CRASH_DIR         -> 应用根目录下绝对路径
    app/session.py             AUTOSAVE_DIR      -> 同上（自动备份）
    app/plugins.py             插件数据目录       -> 同上
    app/config_manager.py      插件列表扫描       -> 用绝对插件目录
    infrastructure/icon_manager.py   DEFAULT_ICON_DIR
    infrastructure/sound_manager.py  DEFAULT_SOUND_DIR

**实测（同一 exe，两种工作目录）**

    修复前: cwd=exe 目录 -> 10/10 ；cwd=C:\ -> 0/0     （随工作目录变化）
    修复后: cwd=exe 目录 -> 10/10 ；cwd=C:\ -> 10/10   （不再依赖工作目录）

### 修复（自检报告采样过早会误报"插件全丢"）

报告原先用**固定 6 秒**写出。冷启动受磁盘/杀毒软件扫描（首次解压
400+ 文件时尤甚）影响可达十几秒，若报告在 `_load_plugins` 完成前写出，
就会记录成 `total=0` —— 看起来"插件全丢了"，实际只是**采样太早**。

现改为**轮询等待插件加载完成**（最多 60 秒），并在报告中写明
`采样耗时: N 秒（轮询 M 次后写出）`，便于区分"加载失败"与"采样过早"。

（写这个修复时我漏了 `import time`，ruff 的 F821 立刻抓到并修正。）

### 新增（回归测试）

`tests/test_path_independence.py`（10 个用例）锁死**工作目录无关性**：
  * `resolve_plugin_dir` 在 C:\、D:\、用户主目录、仓库根下结果一致且存在
  * `app_root_dir()` 等于仓库根目录
  * 崩溃/自动备份/图标/音效目录均为绝对路径且位于应用根目录下
  * `PluginManager.plugin_dir` 为绝对路径
  * 任意工作目录下都能列出插件

全量套件 430 -> **440 passed**。

### 修复（「另存为」丢失编辑 —— P0-B，已复现的数据丢失）

**现象（实测复现）**

    打开文件      : 'OLD LINE 1\nOLD LINE 2\n'
    用户编辑后    : 'NEW CONTENT A\nNEW CONTENT B\nNEW SHOULD BE SAVED'
    另存为返回    : True                ← 报告成功
    磁盘实际内容  : 'OLD LINE 1\nOLD LINE 2\n'   ← 旧内容！
                    ❌ 编辑全部丢失，且没有任何提示

**根因**：`ui/mixins/file_ops_mixin.py` 的 `_save_file_as` 调用
`proxy.document.save(path)`，**绕过**唯一的同步点
`EditorProxy._sync_content_to_provider()`。而 `Document` 只持有 provider、
**拿不到 QScintilla 里的当前文本** —— 于是写下的是"打开文件时"的内容。
更糟的是 `Document.save` 还返回 True、清 modified、删草稿，
用户看到"成功"，编辑丢失且连草稿恢复都救不回来。

**修复**：`_save_file_as` 改走 `proxy.save_file(path)`（同步内容 → 保存
→ 清脏标记 → 通知 LSP → 删草稿），并检查返回值、失败时明确报错。
经全仓核查，生产代码中 `document.save()` 仅剩
`EditorProxy.save_file()` 内部一处正确调用。

**防线**：`tests/test_wiring_audit.py` 新增
`test_no_ui_bypasses_content_sync` —— 禁止 UI/插件层直接调
`document.save()`，防止将来再图省事绕过同步。

### 修复（另存为后 LSP 指向旧文档 · INV-L1/L2）

另存为更新了 `document.filepath`，但 `EditorProxy._lsp_uri` 仍是旧 URI，
而 `_notify_lsp_saved()` / `request_definition()` 都用
`self._lsp_uri or ...` 取值 —— 一旦为真值就永远用旧的。后果：
didSave/didChange 发给旧文档、服务器对旧路径的诊断画到当前编辑器、
补全与跳转用新路径服务器不认识。

**修复**：`Document` 新增 `filepath_changed` 信号统一广播路径变化，
`EditorProxy` 据此注销旧文档、以新 URI 重新 did_open。
**从机制上修**（而不是在某个入口手动补）——这样任何入口另存为都正确。

**同时修复跨标签污染**：`_on_lsp_diagnostics` 原先**不比较 uri 与
self._lsp_uri**，任何来源的诊断都会画到当前编辑器（标签 A 的诊断出现在
标签 B）。现只接受属于本文档的诊断。

### 修复（行尾符切换不生效 · INV-E1）

`Document.set_eol` 只改 `meta.eol` + 标脏，其 docstring 声称"实际转换在
保存时进行"，但**保存路径从不做转换**；`Document.convert_eol()` 在生产
代码中零调用。于是状态栏把 LF 切成 CRLF、保存后磁盘仍是 LF。

**修复**：`set_eol` 同步到 provider 并标记 `_eol_explicit`；
`ContentProvider._apply_eol()` 在保存时按目标行尾转换
（文本层转换，对 UTF-16 等编码也正确）。

**注意实现边界**：只在用户**显式切换过**时转换。原因：`_eol` 在打开时
由探测得出，而探测不可靠（整篇无换行的文件会因 `0 >= 0` 默认取 CRLF），
若无条件转换会把**原文根本没有的换行**改写掉（实测曾让 `'short\n'`
变成 `'short\r\n'`，破坏"保存不改动内容"的不变量）。

### 修复（切换编码后编辑器不刷新 · INV-C）

`Document.change_encoding` 重载了 provider（文本已按新编码正确解码），
但没有任何代码把新文本写回编辑器 —— 用户继续看到旧编码解出的**乱码**，
而 provider 已是正确文本。两者不一致时，查找/替换/另存为/全局替换
都会看到与屏幕不同的内容。

**修复**：`reloaded` 信号（原先零 connect）接到
`EditorProxy._on_document_reloaded`，刷新文本并保留光标、清空撤销栈
（重载等于整体替换，旧撤销历史不再适用）、同步脏标记为干净。

### 新增（问题面板接线 · 补上缺失的**生产者**）

`ui/problems_panel.py` 实现了完整 UI 并从 `ProblemManager` 读问题，但
`set_file_problems()` **全仓零调用** —— 面板挂上去也永远空白。
**缺口在生产端，不在消费端。**

修复：
  * 生产者：`EditorProxy._publish_problems()` 把 LSP 诊断转成 `Problem`
    写入管理器（在 `_on_lsp_diagnostics` 尾部调用），severity 按 LSP 规范
    映射 1/2/3/4 → error/warning/info/hint；
  * 消费者：问题面板接入视图菜单（`视图 → 面板 → 问题`），
    并在 `_LAZY_PANELS` 登记（可被会话恢复）。

实测：2 条诊断 → 面板可见 `[warning] probe.py:1:2` 与 `[error]`，
按严重度统计正确；外来 URI 的诊断被忽略。

### 新增（LSP 其余 7 个能力接线）

`LspClient` 实现了 10 个请求，但除 `request_definition` 外，其余请求的
**结果信号全仓零 connect** —— 请求发得出去、结果永远回不来。

现全部接通并加上用户入口（工具 → 🧠 LSP（智能））：

| 功能 | 快捷键 | 结果展示 |
|---|---|---|
| 悬停信息 | Ctrl+Alt+H | 信息弹窗 |
| 查找引用 | Shift+F12 | 位置列表 |
| 重命名符号 | Ctrl+Alt+N | 报告影响位置数 |
| 文档符号 | Ctrl+Alt+K | 符号列表（含层级） |
| 代码操作 | Ctrl+Alt+O | 选单 |
| 格式化文档 | Ctrl+Alt+L | 就地应用编辑 |
| 签名帮助 | Ctrl+Shift+Space | 状态栏 |

**如实说明**：重命名只报告影响范围、代码操作只报告选择结果 ——
跨文件应用 `WorkspaceEdit` 涉及多文件原子写入，未在本轮范围；
状态栏文案明确写了"应用尚未实现"，不假装完成。

新增快捷键均已通过 `tests/test_shortcuts.py` 的**无重复扫描**
（首次提交时 Ctrl+Alt+R 与"符号跳转"冲突，被该测试当场抓住）。

新增防线：`test_lsp_requests_have_result_handlers` 要求每个请求方法都有
对应的结果信号 connect。

### 变更（国际化决策：删除语言选项，如实标注"仅中文"）

**决策依据（已核实）**：国际化在本项目中**完全无效** ——

1. UI 里没有任何一条字符串走 `tr()`/`_()`（`core/i18n.py` 的
   `I18nManager.tr()` 全仓零调用），gettext 无处施展；
2. Qt 的 `.qm` 路径拼错：`locale/<lang>/qingcao.qm` 不存在，实际文件是
   `locale/<lang>/LC_MESSAGES/*.mo`，`QTranslator` 分支永远不会执行；
3. 翻译目录只有 49 条菜单/按钮词，覆盖不到 0.1% 的 UI。

于是"语言"是一个**假开关**：切到 English 后界面依然是全中文。

**变更**：移除此选项，改为如实告知用户当前仅支持简体中文。
（若将来要真正国际化，需先让 UI 全面使用 tr() 并修好 .qm/.mo 加载路径，
那是独立的大工程。）
  * `ui/preferences_panel.py`：语言下拉框 → 说明文字
  * `ui/first_run_wizard.py`：语言单选页 → 说明页（`get_language()` 保留
    以兼容调用方，恒返回 zh_CN）
  * `tests/test_p1_features.py` 的向导用例同步更新（仍断言无乱码标签）

### 新增（Python 调试器：从"pdb 启动器"变成编辑器内真调试器 · D3）

**改造前**：`plugins/python_debugger` 唯一动作是
`subprocess.Popen([python, "-m", "pdb", file], creationflags=CREATE_NEW_CONSOLE)`
—— 在独立黑框里起一个 pdb 进程，宿主**完全无法控制**（无断点下发、无单步、
无变量查看）。而 `plugin.json` 却宣称"基于 pdb 的 Python 调试器"，属误导。
宿主侧断点设施 `MARKER_BREAKPOINT` 只有 `markerDefine`（画图例），
**全仓无 `markerAdd/markerDelete`** → 点行号边距毫无反应。

**现在**：基于 **Python 标准库 `bdb` + stdio JSON 协议**的完整调试器，
**零第三方依赖**（刻意不用 `debugpy`，避免"未安装就用不了"）：

| 能力 | 实现 |
|---|---|
| 启动调试 / 终止 | `session.py` 的 `DebugSession`（管道 + 驱动子进程） |
| 断点 | 宿主装订线单击 / **F9** / 右键菜单 → `markerAdd/markerDelete` |
| 单步 | 跳过(next) / 进入(step) / 跳出(out) / 继续 |
| 变量与调用栈 | `frame_locals` / `stack_frames`，面板变量树 + 栈帧列表 |
| 停在断点 | 编辑器内**高亮当前执行行**（`MARKER_DEBUG_LINE`） |
| 失败可见 | 后端探测 + 非 Python 文件 / 未保存 / 无标签 均有明确提示 |

**关键实现取舍**：刻意不使用 `bdb` 的 `stopframe/stoplineno/returnframe`
这套 stopinfo，而是自己实现 `dispatch_call/line/return` + 步进模式判定。
原因：bdb 默认 `dispatch_call` 在"该帧不需停"时返回 None，等于**关掉该帧的
局部跟踪** → 函数体内的断点会永不命中。自维护策略语义明确且可单测。

**孤儿进程防护（三层）**：`stop()` 用 quit→wait→terminate→wait→kill→wait
强制序列并断言 kill 被调用；驱动脚本在 stdin 读到 EOF（宿主崩溃/被强杀）时
立即 `os._exit(0)`；插件 `on_deactivate()` + 模块级 `atexit` 兜底。
（Windows 上父进程退出**不会**自动杀子进程，这三层都是必需的。）

**顺带修复（两个真实实现缺陷，由端到端测试暴露）**

1. **断点整体失效**：`set_breaks` 写成 `if result is not None: 记录`，
   但 `bdb.Bdb.set_break()` **成功返回 None、失败返回错误字符串** ——
   于是**只记录失败的、丢弃成功的**，真实运行里断点全部不生效。
   已改为 `if result is None`（成功），失败行单独报给宿主。
2. **越界行号假装成功**：QScintilla 的 `markerAdd()` 对越界行是
   **静默失败**（不报错也不抛异常），而 `_toggle_breakpoint_at_line`
   无条件返回 True → 调用方以为断点设上了。现改为越界返回 False。

**附带**：新增 margin 1 断点装订线（18px）。此前 `markerDefine` 定义了
红圆但**没有任何边距显示它**，即使 markerAdd 也看不见。

### 修复（所有已知接线缺陷清零：4 个 xfail → 0）

`tests/test_wiring_audit.py` 从"4 个 xfail"变为**全部硬断言**：

| 原 xfail | 现状 |
|---|---|
| `stop_autosave` 零调用点 | 已接线（closeEvent 与 start_autosave 配对） |
| `MARKER_BREAKPOINT` 无读写 | 已接线（D3） |
| `external_change_detected` 零 connect | 已接线（`EditorProxy._connect_signals` 转发） |
| 草稿目录两处不一致 | 已统一为**单一事实来源** |

**草稿目录的修法值得记录**：不是把某一处改成另一处的字面量（那样下次改动
仍会漂移），而是让 `main.py` 的 `ensure_directories()` 直接复用写入端定义
`Document._draft_dir()`。对应测试也改为断言"两处解析到同一真实路径 +
main.py 确实在复用"，而非匹配某种字面写法。

**重要方法论**：`xfail(strict=False)` 在功能接线成功后会变成 **XPASS 而不是
失败** —— 留着会让防线**静默失效**（以后再改坏也不会红）。本次逐条复核，
把**每一个已接线的 xfail 都摘掉**恢复为硬断言。

### 变更（死模块清理 · D2）

删除 **19 个**已确认零引用的死模块（全仓 grep 核实，排除 docs/ 提及、
build.py 的打包字符串清单、_archive/ 与 dist/ 产物）：

    ui/macro_editor.py(2280行)  ui/benchmark_dialog.py  ui/file_merge_dialog.py
    ui/git_panel.py  ui/code_metrics_panel.py  ui/usage_stats_panel.py
    ui/snippet_editor.py  ui/refactor_dialog.py  ui/enhanced_scrollbar.py
    ui/breadcrumb.py  ui/debug_panel.py  ui/log_viewer.py  ui/shortcut_overlay.py
    ui/file_association.py  ui/diff_view.py  ui/markdown_preview.py
    ui/terminal_panel.py  plugins/git_deep/commit_panel.py  plugins/git_deep/diff_view.py

关键核实：删除后**没有任何 core/ 模块退化为新死模块**（被删 UI 依赖的后端
macro / git_client / file_merge / code_metrics / usage_stats / snippets
全部另有活引用）。`test_wiring_audit.py` 的死模块基线从 37 条缩到 **17 条**。

**明确保留的 17 条**（登记在基线里，只允许缩小）：其中 5 组是
**已完成但未接线的功能引擎**（协同编辑 / 快照 / 项目任务 / 片段市场 /
性能剖析）。它们零引用，但删除是**不可逆的产品决策**，超出"清理死代码"
的授权范围 —— 正确处置是**接线**而非删除，故明确保留为已知技术债。

### 新增/修复（首选项"假开关"：改了没反应的开关 · P7）

**接线（8 个键，此前只写不读）**

| 键 | 现在的行为 |
|---|---|
| `splash_screen` | `main.py` 创建启动画面前检查，关掉就不再显示 |
| `splash_duration` | `QSplashScreen` 构造签名无时长参数，实现为**最小可见时长** + 补上缺失的 UI 项 |
| `search_threads` / `use_hyperscan` / `search_timeout` | 新增 `SearchOptions.from_preferences()`，`SearchEngine` 默认路径与 `build_search_options` 均走它；越界值夹到 1..16 |
| `log_level` / `log_max_size` | `setup_logging()` 按偏好设置 logger/文件/控制台级别与轮转阈值；`debug_mode` 最高优先级覆盖 |
| `language_auto_detect` | 关闭后不再按系统 locale 猜测语言 |

**删除（15 个半成品：零读取、价值低）**

`caret_blink_rate`、`smooth_scroll`、`virtual_scroll`、`icon_theme`、
`max_loaded_blocks`、`cache_lexer_results`、`startup_delay_load`、
`delay_plugin_load`、`delay_plugin_ms`、`config_sync`、`sync_provider`、
`gist_token`、`encoding_confidence`、`follow_symlinks`、`restore_undo_history`

—— `DEFAULTS`、属性访问器、面板 UI 三处**同时清理**，并清掉
`reset_appearance`/`reset_performance` 里引用 `DEFAULTS[key]` 的键列表
（漏删会 KeyError）。每删一个都记录在此（用户可见的行为变更）。

**测试**：新增 `tests/test_preferences_wiring.py`（18 个用例）——
删除键的三处清理断言、接线键的静态证据、`SearchOptions` 运行时行为，
以及**核心防线**：`DEFAULTS` 里不允许出现基线之外的新"孤儿"键
（既不在面板、也无人读取）。69 个存量孤儿已逐条登记，只允许缩小。

### 新增/修复（接线审计：把"写了没接线"变成可自动检测 · P9）

本项目反复出现**代码写好了但从未接线**（`start_autosave` 零调用点、
`LocalCompleter` 零调用方、LSP 8 个请求零调用方、~35 个死模块）。
新增 `tests/test_wiring_audit.py`（29 个用例 + 4 个已知未完成项）：

* **关键 API 接线断言** —— `start_autosave`、`LocalCompleter.get_completions`、
  `LspClient.request_definition`、`toggle_lsp`、草稿恢复入口必须有生产调用点；
* **死模块基线** —— 35 个已确认死模块逐条登记，**只允许缩小**，
  新增死模块即红（避免"删了没人发现"与"越积越多"）；
* **端到端冒烟** —— 真实构造 `MainWindow`，执行打开文件、断言高亮、
  写自动备份、断言面板 objectName 唯一等。

审计过程中发现并登记了 **16 个任务清单之外的既有死模块**
（`ui/refactor_dialog.py`、`ui/task_panel.py`、`ui/git_panel.py`、
`ui/markdown_preview.py`、`ui/usage_stats_panel.py`、`core/benchmark.py` 等）。

**重要方法论**：`xfail(strict=False)` 在功能接线成功后**会变成 XPASS 而不是失败**
—— 留着就会让防线静默失效。本次逐条复核，把**已接线的 xfail 全部摘掉**恢复为
硬断言（`start_autosave` 相关两条即因此摘除）。

### 修复（测试隔离从未生效 · 重大）

**实测证据**

    QSettings('QingCao','Editor').format() = 0   (NativeFormat / 注册表)
                                              ↑ 即使已调用 setDefaultFormat(IniFormat)

`conftest.py` 声称"把所有 QSettings 写入重定向到 pytest 临时目录"，但
**PyQt5 的 `QSettings(org, app)` 两参构造永远使用 NativeFormat，忽略
`setDefaultFormat`**；而 `app/preferences.py` 用的正是这一形式。后果：

* **所有测试都在读写真实注册表** —— 测试之间互相污染
  （实测：前一个用例把 `local_completion` 写成 `false`，导致后一个用例
   读到污染值而失败）；
* **污染开发者的真实首选项**（实测机器上 `local_completion` 被改成 `false`）。

**修复**：在类级别替换 `PyQt5.QtCore.QSettings`，只改写 `QSettings(str, str)`
这一种重载（放行 `QSettings(fileName, Format)` 等合法重载，否则
`test_secure_storage` 会抛 "arguments did not match any overloaded call"）。
另修 `preferences` fixture 用每用例 `tmp_path` 调用**进程级全局**
`QSettings.setPath` 的缺陷（用例结束后路径指向已删除目录），改为复用
会话级隔离目录 + 每用例 `clear()`。

### 修复（面板默认不显示 · 性能优化引入的功能回归）

**现象**：用户反馈"缺少部分功能"。逐项核对后确认**菜单功能没有缺失**
（148 个菜单条目 + 工具栏 9 项 + 8 个面板 + 12 个命令 + 49 个快捷键，
与旧版本一致且更多），真正的问题是**启动后面板一个都不显示**，界面
只剩欢迎页，观感上就像"功能没了"。

**根因**：为优化冷启动，面板改为**延迟构造**（`_LAZY_PANELS`），但

1. 没有任何机制在启动时构造"默认面板" —— 旧版会同步构造 9 个面板，
   其中 4 个默认可见（项目/全局搜索/插件/性能监控）；
2. 会话保存 `_capture_docks` 按 `findChildren(QDockWidget)` 采集面板，
   启动时一个面板都没有 → **保存出空的 `docks`** →
   关闭时**覆盖掉用户已有的面板布局**；
3. `_restore_docks` 只遍历"已存在"的 dock，未构造的面板**永远无法恢复**。

三者叠加形成恶性循环：**首次运行之后，面板布局被永久清空**。

实测证据（旧版 vs 当前版的 session.json）：

    旧版:  "docks": {"OutlinePanel": {...}, "DirectoryTreeDock": {"visible": true}, ...}
    当前:  "docks": {}          ← 布局全部丢失

**修复**

* 新增 `_DEFAULT_PANELS`：启动时构造并**显示**项目/全局搜索/插件/性能监控
  四个常用面板（仍少于原先的 9 个，保住冷启动优化）；
* 新增 `MainWindow._show_panel()`：统一"面板本身是 dock"与"面板包在 dock 里"
  两种封装形式，避免各处重复判断；
* 为全部 9 个面板补 `setObjectName()`（会话采集/恢复依赖稳定名字，
  原先靠 windowTitle 不稳定）；
* `_capture_docks`：采不到面板时**不覆盖**已有布局（沿用上次记录）；
* `_restore_docks`：先按会话记录**构造**缺失面板再恢复可见性
  （原先对延迟面板直接跳过，导致"上次开过的面板再也不出现"）。

**验证（四场景闭环）**

    场景1 全新用户          -> 默认 4 面板可见          ✅
    场景2 调整布局并保存    -> session.json 记录 6 个面板（含大纲）✅
    场景3 重启恢复          -> 与保存前完全一致         ✅
    场景4 全部隐藏后保存    -> 面板记录未被清空（回归防线）✅

### 新增（面板测试）

`tests/test_p1_features.py` 的面板用例按新行为重写并扩充：
  * 启动时恰好构造 `_DEFAULT_PANELS`，其余仍延迟
  * 默认面板**可见**（不只构造）—— 直接针对本次缺陷
  * 全部 9 个面板都有稳定 objectName
  * 按需构造、未知面板拒绝

`tools/feature_inventory.py`：导出全部功能点（菜单/工具栏/面板/命令/
快捷键/插件能力），用于核对"是否全功能"。
`tools/check_panels.py` / `check_panel_session.py`：面板可用性与
布局保存恢复闭环验证。

全量套件 428 -> **430 passed**。

### 修复（欢迎页不跟随主题 · 连带发现一个静默失效缺陷）

**现象**：护眼等浅色主题下，欢迎页仍是**深色**（#1e1e1e），与浅色工具栏
形成"深色页面 + 浅色工具栏"的割裂观感。

**根因（三层叠加）**

1. `ui/welcome_widget.py` 有 **20+ 处硬编码暗色**（#1e1e1e / #2d2d2d /
   #094771 / #0e639c …），完全没有使用主题色。
2. 该控件的样式**全部是内联样式**（`setStyleSheet`）。内联样式只在构建时
   求值一次，**不随全局 QSS 变化自动更新**，`unpolish/polish` 也无法重算；
   而启动路径 `main.load_theme()` 只调用 `apply_qss` 应用全局样式表，
   **不会**遍历控件调用 `refresh_theme`。因此欢迎页永远用默认暗色渲染。
3. 修复过程中暴露一个**静默失效缺陷**：首次尝试在构造函数里绑定当前主题，
   但代码引用了**未定义**的 `ORG_NAME`，被 `except Exception: pass` 吞掉 ——
   "修复"看起来已生效，实际一行都没执行。这正是本项目最重要的结构性问题
   （宽 except 掩盖失败）的又一实例。

**修复**

* 新增模块级主题色代理 `C`（`_ThemeProxy`）：所有样式通过它读取颜色；
* 为 `WelcomeHeader` / `QuickActionsPanel` / `RecentFilesList` /
  `TipsPanel` / `StatsPanel` / `WelcomeFooter` / `WelcomeWidget` 各加
  `refresh_theme()`，重放各自的内联样式；
* `WelcomeWidget` 构造时调用 `_bind_current_theme()` 主动绑定当前主题；
* `ThemeLoader.apply_qss()` 同时把主题色绑定到 `C`（单一入口，覆盖所有
  应用样式的路径）；
* 定义 `ORG_NAME`，并把该处的宽 `except` 改为**打印异常**，避免再次静默。

**验证（截图像素采样 + 单元测试）**

    打包版欢迎页背景采样: #c7edcc  （护眼 window_bg，修复前为 #1e1e1e）
    四个主题全部跟随：
      护眼  #c7edcc ✅   晨曦 #ffffff ✅
      暗夜  #1e1e1e ✅   高对比 #000000 ✅
    排除性判据：浅色主题下样式里的颜色**必须全部来自该主题**，
    不再出现暗色残留。

### 新增（主题测试）

`tests/test_welcome_theme.py`（13 个用例）：
  * 各面板都具备 refresh_theme（缺一个就会出现"部分区域不变色"）
  * 4 个主题下欢迎页背景 == 该主题 window_bg
  * 浅色主题下样式颜色必须全部属于该主题（防硬编码回归）
  * 浅色主题下不得出现暗色表面值 #1e1e1e / #2d2d2d / #094771
  * 暗色主题仍保持深色、theme=None 不崩溃、代理兜底可用

全量套件 415 -> **428 passed**。

### 修复（护眼主题配色不可读 · 严重）

用户反馈护眼主题下**菜单栏与工具栏文字几乎看不见**。查到三个叠加缺陷：

**① 打包后 JSON 主题从未被加载**
`ThemeLoader` 的主题目录是相对路径 `"themes"`，依赖当前工作目录。
打包后主题被 PyInstaller 放进 `_internal/themes`，exe 同级只有一个空的
`themes/`（留给用户自定义主题），因此
`os.path.exists("themes/eye_protect.json")` 为假 —— 完整的 JSON 主题
**永远不会被读取**，静默回退到内置定义。

**② 内置主题定义严重不完整**
内置 `BuiltinThemes.eye_protect()` 只显式设置 32 个键（JSON 有 70 个），
缺失的键回退到 `ThemeColors` 的**暗色默认值**：

    window_fg / menubar_fg / menu_fg -> #d4d4d4（浅灰）
    button_bg                        -> #0e639c（暗蓝）

于是护眼主题（浅绿底 `#c7edcc`）上，菜单栏与工具栏文字变成浅灰 ——
与背景几乎同色，**完全不可见**。实测像素证据：文字区最暗像素
`#b8dfc0` 与背景 `#b8dfc0` 完全一致。

**③ 内置 `eye_protect.type` 错标为 `dark`**（JSON 是 `light`）

**修复**
* 新增 `resolve_theme_dirs()` / `find_theme_file()`：多目录解析，覆盖
  打包后 `_internal/themes`、源码运行仓库 `themes/`、exe 同级三种情况；
* `load_by_name()` 与 `load_all()` 改为 **JSON 优先于内置定义**，
  并按名称去重（原先同名主题可能返回两份，选到哪份取决于顺序 ——
  这正是"主题时好时坏"难以复现的来源）；
* 修正内置 `eye_protect` 的类型与配色，补齐缺失键。

**验证**（像素级）
    修复前 工具栏文字区最暗像素 = #b8dfc0（与背景相同 → 不可见）
    修复后 工具栏文字区最暗像素 = #2c3e2f（对比度约 7:1 → 清晰）

### 修复（主题对比度不达标）

新增 `tools/audit_themes.py` 做 WCAG 对比度审查，修正 2 个主题的
不达标项（**全部达标**）：

| 主题 | 项 | 原值 | 现值 | 对比度 |
|---|---|---|---|---|
| 护眼 | 注释 | `#6b8e5e` | `#526d48` | 2.90 → 4.53:1 |
| 护眼 | 按钮/状态栏底 | `#4a8f5e` | `#438355` | 3.90 → 4.56:1 |
| 护眼 | 缩进参考线 | `#9cc9a5` | `#96c6a0` | 1.45 → 1.51:1 |
| 晨曦 | 行号/边距/折叠边距 | `#999999` | `#8a8a8a` | 2.50 → 3.01:1 |
| 晨曦 | 控制字符 | `#c0c0c0` | `#959595` | 1.82 → 3.00:1 |
| 晨曦 | 缩进参考线 | `#e0e0e0` | `#d3d3d3` | 1.32 → 1.50:1 |

护眼主题专项结论：背景 `#c7edcc`（亮度 77%，绿色分量最高）、
正文对比度 8.93:1（处于 7~12:1 的舒适区）、类型 light —— 均正确。

### 新增（主题测试与工具）

* `tests/test_theme_integrity.py`（19 个用例）：JSON 优先于内置定义
  （回归防线）、键集合一致性、颜色格式、正文/菜单/UI 元素对比度达标、
  护眼主题类型与亮度、主题列表去重、冻结环境主题目录解析
* `tools/audit_themes.py`：WCAG 对比度审查 + 键完整性 + 语义色可辨性
* `tools/diff_builtin_themes.py`：内置定义与 JSON 的键差异对比
* `tools/dump_theme_qss.py`：导出主题生成的 QSS 便于排查样式
* `tools/fix_theme_contrast.py` / `fix_button_contrast.py`：计算最小修正值

全量套件 396 -> **415 passed**。

### 修复（打包）

- **插件运行时依赖未被打进产物（v2.1.0 打包缺陷）**
  `plugins/` 是作为**数据文件**打包的（`datas` 里的
  `('plugins', 'plugins')`），由 `plugin_loader` 用
  `importlib.util.spec_from_file_location` 在**运行时**从源码加载。
  PyInstaller 的静态分析**看不到插件源码里的 import**，因此插件依赖的
  模块必须在 `hiddenimports` 中显式列出。

  本次新增的三个模块恰好都不在白名单里：

  | 模块 | 用途 | 后果 |
  |---|---|---|
  | `core.ollama_client` | Ollama 本地模型管理 | Ollama 功能不可用 |
  | `core.ai_cache` | AI 结果缓存 | 缓存静默失效 |
  | `ui.ai_inline_completer` | AI 行内补全 | 行内补全不可用 |

  实证（解包 exe 内的 PYZ 归档核对）：
  * 修复前 PYZ 模块数 815，三个模块**全部缺失**
  * 修复后 PYZ 模块数 818，三个模块**全部就位**

  修复方式：在 `build.py` 的 `collect_hidden_imports()` 中新增
  `plugin_runtime_deps` 列表，并加了注释说明"为什么插件依赖必须显式
  列出"，避免以后新增插件依赖时再次遗漏。

  判断方法（以后可复用）：扫描 `plugins/**/*.py` 里 import 的项目内
  模块，取与 `hiddenimports` 的差集。本次差集恰好就是这三个。

### 打包验证方法（可复用）

打包产物最容易被误判：业务模块被塞进 exe 内的 **PYZ 压缩归档**，
直接对 exe 做字符串搜索找不到任何模块名（压缩所致），会得出"模块没
打进去"的错误结论。正确做法有两种：

1. **解包 PYZ 核对**
   ```python
   from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader
   car = CArchiveReader(r"dist\QingCaoEditor\QingCaoEditor.exe")
   open("pyz.tmp","wb").write(car.extract("PYZ.pyz"))
   mods = set(ZlibArchiveReader("pyz.tmp").toc)      # 逐个模块核对
   ```

2. **运行期诊断**（最可靠）
   临时在 `main.py` 里挂一个 `QTimer` 回调，把已激活插件与菜单树写到
   文件后 `app.quit()`，用 `QT_QPA_PLATFORM=offscreen` 跑一次 exe。
   本次验证结果：
   ```
   插件规范数: 10   已激活插件数: 10
   工具菜单条目数: 69
   AI 助手/ （22 项，含 Ollama 与行内补全）
   插件依赖模块可导入性: core.ai_cache OK / core.ollama_client OK
                        ui.ai_inline_completer OK / core.ai_client OK
   ```

  注意：`ROOT_DIR` 在冻结后是 **`_internal`**，所以诊断文件会写到
  `dist\QingCaoEditor\_internal\` 而不是 exe 同级目录。

### 分发

- Inno Setup 未安装，`build_installer.py` 无法运行（会提示安装地址）。
  本次改为提供**便携 ZIP**：`dist/QingCaoEditor-v2.1.0-portable.zip`
  （57.7 MB，427 条目）。已解压到全新目录验证：417 文件、
  `--version` 输出 v2.1.0、插件源码与工作区一致。

### 新增（AI 会话按文件归档）

单一会话窗口下，多文件交替提问会把上下文混在一起 —— 聊 A 文件的内容
被带进 B 文件的提问，既费 token 也污染回答。

现改为**按文件归档**：每个文件拥有独立的对话上下文，切换文件时自动
换出/换入「窗口文本 + 代码上下文 + 对话历史」，互不干扰。

* 会话键取文件绝对路径并做 `normcase` 归一，因此同一文件的不同大小写
  写法（Windows 上常见）归到**同一会话**；
* 未保存的新文件归到 "(未命名文件)" 会话，保存后新会话自动归到文件名下；
* 窗口顶部显示「当前会话：alpha.py · 共 3 个文件会话（各自独立）」；
* **生成中切换文件不串台**：若请求发起于 A 文件、用户中途切到 B，
  A 的后续片段会先累积到后台缓冲，等切回 A 时一次性补上，
  不会出现在 B 的窗口里；
* 「＋ 新会话」只清空**当前文件**的上下文，其他文件的会话不受影响。

### 修复（AI 会话）

- **会话守卫的路径归一化不一致**（自查发现）
  守卫用 `session_key()` 归一化后比较来源会话，但来源值曾直接使用原始
  路径。`normcase` 会把 Windows 路径小写化，于是
  `D:\p\a.py` 与 `d:\p\a.py` 被判成两个会话 ——
  **同一会话的片段会被误当作"后台输出"而丢弃**，表现为"AI 没有输出"。
  现双方统一走 `session_key()` 归一化后再比较。

### 测试

- `tests/test_ai_enhancements.py` 新增 8 个按文件归档用例：
  键归一化（大小写/未命名）、历史隔离与还原、会话计数、同文件不清空、
  生成中切文件不串台、新会话清空归档、标签显示

全量套件 388 -> **396 passed**。

### 新增（AI 体验）

- **推理状态实时反馈**
  大模型（尤其本地 Ollama 在 CPU 上）首字输出可能要等十几秒，此前状态栏
  只有静态"正在生成..."，用户无法判断是在跑还是卡死。现分两阶段显示：

  * **思考中**：`生成中… 已等待 12.3 秒（模型思考中，首字输出较慢属正常）`
  * **接收中**：`接收中… 15.6 秒 · 已收到 842 字 · 54 字/秒`
  * **完成**：`✓ 完成 · 总耗时 18.2 秒`

  首字到达时**立即**刷新（不等 200ms 定时器），首字反馈无延迟。

- **AI 结果缓存**（`core/ai_cache.py`）
  同一段代码 + 同一动作常被重复请求（切标签回来、误关重开、反复
  "再解释一次"），每次都是真实 HTTP 请求。现加**内存 LRU 缓存**：

  * 键覆盖所有影响输出的参数：provider / model / base_url /
    temperature / max_tokens / system / 提示词全文 —— 任一项变化都不会
    命中旧结果（避免"换了模型却拿到旧回答"）；
  * 双重限制：条数（默认 50，LRU 淘汰）与单条长度（默认 20000 字）；
  * 命中时状态栏显示「✓ 来自缓存（未发起新请求）」，并仍可继续追问
    （缓存内容会补进历史，保证上下文与"重新生成"一致）；
  * **多轮追问不使用缓存**（上下文不同）；
  * 纯内存、退出即清空，不落盘（避免敏感代码留痕）；
  * 命令面板新增 `AI: 查看缓存统计` / `AI: 清空结果缓存`；
  * 配置对话框新增「复用结果缓存」开关（默认开启）。

- **AI 对话窗口（非模态、多轮不丢上下文）**
  原先每个动作弹一个**模态**对话框，`exec_()` 阻塞编辑器；切换标签后
  上下文就丢了。现改为**复用同一个非模态窗口**：

  * 窗口一直开着，切换标签/继续操作都不丢上下文，可直接追问；
  * 同一窗口连续执行多个动作会形成对话流（带 `▶ 动作名` 分隔）；
  * 新增「＋ 新会话」按钮：清空上下文开始新话题，但保留窗口内已有
    记录供对照；
  * 受「复用同一个 AI 对话窗口」首选项控制（默认开启），关闭后回退到
    旧的"一次动作一个模态对话框"行为；
  * 菜单新增「💬 打开 AI 对话窗口」。

- **AI 动作接入命令面板**
  `Ctrl+Shift+P` 现可搜到 12 个 AI 命令：9 个动作 + 快速解释 + 缓存
  统计/清空。其中「AI: 快速解释」走 `quick_explain()` 那条**编程式
  API**（不开对话框，结果直接写入剪贴板），与 UI 流式路径共用同一套
  `PROMPT_*` 模板，因此结果语义一致。

### 修复（AI 模块）

- **`AIResultDialog` 缺少必需属性导致"新会话"静默失效**
  该对话框的 `_client` / `_system_prompt` / `_code_context` 等属性只在
  `_run_ai_action` 里动态赋值，构造函数中并未初始化。于是
  `start_new_session()` 里的 `getattr(self, '_client', None)` 拿到
  `None`，清空上下文的动作被宽 `except` **静默吞掉**——用户点"新会话"
  看起来有提示，实际上下文没清。

  修复：构造函数显式初始化全部状态字段；`_get_or_create_session`
  创建窗口后立即绑定客户端；`start_new_session` 在无法清空时**明确
  告知用户**而不是假装成功。

### 测试

- `tests/test_ai_enhancements.py` 新增 32 个用例：
  缓存键构成（6 类参数差异）、LRU/容量/大小限制、并发安全、单例；
  状态阶段切换与计时；会话窗口非模态/复用/新会话语义；命令注册完整性

全量套件 356 -> **388 passed**。

### 新增（AI 能力）

- **多轮对话（追问）**
  `AIClient._history` 此前**只声明、从未使用**，AI 只能一问一答。
  现实现为真正可用的上下文：
  * `chat` / `chat_stream` 均支持 `use_history=True`（三个实现：
    基类兜底、`OpenAIClient`、`ClaudeClient`）；
  * 历史随请求发送，因此模型能"接着上文"回答；
  * `max_history_turns`（默认 10 轮）自动裁剪，避免长会话撑爆上下文窗口；
  * 新增 `reset_history()` / `get_history()` / `history_turns()`。

  UI 侧在 AI 结果对话框加入了**追问输入框**（回车发送）与"记住上下文"
  开关：首轮完成后可直接输入「再简化一点」「换成列表推导式」等继续对话，
  追问会自动附带最初分析的代码，便于模型定位。

- **按任务分档的 token 预算**
  原先所有动作固定 `max_tokens=4096`。对"解释代码/代码摘要"这类只输出
  一两段文字的任务，模型可能一直输出到上限，白等更久也更费 token。
  现引入 `TOKEN_TIERS`（tiny/short/medium/large = 512/1024/2048/4096）
  与 `tokens_for(tier)`，并给 10 个 AI 动作分别定档：
  摘要 → tiny；解释/Docstring → short；重构/修复/注释/优化/Review → medium；
  生成测试/语言转换 → large。

- **AI 行内补全（Ghost Text）接线**
  `ui/ai_inline_completer.py` 此前是**死代码**（完整实现但从未实例化）。
  本次重写并接线，同时修掉它原有的三个缺陷：

  | 原缺陷 | 现方案 |
  |---|---|
  | `_pending` 由工作线程写、主线程读，输入被静默丢弃 | 改为在工作线程只发信号，**主线程**回调里复位 |
  | 每次建议都挂一个不可取消的 5 秒 `singleShot`，快速操作会堆积 | 复用一个可 `start()` 重置的 `QTimer` |
  | 每次按键都可能触发 AI 请求（有延迟、有费用） | 改为**显式触发**，默认**关闭** |

  渲染改用 Scintilla **注解**（`SCI_ANNOTATIONSETTEXT`）而非 CallTip：
  注解本就是"给某行加提示"设计的，且不会像 CallTip 那样遮挡代码。
  接受建议用 `SCI_INSERTTEXT` 插入，**可被 Ctrl+Z 撤销**。

  入口：菜单 工具 → AI 助手 → ⌨ 切换/请求/接受行内补全；
  快捷键 `Ctrl+Alt+Space`（请求）、`Ctrl+Alt+Return`（接受）。

- **修正 `_clean` 的围栏解析**
  生成结果形如 ```` ```python\nreturn 1\n``` ```` 时，原实现先把 ``` 全部
  `replace` 掉再取第一行，会得到**空行**（结果为空）或把语言标记
  `python` 当成代码返回。现先剥围栏并跳过语言标记行，再取首个非空行。

### 修复（AI 模块交互）

- **同一快捷键被重复绑定**
  菜单项通过 `add_menu(..., shortcut)` 绑定一次，`_register_shortcuts()`
  又用 `register_shortcut()` 绑定一次 → 产生两个同名 QAction，Qt 打印
  "Ambiguous shortcut overload" 且**只触发其中一个**。
  现约定：有菜单项的快捷键由菜单负责（菜单里能看到按键提示），
  `register_shortcut` 只用于没有菜单项的（现仅 `Ctrl+Shift+A`）。

- **`QObject` 子类化错误导致插件整体激活失败**
  `PluginBase` 继承自 `object` 而非 `QObject`；创建 `AIInlineCompleter`
  时传 `parent=self` 会抛 `TypeError`，使插件的 `on_activate` 中断 →
  **全部 22 个 AI 菜单项消失**。改为无 parent + 插件实例持强引用。
  （同类问题此前已在 `QTimer(self)` 上踩过一次，已在两处加注释说明。）

### 测试

- `tests/test_ai_client.py` 新增多轮历史（13 个）与 token 分档（5 个）用例
- `tests/test_ai_inline_completer.py` 新增 23 个用例（含围栏/语言标记解析、
  最小间隔、取消作废在途请求、接受可撤销）

全量套件 317 → **356 passed**。

### 修复（AI 模块）

- **Anthropic Claude 的流式输出从未生效**
  `chat_stream` 原先只定义在 `OpenAIClient` 上，而 `ClaudeClient` 继承的是
  `AIClient` → `hasattr(client, 'chat_stream')` 为假。插件因此**静默退化
  为非流式**：用户要盯着空白对话框等到整段回复生成完（流式超时 300 秒）。
  更糟的是任何直接调用 `client.chat_stream(...)` 的代码会抛
  `AttributeError`。

  修复分两处：
  * `AIClient` 基类新增 `chat_stream` 兜底实现（非流式 + 一次性回调），
    保证"接口存在、结果正确"，子类可重写以获得真正的增量输出。
  * `ClaudeClient` 实现**真正的 Anthropic Messages SSE 流式**：
    端点 `/messages`（非 `/chat/completions`）、头 `x-api-key` +
    `anthropic-version`、`system` 放在**顶层**、解析
    `content_block_delta` → `delta.text`，并处理 `error` 事件。

  实测（mock Anthropic SSE）：增量 2 段 `['Hello', ', world']`、
  URL 与鉴权头正确、`system` 在顶层。

- **取消一次后，后续 AI 请求全部"无响应"**
  `OpenAIClient.chat_stream` 开始时**没有清除上一次的取消标志**。
  用户点过一次"取消"后，下一次请求会在第一行 SSE 就 `break`，
  表现为 AI 永久无响应（需重启编辑器）。基类兜底实现有这一步，
  `OpenAIClient` 遗漏。现已在流式入口统一 `self._cancel.clear()`。

### 新增（AI 模块测试）

- `tests/test_ai_client.py` —— **AI 模块此前在 `tests/` 下引用数为 0**，
  这正是上述 Claude 缺陷能长期存在的原因。新增 35 个用例，全部基于
  **mock HTTP**（不发真实网络请求）：
  * OpenAI 兼容族：增量回调、URL/Bearer 头、payload 结构、
    `[DONE]` 哨兵、忽略非 data 行、容错非法 JSON、空 choices、
    空 key 鉴权规则
  * Anthropic：`chat_stream` 存在性（回归防线）、增量回调、
    `/messages` 端点、`x-api-key` + `anthropic-version`、`system` 顶层、
    忽略 ping/message_start、忽略 `thinking_delta`、`error` 事件抛错、
    非流式解析 content blocks
  * 基类兜底、工厂映射（claude/anthropic → ClaudeClient）、
    默认模型与 base_url、未知 provider 抛 `AIConfigError`
  * 取消语义：收到首片即取消后不再继续、返回已收内容、
    **取消标志在新请求时被清除**

  全量套件 282 -> **317 passed**。

### 修复

- **`ui/main_window.py` 关闭路径收尾（审计 F-2）**
  `closeEvent` 原先只停两个主窗口定时器就 `app.quit()`，导致插件持有的
  后台线程在运行中被析构（Qt 打印 "QThread: Destroyed while thread is
  still running"，可能 `qFatal()`）、插件热重载 watcher 未停止、
  语言服务器子进程在 Windows 上变孤儿。
  新增 `_shutdown_background_work()`：显式收尾面板线程 → 停止插件
  watcher → 逐个 `proxy.close()`（停 LSP/草稿定时器；该方法不含对话框，
  不会重复询问未保存）。所有步骤独立 try/except，不阻断退出。

- **`QTimer(self)` 在插件里必然失败**
  `PluginBase` 继承自 `object` 而**不是 `QObject`**，因此
  `QTimer(self)` 抛 `TypeError: argument 1 has unexpected type 'Plugin'`，
  又被宽 `except` 静默吞掉。定时器改挂到面板（QWidget 即 QObject）。

- **插件后台线程统一改用 `threading.Thread` + `QObject` 信号桥**
  `QThread.run()` 不响应 `requestInterruption()`，运行中被析构还会触发
  Qt 警告/qFatal。改为 daemon `threading.Thread`（同项目
  `core/search.py::FileSearcher` 的既有正确样板），彻底消除该竞态。

### 计划中
- 更多 LSP 语言支持
- 协作编辑完善
- 插件市场后端

### 删除

- **移除未接线的插件沙箱原型**
  `infrastructure/plugin_sandbox.py`（1605 行）、
  `infrastructure/sandbox_runtime.py`（1192 行）、
  `core/sandbox_policy.py`（593 行），以及 `tests/test_plugin_sandbox_event.py`
  与 `tests/test_sandbox_socket.py`（共 350 行）。

  **删除理由（有实测证据）**：

  * 这 3390 行**没有任何生产调用方** —— `sandbox_policy` 只被
    `sandbox_runtime` 引用，`sandbox_runtime` 只被测试引用；
    `build.py` 的 hidden-imports 与 `pyproject.toml` 的 coverage omit
    是仅有的其它提及。
  * 它**根本无法启动**：实测 `PluginSandbox.start()` 返回 `False`、
    状态卡在 `RESTARTING`。原因之一是 `_install_security()` 里写的
    `__builtins__.__import__` —— 在非 `__main__` 的普通模块里
    `__builtins__` 是 **dict** 而非 module，赋值会 `AttributeError`
    （已用最小实验复现）。子进程入口与帧协议也有缺陷。
  * 与此同时 **5 个相关单测始终是绿的** —— 它们只测消息常量与
    纯函数，从不真正 `start()`。这正是"测试全绿但功能不可用"的典型。
  * 名字本身构成误导：`plugin_sandbox` 会让人以为插件已被隔离，
    而实际**没有任何隔离**。

  代码可在 git 历史中查阅（`2.1.1` 之前的提交）。若将来要做真隔离，
  需注意这是一项**结构性改造**：现有 `PluginAPI` 大量操作 QWidget
  （面板、菜单、对话框），子进程无法持有这些对象，API 边界必须重新设计。

- 顺带移除 `app/preferences.py` 中无任何 UI/运行时引用的
  `plugin_sandbox` 开关（避免暗示"可以开启真沙箱"）。
- `build.py` 的 hidden-imports 与 `pyproject.toml` 的 coverage omit
  同步清理。验证：78 个 hidden imports 全部可导入。

## [2.1.1] - 2026-09-25

本次更新为**缺陷修复版本**：修复一个会导致**数据损坏**的保存
缺陷、LSP 初始化崩溃、插件权限体系失效，并统一版本号来源、
补齐翻译与资源、降低启动耗时。原有 198 项测试全部保持通过。

### 修复（P0）

- **搜索在大文件上不可用（O(n²)，最严重的性能缺陷）**
  `core/search.py::_get_line_text` 每次调用都执行
  `provider.read_text()` + `text.splitlines()`，即**读取并切分整个
  文件**；而它被 `_build_match` 在**每个匹配**上调用一次，
  复杂度从 O(N) 退化为 O(匹配数 × 文件大小)。

  实测（重复 50 字符文本，纯文本搜索 `quick`）：

  | 文件 | 修复前 | 修复后 |
  |---|---|---|
  | 16 KB（297 匹配） | 0.031 s | — |
  | 64 KB（1 191 匹配） | 0.426 s | — |
  | 256 KB（4 766 匹配） | 9.799 s | < 1 s |
  | 1 MB（19 065 匹配） | **> 25 s 未完成** | **0.415 s** |
  | 10 MB（190 650 匹配） | **> 15 分钟无输出** | **3.702 s** |
  | 10 MB 正则 | 不可用 | 4.479 s |

  上层路径同步受益：`EditorProxy.highlight_all` 对 1 MB / 19 065 处
  高亮从"不可用"降到 **0.928 s**。

  修复方式：新增唯一权威行索引 `_ensure_line_index()`（复用已有的
  全文解码结果，不额外读盘），每行取值降为 O(行长) 切片。

  > **过程中的重要教训（已写入代码注释）**：修复后我尝试把
  > `_build_line_index` 也接到同一个索引上"消除重复构建"，写成
  > `return self._ensure_line_index()[:-1]` —— 结果引入了 **13× 退化**
  > （1 MB 从 0.268 s 变成 3.484 s）。实测每次 `index[:-1]` 要拷贝
  > 19 065 个元素：`_position_to_line_col` 变成 **169.54 µs/次**，
  > 其中列表拷贝占 **182.98 µs/次**，而纯 bisect 只要 **0.60 µs/次**。
  > 改为**直接返回缓存索引、不做任何切片拷贝**后恢复（索引末尾的
  > 哨兵不影响 bisect，因为 `position < len(text)` 永远选不中它）。
  > 这个坑由新增的回归测试 `test_line_index_not_copied_per_match`
  > 长期守住。

- **保存残留旧字节（数据损坏）**
  `core/content_provider.py::_save_dirty_blocks` 只按块
  `seek+write`，**从不截断文件**。把 55 890 字节的文件删到
  12 字节后保存，文件仍是 55 890 字节（新内容 + 旧尾部），
  重开编辑器会看到"已删除的内容又回来了"。
  现按脏块真实长度 `truncate()`，并用磁盘实际大小比较
  （编辑器保存前会先把 `_size` 改成新长度，用它比较会漏掉截断）。
  另修 `_save_as_full` 的 inode 替换问题（`os.replace` 后
  `self._file` 仍指向旧 inode，现重新打开句柄并重建 mmap）。

- **LSP 初始化参数错位导致语言服务不可用**
  `core/editor.py` 调用 `did_open(uri, self.sc.text())`，而签名是
  `did_open(uri, language_id, text, version)`：`language_id` 收到整份
  文件文本、`text` 缺失、`version=None`，随后 `did_change` 必然
  `TypeError`（`NoneType += int`）并被宽泛 `except` 吞掉。
  现已按签名传参、用 `path_to_uri` 生成 URI、补 `did_change`
  防抖同步与 `did_save`/`did_close`；`LspClient` 侧做输入防御
  （text 为 None、version 非法、language_id 疑似全文时回退并告警）。

- **LSP 通道合并污染协议流**
  `QProcess.MergedChannels` 把语言服务器 stderr 并入 stdout，
  stderr 上的日志/banner 会破坏 `Content-Length` 帧解析，
  `_on_stderr` 永不触发。改为 `SeparateChannels`，并让帧解析器
  在遇到非法头时丢弃该段噪声后重试（原实现会一路吃掉后续合法消息）。

- **LSP `initialize()` 必然崩溃**（由真实子进程端到端测试发现）
  `LspClient.initialize()` 调用 `self._uri_to_path(root_uri)`，但本类
  只有无下划线前缀的 `@staticmethod uri_to_path` —— 因此握手第一步
  就抛 `AttributeError`，被 `EditorProxy.toggle_lsp` 的宽泛 `except`
  吞掉。**这意味着即使修好了 did_open 的参数错位，LSP 仍然起不来**；
  纯逻辑单元测试无法发现，只有跨进程握手测试才能暴露。
  已改为 `LspClient.uri_to_path(root_uri)`。

- **插件权限体系失效**
  - 启动路径调用裸 `loader.load_all()`，而
    `PluginManager.load_all` / `_check_and_confirm_permissions`
    全仓无调用者 —— **危险权限确认框永远不会弹出**。
    现改为经 `PluginManager.load_all(auto_activate=True)` 加载。
  - `PluginAPI.grant_permission()` 允许插件一行自我提权
    （`grant_permission('process')` + `run_command(...)`）；
    现在必须由宿主授权，新增 `grant_permissions_by_host()`。
  - `api.win` 是公开属性，插件可经它拿到主窗口与**全权限主 API**
    从而绕过全部检查；现改为弃用属性（打印一次告警）+
    受 `dialog` 权限门控的 `get_main_window()`。
  - `get_plugin_data_dir()` / `save_plugin_config()` 原为
    "无需权限"的写盘后门，现要求 `filesystem` 权限。
  - 内置插件迁移到 `api._host_window()`；为 logtail /
    markdown_preview / todo_panel / wordcount 补上它们实际使用
    的 `dialog` 权限声明。
  - `plugin_sandbox.py` / `sandbox_runtime.py` 顶部加入**醒目的
    未接线警告**（这两份 ~2 800 行代码目前没有任何生产调用方，
    当前版本**没有进程级隔离**）。

### 修复（P1）

- **版本号漂移**：`version.py` / `VERSION` / `installer.iss` /
  各 `build*.py` / 运行时代码共 30 余处各自硬编码版本号，
  且 CHANGELOG 已发布 2.1.0 而代码仍写 2.0.0。
  现统一以 `version.py` 为唯一来源（运行时代码改为导入），
  新增 `tools/check_version.py` 做全仓一致性校验，
  `release.py` 的 bump 会同步写入 `version.py`。
- **插件热重载是空壳**：`_on_directory_changed` 原本只打印一句
  "可能需要重启编辑器"。现实现真正的 unload → load → activate，
  递归监控插件目录与源码文件，支持 `"hot_reload": false` 退出，
  并新增 `plugin_hot_reload` 首选项（默认开）。
- **国际化是空壳**：`locale/` 下只有 1 个 `.po`，其正文是 GBK
  字节却声明 `charset=UTF-8`，且全仓**没有任何 `.mo`** ——
  4 种语言从未生效。现补齐 4 语言（49 条词条）的 UTF-8 `.po`
  与 `.mo`，并新增 `tools/build_translations.py` /
  `tools/compile_locale.py`；`first_run_wizard` 的 `"???"` 韩语
  标签修正为 `한국어`。
- **音效模块是死代码**：`infrastructure/sound_manager.py`（1600+
  行）全仓零调用。现接入文件打开 / 保存 / 报错事件，并新增
  `sound_effects` 首选项（**默认关闭**，避免突然出声）。
- **启动耗时**：`_build_docks` 启动时同步构造全部 9 个面板
  （其中 6 个随即 hide）。改为惰性构造，实测
  `MainWindow()` 从 **2.46 s 降到 1.36 s**。
- `app/plugins.py` 补齐 README 已文档化但代码缺失的
  `lsp` / `debugger` 权限常量。

### 修复（P2）

- **README 渲染崩塌**：全文只有 2 个代码栅栏，中间 17 处裸语言
  标记（`bash`/`json`/`python`/`text`），GitHub 上从第 97 行起
  整篇被渲染成代码块。现重建为 26 个成对栅栏，并修正
  "方式三 pip 安装"（尚未发布 PyPI）、`create_plugin.py` 路径、
  配置文件路径、权限表、`Ctrl+H` 等与实现不符的描述。
- **安装包构建阻断**：`installer.iss` 引用的
  `resources/icons/qingcao.ico` 不存在。现新增
  `tools/make_assets.py`，生成 `qingcao.png` / `qingcao.ico`
  （含 7 种尺寸）与 `splash.png`。
- **lint 配置缺失**：仓库无任何 lint 配置，而 CI 对全仓运行
  ruff/black/isort，必然失败。现新增 `pyproject.toml`
  （ruff / black / isort / pytest / coverage），修复全部
  `F821` 未定义名与 `F811` 重定义（真实缺陷），自动整理
  380 处导入顺序，并把历史存量规则显式记录在 `ignore` 中；
  `ruff check .` 现在 0 告警。工作流改为 ruff 单一门禁 +
  版本一致性 + 翻译编译 + 测试四个 job。
- **仓库卫生**：新增 `tools/clean_repo.py`（默认 dry-run）
  清理 103 个 `*.bak.*` 备份（69 447 行），补全 `.gitignore`
  对 `msg.txt` / `findstr` / `.qingcao-tasks.json` /
  根目录 `fix_*.py` / `_archive/` 的忽略。

### 测试

- 新增回归测试覆盖以上 P0/P1 修复：
  `tests/test_save_truncate.py`（6）、`tests/test_lsp_did_open.py`（10）、
  `tests/test_plugin_permissions.py`（16）、`tests/test_version.py`（13）、
  `tests/test_p1_features.py`（28）、`tests/test_lsp_integration.py`（2）、
  `tests/test_search_performance.py`（8），合计新增 83 项。
- **`tests/test_search_performance.py` 的价值已单向验证**：临时把
  `_get_line_text` 换回修复前实现后，该文件的 8 项中有 **2 项立即
  失败**（256 KB / 4 766 匹配耗时 5.31 s、1 MB 超时），且文件总耗时
  从 1.28 s 膨胀到 180.52 s；换回修复版后恢复 0.93 s 全过。
  它同时守住"每次搜索只构建一次行索引"与"不得按匹配拷贝整表"。
- **`tests/test_lsp_integration.py` 是本次最有价值的补充**：它启动一个
  真实的最小 LSP 服务器子进程，经 `QProcess` 走完
  `initialize → didOpen → didChange → didSave → didClose`，并断言
  服务端**实际收到**的 `languageId`、文本与递增版本号。它当场抓出了
  `initialize()` 的 `AttributeError` 崩溃 —— 这是纯逻辑单元测试无法
  发现的一类缺陷。
  注意：等待必须用 `pytest-qt` 的 `qtbot.waitUntil`（会驱动 Qt 事件
  循环）；用 `time.sleep` 轮询是收不到跨进程信号的。
- **`tests/test_lsp_real_server.py`（7 项，标记 `realserver`）**：
  进一步用**真实 python-lsp-server** 验证语义层 —— 握手 3.8s 完成、
  `completionProvider` 能力被正确解析、`didChange` 后版本 1→2 且
  服务器**再次推送诊断**（这正是 P0-2 的语义后果：修复前
  `version=None` 会抛 TypeError，服务器永远停在打开时的快照）、
  补全返回 **454 项**真实候选。
  因每个用例会 spawn 一个 pylsp（约 25s），已排除出默认套件：
  `python -m pytest -m realserver`。
- 修复 `tests/test_secure_storage.py::test_is_secure` 的顺序依赖：
  原断言硬编码"降级为明文"，在 keyring 可用的真实环境里会随执行
  顺序时通时不通；现改为校验"安全标记与后端类型一致"。
- **198 → 288 passed**（默认 281 + realserver 7）；`ruff check .` 0 告警。

### 打包验证（P2）

- 实际执行 `python build.py`：**成功**，`main()` 返回 0，产出
  `dist/QingCaoEditor/`（377 文件 / 137.0 MB，主程序 7.2 MB）。
- 打包产物实测可运行：`QingCaoEditor.exe --version` 输出
  **v2.1.0**（Qt 5.15.2 / PyQt5 5.15.11 / QScintilla 2.14.1），
  退出码 0 —— 这独立佐证了 P1-1 版本统一确实生效。
- `generate_icon()` 成功产出 `resources/icons/qingcao.ico`，
  即此前阻断 `installer.iss` 编译的那个文件。
  **Inno Setup (ISCC) 本机未安装，因此未实际编译安装包。**
- 新增 `.gitattributes` 统一行尾约定（库内 LF），并将
  `version_info.txt` / `*.spec` / `.pytest_cache/` 加入 `.gitignore`。

## [2.1.0] - 2026-09-24

本次更新聚焦于**跨模块代码审查修复**、**Vim 模式补全**、
**主题切换修复**、**搜索偏移修正**。

### 新增
- **Vim 模式完整实现**
  - 操作符 + 动作: `dw` / `de` / `db` / `d$` / `d0` / `dG` / `dgg`
  - 修改操作符: `cw` / `ce` / `cb` / `c$` / `cc`
  - 复制操作符: `yw` / `ye` / `yb` / `yy`
  - 文本对象: `iw` / `aw` / `i"` / `a"` / `i(` / `a(` / `i[` / `a[` / `i{` / `a{`
  - 具名寄存器: `"a` 前缀（a-z / 0-9 / " / + / * / - / _）
  - 查找重复: `n` / `N`
  - 入口: 工具菜单 → Vim 模式（`Ctrl+Shift+V`）
- **UI 测试套件** (tests/test_vim_mode.py, 11 个测试)
- 测试总数: 187 → 198

### 修复
- **主题切换核心 bug**: `themes/*.json` 无 `qss` 字段，
  `_apply_theme_by_name` 只做 `if theme.qss: setStyleSheet(...)`，
  导致全局 QSS 从未应用。改用 `loader.apply_qss()` 自动生成。
- **主题跟随不全**: 扩展 `adapt_qss_colors` 替换表，
  补充终端色 (`#0d0d0d`)、次要文字、聚焦色 (`#007acc`) 等
- **主题菜单显示**: 从文件名 (`light_clean`) 改为 `display_name` (`晨曦`)
- **字符/字节偏移**: `SearchMatch` 双写 `start/end`（字节）
  和 `char_start/char_end`（字符），修复含中文文件搜索高亮/替换错位
- **`EditorProxy.highlight_all`**: 调用不存在的 `search_all()` →
  改用 `search()`
- **`EditorProxy.search_next`**: 调用签名错误 →
  Python 层遍历 `result.matches`
- **`_search_next` 不前进**: 从 `pos` 开始 → 从 `pos+1` 开始
- **`"a` 寄存器覆盖**: 两次 alnum 输入互相覆盖 →
  加独立 `_waiting_for_register` 状态
- **`yy` 后 `p` 不粘贴**: paste 从旧 `self.register` 读 →
  改从 `registers['"']` 读
- **`SCI_WORDRIGHTPOSITION` 不存在**: `PyQt5` 未导出该常量 →
  改用 `SCI_WORDRIGHT`
- **Ctrl+Z/Ctrl+Y 被吞**: QScintilla 内置绑定占用 →
  `SCI_CLEARCMDKEY` 清除，让主窗口菜单收到
- **`Ctrl+Alt+V` 被 AltGr 解释**: Windows 上无效 →
  改 `Ctrl+Shift+V`
- **`ProjectFileEvent` 子类分派**: `Removed`/`Renamed` 被误当
  `Added` → 先检查子类
- **事件类双重定义**: `app/event_bus.py` 与 `core/events.py`
  各有 44 个同名类 → 统一从 `core.events` 重导出
- **`PluginAPI` 死信号**: `plugin_loaded` / `plugin_unloaded`
  从未 emit → 删除
- **快捷键冲突 5 处**:
  - AI 助手: `Ctrl+Shift+E` → `Ctrl+Alt+E`
  - AI 助手: `Ctrl+Shift+R` → `Ctrl+Alt+Shift+R`
  - Markdown 预览: `Ctrl+Shift+M` → `Ctrl+Alt+M`
  - Python 调试器: `F5` → `F6`
  - TODO 面板: `Ctrl+Shift+T` → `Ctrl+Alt+T`
- **每日技巧日期边界**: 手动点击也更新 `last_tip_date` →
  仅自动触发时更新
- **`outline_panel` 硬编码 50000 行**: 改用
  `large_file_threshold` 偏好推导
- **`DirectoryTree` Git 缓存 5 秒过短**: 改为 30 秒 + 可配置
- **`PythonHighlighter` 性能**: 80 条关键字正则合并为 2 条
- **`command_palette` 使用历史 key 冲突**: `title` 改为
  `action_name`
- **`sandbox_policy.DANGEROUS_MODULES` 冗余**: 移除由权限门控的
  `socket` / `shutil` / `subprocess` 等
- **LSP 位置转换**: 用 `SCI_FINDCOLUMN` → 改用字节偏移
- **pytest-qt 绑定**: PySide6 → PyQt5（避免混用崩溃）

### 变更
- **`adapt_qss_colors` 扩表**:
  - `#0d0d0d` → `background`（终端/控制台）
  - `#2a2d2e` / `#333333` / `#4c4c4c` → 面板变体
  - `#858585` / `#808080` / `#c0c0c0` → 次要文字
  - `#007acc` → `input_focus`（聚焦色）
  - `#404040` → `indent_guide`
  - `#5a5a5a` / `#8f1e1e` → 危险按钮
- `tests/conftest.py`: 设置 `PYTEST_QT_API=pyqt5`
- `EditorWidget.keyPressEvent`: 优先让 VimMode 处理

### 删除
- `PluginAPI.plugin_loaded` / `plugin_unloaded`（死信号）
- `sandbox_policy.DANGEROUS_MODULES` 中由权限门控的冗余模块
- 归档 `fix_*.py` 到 `_archive/fixes/`

### 测试
- 198 passed（187 → 198，新增 11 个 Vim 测试）

## [2.0.0] - 2026-09-19

### 新增
- 全新的 PyQt5 架构
- 完整的 LSP 客户端
- 插件系统与沙箱
- 宏录制与回放
- 多光标与列模式
- 命令面板与文件切换
- AI 助手集成
- 代码片段系统
- 主题编辑器
- 性能监控面板
- 会话快照
- 集成终端
- Git 集成
- 自动更新

### 修复
- 编辑器渲染性能
- 大文件加载
- 快捷键冲突检测

### 变更
- 从 PySide6 迁移到 PyQt5
