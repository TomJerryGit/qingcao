# i18n 英文术语表（v2.20 官方英文版）

> 统一英文界面用词；新增翻译必须遵循本表。语言：en_US。

| 中文 | 英文 | 说明 |
|---|---|---|
| 编辑器 | Editor | 不译作 IDE |
| 面板 | Panel | 侧边栏停靠面板 |
| 大纲 | Outline | 符号大纲 |
| 目录树 | Directory Tree | 文件树 |
| 问题面板 | Problems Panel | LSP 诊断 |
| 全局搜索 | Global Search | 项目级搜索 |
| 命令面板 | Command Palette | |
| 首选项 | Preferences | 设置对话框 |
| 快捷键 | Shortcut | |
| 快捷键方案 | Shortcut Profile | VSCode/Sublime/Vim |
| 主题 | Theme | |
| 高对比度 | High Contrast | |
| 无障碍 | Accessibility | |
| 插件市场 | Plugin Market | |
| 插件 | Plugin | |
| 沙箱 | Sandbox | 沙箱子进程 |
| 会话快照 | Session Snapshot | |
| 增量保存 | Incremental Save | mmap 等长补丁 |
| 行尾符 | Line Ending | LF/CRLF/CR |
| 编码 | Encoding | |
| 状态栏 | Status Bar | |
| 工具栏 | Toolbar | |
| 标签页 | Tab | |
| 工作区 | Workspace | |
| 项目 | Project | |
| 模板 | Template | |
| 片段 | Snippet | |
| 宏 | Macro | |
| 录制/回放 | Record / Replay | |
| 断点 | Breakpoint | |
| 实时沙箱诊断 | Live Sandbox Diagnostics | |
| 依赖 | Dependencies | |
| 权限 | Permissions | |
| 签名 | Signature | Ed25519/HMAC |
| 撤销/重做 | Undo / Redo | |
| 运行当前文件 | Run Current File | F5 |
| 转到定义 | Go to Definition | F12 |
| 查找引用 | Find References | |
| 保存/另存为 | Save / Save As | |
| 未保存 | Unsaved | |
| 只读 | Read-only | |
| 就绪 | Ready | 状态栏 |
| 加载中 | Loading | |

## 规则
1. 按钮/菜单用**首字母大写**的短语（Title Case 适度），避免全大写；
2. 保留占位符（`%s`、`{e}`、`{n}`）与加速键（`(&F)`）；
3. 代码示例、日志前缀（`[MainWindow]`）、内部文档**不翻译**；
4. 产品名 `QingCao Editor` 不翻译；开关名保持简短；
5. 新增词条先查本表，冲突时提交更新本表。


## 繁體中文（zh_TW）術語

| 简体 | 繁體（台灣用法） |
|---|---|
| 文件 | 檔案 |
| 文件夹 | 資料夾 |
| 设置/配置 | 設定 |
| 默认 | 預設 |
| 保存 | 儲存 |
| 另存为 | 另存新檔 |
| 粘贴/复制/剪切 | 貼上/複製/剪下 |
| 撤销 | 復原 |
| 界面 | 介面 |
| 插件/插件市场 | 外掛/外掛市場 |
| 首选项 | 偏好設定 |
| 打印/打印预览 | 列印/預覽列印 |
| 光标 | 游標 |
| 网络/信息 | 網路/資訊 |

生成工具：`python tools/build_zh_tw.py`（OpenCC s2twp + 术语覆盖）。
