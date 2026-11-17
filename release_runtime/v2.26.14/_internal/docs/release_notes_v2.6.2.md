# 青草编辑器 v2.6.2 发布说明

> 发布日期：2026-10-26 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.6.2`）
> 维护版本：包含 v2.6.1 全部内容 + 以下 CI 修复。

---

## 一句话概括

v2.6.2 修复自托管 CI 的两个稳定性问题：conformance 契约在 CI 时序下的
误报、测试日志编码问题；功能与 v2.6.1 完全一致。

---

## 修复

### conformance 契约 CI 误报

- 现象：`test_extension_contracts` 在自托管 Runner 上稳定失败，
  本地却通过；
- 根因：`editor-context-menu` 契约断言"清理后右键菜单全局为空"，
  而内置插件 json_formatter 的菜单项是合法存在，CI 上插件激活时序
  不同导致暴露；
- 修复：契约只断言"本插件自己注册的项被清理"，不再要求全局为空。

### 测试日志编码

- 现象：CI 失败时本地 `test.log` 为 UTF-16，无法直接检索；
- 修复：测试输出显式以 UTF-8 写入日志，失败用例可直接定位。

---

## 基础设施

- 自托管 Runner 增加**用户登录自启动**（Startup 脚本，保留 SSH key
  与 Python 环境），重启后无需手动启动；
- 发布继续使用 `tools/ci_publish_release.py`（Python/标准库实现，
  幂等、重试、资产校验）。

---

## 升级注意事项

1. v2.6.1 → v2.6.2 无数据迁移、无接口变化；
2. 仅 CI/测试稳定性修复。

---

## 包校验

发布包由自托管 Runner 构建：

* `QingCaoEditor-v2.6.2-windows.zip`
* `QingCaoEditor-v2.6.2-windows.zip.sha256.txt`
