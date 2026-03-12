#!/bin/bash

# ComfyBridge 参数化定时清理脚本
# 支持多目标本地文件清理和内存缓存清理
# 使用配置文件或命令行参数进行灵活配置

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 配置文件路径
CONFIG_FILE="$SCRIPT_DIR/cleanup_config.conf"


# 记录日志函数
log() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $message"
}

# 默认配置
DEFAULT_FILE_TARGETS=""
DEFAULT_MEMORY_SERVERS="http://localhost:8188"
DEFAULT_MEMORY_INTERVAL="6"
DEFAULT_MEMORY_CLEANUP_MODE="history-only"  # history-only | full
DEFAULT_SCHEDULE_INTERVAL="24"

# 显示帮助信息
show_help() {
    cat << EOF
ComfyBridge 参数化定时清理脚本

用法: $0 <命令> [参数]

快速示例:
  # 一次性清理（仅历史 + 三目录容量/数量）
  $0 full-cleanup \
    --file-targets "/app/code/ComfyUI/input:size:30,/app/code/ComfyUI/input:count:300,/app/code/ComfyUI/temp:size:30,/app/code/ComfyUI/temp:count:500,/app/code/ComfyUI/output:size:30,/app/code/ComfyUI/output:count:300" \
    --memory-servers "http://127.0.0.1:8188" \
    --memory-cleanup-mode history-only

  # 定时清理（每12小时，后台运行，日志到 /var/log/cleanup_scheduler.log）
  LOG_FILE="/var/log/cleanup_scheduler.log" $0 schedule \
    --file-targets "/app/code/ComfyUI/input:size:30,/app/code/ComfyUI/input:count:300,/app/code/ComfyUI/temp:size:30,/app/code/ComfyUI/temp:count:500,/app/code/ComfyUI/output:size:30,/app/code/ComfyUI/output:count:300" \
    --memory-servers "http://127.0.0.1:8188" \
    --schedule-interval 12 \
    --memory-cleanup-mode history-only \
    --daemon

命令:
  file-cleanup     执行本地文件清理
  memory-cleanup   执行内存缓存清理
  full-cleanup     执行完整清理（文件+内存）
  schedule         启动定时清理任务
  config           生成配置文件模板
  help             显示此帮助信息

本地文件清理参数:
  --file-targets   文件目标配置，格式: "路径1:类型1:参数1,路径2:类型2:参数2"
                   类型: time(按时间,参数=保留天数) | size(按大小,参数=最大MB) | count(按数量,参数=最大文件数)
                   示例: "logs:time:7,output:size:500,/tmp/cache:time:3,/data/images:count:300"

内存缓存清理参数:
  --memory-servers ComfyUI服务器列表，用逗号分隔
  --memory-interval 内存清理间隔小时数 (默认: 6)
  --memory-cleanup-mode 内存清理模式 (默认: history-only)
                   history-only: 仅清理历史，保留模型与缓存（推荐，适合 --gpu-only）
                   full: 完整清理，包括卸载模型与清空缓存（会影响性能）

定时任务参数:
  --schedule-interval 定时清理间隔小时数 (默认: 24)
  --daemon         后台运行
  --config-file    使用指定配置文件

配置文件格式 (cleanup_config.conf):
  FILE_TARGETS="/app/code/ComfyUI/input:size:30,/app/code/ComfyUI/input:count:300,/app/code/ComfyUI/temp:size:30,/app/code/ComfyUI/output:size:30"
  MEMORY_SERVERS="http://localhost:8188,http://localhost:8189"
  MEMORY_INTERVAL="6"
  MEMORY_CLEANUP_MODE="history-only"  # history-only | full
  SCHEDULE_INTERVAL="24"

内存清理说明:
  默认使用 history-only 模式，仅清理执行历史，不会影响:
  - 正在运行的工作流任务
  - 已加载的模型文件（适合 --gpu-only 启动模式）
  - workflow 节点缓存（保持同一 workflow 的性能）
  - 服务器的正常运行
  
  full 模式会卸载模型与清空缓存，下次推理需要重新加载（有延迟）。
  推荐使用 history-only 模式配合定期文件清理。

EOF
}

 

