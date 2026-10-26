# 青草编辑器 v2.9.0 发布说明

> 发布日期：2026-10-26 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.9.0`）
> 功能版本：包含 v2.8.0 全部内容。

---

## 一句话概括

v2.9.0 补全多实例协作（打开/关闭事件、状态提示、实例目录清理、协议版本号），
并让沙箱插件重新拥有**菜单/状态栏能力**（宿主代理），发布流程自带包体积/SHA 报告。

---

## 新增 / 改进

### 多实例事件补全（P0）

- 广播协议新增 **`file_opened` / `file_closed`** 事件，并加**协议版本号**
  （`v: 1`，便于以后兼容旧实例）；
- 宿主接入 `tab_opened/tab_closed`：打开/关闭文件时自动广播；
- 其它实例打开/关闭时状态栏提示（不自动打开远端文件）；
- 保存事件行为不变（未修改自动重载、已修改询问）；
- 启动时**清理已退出实例的配置目录**（Windows 安全存活检测）。

### 沙箱菜单/状态代理（P1）

- 协议层：受限 `menu_items` / `invoke_menu` / `status_text`，
  worker 校验字段（label/id/path 长度、过滤非法项、上限 50）；
- 宿主数据层：`collect_menu_specs()` 统一收集菜单声明；
- UI 层：工具菜单「🧩 插件菜单」动态生成，点击经 RPC 调用插件回调，
  状态栏显示执行结果与插件 `status_text`，支持手动刷新；
- 沙箱插件（如 spell_check）因此保留菜单能力，同时继续在子进程运行。

### 发布质量（P3）

- CI 发布器自动在 Release 正文追加「包信息（自动生成）」：
  ZIP/哈希文件大小 + SHA256。

---

## 测试

新增：
- `tests/test_sandbox_menu_protocol.py`（2 项）
- `tests/test_sandbox_menu_specs.py`（3 项）
- `tests/test_sandbox_menu_ui.py`（3 项）
- 多实例事件/清理相关测试扩展

全量 pytest 通过；ruff 0；`tools/check_version` 通过。

---

## 升级注意事项

1. v2.8.0 → v2.9.0 无数据迁移、无接口破坏；
2. 广播协议向后兼容（旧实例忽略新事件字段）；
3. 沙箱插件需在 `menu_items()` 中声明菜单，否则不显示。

---

## 已知限制

- 多实例广播不含"撤销/重做"等编辑操作事件；
- 沙箱插件配置读写代理尚未实现（P1 后续）；
- 真实双显示器 / 跨屏 DPI 变化未物理验证；
- Runner 当前用 Startup 自启（服务化需管理员凭据）。

---

## 包校验

发布包由自托管 Runner 构建：

* `QingCaoEditor-v2.9.0-windows.zip`
* `QingCaoEditor-v2.9.0-windows.zip.sha256.txt`
