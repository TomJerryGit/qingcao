# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""AI 配置对话框（v2.24 拆出）。"""

from .ai_common import *  # noqa: F401,F403,F405


class AIConfigDialog(QDialog):
    """
    AI 配置对话框。

    配置 Provider / API Key / Model / Base URL。
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("AI 助手配置")
        self.resize(520, 420)

        self._build_ui()
        self._apply_style()
        self._load_settings()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 说明
        info = QLabel(
            "配置 AI 服务。支持 OpenAI、DeepSeek、Ollama（本地）、"
            "通义千问、Moonshot、智谱 GLM、Claude 等。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888; padding: 8px; font-size: 12px;")
        layout.addWidget(info)

        # 表单
        form = QFormLayout()

        # Provider
        self.provider_combo = QComboBox()
        if AIClientFactory:
            try:
                providers = AIClientFactory.list_providers()
                for key, display in providers:
                    self.provider_combo.addItem(display, key)
            except Exception:
                self._add_fallback_providers()
        else:
            self._add_fallback_providers()

        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("提供商:", self.provider_combo)

        # API Key
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("sk-...")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        form.addRow("API Key:", self.api_key_edit)

        # Model
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        form.addRow("模型:", self.model_combo)

        # Base URL
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("留空使用默认地址（如 https://api.openai.com/v1）")
        form.addRow("Base URL:", self.base_url_edit)

        layout.addLayout(form)

        # Ollama 探测结果提示（仅在 provider=ollama 时显示）
        self.ollama_hint = QLabel("")
        self.ollama_hint.setWordWrap(True)
        self.ollama_hint.setStyleSheet("color: #4ec9b0; font-size: 11px; padding: 4px 0;")
        self.ollama_hint.setVisible(False)
        layout.addWidget(self.ollama_hint)

        # 结果缓存开关
        self.cache_check = QCheckBox("复用结果缓存（相同代码 + 相同动作不重复请求）")
        self.cache_check.setToolTip(
            "开启后，若 provider / 模型 / 温度 / token 上限 / 提示词完全相同，\n"
            "直接显示上次结果，省一次请求。\n"
            "多轮追问不使用缓存。缓存仅存内存，退出即清空。\n"
            "如需强制重新生成，取消勾选此项。"
        )
        try:
            self.cache_check.setChecked(
                QSettings("QingCao", "AI").value("result_cache", True, type=bool)
            )
        except Exception:
            self.cache_check.setChecked(True)
        layout.addWidget(self.cache_check)

        # 会话窗口开关
        self.session_check = QCheckBox("复用同一个 AI 对话窗口（非模态，保留上下文）")
        self.session_check.setToolTip(
            "开启（默认）：所有 AI 动作共用一个非模态窗口，\n"
            "切换标签、继续操作都不会丢上下文，可直接追问。\n"
            "关闭：每次动作弹一个独立模态对话框（旧行为）。"
        )
        try:
            self.session_check.setChecked(
                QSettings("QingCao", "AI").value("session_window", True, type=bool)
            )
        except Exception:
            self.session_check.setChecked(True)
        layout.addWidget(self.session_check)

        # 隐私模式（禁网）
        self.privacy_check = QCheckBox("隐私模式（禁止联网：不使用任何远程 AI 服务）")
        self.privacy_check.setToolTip(
            "开启后拒绝所有网络请求；仅影响本插件发起的外部调用。\n"
            "适合敏感代码/离线环境；本地 Ollama 不受影响。"
        )
        try:
            self.privacy_check.setChecked(
                QSettings("QingCao", "AI").value("privacy_mode", False, type=bool)
            )
        except Exception:
            self.privacy_check.setChecked(False)
        layout.addWidget(self.privacy_check)

        # 提示
        hint = QLabel(
            "💡 提示：\n"
            "  · Ollama 本地模型无需 API Key；模型列表会自动从本机 Ollama 读取\n"
            "  · 更完整的模型管理（拉取/删除/已加载）见：工具 → AI 助手 → 🦙 Ollama 管理面板\n"
            "  · API Key 存储在 QSettings（明文），请勿在共享环境使用"
        )
        hint.setStyleSheet("color: #888; font-size: 11px; padding: 8px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()

        # 按钮
        btn_layout = QHBoxLayout()

        self.test_btn = QPushButton("🔌 测试连接")
        self.test_btn.clicked.connect(self._on_test)
        btn_layout.addWidget(self.test_btn)

        btn_layout.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        btn_layout.addWidget(buttons)

        layout.addLayout(btn_layout)

    def _add_fallback_providers(self):
        """添加后备提供商列表"""
        fallback = [
            ("OpenAI", "openai"),
            ("Ollama (本地)", "ollama"),
            ("DeepSeek", "deepseek"),
            ("通义千问", "qwen"),
            ("Moonshot", "moonshot"),
            ("智谱 GLM", "zhipu"),
            ("Anthropic Claude", "claude"),
        ]
        for display, key in fallback:
            self.provider_combo.addItem(display, key)

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QLabel { color: #d4d4d4; }
            QLineEdit, QComboBox {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
                min-height: 20px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #007acc;
            }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: #d4d4d4;
                selection-background-color: #094771;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 14px;
                font-size: 12px;
                min-width: 70px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #666;
            }
        """)

    def _load_settings(self):
        """加载已有配置"""
        try:
            settings = QSettings("QingCao", "AI")
            provider = settings.value("provider", "openai", type=str)
            api_key = settings.value("api_key", "", type=str)
            model = settings.value("model", "", type=str)
            base_url = settings.value("base_url", "", type=str)

            # 选中 provider
            for i in range(self.provider_combo.count()):
                if self.provider_combo.itemData(i) == provider:
                    self.provider_combo.setCurrentIndex(i)
                    break

            self.api_key_edit.setText(api_key)
            self.model_combo.setCurrentText(model)
            self.base_url_edit.setText(base_url)
            try:
                self.privacy_check.setChecked(settings.value("privacy_mode", False, type=bool))
            except Exception:
                pass

            # 更新模型列表
            self._on_provider_changed()

        except Exception as e:
            print(f"[AI插件] 加载配置失败: {e}")

    def _on_provider_changed(self):
        """Provider 变化 → 更新模型列表"""
        provider = self.provider_combo.currentData()

        # 清空
        self.model_combo.clear()

        # 从工厂获取默认模型
        models = []
        if AIClientFactory:
            try:
                models = AIClientFactory.get_default_models(provider)
            except Exception:
                pass

        # 后备默认模型
        if not models:
            defaults = {
                "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
                "ollama": ["llama3.2", "llama3.1", "qwen2.5"],
                "deepseek": ["deepseek-chat", "deepseek-coder"],
                "qwen": ["qwen-plus", "qwen-turbo", "qwen-max"],
                "moonshot": ["moonshot-v1-8k"],
                "zhipu": ["glm-4", "glm-4-plus", "glm-4-flash"],
                "claude": [
                    "claude-3-5-sonnet-20241022",
                    "claude-3-5-haiku-20241022",
                ],
            }
            models = defaults.get(provider, [])

        # Ollama：优先用本地服务真实安装的模型（覆盖硬编码列表）
        # 硬编码列表只是"连不上时"的兜底提示，避免下拉框为空。
        ollama_note = ""
        if provider == "ollama":
            models, ollama_note = self._fetch_ollama_models(models)

        for m in models:
            self.model_combo.addItem(m)

        # Ollama 不需要 API Key
        if provider == "ollama":
            self.api_key_edit.setPlaceholderText("（本地模型无需 Key）")
        else:
            self.api_key_edit.setPlaceholderText("sk-...")

        # 把 Ollama 的探测结果提示给用户
        if ollama_note:
            try:
                self.ollama_hint.setText(ollama_note)
                self.ollama_hint.setVisible(True)
            except Exception:
                pass
        else:
            try:
                self.ollama_hint.setVisible(False)
            except Exception:
                pass

    def _fetch_ollama_models(self, fallback: List[str]):
        """向本机 Ollama 查询已安装模型。

        返回 (模型名列表, 提示文本)。查询失败时回退到 fallback，
        并把失败原因作为提示返回 —— 不阻塞、不抛异常。
        """
        try:
            host = self.base_url_edit.text().strip() or OllamaClient.DEFAULT_HOST
            # base_url 可能是 OpenAI 兼容端点（带 /v1），去掉后用于原生 API
            host = host.rstrip("/")
            if host.endswith("/v1"):
                host = host[:-3]
            cli = OllamaClient(host)
            ok, models = cli.list_models()
            if not ok:
                return fallback, (
                    "⚠️ 未能连接 Ollama（%s）。下拉框显示的是"
                    "常见模型名，请确认服务已启动：ollama serve" % host
                )
            if not models:
                return fallback, (
                    "⚠️ Ollama 已连接，但尚未安装任何模型。"
                    "先运行：ollama pull qwen2.5:7b   "
                    "（或使用 工具 → AI 助手 → 🦙 Ollama 管理面板）"
                )
            names = [m["name"] for m in models]
            return names, (
                "✅ 已从本机 Ollama 读取 %d 个模型：%s"
                % (len(names), "、".join(names[:5]) + ("…" if len(names) > 5 else ""))
            )
        except Exception as e:
            return fallback, "⚠️ 查询 Ollama 失败：%s" % e

    def _on_test(self):
        """测试连接"""
        provider = self.provider_combo.currentData()
        api_key = self.api_key_edit.text().strip()
        model = self.model_combo.currentText().strip()
        base_url = self.base_url_edit.text().strip()

        if provider != "ollama" and not api_key:
            QMessageBox.warning(self, "测试失败", "请先填写 API Key")
            return

        if not _AI_CLIENT_OK:
            QMessageBox.warning(self, "测试失败", "core.ai_client 模块不可用，无法测试连接")
            return

        if not _requests_ok():
            QMessageBox.warning(self, "测试失败", "缺少 requests 库\n请运行: pip install requests")
            return

        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中...")

        try:
            client = AIClientFactory.create(
                provider=provider,
                api_key=api_key,
                model=model,
                base_url=base_url,
            )

            result = client.chat(
                prompt="请回复：OK",
                system="你是一个测试助手，只需回复 OK。",
            )

            QMessageBox.information(self, "测试成功", f"✓ 连接成功！\n\n返回：{str(result)[:200]}")
        except Exception as e:
            QMessageBox.critical(self, "测试失败", f"✗ 连接失败：\n\n{e}")
        finally:
            self.test_btn.setEnabled(True)
            self.test_btn.setText("🔌 测试连接")

    def _on_save(self):
        """保存配置"""
        provider = self.provider_combo.currentData()
        api_key = self.api_key_edit.text().strip()
        model = self.model_combo.currentText().strip()
        base_url = self.base_url_edit.text().strip()

        try:
            settings = QSettings("QingCao", "AI")
            settings.setValue("provider", provider)
            settings.setValue("api_key", api_key)
            settings.setValue("model", model)
            settings.setValue("base_url", base_url)
            # 结果缓存开关
            try:
                settings.setValue("result_cache", self.cache_check.isChecked())
                settings.setValue("session_window", self.session_check.isChecked())
                settings.setValue("privacy_mode", self.privacy_check.isChecked())
            except Exception:
                pass
            settings.sync()

            QMessageBox.information(self, "保存成功", "AI 配置已保存")
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))


# ============================================================
# Ollama 管理面板
# ============================================================
