# 插件商店/更新器 调研 + 改造方案（NPP Plugins Admin 对标）

> 目标：对齐 Notepad++ Plugins Admin 的"兼容性目录 + 一键更新"体验。
> 现状核查：`infrastructure/plugin_updater.py`（1732 行）、
> `ui/plugin_store.py`（2573 行）、`app/plugin_manager.py`（960 行）。

## 一、现状（已具备的能力，不用重造）

| 能力 | 位置 | 说明 |
|---|---|---|
| 更新检查 | `PluginUpdater.check_updates()` | 远程注册表 + 磁盘缓存 + 更新通道（stable/beta）、自动检查定时器 |
| 语义化版本 | `SemVer` | 比较/主版本判定 |
| **批量更新** | `PluginUpdater.update_all(updates)` | **后端已存在** |
| 单插件更新 | `update_plugin(info)` | 下载 → 校验 hash → 备份 → 原子安装 → 失败回滚 |
| 回滚/历史 | `_rollback` / `get_history` | 备份清理策略 |
| 依赖检查 | `_check_dependencies` / `_install_python_dependencies` | 插件依赖 + Python 包 |
| 更新信息结构 | `UpdateInfo` | 已有 `changelog`、`min_app_version`、`is_major`、`is_security`、`channel` |
| 商店侧 | `PluginInfo.has_update()` / `get_dependency_status()` | 已能判断"可更新"/依赖状态 |

## 二、缺口（NPP 有、我们没有）

1. **兼容性门控未生效**：清单里有 `min_app_version`/`max_app_version`，
   但安装/更新路径**没有强制校验** —— 旧应用可能装上新插件直接崩。
   NPP 用 `npp-compatible-version` 在 Plugins Admin 里置灰不兼容版本。
2. **`max_app_version` 在 UpdateInfo 里缺失**（只有 min）。
3. **商店列表不展示兼容性徽章**（不兼容项应置灰+原因 tooltip）。
4. **"全部更新"缺 UI 入口确认**：后端 `update_all()` 存在，
   商店 UI 是否有按钮/进度汇总需核对（本次未改 UI）。
5. **`changelog`/`update_url` 展示**：UpdateInfo 有 changelog 字段，
   商店详情尚未展示；`update_url` 字段不存在。
6. 插件管理器的禁用/启用与商店状态未联动提示（低优先级）。

## 三、本轮已改造（代码）

`infrastructure/plugin_updater.py`：

* `UpdateInfo` 新增 `max_app_version` 字段；
* 新增 `get_app_version()`（读 `version.py`，唯一版本源）；
* 新增 **`is_app_version_compatible(min, max, app_version="")`**：
  - 空约束 = 不限；`min` 超限/`max` 超限都拒绝并给出可读原因；
  - **严格校验版本格式**（`1.2`、`1.2.3`、`1.2.3-beta` 合法；
    `not-a-version` 直接拒绝 —— 防止 SemVer 宽松解析成 0.0.0 而误判兼容）；
* `PluginUpdater.check_compatibility(info)` 便捷包装。

`tests/test_plugin_compatibility.py`（3 项）：
范围判定（min/max/双向）、非法版本拒绝、updater 包装。

## 四、后续改造（建议排期）

**P0（1 天，安全优先）— ✅ 已完成**
1. ✅ `update_plugin()` 入口调用 `check_compatibility()`：不兼容直接返回
   失败 `UpdateResult`，**不下载不安装**；
2. ✅ `update_all()` 循环内跳过不兼容项，汇总里给出"跳过: 原因"。
   测试：`tests/test_plugin_compatibility.py`（门控不触网、批量跳过）。

**P1（2 天，管理体验）**
3. 商店列表加兼容性徽章：✅ 兼容 / ⚠️ 不兼容（tooltip 显示原因）；
   不兼容行禁用"安装/更新"按钮；
4. 商店工具栏加「全部更新」：复用 `update_all()`，显示总数/成功/失败/
   跳过汇总，成功后刷新列表；
5. 详情面板展示 `changelog`（已有字段）与新增 `update_url`。

**P2**
6. 依赖不满足时同样置灰（`get_dependency_status()` 已具备）；
7. 更新失败自动重试一次 + 通知中心汇总。

## 五、与 NPP Plugins Admin 的对照

| 项 | NPP | 青草（本轮后） |
|---|---|---|
| 兼容性元数据 | `npp-compatible-version` | `min/max_app_version` ✅ |
| 兼容性判定实现 | Plugins Admin 内 | `is_app_version_compatible()` ✅ |
| 兼容性门控（拦截安装/更新） | ✅ | ⬜ 下一步（接口已就绪） |
| 一键全量更新 | ✅ | 后端 ✅ / UI ⬜ |
| 更新日志展示 | ✅ | 字段 ✅ / UI ⬜ |
| 回滚 | 无 | ✅（我们更强） |
| 更新通道/自动检查 | 部分 | ✅ |
