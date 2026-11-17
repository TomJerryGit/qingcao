# 青草编辑器 v2.5.0 发布说明

> 发布日期：2026-10-22 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.5.0`）
> 基于 v2.4.0，包含其全部内容。

---

## 一句话概括

v2.5.0 聚焦**插件质量与安全**：拼写检查支持忽略词/自定义词典与状态栏
计数；新增**插件安全沙箱审计**（AST 扫描危险能力 + 权限声明校验），
并接入 CI 基线，阻止"低权限声明却联网/起进程/动态执行"的插件合入。

---

## 新增功能

### 拼写检查增强（DSpellCheck 对标）

- **忽略词 / 自定义词典**：`data/spell_ignore.txt`（每行一词、`#` 注释、
  大小写不敏感）；菜单「重新加载忽略词」「编辑忽略词…」（文件不存在自动
  创建模板）；
- **状态栏计数**：检查后显示「拼写: N」，清除后归零；
- 零依赖兜底词表 + 可选 `pyspellchecker` 提升词典质量。

### 插件安全沙箱（P2 第一阶段）

- `infrastructure/plugin_sandbox.py`：AST 扫描危险 import / 调用 /
  `eval/exec/compile` / 写文件；比对 manifest 权限声明；
  判定 `pass / warn / review / reject`；
- `tools/audit_plugins.py` CLI：默认 / `--json` / `--strict` / `--baseline`；
- **CI 接入**：`test.yml` 新增「Plugin security audit」步骤，
  未登记的新插件必须 pass；既有合法项登记在
  `tools/plugin_audit_baseline.json`（如 `python_debugger: review`）。

---

## 修复与改进

- `spell_check` 补齐 `filesystem` 权限（写忽略词文件）——由此暴露并修正
  了权限声明不完整的问题；
- 沙箱判定策略：`eval/compile` 等 danger 项改为**人工评审**而非自动拒绝，
  兼容调试器等合法用途。

---

## 测试

新增/补强：
- `tests/test_spell_check_plugin.py`（7 项：manifest/误报过滤/忽略词/
  FakeApi 行为/状态栏计数）；
- `tests/test_plugin_sandbox.py`（8 项：干净插件、网络/进程/文件系统能力、
  danger 评审、基线比较、基线文件覆盖当前插件）。

全量 pytest 套件通过；ruff 0；`tools/check_version` 通过；审计基线 exit 0。

---

## 升级注意事项

1. v2.4.0 → v2.5.0 无数据迁移；
2. 新增 `data/spell_ignore.txt`（可直接编辑）；
3. 插件开发者：清单权限需与代码实际能力一致，否则 CI 审计失败；
4. 拖放/双击等 v2.4.0 行为不变。

---

## 已知限制

- 内置拼写词表为常用词兜底，专业词建议加忽略词或装 pyspellchecker；
- 沙箱为**静态审计**（准入控制），运行时进程隔离留作后续阶段；
- 真实双显示器 / 跨屏 DPI 变化未物理验证；
- 24h+ 内存泄漏与 IME 组合输入未专项测试；
- Inno Setup 安装包未编译（本机无 ISCC）。

---

## 包校验

发布包由 GitHub Actions 在 `windows-latest` 构建：

* `QingCaoEditor-v2.5.0-windows.zip`
* `QingCaoEditor-v2.5.0-windows.zip.sha256.txt`

```powershell
Get-FileHash .\QingCaoEditor-v2.5.0-windows.zip -Algorithm SHA256
# 与 .sha256.txt 比对
```
