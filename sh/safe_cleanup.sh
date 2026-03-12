#!/bin/bash

# 安全清理脚本 - 带重试和验证机制

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 配置
MAX_RETRIES=3
RETRY_DELAY=5
COMFYUI_SERVER="http://0.0.0.0:12374"
FILE_TARGETS="logs:time:7,output:size:500,temp:time:1"

echo "=========================================="
echo "安全清理脚本（带重试机制）"
echo "=========================================="
echo ""

# 函数: 检查 ComfyUI 是否可达
check_comfyui() {
    echo "检查 ComfyUI 服务器..."
    if curl -s --connect-timeout 5 "$COMFYUI_SERVER/system_stats" > /dev/null 2>&1; then
        echo "✅ ComfyUI 服务器可达"
        return 0
    else
        echo "❌ ComfyUI 服务器不可达"
        return 1
    fi
}

# 函数: 带重试的内存清理
cleanup_memory_with_retry() {
    local attempt=1
    
    while [ $attempt -le $MAX_RETRIES ]; do
        echo ""
        echo "尝试内存清理 (第 $attempt/$MAX_RETRIES 次)..."
        
        ./cleanup/cleanup_scheduler.sh memory-cleanup \
            --memory-servers "$COMFYUI_SERVER"
        
        if [ $? -eq 0 ]; then
            echo "✅ 内存清理成功"
            return 0
        else
            echo "⚠️ 内存清理失败"
            
            if [ $attempt -lt $MAX_RETRIES ]; then
                echo "等待 $RETRY_DELAY 秒后重试..."
                sleep $RETRY_DELAY
            fi
        fi
        
        attempt=$((attempt + 1))
    done
    
    echo "❌ 内存清理失败（已重试 $MAX_RETRIES 次）"
    return 1
}

# 函数: 带重试的文件清理
cleanup_files_with_retry() {
    local attempt=1
    
    while [ $attempt -le $MAX_RETRIES ]; do
        echo ""
        echo "尝试文件清理 (第 $attempt/$MAX_RETRIES 次)..."
        
        ./cleanup/cleanup_scheduler.sh file-cleanup \
            --file-targets "$FILE_TARGETS"
        
        if [ $? -eq 0 ]; then
            echo "✅ 文件清理成功"
            return 0
        else
            echo "⚠️ 文件清理部分失败"
            
            if [ $attempt -lt $MAX_RETRIES ]; then
                echo "等待 $RETRY_DELAY 秒后重试..."
                sleep $RETRY_DELAY
            fi
        fi
        
        attempt=$((attempt + 1))
    done
    
    echo "⚠️ 文件清理完成（可能有部分文件无法删除）"
    return 0  # 文件清理失败不算致命错误
}

# 函数: 验证清理效果
verify_cleanup() {
    echo ""
    echo "=========================================="
    echo "验证清理效果"
    echo "=========================================="
    
    # 验证内存清理
    echo ""
    echo "1. 检查 ComfyUI 历史记录..."
    if command -v jq > /dev/null 2>&1; then
        history_count=$(curl -s "$COMFYUI_SERVER/history" | jq 'length' 2>/dev/null)
        if [ -n "$history_count" ]; then
            echo "   历史记录数量: $history_count 条"
            if [ "$history_count" -le 5 ]; then
                echo "   ✅ 历史记录正常（≤ 5 条）"
            else
                echo "   ⚠️ 历史记录较多（> 5 条）"
            fi
        else
            echo "   ⚠️ 无法获取历史记录数量"
        fi
    else
        echo "   ℹ️ 未安装 jq，跳过历史记录检查"
    fi
    
    # 验证文件清理
    echo ""
    echo "2. 检查磁盘使用..."
    if [ -d "logs" ]; then
        logs_size=$(du -sh logs 2>/dev/null | cut -f1)
        echo "   logs/ 目录: $logs_size"
    fi
    if [ -d "output" ]; then
        output_size=$(du -sh output 2>/dev/null | cut -f1)
        echo "   output/ 目录: $output_size"
    fi
    if [ -d "temp" ]; then
        temp_size=$(du -sh temp 2>/dev/null | cut -f1)
        echo "   temp/ 目录: $temp_size"
    fi
}

# 主流程
main() {
    # 1. 检查 ComfyUI 连接
    if ! check_comfyui; then
        echo ""
        echo "⚠️ ComfyUI 服务器不可达，跳过内存清理"
        echo "   只执行文件清理..."
        cleanup_files_with_retry
        verify_cleanup
        return 0
    fi
    
    # 2. 执行文件清理
    cleanup_files_with_retry
    file_result=$?
    
    # 3. 执行内存清理
    cleanup_memory_with_retry
    memory_result=$?
    
    # 4. 验证清理效果
    verify_cleanup
    
    # 5. 总结
    echo ""
    echo "=========================================="
    echo "清理完成"
    echo "=========================================="
    
    if [ $file_result -eq 0 ] && [ $memory_result -eq 0 ]; then
        echo "✅ 所有清理任务成功完成"
        return 0
    elif [ $memory_result -ne 0 ]; then
        echo "⚠️ 内存清理失败，但文件清理成功"
        echo "   建议: 检查 ComfyUI 服务器状态"
        return 1
    else
        echo "⚠️ 部分清理任务失败"
        return 1
    fi
}

# 执行主函数
main
exit $?
