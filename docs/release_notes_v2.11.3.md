# 青草编辑器 v2.11.3 发布说明

> 发布日期：2026-10-27 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.11.3`）
> 维护版本：包含 v2.11.2 全部内容。

---

## 一句话概括

v2.11.3 为开发者信息更新版本：开发者署名由 `hedongwei` 统一更新为
**TomJerry**，功能与 v2.11.2 完全一致。

---

## 变更

- 开发者署名更新为 **TomJerry**（100+ 处），包括：
  - 源码头注释、`main.py` 的 `__author__` / `__copyright__`
  - 帮助 → 关于对话框
  - Windows 安装器发布者（`MyAppPublisher`）
  - 全部内置插件的 `AUTHOR` 与 `plugin.json`
  - README / LICENSE / Dockerfile / docs / requirements 等
- 联系邮箱保持不变（`1265338136@qq.com`）。

---

## 测试

- 分片全量测试（2 片）通过；ruff 0；`tools/check_version` 通过。

---

## 升级注意事项

1. v2.11.2 → v2.11.3 无数据迁移、无接口破坏；
2. 仅元信息变更，功能无差异。

---

## 已知限制

- 跨屏 DPI 与系统高对比度仍需真机人工验证；
- 偶发 offscreen 崩溃已通过分片+重试缓解，持续观察；
- Python 3.12 为软矩阵（不阻塞发布）。

---

## 包校验

发布包由自托管 Runner 构建：

* `QingCaoEditor-v2.11.3-windows.zip`
* `QingCaoEditor-v2.11.3-windows.zip.sha256.txt`
