# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""插件扩展点注册（v2.25 从 capability_wiring 拆出）。"""

from ui.mixins.capability_wiring_common import *  # noqa: F401,F403


class PluginsMixin:
    def register_plugin_completion_provider(self, provider, language_ids=None, plugin_name=""):
        """登记插件补全提供者（由 PluginAPI.register_completion_provider 调用）"""
        try:
            providers = getattr(self, "_plugin_completion_providers", None)
            if providers is None:
                providers = []
                self._plugin_completion_providers = providers
            providers.append(
                {
                    "provider": provider,
                    "languages": [str(x).lower() for x in (language_ids or [])],
                    "plugin": plugin_name or "unknown",
                }
            )
            return True
        except Exception as e:
            print(f"[MainWindow] 注册插件补全提供者失败: {e}")
            return False

    def unregister_plugin_completion_provider(self, plugin_name: str):
        """注销某插件的全部补全提供者（插件卸载时）"""
        providers = getattr(self, "_plugin_completion_providers", None)
        if not providers:
            return
        try:
            self._plugin_completion_providers = [
                p for p in providers if p.get("plugin") != plugin_name
            ]
        except Exception:
            pass

    def collect_plugin_completions(
        self, prefix: str, language: str = "", filepath: str = "", limit: int = 50
    ):
        """收集所有插件补全候选（供编辑器调用）

        语言匹配规则：
            * 提供者 language_ids 为空 → 对所有语言生效；
            * 否则语言键（如 "python"）或扩展名（如 ".py"）命中即可。
        """
        out = []
        providers = getattr(self, "_plugin_completion_providers", None) or []
        if not providers or not prefix:
            return out
        lang = (language or "").lower()
        ext = os.path.splitext(filepath or "")[1].lower()
        for entry in providers:
            try:
                langs = entry.get("languages") or []
                if langs and lang not in langs and ext not in langs:
                    continue
                fn = entry.get("provider")
                if not callable(fn):
                    continue
                items = fn(prefix, language=lang, filepath=filepath) or []
                for item in items:
                    if isinstance(item, dict):
                        word = item.get("insert_text") or item.get("label") or ""
                    else:
                        word = str(item)
                    word = word.strip()
                    if word and word not in out:
                        out.append(word)
                        if len(out) >= limit:
                            return out
            except Exception as e:
                print(f"[MainWindow] 插件补全提供者异常({entry.get('plugin')}): {e}")
        return out

    # ========================================================
    # 插件扩展点 v2.4：hover / 右键菜单 / 代码操作 / 状态栏 / 设置
    # ========================================================
    def _ensure_plugin_extension_registries(self):
        for attr, factory in (
            ("_plugin_hover_providers", list),
            ("_plugin_context_actions", list),
            ("_plugin_code_action_providers", list),
            ("_plugin_status_items", list),
            ("_plugin_settings_schemas", dict),
            ("_plugin_symbol_providers", list),
        ):
            if not hasattr(self, attr):
                setattr(self, attr, factory())

    def register_plugin_hover_provider(self, provider, language_ids=None, plugin_name=""):
        """登记插件 hover 提供者"""
        self._ensure_plugin_extension_registries()
        self._plugin_hover_providers.append(
            {
                "provider": provider,
                "languages": [str(x).lower() for x in (language_ids or [])],
                "plugin": plugin_name or "unknown",
            }
        )
        return True

    def collect_plugin_hover(self, filepath: str, line: int, col: int, language: str = "") -> str:
        """收集插件 hover 文本（按语言过滤，多个提供者用空行分隔）"""
        self._ensure_plugin_extension_registries()
        lang = (language or "").lower()
        ext = os.path.splitext(filepath or "")[1].lower()
        parts = []
        for entry in self._plugin_hover_providers:
            try:
                langs = entry.get("languages") or []
                if langs and lang not in langs and ext not in langs:
                    continue
                fn = entry.get("provider")
                if not callable(fn):
                    continue
                text = fn(line, col, filepath=filepath, language=lang)
                if text:
                    parts.append(str(text).strip())
            except Exception as e:
                print(f"[MainWindow] hover 提供者失败({entry.get('plugin')}): {e}")
        return "\n\n".join(p for p in parts if p)[:4000]

    def add_plugin_editor_context_action(self, label: str, callback, plugin_name=""):
        """登记插件编辑器右键菜单项"""
        self._ensure_plugin_extension_registries()
        if not callable(callback):
            return False
        self._plugin_context_actions.append(
            {
                "label": label,
                "callback": callback,
                "plugin": plugin_name or "unknown",
            }
        )
        return True

    def collect_editor_context_actions(self, editor=None):
        """取当前插件的右键菜单项（返回副本，安全迭代）"""
        self._ensure_plugin_extension_registries()
        return list(self._plugin_context_actions)

    def register_plugin_code_action_provider(self, provider, language_ids=None, plugin_name=""):
        """登记插件代码操作提供者"""
        self._ensure_plugin_extension_registries()
        self._plugin_code_action_providers.append(
            {
                "provider": provider,
                "languages": [str(x).lower() for x in (language_ids or [])],
                "plugin": plugin_name or "unknown",
            }
        )
        return True

    def collect_code_actions(self, filepath: str, line: int, col: int, language: str = ""):
        """收集代码操作（统一结构：title/callback/kind）"""
        self._ensure_plugin_extension_registries()
        lang = (language or "").lower()
        ext = os.path.splitext(filepath or "")[1].lower()
        out = []
        for entry in self._plugin_code_action_providers:
            try:
                langs = entry.get("languages") or []
                if langs and lang not in langs and ext not in langs:
                    continue
                fn = entry.get("provider")
                if not callable(fn):
                    continue
                items = fn(line, col, filepath=filepath, language=lang) or []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    title = item.get("title") or item.get("label")
                    callback = item.get("callback") or item.get("run")
                    if title and callable(callback):
                        out.append(
                            {
                                "title": str(title),
                                "kind": str(item.get("kind", "")),
                                "callback": callback,
                                "plugin": entry.get("plugin"),
                            }
                        )
            except Exception as e:
                print(f"[MainWindow] 代码操作提供者失败({entry.get('plugin')}): {e}")
        return out

    def show_plugin_code_actions(self, editor) -> bool:
        """弹出代码操作菜单并执行选中项（右键菜单入口）"""
        try:
            from PyQt5.QtWidgets import QMenu

            line, col = editor.getCursorPosition()
            actions = self.collect_code_actions(
                getattr(getattr(editor, "document", None), "filepath", "") or "",
                line,
                col,
                language=getattr(editor, "_completion_language", lambda: "")(),
            )
            if not actions:
                return False
            menu = QMenu(self)
            for action in actions:
                label = action["title"]
                if action["kind"]:
                    label = "%s（%s）" % (label, action["kind"])
                act = menu.addAction(label)
                act.triggered.connect(lambda _checked=False, cb=action["callback"]: cb())
            menu.exec_(editor.mapToGlobal(editor.cursorRect().bottomRight()))
            return True
        except Exception as e:
            print(f"[MainWindow] 代码操作菜单失败: {e}")
            return False

    def register_plugin_symbol_provider(self, provider, language_ids=None, plugin_name=""):
        """登记插件符号提供者（大纲面板合并）"""
        self._ensure_plugin_extension_registries()
        self._plugin_symbol_providers.append(
            {
                "provider": provider,
                "languages": [str(x).lower() for x in (language_ids or [])],
                "plugin": plugin_name or "unknown",
            }
        )
        return True

    def collect_plugin_symbols(
        self, text: str, filepath: str = "", language: str = "", limit: int = 5000
    ):
        """收集插件符号（规范化为 dict 列表，含 children）"""
        self._ensure_plugin_extension_registries()
        lang = (language or "").lower()
        ext = os.path.splitext(filepath or "")[1].lower()

        def _norm(items, depth=0):
            out = []
            if depth > 8 or not items:
                return out
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("label")
                if not name:
                    continue
                node = {
                    "name": str(name),
                    "type": str(item.get("type") or item.get("kind") or "unknown"),
                    "line": int(item.get("line") or 0),
                    "col": int(item.get("col") or 0),
                    "end_line": int(item.get("end_line") or 0),
                    "indent": int(item.get("indent") or depth),
                    "signature": str(item.get("signature") or ""),
                }
                children = _norm(item.get("children") or [], depth + 1)
                if children:
                    node["children"] = children
                out.append(node)
                if len(out) >= limit:
                    break
            return out

        collected = []
        for entry in getattr(self, "_plugin_symbol_providers", []):
            try:
                langs = entry.get("languages") or []
                if langs and lang not in langs and ext not in langs:
                    continue
                fn = entry.get("provider")
                if not callable(fn):
                    continue
                items = fn(text, filepath=filepath, language=lang) or []
                collected.extend(_norm(items))
                if len(collected) >= limit:
                    break
            except Exception as e:
                print(f"[MainWindow] symbol provider 失败({entry.get('plugin')}): {e}")
        # B-3b：合并沙箱插件的符号（只读代理；失败/降级自动跳过）
        try:
            getter = getattr(self, "_get_sandboxed_plugins", None)
            if callable(getter):
                for sp in getter().values():
                    try:
                        items = sp.symbols(text, filepath or "", lang) or []
                        collected.extend(_norm(items))
                    except Exception:
                        continue
        except Exception:
            pass
        return collected[:limit]

    def register_plugin_settings_schema(self, plugin_name: str, schema):
        """登记插件设置 schema（供设置面板/文档展示；对话框由插件 API 生成）"""
        self._ensure_plugin_extension_registries()
        self._plugin_settings_schemas[plugin_name or "unknown"] = list(schema)
        return True

    def unregister_plugin_extras(self, plugin_name: str):
        """注销某插件的全部 v2.4 扩展点（插件卸载时）"""
        self._ensure_plugin_extension_registries()
        for attr in (
            "_plugin_hover_providers",
            "_plugin_code_action_providers",
            "_plugin_context_actions",
            "_plugin_symbol_providers",
        ):
            current = getattr(self, attr, [])
            setattr(self, attr, [e for e in current if e.get("plugin") != plugin_name])
        schemas = getattr(self, "_plugin_settings_schemas", {})
        schemas.pop(plugin_name, None)

    def add_plugin_status_item(self, widget):
        """把控件加到状态栏右侧（返回控件，由调用方负责移除）"""
        try:
            if self.statusBar() is None:
                return None
            self.statusBar().addPermanentWidget(widget)
            return widget
        except Exception as e:
            print(f"[MainWindow] 添加状态栏项失败: {e}")
            return None

    # ========================================================
    # 面板：LSP 状态 / 撤销历史（对应孤立 UI 文件）
    # ========================================================
