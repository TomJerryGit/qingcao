# QingCao Editor v2.24.3 发布说明（热修复）

> 2026-11-11 · 上一版本：v2.24.2

## 热修复（重要）
- **修复安装包启动崩溃**：`main.py` 拆分后 `app/main_run.py` / `main_helpers.py` 未显式导入 `__version__`，导致启动即 `NameError`；
- 影响版本：**v2.24.1 / v2.24.2 安装包**（源码运行同样受影响）；
- 修复提交：`c661195`，并补充 `tests/test_v224_architecture_split.py::test_main_run_has_version` 回归。

## 同时包含（v2.24.2 之后增量）
- **终端 P2**：ANSI/alt-screen 屏幕模拟（光标/清屏/SGR 颜色/`?1049`/CJK 宽字符）；
- **命令面板分类筛选**：全部/命令/文件/符号/主题/插件；
- **菜单默认快捷键接线修复**：`Ctrl+Shift+M` 等生效；插件卡片「详情」按钮显式化；
- **真实评分上线**：16 个插件真实评分聚合，签名 `ratings.json` 已重发（count=1，average=5.0）。

## 验证
- `check_version` 一致；定向测试通过；CI 全量；
- 发布资产含 ZIP + SHA256 + Ed25519 `.sig`。
