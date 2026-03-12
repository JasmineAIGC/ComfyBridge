#!/bin/bash

# =============================================================================
# ComfyBridge 推理平台部署启动脚本（镜像内运行）
#
# 功能：启动 ComfyUI + ComfyBridge 服务，执行模型预热，并持续健康监控
#
# 使用方法：
#   ./run_deploy.sh              # 默认测试环境
#   DEPLOY_ENV=prod ./run_deploy.sh  # 生产环境
#
# 流程：
#   1. 加载配置
#   2. 激活 Conda 环境
#   3. 清理旧进程
#   4. 启动 ComfyUI
#   5. 启动 ComfyBridge
#   6. 执行模型预热（test.py）
#   7. 进入健康监控循环
# =============================================================================

# =============================================================================
# 1. 配置区
# =============================================================================

# 部署环境：test 或 prod
DEPLOY_ENV=${DEPLOY_ENV:-${1:-test}}

# Conda 环境配置
CONDA_ROOT=/root/miniconda3
CONDA_ENV_NAME=py312
PYTHON_PATH=$CONDA_ROOT/envs/$CONDA_ENV_NAME/bin/python

# 代码路径（镜像内固定路径）
COMFYUI_DIR=/home/ComfyUI
COMFYBRIDGE_DIR=/home/FUN_MFP

# 日志路径（推理平台要求）
LOG_DIR=/home/finance/Logs
COMFYBRIDGE_LOG_FILE="$LOG_DIR/comfybridge.log"

# 服务端口
COMFYUI_PORT=44311
COMFYBRIDGE_PORT=44321

# Pinpoint 链路追踪配置
PINPOINT_COLLECTOR_HOST_TEST="tcp:10.245.15.173:9999"
PINPOINT_COLLECTOR_HOST_PROD="tcp:10.187.131.122:9999"
PINPOINT_APP_NAME="comfybridge_aging"

# 根据环境选择 Pinpoint Collector
case "${DEPLOY_ENV,,}" in
    prod|production)
        PINPOINT_COLLECTOR_HOST=$PINPOINT_COLLECTOR_HOST_PROD
        DEPLOY_ENV=prod
        ;;
    *)
        PINPOINT_COLLECTOR_HOST=$PINPOINT_COLLECTOR_HOST_TEST
        DEPLOY_ENV=test
        ;;
esac

# 健康检查配置
MAX_FAIL_COUNT=3        # 连续失败次数阈值
CHECK_INTERVAL=120       # 检查间隔（秒）
STATUS_LOG_INTERVAL=10   # 状态日志间隔（分钟）

# =============================================================================
# 2. 激活 Conda 环境
# =============================================================================

echo "$(date): [INFO] ========== 启动部署脚本 =========="

ACTIVATE_SCRIPT="$CONDA_ROOT/bin/activate"
if [ -f "$ACTIVATE_SCRIPT" ]; then
    echo "$(date): [INFO] 激活 Conda 环境: $CONDA_ENV_NAME"
    # shellcheck disable=SC1090,SC1091
    source "$ACTIVATE_SCRIPT" "$CONDA_ENV_NAME"
else
    echo "$(date): [ERROR] Conda 激活脚本不存在: $ACTIVATE_SCRIPT"
    exit 1
fi

# =============================================================================
# 3. 打印配置信息
# =============================================================================

echo "=========================================="
echo "ComfyBridge 推理平台部署"
echo "=========================================="
echo "部署环境: $DEPLOY_ENV"
echo "Pinpoint: $PINPOINT_COLLECTOR_HOST"
echo "ComfyUI:  http://127.0.0.1:$COMFYUI_PORT"
echo "Server:   http://0.0.0.0:$COMFYBRIDGE_PORT"
echo "日志目录: $LOG_DIR"
echo "=========================================="

# =============================================================================
# 4. 创建必要目录
# =============================================================================

mkdir -p "$LOG_DIR"

# =============================================================================
# 5. 服务启动函数
# =============================================================================

# 启动 ComfyUI 服务
start_comfyui() {
    echo "$(date): [INFO] 启动 ComfyUI (端口: $COMFYUI_PORT)..."
    
    # 停止已有进程
    pkill -f "python main.py" 2>/dev/null || true
    sleep 2
    
    # 启动服务
    cd "$COMFYUI_DIR"
    nohup $PYTHON_PATH main.py --listen 0.0.0.0 --port $COMFYUI_PORT > "$LOG_DIR/comfyui.log" 2>&1 &
    
    # 等待服务就绪（最多 60 秒）
    echo "$(date): [INFO] 等待 ComfyUI 启动..."
    for i in {1..60}; do
        if curl -s --max-time 5 "http://localhost:$COMFYUI_PORT" > /dev/null 2>&1; then
            echo "$(date): [INFO] ComfyUI 启动成功"
            return 0
        fi
        sleep 1
    done
    
    echo "$(date): [ERROR] ComfyUI 启动失败（超时 60 秒）"
    return 1
}

