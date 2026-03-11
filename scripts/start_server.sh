#!/bin/bash
# 开发模式启动：仅启动 API 服务，支持热重载
# 不执行依赖安装、数据库初始化、知识库构建

set -e
cd "$(dirname "$0")/.."

PORT=${PORT:-8000}
echo "启动开发服务器 (端口 $PORT，热重载)..."
python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port "$PORT" --reload