# 执行本地文件清理
run_file_cleanup() {
    local file_targets="${1:-$DEFAULT_FILE_TARGETS}"
    
    log "开始执行本地文件清理..."
    log "文件目标配置: $file_targets"
    
    # 构建Python清理配置
    python3 -c "
import sys, os
sys.path.append('$PROJECT_ROOT')
from cleanup.file_cleanup import cleanup_multiple_targets

# 解析文件目标配置
file_targets = '$file_targets'
cleanup_configs = []

for target_config in file_targets.split(','):
    parts = target_config.strip().split(':')
    if len(parts) != 3:
        continue
    
    path, cleanup_type, param = parts
    path = path.strip()
    cleanup_type = cleanup_type.strip()
    param = param.strip()
    
    # 仅支持绝对/相对路径，不再提供简写映射
    actual_path = path
    file_patterns = None
    
    # 构建清理配置
    config_item = {
        'target': actual_path,
        'target_type': 'directory',
        'cleanup_type': cleanup_type,
        'recursive': True
    }
    
    if cleanup_type == 'time':
        config_item['days_to_keep'] = int(param)
        if file_patterns:
            config_item['file_patterns'] = file_patterns
    elif cleanup_type == 'size':
        config_item['max_size_mb'] = float(param)
        config_item['strategy'] = 'oldest_first'
    elif cleanup_type == 'count':
        config_item['max_files'] = int(param)
        config_item['strategy'] = 'oldest_first'
    
    cleanup_configs.append(config_item)

if cleanup_configs:
    result = cleanup_multiple_targets(cleanup_configs)
    print(f'文件清理完成: 处理了 {result.get(\"targets_processed\", 0)} 个目标')
    print(f'删除了 {result.get(\"files_deleted\", 0)} 个文件')
    print(f'释放了 {result.get(\"bytes_freed\", 0) / 1024 / 1024:.2f} MB')
    if result.get('errors'):
        print(f'错误: {result[\"errors\"]}')
else:
    print('未找到有效的文件清理配置')
"
    
    if [ $? -eq 0 ]; then
        log "本地文件清理完成"
    else
        log "本地文件清理失败"
        return 1
    fi
}

# 执行内存缓存清理
run_memory_cleanup() {
    local servers="${1:-$DEFAULT_MEMORY_SERVERS}"
    local interval="${2:-$DEFAULT_MEMORY_INTERVAL}"
    local mode="${3:-$DEFAULT_MEMORY_CLEANUP_MODE}"
    
    log "开始执行内存缓存清理..."
    log "服务器: $servers, 清理间隔: ${interval}小时, 模式: $mode"
    
    # 执行异步Python清理
    python3 -c "
import sys, os, asyncio, logging
sys.path.append('$PROJECT_ROOT')

# 配置日志输出到控制台
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

from cleanup.memory_cleanup import smart_cleanup_comfyui

async def main():
    servers = '$servers'.split(',')
    servers = [s.strip() for s in servers]
    mode = '$mode'
    result = await smart_cleanup_comfyui(servers, mode=mode)
    
    # 显示详细结果
    servers_processed = result.get('servers_processed', 0)
    mode_used = result.get('mode', 'unknown')
    print(f'内存清理完成: 模式={mode_used}, 处理了 {servers_processed} 个服务器')
    
    # 显示错误信息
    errors = result.get('errors', [])
    
    if errors:
        print(f'错误: {errors}')
        return 1
    return 0

exit(asyncio.run(main()))
"
    
    if [ $? -eq 0 ]; then
        log "内存缓存清理完成"
    else
        log "内存缓存清理失败"
        return 1
    fi
}

# 执行完整清理
run_full_cleanup() {
    local file_targets="$1"
    local memory_servers="$2"
    local memory_interval="$3"
    local memory_mode="${4:-$DEFAULT_MEMORY_CLEANUP_MODE}"
    
    log "开始执行完整清理..."
    
    # 先执行文件清理
    run_file_cleanup "$file_targets"
    local file_result=$?
    
    # 再执行内存清理
    run_memory_cleanup "$memory_servers" "$memory_interval" "$memory_mode"
    local memory_result=$?
    
    if [ $file_result -eq 0 ] && [ $memory_result -eq 0 ]; then
        log "完整清理成功完成"
        return 0
    else
        log "完整清理部分失败"
        return 1
    fi
}

# 启动定时清理任务
run_schedule() {
    local schedule_interval="${1:-$DEFAULT_SCHEDULE_INTERVAL}"
    local daemon="${2:-false}"
    local file_targets="${3:-$DEFAULT_FILE_TARGETS}"
    local memory_servers="${4:-$DEFAULT_MEMORY_SERVERS}"
    local memory_interval="${5:-$DEFAULT_MEMORY_INTERVAL}"
    local memory_mode="${6:-$DEFAULT_MEMORY_CLEANUP_MODE}"
    
    log "启动定时清理任务，间隔: ${schedule_interval}小时"
    log "文件目标: $file_targets"
    log "内存服务器: $memory_servers (${memory_interval}小时间隔, 模式: $memory_mode)"
    
    if [ "$daemon" = "true" ]; then
        log "以守护进程模式运行"
        # 如果未指定 LOG_FILE，设置一个安全默认值
        if [ -z "$LOG_FILE" ]; then
            LOG_FILE="$PROJECT_ROOT/cleanup_scheduler.log"
        fi
        mkdir -p "$(dirname "$LOG_FILE")"
        nohup bash "$0" _schedule_loop "$schedule_interval" "$file_targets" "$memory_servers" "$memory_interval" "$memory_mode" >> "$LOG_FILE" 2>&1 &
        echo $! > "$PROJECT_ROOT/cleanup_scheduler.pid"
        log "守护进程已启动，PID: $(cat "$PROJECT_ROOT/cleanup_scheduler.pid")"
    else
        bash "$0" _schedule_loop "$schedule_interval" "$file_targets" "$memory_servers" "$memory_interval" "$memory_mode"
    fi
}

