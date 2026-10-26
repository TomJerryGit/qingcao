# 青草编辑器 v2.10.0 发布说明

> 发布日期：2026-10-26 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.10.0`）
> 功能版本：包含 v2.9.0 全部内容。

---

## 一句话概括

v2.10.0 完成沙箱插件**配置代理闭环**（协议 → 持久化 → 设置 UI → 启动下发），
并新增 P2 显示环境自检工具与真机验证清单。

---

## 新增 / 改进

### 沙箱插件配置代理（P1 完成）

- **协议层**：受限 `config_schema` / `config_apply`；worker 校验字段类型
  （str/int/float/bool/str_list）、键数与长度，非法值过滤；
- **宿主持久化**：`config_coerce` / `load_plugin_config` /
  `save_plugin_config`（QSettings `Plugin_<name>`，默认值回填、未知键忽略、
  列表 JSON 存储）；
- **设置 UI**：工具 → 🧩 插件菜单 → ⚙ 设置：按 schema 动态渲染
  （bool→复选框、int/float→数值框、str→输入框、str_list→多行），
  保存后写回并 `config_apply` 下发；
- **启动下发**：应用启动后延迟自动读取已保存配置并下发到各沙箱插件。

### P2 真机验证工具

- `tools/verify_display_env.py`：枚举显示器、主屏 DPI/缩放比例、
  Windows 高对比度开关、Qt 缩放环境变量，支持 `--json`；
- `docs/manual_validation_v2.10.md`：跨屏 DPI / 高对比度 / 多实例协作
  的人工验证清单与记录模板。

### 收尾修复

- 修复 worker 通用方法检查误拦 `config_apply` 的问题（插件实际方法
  为 `on_config`）；
- 测试补充：配置协议、持久化、设置 UI、显示环境自检。

---

## 测试

全量 pytest 通过；ruff 0；`tools/check_version` 通过。

---

## 升级注意事项

1. v2.9.0 → v2.10.0 无数据迁移、无接口破坏；
2. 沙箱插件需实现 `config_schema()` / `on_config(values)` 才会出现设置入口；
3. 配置存储于 `QingCao/Plugin_<name>`（便携模式在 data 目录）。

---

## 已知限制

- 跨屏 DPI 与高对比度仍需真机按清单人工验证（工具已就绪）；
- Runner 当前为用户登录 Startup 自启（服务化需管理员凭据）；
- 沙箱插件配置仅在启动与手动保存时下发，暂无实时热更新。

---

## 包校验

发布包由自托管 Runner 构建：

* `QingCaoEditor-v2.10.0-windows.zip`
* `QingCaoEditor-v2.10.0-windows.zip.sha256.txt`
