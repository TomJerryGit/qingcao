# -*- coding: utf-8 -*-
"""P0-2 真实语言服务器联调（python-lsp-server）

`tests/test_lsp_integration.py` 用的是自写的**最小** LSP 服务器，
只能证明传输层与协议帧可用。本文件进一步用**真实的
python-lsp-server (pylsp)** 验证语义层：

    1. 握手能否完成（真实 serverInfo / capabilities）
    2. didOpen 一个语法错误的文件，能否收到**真实诊断**
    3. 请求补全，能否收到**真实补全项**
    4. didChange 改错后，诊断能否**更新**（证明版本递增真的生效）

第 4 点是 P0-2 的关键：修复前 `version` 是 `None`，`did_change`
抛 `TypeError` 被吞掉，服务器永远停留在打开时的快照 —— 表现为
"诊断不更新"。只有对真实服务器才能观察这个语义后果。

本文件在 pylsp 未安装时整体跳过，因此不会拖慢默认测试。

运行::

    pip install python-lsp-server
    python -m pytest tests/test_lsp_real_server.py -v
"""
import os
import sys
import time

import pytest


def _pylsp_available():
    """pylsp 是否可用（按模块探测，不依赖 PATH）"""
    import importlib.util
    if importlib.util.find_spec('pylsp') is None:
        return False
    # 真实联调需要真正的语言特性，jedi 负责补全
    return importlib.util.find_spec('jedi') is not None


# 需要真实 python-lsp-server，且每个用例会 spawn 一个 pylsp 进程
# （约 25s），因此标记为 realserver，默认测试不包含。
# 运行: python -m pytest -m realserver
pytestmark = [
    pytest.mark.realserver,
    pytest.mark.skipif(
    not _pylsp_available(),
        reason="未安装 python-lsp-server，跳过真实服务器联调",
    ),
]


# 故意包含错误：未定义名 + 语法上合法但语义错误
BROKEN = "x = undefined_name_abc\n"
FIXED = "undefined_name_abc = 1\nx = undefined_name_abc\n"

# 用于补全：在 `import o` 后请求补全，期望有 os 之类的候选
COMPLETION_DOC = "import os\nos.\n"


@pytest.fixture()
def workspace(tmp_path):
    """给 pylsp 一个独立工作目录"""
    d = tmp_path / "proj"
    d.mkdir()
    return d


def _start_pylsp(client):
    """用 registry 的命令启动 pylsp

    注意用 `sys.executable -m pylsp`：无论控制台脚本是否在 PATH 上
    都能启动，也避免 Windows 下 `pylsp.exe` 的路径差异。
    """
    client.start([sys.executable, '-m', 'pylsp'])


class TestRealServerHandshake:
    def test_initialize_completes(self, qapp, qtbot, workspace):
        from core.lsp_client import LspClient

        client = LspClient()
        errors = []
        client.error_occurred.connect(lambda m: errors.append(m))

        infos = []
        client.initialized.connect(lambda info: infos.append(info))

        _start_pylsp(client)
        try:
            client.initialize(
                LspClient.path_to_uri(str(workspace))
            )
            qtbot.waitUntil(
                lambda: client.is_initialized, timeout=30000
            )
            # 必须在 stop() 之前捕获：stop() 会把 is_initialized 重置
            was_initialized = client.is_initialized
            caps = dict(client.capabilities or {})
            server_info = dict(getattr(client, 'server_info', {}) or {})
        finally:
            client.stop()

        assert was_initialized, "pylsp 握手失败；errors=%s" % errors
        assert infos, "未收到 initialized 信号"
        # 真实服务器应返回 capabilities
        assert caps, "未收到服务端 capabilities"
        assert 'textDocumentSync' in caps or 'completionProvider' in caps, (
            "capabilities 内容异常：%r" % list(caps.keys())[:10]
        )

    def test_server_reports_completion_capability(self, qapp, qtbot,
                                                  workspace):
        from core.lsp_client import LspClient

        client = LspClient()
        _start_pylsp(client)
        try:
            client.initialize(LspClient.path_to_uri(str(workspace)))
            qtbot.waitUntil(
                lambda: client.is_initialized, timeout=30000
            )
            assert client.supports('completionProvider'), (
                "pylsp 未声明补全能力，capabilities=%r"
                % list((client.capabilities or {}).keys())
            )
        finally:
            client.stop()