# 定时循环（内部使用）
_schedule_loop() {
    local schedule_interval="$1"
    local file_targets="$2"
    local memory_servers="$3"
    local memory_interval="$4"
    local memory_mode="${5:-$DEFAULT_MEMORY_CLEANUP_MODE}"
    local interval_seconds=$((schedule_interval * 3600))
    
    while true; do
        log "执行定时清理任务..."
        run_full_cleanup "$file_targets" "$memory_servers" "$memory_interval" "$memory_mode"
        log "下次清理将在 ${schedule_interval} 小时后执行"
        sleep "$interval_seconds"
    done
}

# 停止定时任务
stop_schedule() {
    if [ -f "$PROJECT_ROOT/cleanup_scheduler.pid" ]; then
        local pid=$(cat "$PROJECT_ROOT/cleanup_scheduler.pid")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            rm -f "$PROJECT_ROOT/cleanup_scheduler.pid"
            log "定时清理任务已停止"
        else
            log "定时清理任务未运行"
            rm -f "$PROJECT_ROOT/cleanup_scheduler.pid"
        fi
    else
        log "未找到运行中的定时清理任务"
    fi
}

# 生成配置文件模板
generate_config() {
    local config_file="${1:-$CONFIG_FILE}"
    
    cat > "$config_file" << EOF
# ComfyBridge 清理配置文件
# 文件目标配置：路径:类型:参数，多个用逗号分隔
# 类型: time(按时间,参数=保留天数) | size(按大小,参数=最大MB) | count(按数量,参数=最大文件数)
FILE_TARGETS="/app/code/ComfyUI/input:size:30,/app/code/ComfyUI/input:count:300,/app/code/ComfyUI/temp:size:30,/app/code/ComfyUI/output:size:30"

# ComfyUI服务器列表，多个用逗号分隔
MEMORY_SERVERS="http://localhost:8188"

# 内存清理间隔（小时）
MEMORY_INTERVAL="6"

# 内存清理模式（history-only | full）
MEMORY_CLEANUP_MODE="history-only"

# 定时清理间隔（小时）
SCHEDULE_INTERVAL="24"
EOF
    
    log "配置文件已生成: $config_file"
}

# 加载配置文件
load_config() {
    local config_file="${1:-$CONFIG_FILE}"
    
    if [ -f "$config_file" ]; then
        source "$config_file"
        log "已加载配置文件: $config_file"
    else
        log "配置文件不存在，使用默认配置"
    fi
}

# 解析参数
parse_args() {
    while [ $# -gt 0 ]; do
        case $1 in
            --file-targets)
                FILE_TARGETS="$2"
                shift 2
                ;;
            --memory-servers)
                MEMORY_SERVERS="$2"
                shift 2
                ;;
            --memory-interval)
                MEMORY_INTERVAL="$2"
                shift 2
                ;;
            --memory-cleanup-mode)
                MEMORY_CLEANUP_MODE="$2"
                shift 2
                ;;
            --schedule-interval)
                SCHEDULE_INTERVAL="$2"
                shift 2
                ;;
            --config-file)
                CONFIG_FILE="$2"
                shift 2
                ;;
            --daemon)
                DAEMON="true"
                shift
                ;;
            *)
                shift
                ;;
        esac
    done
}

# 主逻辑
main() {
    local command="${1:-help}"
    shift
    
    # 解析参数
    parse_args "$@"
    
    # 加载配置文件
    load_config "$CONFIG_FILE"
    
    # 使用参数或配置文件中的值，优先使用命令行参数
    local file_targets="${FILE_TARGETS:-$DEFAULT_FILE_TARGETS}"
    local memory_servers="${MEMORY_SERVERS:-$DEFAULT_MEMORY_SERVERS}"
    local memory_interval="${MEMORY_INTERVAL:-$DEFAULT_MEMORY_INTERVAL}"
    local memory_mode="${MEMORY_CLEANUP_MODE:-$DEFAULT_MEMORY_CLEANUP_MODE}"
    local schedule_interval="${SCHEDULE_INTERVAL:-$DEFAULT_SCHEDULE_INTERVAL}"
    
    case "$command" in
        "file-cleanup")
            run_file_cleanup "$file_targets"
            ;;
        "memory-cleanup")
            run_memory_cleanup "$memory_servers" "$memory_interval" "$memory_mode"
            ;;
        "full-cleanup")
            run_full_cleanup "$file_targets" "$memory_servers" "$memory_interval" "$memory_mode"
            ;;
        "schedule")
            run_schedule "$schedule_interval" "${DAEMON:-false}" "$file_targets" "$memory_servers" "$memory_interval" "$memory_mode"
            ;;
        "config")
            generate_config "${CONFIG_FILE}"
            ;;
        "stop")
            stop_schedule
            ;;
        "_schedule_loop")
            _schedule_loop "$1" "$2" "$3" "$4" "$5"
            ;;
        "help"|"-h"|"--help"|*)
            show_help
            ;;
    esac
}

# 执行主函数
main "$@"
