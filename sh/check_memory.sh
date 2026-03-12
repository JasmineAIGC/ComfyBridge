#!/bin/bash

# 查看 ComfyBridgege 内存占用脚本

echo "=========================================="
echo "ComfyBridgege 内存占用检查"
echo "=========================================="
echo ""

# 1. 查找 ComfyBridgege 进程
echo "1. 查找 ComfyBridgege 进程..."

# 尝试多种方式查找进程
PIDS=$(pgrep -f "python.*server.py" 2>/dev/null)
if [ -z "$PIDS" ]; then
    PIDS=$(pgrep -f "python.*nexus" 2>/dev/null)
fi
if [ -z "$PIDS" ]; then
    PIDS=$(pgrep -f "uvicorn.*nexus" 2>/dev/null)
fi
if [ -z "$PIDS" ]; then
    PIDS=$(pgrep -f "uvicorn" 2>/dev/null)
fi

if [ -z "$PIDS" ]; then
    echo "   ❌ 未找到 ComfyBridgege 进程"
    echo ""
    echo "尝试查找所有 Python 进程:"
    ps aux | grep python | grep -v grep
    exit 1
fi

echo "   ✅ 找到进程 PID: $PIDS"
echo ""

# 2. 显示详细内存信息
echo "2. 内存占用详情:"
echo ""

for PID in $PIDS; do
    # 获取进程信息
    PROCESS_INFO=$(ps -p $PID -o pid,ppid,cmd,%mem,rss,vsz 2>/dev/null)
    
    if [ -n "$PROCESS_INFO" ]; then
        echo "   进程 PID: $PID"
        echo "   $PROCESS_INFO" | tail -n 1 | awk '{
            printf "   内存占用百分比: %s%%\n", $4
            printf "   RSS (实际物理内存): %.2f MB\n", $5/1024
            printf "   VSZ (虚拟内存): %.2f MB\n", $6/1024
        }'
        echo ""
    fi
done

# 3. 使用 ps 显示更详细的信息
echo "3. 详细进程信息:"
echo ""
ps aux | head -1
for PID in $PIDS; do
    ps aux | grep "^[^ ]* *$PID " | grep -v grep
done
echo ""

# 4. 如果有 /proc 文件系统（Linux）
if [ -d "/proc" ]; then
    echo "4. 详细内存统计 (从 /proc):"
    echo ""
    
    for PID in $PIDS; do
        if [ -f "/proc/$PID/status" ]; then
            echo "   进程 PID: $PID"
            grep -E "^(VmRSS|VmSize|VmPeak|VmData|VmStk|VmExe|VmLib):" /proc/$PID/status | awk '{
                printf "   %-12s: %8s %s\n", $1, $2, $3
            }'
            echo ""
        fi
    done
fi

# 5. 计算总内存占用
echo "5. 总内存占用:"
echo ""

TOTAL_RSS=0
for PID in $PIDS; do
    RSS=$(ps -p $PID -o rss= 2>/dev/null)
    if [ -n "$RSS" ]; then
        TOTAL_RSS=$((TOTAL_RSS + RSS))
    fi
done

# 使用 awk 代替 bc（更通用）
TOTAL_RSS_MB=$(awk "BEGIN {printf \"%.2f\", $TOTAL_RSS / 1024}")
TOTAL_RSS_GB=$(awk "BEGIN {printf \"%.2f\", $TOTAL_RSS / 1024 / 1024}")

echo "   总物理内存 (RSS): $TOTAL_RSS_MB MB ($TOTAL_RSS_GB GB)"
echo ""

# 6. 系统总内存
echo "6. 系统内存概况:"
echo ""
free -h 2>/dev/null || vmstat -s 2>/dev/null | head -5
echo ""

# 7. 内存增长趋势（如果有历史记录）
MEMORY_LOG="/tmp/comfybridge_memory.log"
CURRENT_TIME=$(date '+%Y-%m-%d %H:%M:%S')

# 记录当前内存
echo "$CURRENT_TIME,$TOTAL_RSS_MB" >> "$MEMORY_LOG"

# 显示最近的记录
if [ -f "$MEMORY_LOG" ]; then
    echo "7. 内存增长趋势（最近 10 次记录）:"
    echo ""
    echo "   时间                    内存(MB)"
    echo "   ----------------------------------------"
    tail -10 "$MEMORY_LOG" | awk -F',' '{printf "   %-20s  %8.2f MB\n", $1, $2}'
    echo ""
    
    # 计算增长率
    FIRST_RECORD=$(head -1 "$MEMORY_LOG" | cut -d',' -f2)
    LAST_RECORD=$(tail -1 "$MEMORY_LOG" | cut -d',' -f2)
    
    if [ -n "$FIRST_RECORD" ] && [ -n "$LAST_RECORD" ]; then
        # 使用 awk 代替 bc
        GROWTH=$(awk "BEGIN {printf \"%.2f\", $LAST_RECORD - $FIRST_RECORD}")
        echo "   从首次记录到现在增长: $GROWTH MB"
    fi
fi

echo ""
echo "=========================================="
echo "检查完成"
echo "=========================================="
echo ""
echo "提示:"
echo "  - RSS (Resident Set Size): 实际占用的物理内存"
echo "  - VSZ (Virtual Size): 虚拟内存大小"
echo "  - 内存记录保存在: $MEMORY_LOG"
echo "  - 定期运行此脚本可以观察内存增长趋势"
echo ""
