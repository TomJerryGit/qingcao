# 插件样例与分类说明（P4）

| 插件 | 类型 | 状态 | 说明 |
|---|---|---|---|
| `demo` | 示例 | 启用 | 最小插件模板（菜单/状态/设置/i18n） |
| `my_plugin` | 脚手架示例 | **默认禁用** | `tools/new_plugin.py` 生成的占位示例 |
| `sandbox_demo` | 示例 | 禁用 | manifest `sandbox:true` 只读子进程示例 |
| `wordcount_sandbox` | 沙箱试点 | 启用 | 字数统计只读沙箱样例 |
| `whitespace_sandbox` | 沙箱诊断 | 启用 | 行尾空白/Tab/超长行 |

## 处理原则

- 示例插件保留用于说明扩展点，但默认不干扰普通用户（`my_plugin` 禁用）；
- 市场分类中标记 `sample`/`sandbox`，避免与生产插件混淆；
- 新增插件请以 `demo` 为模板，不使用 `my_plugin` 作为起点。
