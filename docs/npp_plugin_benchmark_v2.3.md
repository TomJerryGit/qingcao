# Notepad++ 插件体系对比与借鉴（v2.3）

> 目的：对照 Notepad++ 的成熟插件生态，找出本软件插件系统的**结构性差距**，
> 给出可排期的改进项。所有"青草现状"均来自本仓库代码核查（2026-10）。

## 一、两套插件模型的根本差异

| 维度 | Notepad++ | 青草编辑器 |
|---|---|---|
| 语言/绑定 | 原生 DLL，C ABI（`pluginapi.h`） | Python 模块（进程内 import） |
| 接口形态 | **函数指针表 + `NPPM_*` 消息**（宿主→插件 `beNotified` 收 `NPPN_*`） | **`PluginAPI` 对象**（90+ 方法，信号/事件订阅） |
| 版本兼容 | 头文件按 API 版本演进，插件编译期绑定 | `api_version` + `min/max_app_version` 清单声明 |
| 能力探测 | 函数表存在性 + `NPPM_GETNPPVERSION` | 本轮新增 `api.get_api_capabilities()` |
| 事件通知 | `NPPN_BUFFERACTIVATED` 等固定通知集 | 15 个事件总线事件（`api.subscribe`） |
| 崩溃隔离 | **无**（DLL 崩溃拖垮整个 Notepad++） | 同为进程内（更危险：Python 异常可控但 Qt 崩溃会带走进程） |
| 权限模型 | **无**（DLL 有完整进程权限） | **有**（10 种权限 + 用户确认 + 卸载清理） |
| 安装/更新 | Plugins Admin（官方目录、一键安装/更新/卸载） | 插件商店（安装/卸载/更新检查）+ 本地目录安装 |
| 热重载 | 不支持（需重启） | **支持**（`reload_plugin`，开发模式可加保存即重载） |
| 语言扩展 | UDL（用户自定义语言，声明式）+ Lexer 插件 | `register_lexer`（代码式）+ 4 主题；**缺声明式语言定义** |
| 函数列表 | `functionList.xml` + 插件可注册 parser | 大纲面板（内建解析）；**缺插件 symbol provider** |
| 自动补全配置 | 每语言 XML（关键字/调用提示）可扩展 | 内建 LocalCompleter + `register_completion_provider`（代码式） |
| 本地化 | 插件菜单名可随 nativeLang 本地化 | 仅中文（已决策，暂不做 i18n） |

## 二、Notepad++ 做得更好、值得借鉴的 8 点

1. **能力探测（本轮已落地）**
   NPP 插件拿到 `NppData` 后先看函数表/版本再决定功能；我们新增
   `get_api_capabilities()`，第三方插件可以：
   ```python
   caps = api.get_api_capabilities()
   if caps["extension_points"].get("completion"):
       api.register_completion_provider(self.suggest)
   ```
   避免"盲试 API → 旧宿主 AttributeError"。

2. **通知目录可枚举（本轮已落地）**
   NPP 文档列全 `NPPN_*`；我们新增 `api.list_events()`（15 个），
   并在 conformance 中锁定事件目录下限。

3. **声明式语言定义（UDL 等价物）—— P0 路线**
   NPP 最大众的功能之一：用户不写代码就能加一门语言的语法高亮/折叠/
   注释规则（UDL XML）。我们目前只能用 `register_lexer` 写代码。
   建议新增 `language_pack`（JSON）：
   ```json
   {"extensions": [".mylang"], "keywords": ["if","else"],
    "line_comment": "//", "block_comment": ["/*","*/"],
    "strings": ["\"", "'"], "folding": {"start":"{","end":"}"}}
   ```
   宿主用通用 `QsciLexerCustom` 实现；插件/用户目录均可投放。
   **工程量：~1.5 天；收益：把"加语言"从写代码降为写 JSON。**

4. **函数列表 ⇒ 插件 symbol provider —— P0 路线**
   NPP `functionList.xml` 允许用户/插件贡献解析器。我们大纲面板是内建
   解析，建议新增：
   ```python
   api.register_symbol_provider(language_ids, parser)
   # parser(text, filepath) -> [{"name","kind","line","children"}]
   ```
   并在 `OutlinePanel` 里合并插件符号。
   **工程量：~1 天；收益：新语言无需改宿主即可进大纲。**

