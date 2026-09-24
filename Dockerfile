# QingCao Editor 开发环境
FROM python:3.11-slim

LABEL maintainer="hedongwei <1265338136@qq.com>"
LABEL description="QingCao Editor development environment"

# 系统依赖
RUN apt-get update && apt-get install -y \
    qt5-default \
    libqt5scintilla2-dev \
    libqt5svg5-dev \
    libqt5multimedia5-plugins \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 工作目录
WORKDIR /app

# 复制源码
COPY . /app

# 环境变量
ENV PYTHONPATH=/app
ENV QT_QPA_PLATFORM=offscreen

# 默认命令
CMD ["python", "-m", "unittest", "discover", "-s", "tests"]