# 贡献指南

欢迎提交 Issue 和 PR。

## 提交 PR 前

- [ ] 本地测试通过：`python -m pytest tests`
- [ ] 静态检查通过：`python -m ruff check .`
- [ ] 版本号一致：`python tools/check_version.py`
- [ ] 如改动了翻译：`python tools/compile_locale.py` 并提交 `.mo`
- [ ] 如适用，已补充/更新测试用例
- [ ] 提交信息清晰（推荐 [Conventional Commits](https://www.conventionalcommits.org/)）

## 开发环境

```bash
git clone https://github.com/qingcao-editor/qingcao.git
cd qingcao
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
python main.py
```

## 项目结构

```
qingcao/
├── main.py                 # 启动入口
├── app/                    # 应用层（动作、事件总线、标签、会话、插件 API）
├── core/                   # 核心层（编辑器、文档、搜索、LSP、撤销、宏）
├── ui/                     # UI 层（主窗口、面板、对话框）
├── infrastructure/         # 基础设施（插件加载、主题、图标、音效）
├── plugins/                # 内置插件
├── themes/                 # 主题
├── resources/              # 图标、音效、启动画面、QSS
├── locale/                 # 翻译（.po / .mo）
├── tools/                  # 开发与维护脚本
├── tests/                  # 测试
└── docs/                   # 本文档
```

## 常见改动指引

| 你要改… | 去哪里 |
|---|---|
| 菜单项 / 快捷键 | `ui/main_window.py` 的 `_add_action(...)` |
| 编辑器行为 | `core/editor.py`（`EditorProxy`） |
| 文件读写与编码 | `core/content_provider.py` |
| 搜索与替换 | `core/search.py`（注意 `_ensure_line_index` 缓存契约） |
| 语言服务 | `core/lsp_client.py` |
| 插件 API | `app/plugins.py`（**请同步更新 `docs/api/index.md`**） |
| 主题适配 | `infrastructure/theme_loader.py` 的 `adapt_qss_colors` |
| 状态栏 | `ui/mixins/status_bar_mixin.py` |

## 测试

```bash
python -m pytest tests                 # 默认套件（快速，约 20 s）
python -m pytest -m realserver         # 需要 python-lsp-server
python -m pytest tests/test_search_performance.py -v   # 性能回归
```

### 写测试的两个经验教训

本仓库有过两次"测试全绿但功能不可用"的情况，值得注意：

1. **纯逻辑单测覆盖不到跨进程路径。**
   LSP 的 `initialize()` 曾调用一个不存在的方法，纯单测无法发现；
   是 `tests/test_lsp_integration.py`（启动真实子进程 LSP 服务器）
   抓出来的。
   > 注意：等待 Qt 跨进程信号必须用 `pytest-qt` 的
   > `qtbot.waitUntil`，用 `time.sleep` 轮询收不到信号。

2. **性能缺陷需要规模负载才能暴露。**
   搜索曾是 O(n²)，小文件测不出来；`tests/test_search_performance.py`
   用"多匹配 + 中等体积"把复杂度卡住，并已验证：临时换回旧实现会
   使该文件 2 项失败、总耗时从 1.3 s 膨胀到 180 s。

## 代码风格

- 行宽 100，由 `ruff` 统一（配置见 `pyproject.toml`）
- **不要**引入新的 `F821`（未定义名）/ `F811`（重定义）
- 延迟导入是刻意设计（`main.py` 用它压低启动耗时），不要"优化"掉
- 中文注释与全角标点是允许的

## 文档

- 用户向文档在 `docs/`（MkDocs Material）
- 本地预览：`mkdocs serve`
- 构建：`mkdocs build --strict`

## 报告 Bug

请提供：

1. 操作系统与版本
2. 青草版本（帮助 → 关于）
3. Python 版本
4. 复现步骤
5. 期望行为 / 实际行为
6. `logs/runtime.log` 与 `crash.log` 的相关片段

## 提交信息约定

```
fix(search): 消除 _get_line_text 的 O(n²) 退化
feat(plugins): 支持插件热重载
chore(repo): 清理备份文件
docs(api): 补充 PluginAPI 参考
```

范围（scope）建议用模块名：`search` / `save` / `lsp` / `plugins` / `ui` /
`repo` / `docs` / `tools`。

## 许可

贡献的代码默认以 MIT License 授权。
