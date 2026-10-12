# ============================================================
# QingCao Editor 开发 / 测试环境
# ============================================================
# 说明（已修复的三处问题）：
#
# 1. 原 `qt5-default` 在 Debian bookworm（python:3.11-slim 的基础镜像）
#    已被移除 → `apt-get install` 会失败，**镜像根本构建不出来**。
#    现改为安装实际存在的 Qt5 运行库 + xvfb（无显示器时跑 GUI 测试）。
#
# 2. 镜像只安装了 requirements.txt（运行时依赖），但 docker-compose 的
#    test 服务执行的是 `python -m pytest` → 必然
#    ModuleNotFoundError: No module named pytest。
#    现通过 build arg INSTALL_DEV 安装 requirements-dev.txt。
#
# 3. 默认 CMD 原是 `python -m unittest discover`，会**绕过 conftest.py**
#    的 autouse fixture（_isolate_qsettings / qapp），既与 compose 的
#    test 服务不一致，还可能污染真实配置。
#    现统一为 pytest，并默认排除 realserver（需要真实语言服务器）。
# ============================================================
FROM python:3.11-slim

LABEL maintainer="hedongwei <1265338136@qq.com>"
LABEL description="QingCao Editor development & test environment"

# ---- 是否需要测试依赖（docker-compose 的 test 服务用 INSTALL_DEV=1）----
ARG INSTALL_DEV=0

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    QT_QPA_PLATFORM=offscreen \
    PYTHONPATH=/app

# ---- 系统依赖 ----
# PyQt5 与 QScintilla 以 manylinux wheel 安装，只需要 Qt 运行时共享库；
# 追加 xvfb 以便必要时用 xvfb-run 跑真实 GUI 测试。
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libegl1 \
        libxkbcommon-x11-0 \
        libdbus-1-3 \
        libxcb-icccm4 \
        libxcb-image0 \
        libxcb-keysyms1 \
        libxcb-randr0 \
        libxcb-render-util0 \
        libxcb-shape0 \
        libxcb-xinerama0 \
        libxcb-xkb1 \
        libxcb-cursor0 \
        libfontconfig1 \
        libglib2.0-0 \
        xvfb \
        git \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- Python 依赖（分层缓存：先依赖、后源码）----
COPY requirements.txt requirements-dev.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && if [ "$INSTALL_DEV" = "1" ]; then \
           pip install --no-cache-dir -r /tmp/requirements-dev.txt; \
       fi

# ---- 源码 ----
COPY . /app

# ---- 默认命令：与 docker-compose 的 test 服务保持一致 ----
# 排除 realserver 标记（需要真实 python-lsp-server，默认不跑）
CMD ["python", "-m", "pytest", "tests/", "-q", "-m", "not realserver"]
