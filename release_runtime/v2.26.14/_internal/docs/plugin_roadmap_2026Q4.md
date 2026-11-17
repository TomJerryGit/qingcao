# 插件建设与优化路线图（2026 Q4，基于两次分析）

> 输入：`docs/plugin_audit_2026-11-13.md`（14 插件审计，8.0/10）+ `docs/plugin_enhancement_plan.md`（逐插件增强建议）。
> 主线：**安全 → 架构/隔离 → 核心体验 → 覆盖补齐 → 样例与生态**。

## 一、目标（3 个月）

| 指标 | 现状 | 目标 |
|---|---|---|
| 插件总分 | 8.0 | **8.6** |
| manifest 沙箱插件 | 3/14（21%） | **7/14（50%）** |
| 高风险权限在主进程 | 3（git_deep/python_debugger/ai_assistant） | **0**（隔离或强制签名+确认） |
| >1,300 行插件 | 2（ai 3,299 / debugger 1,965） | **0** |
| 核心插件测试 | 1–11 不等 | **≥8 用例/核心插件** |
| 插件激活总量 | ~0.4s（AI 0.28s） | **<0.25s**（拆分+延后） |

## 二、阶段安排（10 周）

### P0 安全与正确性（W1–2，v2.25.3）
| 任务 | 插件 | 验收 |
|---|---|---|
| git 命令参数化（去 shell）+ 超时/输出上限 | git_deep | 无 shell=True；注入用例被拒 |
| AI 网络超时/取消/隐私模式（禁网开关） | ai_assistant | 断网/超时可取消；不阻塞 UI |
| 高风险权限逐次确认 + 签名信任设计 | git_deep/python_debugger/ai_assistant | 未签名/未确认调用被拒 |
| 插件 sandbox 审计纳入 CI（已有阶段 A） | 全部 | 非可信高危 0 |

### P1 架构与隔离扩展（W3–4，v2.26.0）
| 任务 | 插件 | 验收 |
|---|---|---|
| ai_assistant 拆分（Ollama/内联 mixin） | ai_assistant | ✅ 入口 904 行；AI 测试 117 通过 |
| python_debugger 拆分（guards mixin） | python_debugger | ✅ 入口 589 行；debugger 测试 82 通过 |
| 远程面板协议 B2.2（text/markdown） | logtail/todo_panel/markdown_preview | ✅ todo/markdown 隔离可用；logtail 待文件跟随 |
| spell_check 迁标准沙箱运行时 | spell_check | 沙箱启用且诊断 UI 保留 |
| 隔离兼容集合扩展 | 全部 | 可隔离插件 3→6+ |

### P2 核心体验（W5–6，v2.26.1）
| 任务 | 插件 |
|---|---|
| 流式输出/选区操作/diff 预览/Provider 切换 | ai_assistant |
| 分支状态栏、diff 查看、hunk stage、stash/amend | git_deep |
| 条件/日志断点、监视表达式、异常暂停 | python_debugger |
| 用户/项目词典、camelCase 拆分、右键建议 | spell_check |

### P3 覆盖补齐（W7–8，v2.26.2）
| 任务 | 插件 |
|---|---|
| JSONC/JSON5/JSONL + Schema 校验 + 选区格式化 | json_formatter |
| 选区统计/CJK/目标进度/排除注释 | wordcount |
| 多文件标签/过滤高亮/轮转检测/环形缓冲 | logtail |
| 同步滚动/TOC/Mermaid/HTML·PDF 导出 | markdown_preview |
| 点击跳转/分组/自定义模式/编辑器高亮 | todo_panel |
| 一键修复空白/可配置行宽/format-on-save | whitespace_sandbox |

### P4 样例与生态（W9–10，v2.27）
| 任务 | 插件 |
|---|---|
| demo 升级为开发模板（provider/settings/i18n/测试） | demo |
| my_plugin 改为脚手架示例或移出默认目录 | my_plugin |
| wordcount_sandbox 对齐主插件能力（沙箱回归样例） | wordcount_sandbox |
| sandbox_demo 扩展 hover/completion 示例 | sandbox_demo |
| 市场元数据/分类/文档/i18n 补齐 | 全部 |

## 三、按周排期（建议）

| 周 | 交付 |
|---|---|
| W1 | git_deep 去 shell + 权限确认；AI 超时/取消 |
| W2 | AI 隐私模式；高风险签名设计；v2.25.3 |
| W3 | ai_assistant 拆分；远程面板 B2.2 设计 |
| W4 | python_debugger 拆分；logtail/todo 接面板；v2.26.0 |
| W5 | AI 流式/选区/diff；git 状态栏/分支 |
| W6 | debugger 条件断点/监视；spell 词典；v2.26.1 |
| W7 | JSON/wordcount 增强；logtail 过滤/轮转 |
| W8 | markdown/todo/whitespace；v2.26.2 |
| W9 | 样例与市场元数据；测试补齐 |
| W10 | 回归/审计复评；v2.27 规划 |

## 四、依赖与风险

| 依赖/风险 | 缓解 |
|---|---|
| 远程面板协议（B2.2）工作量 | 先支持状态型面板（logtail/todo），markdown 后置 |
| 高风险插件签名信任 | 复用现有 Ed25519 + 密钥轮换；先“逐次确认”后签名 |
| AI 拆分影响体验 | feature flag + 回归测试；保持 API 兼容 |
| 测试覆盖补齐耗时 | 每插件按“权限拒绝/大文件/异常”三类模板补 |
| 插件隔离破坏现有 UI | 默认 off；逐插件灰度（demo/wordcount/json_formatter 已验证） |

## 五、验收与复评

- 每阶段结束：`plugin_audit` 更新评分 + `docs/plugin_enhancement_plan.md` 勾选；
- 安全指标：非可信高危 0；高风险调用均有审计；
- 质量门禁：ruff/format/tests 全绿；核心插件 ≥8 用例；
- 3 个月后复评目标 **8.6/10**。

## 六、立即开始（本周）

1. `git_deep` 去 shell + 参数白名单（P0）；
2. `ai_assistant` 网络超时/取消/隐私开关（P0）；
3. 为两者补权限拒绝/超时测试；
4. 输出 v2.25.3。
