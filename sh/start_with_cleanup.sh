#!/bin/bash

# ComfyBridgege 启动脚本（带自动清理）
# 用途：启动 ComfyBridgege 服务，并自动启动后台清理任务

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "ComfyBridgege 启动脚本（带自动清理）"
echo "=========================================="
echo ""

# 1. 检查 Python 环境
echo "1. 检查 Python 环境..."
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 python3"
    exit 1
fi
echo "✅ Python 环境正常"
echo ""

# 2. 检查依赖
echo "2. 检查依赖..."
if [ ! -f "requirements.txt" ]; then
    echo "⚠️  警告: 未找到 requirements.txt"
else
    echo "✅ 依赖文件存在"
fi
echo ""

# 3. 启动清理调度器（后台运行）
echo "3. 启动清理调度器..."
if [ -f "cleanup/cleanup_scheduler.sh" ]; then
    # 配置清理参数
    FILE_TARGETS="logs:time:7,output:size:500,temp:time:1"
    MEMORY_SERVERS="http://0.0.0.0:12374"
    MEMORY_INTERVAL="6"
    SCHEDULE_INTERVAL="12"  # 每 12 小时执行一次完整清理
    
    # 启动定时清理（后台守护进程）
    bash cleanup/cleanup_scheduler.sh schedule \
        --file-targets "$FILE_TARGETS" \
        --memory-servers "$MEMORY_SERVERS" \
        --memory-interval "$MEMORY_INTERVAL" \
        --schedule-interval "$SCHEDULE_INTERVAL" \
        --daemon
    
    if [ $? -eq 0 ]; then
        echo "✅ 清理调度器已启动（后台运行）"
        echo "   - 文件清理: $FILE_TARGETS"
        echo "   - 内存清理: $MEMORY_SERVERS (每 ${MEMORY_INTERVAL}h)"
        echo "   - 清理周期: 每 ${SCHEDULE_INTERVAL} 小时"
        
        if [ -f "cleanup_scheduler.pid" ]; then
            echo "   - 进程 PID: $(cat cleanup_scheduler.pid)"
        fi
    else
        echo "⚠️  警告: 清理调度器启动失败，但不影响主服务"
    fi
else
    echo "⚠️  警告: 未找到清理脚本，跳过清理调度器"
fi
echo ""

# 4. 执行一次立即清理（可选）
echo "4. 执行初始清理..."
if [ -f "cleanup/cleanup_scheduler.sh" ]; then
    echo "   清理历史数据和临时文件..."
    bash cleanup/cleanup_scheduler.sh full-cleanup \
        --file-targets "$FILE_TARGETS" \
        --memory-servers "$MEMORY_SERVERS" \
        --memory-interval "$MEMORY_INTERVAL" 2>&1 | head -n 10
    echo "✅ 初始清理完成"
else
    echo "⚠️  跳过初始清理"
fi
echo ""

# 5. 启动 ComfyBridgege 服务
echo "5. 启动 ComfyBridgege 服务..."
echo "=========================================="
echo ""

# 启动服务（前台运行）
python3 server.py

# 如果服务退出，清理后台任务
echo ""
echo "=========================================="
echo "服务已停止，清理后台任务..."
echo "=========================================="

# 停止清理调度器
if [ -f "cleanup/cleanup_scheduler.sh" ]; then
    bash cleanup/cleanup_scheduler.sh stop
    echo "✅ 清理调度器已停止"
fi

echo ""
echo "ComfyBridgege 已完全停止"
