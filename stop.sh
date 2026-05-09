#!/bin/bash

# MeetMind 停止脚本
# 停止所有运行的服务

echo "🛑 停止 MeetMind 会议助手..."
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 读取 PID 文件
BACKEND_PID_FILE="$SCRIPT_DIR/.backend.pid"
FRONTEND_PID_FILE="$SCRIPT_DIR/.frontend.pid"

# 停止后端
if [ -f "$BACKEND_PID_FILE" ]; then
    BACKEND_PID=$(cat "$BACKEND_PID_FILE")
    if ps -p $BACKEND_PID > /dev/null 2>&1; then
        echo "🔴 停止后端服务 (PID: $BACKEND_PID)..."
        kill $BACKEND_PID
        echo "✅ 后端服务已停止"
    else
        echo "⚠️  后端服务未运行"
    fi
    rm "$BACKEND_PID_FILE"
else
    echo "⚠️  未找到后端 PID 文件"
    # 尝试通过端口查找并关闭
    BACKEND_PORT_PID=$(lsof -ti:8765)
    if [ ! -z "$BACKEND_PORT_PID" ]; then
        echo "🔍 通过端口找到后端进程 (PID: $BACKEND_PORT_PID)，正在停止..."
        kill $BACKEND_PORT_PID
        echo "✅ 后端服务已停止"
    fi
fi

echo ""

# 停止前端
if [ -f "$FRONTEND_PID_FILE" ]; then
    FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
    if ps -p $FRONTEND_PID > /dev/null 2>&1; then
        echo "🔴 停止前端服务 (PID: $FRONTEND_PID)..."
        kill $FRONTEND_PID
        echo "✅ 前端服务已停止"
    else
        echo "⚠️  前端服务未运行"
    fi
    rm "$FRONTEND_PID_FILE"
else
    echo "⚠️  未找到前端 PID 文件"
    # 尝试通过端口查找并关闭
    FRONTEND_PORT_PID=$(lsof -ti:3000)
    if [ ! -z "$FRONTEND_PORT_PID" ]; then
        echo "🔍 通过端口找到前端进程 (PID: $FRONTEND_PORT_PID)，正在停止..."
        kill $FRONTEND_PORT_PID
        echo "✅ 前端服务已停止"
    fi
fi

echo ""
echo "✨ MeetMind 所有服务已停止"