# 启动 ComfyBridge 服务
start_comfybridge() {
    echo "$(date): [INFO] 启动 ComfyBridge (端口: $COMFYBRIDGE_PORT)..."
    
    # 停止已有进程
    pkill -f "server.py" 2>/dev/null || true
    sleep 2
    
    # 设置服务环境变量
    export COMFYBRIDGE_HOST="0.0.0.0"
    export COMFYBRIDGE_PORT=$COMFYBRIDGE_PORT
    export COMFYBRIDGE_LOG_DIR=$LOG_DIR
    export COMFYBRIDGE_LOG_FILE=$COMFYBRIDGE_LOG_FILE
    export COMFY_SERVERS="http://127.0.0.1:$COMFYUI_PORT/"
    export PINPOINT_COLLECTOR_HOST=$PINPOINT_COLLECTOR_HOST
    export PINPOINT_APP_NAME=$PINPOINT_APP_NAME
    
    # 启动服务
    cd "$COMFYBRIDGE_DIR"
    nohup python server.py >> "$COMFYBRIDGE_LOG_FILE" 2>&1 &
    
    # 等待服务就绪（最多 30 秒）
    echo "$(date): [INFO] 等待 ComfyBridge 启动..."
    for i in {1..30}; do
        if curl -s --max-time 5 "http://localhost:$COMFYBRIDGE_PORT/aigc/system/health" > /dev/null 2>&1; then
            echo "$(date): [INFO] ComfyBridge 启动成功"
            return 0
        fi
        sleep 1
    done
    
    echo "$(date): [ERROR] ComfyBridge 启动失败（超时 30 秒）"
    return 1
}

# 执行模型预热测试
run_warmup_test() {
    echo "$(date): [INFO] 执行模型预热测试..."
    
    cd "$COMFYBRIDGE_DIR"
    if [ -f "test.py" ]; then
        if python test.py > >(tee -a "$COMFYBRIDGE_LOG_FILE") 2>&1; then
            echo "$(date): [INFO] 模型预热完成"
            return 0
        else
            echo "$(date): [WARN] 模型预热测试失败，查看日志: $COMFYBRIDGE_LOG_FILE"
            return 1
        fi
    else
        echo "$(date): [WARN] 预热测试脚本不存在: $COMFYBRIDGE_DIR/test.py"
        return 0
    fi
}

# =============================================================================
# 6. 首次启动流程
# =============================================================================

echo "$(date): [INFO] 清理已有进程..."
pkill -f "python main.py" 2>/dev/null || true
pkill -f "server.py" 2>/dev/null || true
sleep 2

echo "$(date): [INFO] GPU 状态:"
nvidia-smi || echo "$(date): [WARN] nvidia-smi 不可用"

# 启动 ComfyUI（必须成功）
if ! start_comfyui; then
    echo "$(date): [ERROR] ComfyUI 启动失败，退出部署"
    exit 1
fi

# 启动 ComfyBridge（必须成功）
if ! start_comfybridge; then
    echo "$(date): [ERROR] ComfyBridge 启动失败，退出部署"
    exit 1
fi

# 执行模型预热（失败不阻塞服务）
if ! run_warmup_test; then
    echo "$(date): [WARN] 预热失败但服务已启动，继续运行"
fi

echo ""
echo "=========================================="
echo "$(date): [INFO] 所有服务启动完成!"
echo "ComfyUI 日志:     tail -f $LOG_DIR/comfyui.log"
echo "ComfyBridge 日志: tail -f $COMFYBRIDGE_LOG_FILE"
echo "=========================================="
echo ""

# =============================================================================
# 7. 健康监控循环（失败自动重启）
# =============================================================================

COMFYUI_FAIL_COUNT=0
COMFYBRIDGE_FAIL_COUNT=0
CHECK_COUNT=0

while true; do
    sleep $CHECK_INTERVAL
    CHECK_COUNT=$((CHECK_COUNT + 1))
    
    # 检查 ComfyUI 健康状态
    if curl -s --max-time 10 "http://localhost:$COMFYUI_PORT" > /dev/null 2>&1; then
        COMFYUI_FAIL_COUNT=0
    else
        COMFYUI_FAIL_COUNT=$((COMFYUI_FAIL_COUNT + 1))
        echo "$(date): [WARN] ComfyUI 无响应 (失败: $COMFYUI_FAIL_COUNT/$MAX_FAIL_COUNT)"
        
        if [ $COMFYUI_FAIL_COUNT -ge $MAX_FAIL_COUNT ]; then
            echo "$(date): [ERROR] ComfyUI 连续失败，正在重启..."
            start_comfyui
            COMFYUI_FAIL_COUNT=0
        fi
    fi
    
    # 检查 ComfyBridge 健康状态
    if curl -s --max-time 10 "http://localhost:$COMFYBRIDGE_PORT/aigc/system/health" > /dev/null 2>&1; then
        COMFYBRIDGE_FAIL_COUNT=0
    else
        COMFYBRIDGE_FAIL_COUNT=$((COMFYBRIDGE_FAIL_COUNT + 1))
        echo "$(date): [WARN] ComfyBridge 无响应 (失败: $COMFYBRIDGE_FAIL_COUNT/$MAX_FAIL_COUNT)"
        
        if [ $COMFYBRIDGE_FAIL_COUNT -ge $MAX_FAIL_COUNT ]; then
            echo "$(date): [ERROR] ComfyBridge 连续失败，正在重启..."
            start_comfybridge
            COMFYBRIDGE_FAIL_COUNT=0
        fi
    fi
    
    # 定期输出运行状态
    if [ $((CHECK_COUNT % STATUS_LOG_INTERVAL)) -eq 0 ]; then
        echo "$(date): [OK] 服务运行正常 - 已运行: ${CHECK_COUNT} 分钟"
    fi
done
