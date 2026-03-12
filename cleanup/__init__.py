"""系统清理工具模块。

提供本地文件系统和远程服务器缓存的清理功能。

子模块:
    file_cleanup: 本地文件/目录清理（按时间、大小、数量）
    memory_cleanup: ComfyUI 服务器内存缓存清理

文件清理函数:
    cleanup_directory_by_time: 按修改时间清理目录
    cleanup_directory_by_size: 按容量限制清理目录
    cleanup_directory_by_count: 按文件数量清理目录
    cleanup_file_by_lines: 按行数截断日志文件
    cleanup_file_by_size: 按大小截断日志文件
    cleanup_multiple_targets: 批量清理多个目标
    get_target_info: 获取清理目标信息

内存清理函数:
    cleanup_comfyui_cache: 清理 ComfyUI 服务器缓存
    smart_cleanup_comfyui: 智能清理策略
"""

from cleanup.file_cleanup import (
    cleanup_directory_by_time,
    cleanup_directory_by_size,
    cleanup_directory_by_count,
    cleanup_file_by_lines,
    cleanup_file_by_size,
    cleanup_multiple_targets,
    get_target_info,
)
from cleanup.memory_cleanup import (
    cleanup_comfyui_cache,
    smart_cleanup_comfyui,
)

__all__ = [
    # 文件清理
    'cleanup_directory_by_time',
    'cleanup_directory_by_size',
    'cleanup_directory_by_count',
    'cleanup_file_by_lines',
    'cleanup_file_by_size',
    'cleanup_multiple_targets',
    'get_target_info',
    # 内存清理
    'cleanup_comfyui_cache',
    'smart_cleanup_comfyui',
]
