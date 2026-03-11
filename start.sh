#!/bin/bash
# 保险营销内容智能审核系统 - 一键启动脚本

set -e
cd "$(dirname "$0")"

# 显示使用帮助
show_help() {
    cat << EOF
使用方法：
  bash start.sh [选项]

选项：
  --port PORT       指定服务端口（默认：8000或config.yaml中配置的端口）
  --help, -h        显示此帮助信息

示例：
  bash start.sh                # 使用默认端口
  bash start.sh --port 8001    # 使用8001端口
  PORT=8001 bash start.sh      # 通过环境变量指定端口

端口优先级：
  1. --port 参数（最高）
  2. PORT 环境变量
  3. config.yaml 配置
  4. 默认值 8000（最低）
EOF
    exit 0
}

# 解析命令行参数
CUSTOM_PORT=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --port)
            CUSTOM_PORT="$2"
            shift 2
            ;;
        --help|-h)
            show_help
            ;;
        *)
            echo "错误：未知参数 '$1'"
            echo "使用 'bash start.sh --help' 查看帮助"
            exit 1
            ;;
    esac
done

echo "=== 保险营销内容智能审核系统 ==="

# 读取配置文件中的默认端口
DEFAULT_PORT=8000
if [ -f "config.yaml" ]; then
    CONFIG_PORT=$(grep -E "^\s*port:" config.yaml | awk '{print $2}' | head -1)
    if [ -n "$CONFIG_PORT" ]; then
        DEFAULT_PORT=$CONFIG_PORT
    fi
fi

# 端口优先级：命令行参数 > 环境变量 > 配置文件 > 默认值
PORT=${CUSTOM_PORT:-${PORT:-$DEFAULT_PORT}}

# 检查端口是否被占用
echo "[0/6] 检查端口 $PORT..."
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "  ❌ 错误：端口 $PORT 已被占用"
    echo ""
    echo "解决方案："
    echo "  1. 停止占用端口的进程："
    echo "     lsof -ti:$PORT | xargs kill -9"
    echo ""
    echo "  2. 或使用其他端口启动："
    echo "     bash start.sh --port 8001"
    echo "     或 PORT=8001 bash start.sh"
    echo ""
    exit 1
fi
echo "  ✅ 端口 $PORT 可用"

# 1. 检测并选择 ARM64 原生 Python（Apple Silicon 必须使用，避免 numpy/faiss 架构不匹配）
echo "[1/6] 检查 Python 环境..."
PYTHON_CMD=()
# 优先：Homebrew ARM64 Python（/opt/homebrew 为 Apple Silicon 的 Homebrew 路径）
for candidate in /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3.10 /opt/homebrew/bin/python3; do
    if [ -x "$candidate" ]; then
        arch_check=$("$candidate" -c "import platform; print(platform.machine())" 2>/dev/null)
        if [ "$arch_check" = "arm64" ] || [ "$arch_check" = "aarch64" ]; then
            PYTHON_CMD=("$candidate")
            break
        fi
    fi
done
# 备选：系统 Python 强制 ARM64 执行
if [ ${#PYTHON_CMD[@]} -eq 0 ] && [ -x /usr/bin/python3 ]; then
    PYTHON_CMD=(arch -arm64 /usr/bin/python3)
fi
if [ ${#PYTHON_CMD[@]} -eq 0 ]; then
    echo "错误: 未找到 ARM64 原生 Python。Apple Silicon Mac 请安装: brew install python@3.12"
    exit 1
fi
PYTHON_VERSION=$("${PYTHON_CMD[@]}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  Python: ${PYTHON_CMD[*]} (版本 $PYTHON_VERSION)"

# 2. 安装依赖
echo "[2/6] 安装依赖..."
"${PYTHON_CMD[@]}" -m pip install -q -r requirements.txt
echo "  依赖安装完成"

# 3. 检查 API 密钥（可选：有 .env 则为开发者模式，无则需注册登录后在界面配置）
# 不再强制要求 .env，用户可注册后在 Web 界面配置 API 密钥

# 4. 初始化数据库
echo "[4/6] 初始化数据库..."
"${PYTHON_CMD[@]}" scripts/init_database.py || true

# 5. 构建知识库（若向量库不存在则尝试构建）
VECTOR_INDEX="data/vectorstore/faiss.index"
if [ ! -f "$VECTOR_INDEX" ]; then
    echo "[5/6] 构建知识库..."
    "${PYTHON_CMD[@]}" scripts/build_knowledge_base.py || echo "  （无监管文档时跳过，可将 PDF/DOCX/TXT 放入 data/documents/ 后重试）"
else
    echo "[5/6] 知识库已存在，跳过构建"
fi

# 6. 启动服务
echo "[6/6] 启动服务..."
echo "  服务地址: http://localhost:$PORT"

# 设置优雅退出处理
cleanup() {
    echo ""
    echo "=== 正在停止服务 ==="
    if [ -n "$UVICORN_PID" ]; then
        echo "  停止进程 $UVICORN_PID..."
        kill -TERM $UVICORN_PID 2>/dev/null || true
        # 等待进程结束
        for i in {1..5}; do
            if ! kill -0 $UVICORN_PID 2>/dev/null; then
                break
            fi
            sleep 1
        done
        # 如果还没结束，强制kill
        if kill -0 $UVICORN_PID 2>/dev/null; then
            kill -9 $UVICORN_PID 2>/dev/null || true
        fi
        echo "  ✅ 服务已停止，端口 $PORT 已释放"
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# 后台启动 uvicorn
"${PYTHON_CMD[@]}" -m uvicorn src.api.main:app --host 0.0.0.0 --port "$PORT" &
UVICORN_PID=$!

# 等待服务就绪
echo "等待服务就绪..."
for i in {1..15}; do
    if curl -s "http://localhost:$PORT/api/health" > /dev/null 2>&1; then
        echo "  服务已就绪"
        break
    fi
    sleep 1
    if [ $i -eq 15 ]; then
        echo "  服务启动超时"
        kill $UVICORN_PID 2>/dev/null || true
        exit 1
    fi
done

# 打开浏览器
if command -v open &> /dev/null; then
    open "http://localhost:$PORT"
elif command -v xdg-open &> /dev/null; then
    xdg-open "http://localhost:$PORT"
fi

echo ""
echo "=== 启动完成 ==="
echo "  服务地址: http://localhost:$PORT"
echo "  按 Ctrl+C 停止服务"
echo ""
wait $UVICORN_PID