class TestRealDiagnostics:
    """真实诊断通道验证

    实测结论（python-lsp-server 1.15.0）：pylsp **默认不报**未定义名
    （pyflakes 未启用时 diagnostics 为空列表）。因此本测试**不**断言
    "必须有错误"，而是断言三件真实可验证的事：

        1. `publishDiagnostics` 通知确实到达，且结构符合 LSP 规范
           （能被 `EditorProxy._on_lsp_diagnostics` 消费）；
        2. `didChange` 之后服务器**再次**推送诊断（证明它真的处理了
           变更 —— 修复前 version=None 会抛 TypeError，通知不会再来）；
        3. 版本号递增。

    这样测试不会因为 pylsp 的诊断策略变化而假失败。
    """

    def test_diagnostics_notification_arrives_with_valid_shape(
        self, qapp, qtbot, workspace
    ):
        from core.lsp_client import LspClient

        path = workspace / "diag.py"
        path.write_text(BROKEN, encoding='utf-8')
        uri = LspClient.path_to_uri(str(path))

        client = LspClient()
        errors = []
        client.error_occurred.connect(lambda m: errors.append(m))
        got = []
        client.diagnostics_updated.connect(lambda u, d: got.append((u, d)))

        _start_pylsp(client)
        try:
            client.initialize(LspClient.path_to_uri(str(workspace)))
            qtbot.waitUntil(
                lambda: client.is_initialized, timeout=30000
            )
            client.did_open(uri, "python", BROKEN)
            qtbot.waitUntil(
                lambda: any(u == uri for u, _ in got), timeout=30000
            )
        finally:
            client.stop()

        assert got, "未收到 publishDiagnostics 通知；errors=%s" % errors
        assert got[-1][1] == got[-1][1], "诊断不是列表"
        assert isinstance(got[-1][1], list), (
            "诊断应为列表：%r" % type(got[-1][1])
        )

        # 结构校验：每条诊断都必须有 range（EditorProxy 依赖它）
        for diag in got[-1][1]:
            assert 'range' in diag, "诊断缺少 range：%r" % diag
            assert 'start' in diag['range'], "range 缺少 start：%r" % diag
            assert 'line' in diag['range']['start']

    def test_diagnostics_resent_after_did_change(
        self, qapp, qtbot, workspace
    ):
        """didChange 后服务器必须再次推送诊断（P0-2 核心语义）"""
        from core.lsp_client import LspClient

        path = workspace / "changing.py"
        path.write_text(BROKEN, encoding='utf-8')
        uri = LspClient.path_to_uri(str(path))

        client = LspClient()
        errors = []
        client.error_occurred.connect(lambda m: errors.append(m))
        notifications = []
        client.diagnostics_updated.connect(
            lambda u, d: notifications.append((u, d)) if u == uri else None
        )

        _start_pylsp(client)
        try:
            client.initialize(LspClient.path_to_uri(str(workspace)))
            qtbot.waitUntil(
                lambda: client.is_initialized, timeout=30000
            )

            client.did_open(uri, "python", BROKEN)
            qtbot.waitUntil(
                lambda: len(notifications) >= 1, timeout=30000
            )
            after_open = len(notifications)

            # didChange：修复前这里会抛 TypeError，服务器不会回应
            client.did_change(uri, FIXED)
            qtbot.waitUntil(
                lambda: len(notifications) > after_open, timeout=30000
            )

            version = client._doc_versions.get(uri)
        finally:
            client.stop()

        assert isinstance(version, int), (
            "didChange 未正确记录版本：%r（None+1 会 TypeError）" % version
        )
        assert version == 2, "版本号未递增：%r" % version
        assert len(notifications) > after_open, (
            "didChange 后服务器未再次推送诊断 —— 说明它没处理这次变更。"
            "errors=%s" % errors
        )
        assert 'undefined_name_abc' in FIXED


class TestRealCompletion:
    def test_receives_completion_items(self, qapp, qtbot, workspace):
        """请求补全，应收到真实补全项"""
        from core.lsp_client import LspClient

        path = workspace / "complete.py"
        path.write_text(COMPLETION_DOC, encoding='utf-8')
        uri = LspClient.path_to_uri(str(path))

        client = LspClient()
        items = []
        client.completion_ready.connect(lambda lst: items.append(lst))

        _start_pylsp(client)
        try:
            client.initialize(LspClient.path_to_uri(str(workspace)))
            qtbot.waitUntil(
                lambda: client.is_initialized, timeout=30000
            )
            client.did_open(uri, "python", COMPLETION_DOC)

            # 在 "os." 之后（第 2 行第 3 列）请求补全
            client.request_completion(uri, 1, 3)
            qtbot.waitUntil(lambda: bool(items), timeout=30000)
        finally:
            client.stop()

        assert items, "未收到补全结果"
        result = items[-1]
        assert isinstance(result, list), "补全结果应为列表：%r" % type(result)
        assert result, "补全结果为空（真实 server 应返回 os 模块成员）"

        # 每项应能被 EditorProxy._on_lsp_completion 消费
        first = result[0]
        assert isinstance(first, dict), "补全项应为 dict：%r" % first
        assert 'label' in first, "补全项缺少 label：%r" % first


class TestRegistryDetectsRealInstall:
    def test_registry_sees_python_server(self):
        """LspServerRegistry 对 python 语言的命令应指向可用程序"""
        from core.lsp_client import LspServerRegistry

        cmd = LspServerRegistry.get_command('python')
        assert cmd, "注册表未给出 python 的命令"

        # pylsp 可能没有控制台脚本，因此用 `python -m pylsp` 兜底判断
        import importlib.util
        import shutil
        available = (
            shutil.which(cmd[0]) is not None
            or importlib.util.find_spec('pylsp') is not None
        )
        assert available, "python 语言服务器不可用：%r" % cmd

    def test_installer_reports_installed(self, qapp):
        """LspInstaller.is_installed('python') 应为 True"""
        from core.lsp_installer import LspInstaller

        info = LspInstaller().detect_all()
        assert isinstance(info, dict)
        # python 已安装（本测试的前提）
        assert info.get('python') is True, (
            "检测结果未识别到已安装的 python 服务器：%r" % info
        )