5. **Plugins Admin 的"兼容性目录" —— P1 路线**
   NPP 目录里每个插件带 `npp-compatible-version`，Plugins Admin 据此
   灰掉不兼容版本。我们清单已有 `min/max_app_version`，但商店 UI 尚未
   展示/拦截。建议：商店列表显示兼容性徽章 + "全部更新"按钮。

6. **插件工具栏图标 —— P1**
   NPP 插件可注册工具栏图标（`NPPM_ADDTOOLBARICON`）。我们有
   `add_toolbar_action(icon=...)`，但 UI 图标体系仍是 emoji（已在优化
   计划中列为 SVG 化）。图标体系完成后插件即可提供一致图标。

7. **通知的"生命周期保证"要写清楚 —— P1 文档**
   NPP 文档明确通知顺序（如 shutdown 前先 bufferactivated）。我们的
   事件总线没有成文的顺序/线程保证：建议在 SDK 文档中声明
   "全部事件在主线程派发、`file_saved` 在磁盘写入成功后发出、
   `theme_changed` 在 QSS 应用后发出"，并加对应用例。

8. **插件模板与 SDK 一致性 —— P1**
   NPP 有 `pluginTemplate` / `NppPluginTemplate` 与头文件。我们有
   conformance 契约（扩展点/清单/API 面）与真实插件样例，
   还缺"一键生成插件骨架"（`工具 → 新建插件` / CLI）。

## 三、青草比 Notepad++ 做得更好的地方（不要丢）

| 项 | 说明 |
|---|---|
| **权限模型** | NPP 插件完全无沙箱；我们有 10 种权限 + 用户确认 + 会话记忆 |
| **热重载** | NPP 要重启；我们支持 `reload_plugin`（可加保存即重载） |
| **扩展点覆盖** | 我们已有 9 个编辑器智能扩展点（补全/诊断/hover/代码操作/右键菜单/状态栏/装饰/后台任务/设置） |
| **后台任务安全** | `run_background` 带主线程回调 + 卸载取消（NPP 无此概念） |
| **conformance 契约** | 9 条扩展点契约 + 清单 AST + 能力探测契约，NPP 生态没有 |
| **故障可诊断** | 插件错误面板/日志 + 失败隔离 try/except；NPP 崩溃即全军覆没 |

## 四、建议排期（按"借鉴性价比"排序）

**P0（1~2 周，直接扩大生态宽度）**
1. 声明式语言定义（UDL 等价物，JSON → 通用 lexer）
2. 插件 symbol provider → 大纲面板合并
3. 事件目录/能力探测文档化（本轮已完成 API，补 SDK 文档示例）

**P1（2~3 周，插件管理体验对齐 Plugins Admin）**
4. 商店兼容性徽章 + 全部更新 + 更新日志字段（`changelog`/`update_url`）
5. 插件模板脚手架（`python tools/new_plugin.py --name foo`）
6. 事件生命周期/线程保证写入 SDK 文档 + 用例

**P2（生态与隔离）**
7. 插件子进程沙箱（不可信插件）
8. 插件工具栏图标随 SVG 图标体系落地
9. 本地化（若未来需要多语言）

## 五、后续已落地（代码）

* **P0-1 声明式语言包（UDL 等价物）**：`core/language_pack.py` +
  `ui/generic_lexer.py`，JSON 定义语言，见 `docs/language_packs.md`。
* **P0-2 插件 symbol provider**：`api.register_symbol_provider()` →
  「大纲」面板合并（等价 NPP `functionList.xml`）；
  `markdown_preview` 已实际用其提供标题大纲；
  大纲在插件 provider 增减时自动重解析。

## 六、最初落地记录（能力探测 + 事件目录）

* `api.get_api_capabilities()`：能力探测（9 个扩展点 + 事件目录 + 权限）
* `api.list_events()`：15 个可订阅事件可枚举
* conformance 新增 `test_api_capabilities_and_event_catalog`
