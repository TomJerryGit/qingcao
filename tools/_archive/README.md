# tools/_archive/ - 一次性脚本归档

本目录保存已完成使命的一次性脚本，**仅供历史参考**。

## 脚本列表

| 脚本 | 用途 | 状态 |
|------|------|------|
| `fix_p0.py` | EditorProxy.prov 别名 + OutlinePanel 修复 | ✅ 已应用 |
| `fix_p0_2.py` | prov setter + tabs/plugins 迁移 | ✅ 已应用 |
| `fix_p0_3.py` | provider 显式 open + 草稿保存防御 | ✅ 已应用 |
| `fix_p2p3.py` | AI 404 提示优化 + PNG 清理 | ✅ 已应用 |
| `fix_p3_3.py` | 状态栏组件集成 + 冗余文件清理 | ✅ 已应用 |
| `fix_ai_plugin.py` | AI 插件诊断（缩进/隐藏字符） | ✅ 已应用 |
| `fix_gbk.py` | 批量 GBK → UTF-8 转换 | ✅ 已应用 |
| `fix_health.py` | .gitignore + LICENSE + 文件整理 | ✅ 已应用 |
| `create_all_plugins.py` | 一键创建所有插件骨架 | ✅ 已完成 |

## 如果需要重新执行

**不推荐**——这些脚本已经被 `tools/` 下的正式工具替代：

- `fix_health.py` → `qingcao.py health`
- `fix_ai_plugin.py` → `qingcao.py diagnose-ai`
- 其他 `fix_*` → 均已写入代码，重复执行会显示"已跳过"

## 删除条件

满足以下任一即可安全删除本目录：

1. 项目稳定运行 1 个月无相关回归
2. 项目已发新版本并通过完整回归测试
3. 不再需要追溯历史修复记录
