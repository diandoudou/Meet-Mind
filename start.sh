#!/bin/bash

# MeetMind 一键启动脚本
# 同时启动后端和前端服务

echo "🚀 启动 MeetMind 会议助手..."
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# 检查目录是否存在
if [ ! -d "$BACKEND_DIR" ]; then
    echo "❌ 错误: 后端目录不存在: $BACKEND_DIR"
    exit 1
fi

if [ ! -d "$FRONTEND_DIR" ]; then
    echo "❌ 错误: 前端目录不存在: $FRONTEND_DIR"
    exit 1
fi

# 创建日志目录
mkdir -p "$SCRIPT_DIR/logs"

# 启动后端
echo "📡 启动后端服务..."
cd "$BACKEND_DIR"

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "❌ 错误: Python 虚拟环境不存在"
    echo "   请先运行: cd backend && python -m venv .venv"
    exit 1
fi

# 激活虚拟环境并启动后端
source .venv/bin/activate
nohup python src/websocket_server.py > "$SCRIPT_DIR/logs/backend.log" 2>&1 &
BACKEND_PID=$!
echo "✅ 后端服务已启动 (PID: $BACKEND_PID)"
echo "   日志文件: logs/backend.log"
echo "   API: http://localhost:8765"
echo ""

# 等待后端启动
sleep 3

# 启动前端
echo "🎨 启动前端服务..."
cd "$FRONTEND_DIR"

# 检查 node_modules
if [ ! -d "node_modules" ]; then
    echo "⚠️  警告: node_modules 不存在，正在安装依赖..."
    npm install
fi

# 启动前端
nohup npm run dev > "$SCRIPT_DIR/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "✅ 前端服务已启动 (PID: $FRONTEND_PID)"
echo "   日志文件: logs/frontend.log"
echo ""

# 保存 PID 到文件
echo "$BACKEND_PID" > "$SCRIPT_DIR/.backend.pid"
echo "$FRONTEND_PID" > "$SCRIPT_DIR/.frontend.pid"

# 等待前端启动
echo "⏳ 等待服务完全启动..."
sleep 5

echo ""
echo "✨ MeetMind 已成功启动！"
echo ""
echo "📍 访问地址:"
echo "   前端: http://localhost:3000"
echo "   后端: http://localhost:8765"
echo "   WebSocket: ws://localhost:8765/ws"
echo ""
echo "📋 管理命令:"
echo "   查看后端日志: tail -f logs/backend.log"
echo "   查看前端日志: tail -f logs/frontend.log"
echo "   停止服务: ./stop.sh"
echo ""
echo "按 Ctrl+C 不会停止服务，请使用 ./stop.sh 停止"
