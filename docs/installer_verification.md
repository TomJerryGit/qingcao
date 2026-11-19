# Windows 安装器验证（Sprint 4 / task-27）

日期：2026-11-19

## 环境

- Inno Setup 6.7.3（winget 已安装，路径：%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe）
- 修复：`build_installer.py` 增加 per-user Inno 路径；
- 缺失中文语言文件 `ChineseSimplified.isl` → 自动降级英文安装界面编译（`installer_local.iss`）。

## 构建

- 命令：`python build_installer.py`
- 结果：成功
- 产物：`installer/QingCaoEditor_Setup_v2.26.20.exe`（44.89MB）

## 验证

| 路径 | 结果 |
|---|---|
| 静默安装（/DIR=临时目录） | ✅ exit 0，14 个文件，主程序存在 |
| 覆盖安装（升级路径） | ✅ 两次安装均 exit 0 |
| 卸载 | ✅ exit 0，安装目录删除 |

## 遗留

- 中文安装界面需补充 `ChineseSimplified.isl`（当前英文）；
- 安装器资产未纳入 Release（仅本地验证）。

## 补充（2026-11-19）

- 中文语言文件已加入 `installer/ChineseSimplified.isl`（来源：kira-96 翻译项目）；
- 安装器编译**中文界面成功**；
- `ci_publish_release.py` 自动包含安装器资产；
- v2.26.20 Release 已补传：`QingCaoEditor_Setup_v2.26.20.exe`（44.9MB）。
