# i18n 迁移计划（v2.18.x P3 脚手架）

## 当前状态

- UI 全中文；此前移除"假语言开关"（仅中文）。
- 本次新增**轻量 i18n 脚手架**，不做全量 tr() 改造。

## 脚手架

| 组件 | 作用 |
|---|---|
| `core/i18n_json.py` | `tr(text)`：按 `locale/<lang>/strings.json` 映射，未命中回退原文 |
| `tools/extract_i18n_strings.py` | AST 扫描 ui/core/app，提取中文串生成模板 |

```powershell
python tools/extract_i18n_strings.py
# -> locale/zh_CN/strings.json（键值=原文，作为翻译模板）
```

## 迁移路径（后续版本）

1. 新增 `locale/en_US/strings.json`，翻译模板条目（可分批）；
2. UI 字符串逐步改为 `tr("中文原文")`（保持回退安全）；
3. 设置页恢复语言选项（仅当覆盖率达到阈值，如 90%）；
4. 长期：切换到 gettext/mo 或 Fluent，支持复数/变量。

## 为什么不做全量 tr()

- 全仓数万条 UI 字符串，一次性改造回归风险极高；
- 当前无英文翻译资源，先搭建提取→翻译→替换的流水线更可控。

## 验收

- `tr()` 未命中回退原文（安全）；
- 提取工具可重复执行、输出稳定排序；
- 新增测试覆盖两者。


## 进展（2026-11-03）

- ✅ 语言菜单（设置 → 界面语言，重启生效）；
- ✅ 菜单/欢迎页翻译（170+ 动作，含 emoji/加速键匹配）；
- ✅ 偏好页/对话框：通用控件树翻译 `ui/i18n_widgets.py`；
- ✅ 英文词典 161 条；覆盖率报告 `docs/i18n_coverage_report.md`；
- ⏳ 长尾：`locale/zh_CN/strings.json` 模板 5218 条继续分批翻译。
