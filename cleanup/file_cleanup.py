#!/usr/bin/env python3
"""本地文件清理工具。

提供本地文件系统的清理功能，支持多种清理策略和批量操作。

清理策略:
    按时间: 删除超过指定天数的文件
    按大小: 当目录超过容量限制时删除旧文件
    按数量: 当文件数超过限制时删除旧文件
    日志轮转: 按行数或大小截断日志文件

Classes:
    FileCleanup: 文件清理工具类

便捷函数:
    cleanup_directory_by_time: 按时间清理目录
    cleanup_directory_by_size: 按大小清理目录
    cleanup_directory_by_count: 按数量清理目录
    cleanup_file_by_lines: 按行数截断文件
    cleanup_file_by_size: 按大小截断文件
    cleanup_multiple_targets: 批量清理多个目标
    get_target_info: 获取目标信息
"""

import os
import sys
import shutil
import tempfile
import time
import re
from datetime import datetime, timedelta
from typing import Dict, List, Union
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from nexus.logger import logger


class FileCleanup:
    """本地文件清理工具类。

    提供目录和文件的清理功能，支持多种清理策略。
    所有操作都会记录统计信息，便于追踪清理效果。

    Attributes:
        cleanup_stats: 清理统计信息字典。
    """

    def __init__(self):
        """初始化清理工具，重置统计信息。"""
        self.cleanup_stats = {
            "files_deleted": 0,
            "dirs_deleted": 0,
            "lines_removed": 0,
            "bytes_freed": 0,
            "errors": []
        }
    
    # ==================== 目录清理功能 ====================
    
    def cleanup_directory_by_time(self, 
                                 directory: Union[str, Path], 
                                 days_to_keep: int = 7,
                                 file_patterns: List[str] = None,
                                 recursive: bool = True) -> Dict:
        """按时间清理目录"""
        directory = Path(directory)
        if not directory.exists():
            logger.debug(f"目录不存在，跳过清理: {directory}")
            return {"files_deleted": 0, "bytes_freed": 0}
        
        logger.info(f"开始按时间清理目录: {directory}，保留最近 {days_to_keep} 天")
        
        cutoff_time = time.time() - (days_to_keep * 24 * 3600)
        stats = {"files_deleted": 0, "bytes_freed": 0}
        
        if file_patterns is None:
            file_patterns = ['*']
        
        # 收集所有需要删除的文件和目录
        items_to_delete = []
        
        if recursive:
            # 递归遍历所有文件和目录
            for root, dirs, files in os.walk(directory):
                root_path = Path(root)
                
                # 检查文件
                for file_name in files:
                    file_path = root_path / file_name
                    if any(file_path.match(pattern) for pattern in file_patterns):
                        try:
                            if file_path.stat().st_mtime < cutoff_time:
                                items_to_delete.append(('file', file_path))
                        except Exception as e:
                            logger.warning(f"检查文件失败 {file_path}: {e}")
                
                # 检查子目录（不包括根目录本身）
                for dir_name in dirs:
                    dir_path = root_path / dir_name
                    # 确保不删除根目录本身
                    if dir_path != directory:
                        try:
                            if dir_path.stat().st_mtime < cutoff_time:
                                # 检查目录是否应该被完全删除
                                should_delete_dir = True
                                for item in dir_path.rglob('*'):
                                    if item.is_file() and item.stat().st_mtime >= cutoff_time:
                                        should_delete_dir = False
                                        break
                                
                                if should_delete_dir:
                                    items_to_delete.append(('dir', dir_path))
                        except Exception as e:
                            logger.warning(f"检查目录失败 {dir_path}: {e}")
        else:
            # 非递归模式，只处理当前目录的文件
            for pattern in file_patterns:
                for file_path in directory.glob(pattern):
                    if file_path.is_file():
                        try:
                            if file_path.stat().st_mtime < cutoff_time:
                                items_to_delete.append(('file', file_path))
                        except Exception as e:
                            logger.warning(f"检查文件失败 {file_path}: {e}")
        
        # 执行删除操作
        for item_type, item_path in items_to_delete:
            try:
                if item_type == 'file':
                    file_size = item_path.stat().st_size
                    item_path.unlink()
                    stats["files_deleted"] += 1
                    stats["bytes_freed"] += file_size
                    logger.debug(f"已删除文件: {item_path}")
                elif item_type == 'dir':
                    # 计算目录大小
                    dir_size = sum(f.stat().st_size for f in item_path.rglob('*') if f.is_file())
                    file_count = len([f for f in item_path.rglob('*') if f.is_file()])
                    
                    # 删除整个目录
                    shutil.rmtree(item_path)
                    stats["files_deleted"] += file_count
                    stats["dirs_deleted"] = stats.get("dirs_deleted", 0) + 1
                    stats["bytes_freed"] += dir_size
                    logger.debug(f"已删除目录: {item_path} (包含 {file_count} 个文件)")
            except Exception as e:
                logger.warning(f"删除失败 {item_path}: {e}")
                self.cleanup_stats["errors"].append(f"{item_type} {item_path}: {e}")
        
        # 清理空目录（如果出错不影响主要统计结果）
        if recursive:
            try:
                self._remove_empty_dirs(directory, stats)
            except Exception as e:
                logger.warning(f"清理空目录时出错: {e}")
        
        logger.info(f"目录时间清理完成: 删除 {stats['files_deleted']} 个文件，释放 {stats['bytes_freed']} 字节")
        return stats
    
    def _remove_empty_dirs(self, directory: Path, stats: Dict) -> None:
        """递归删除空目录（在文件清理后清理剩余的空目录，但保留根目录）"""
        try:
            # 从最深层开始，向上删除空目录
            for root, dirs, files in os.walk(directory, topdown=False):
                for dir_name in dirs:
                    dir_path = Path(root) / dir_name
                    # 确保不删除根目录本身
                    if dir_path != directory:
                        try:
                            # 检查目录是否为空
                            if dir_path.exists() and dir_path.is_dir():
                                # 尝试删除空目录
                                try:
                                    dir_path.rmdir()  # 只能删除空目录
                                    stats["dirs_deleted"] = stats.get("dirs_deleted", 0) + 1
                                    logger.debug(f"已删除空目录: {dir_path}")
                                except OSError:
                                    # 目录不为空，跳过
                                    pass
                        except Exception as e:
                            logger.debug(f"检查目录时出错 {dir_path}: {e}")
        except Exception as e:
            logger.warning(f"清理空目录时出错: {e}")
    
    def cleanup_directory_by_size(self, 
                                 directory: Union[str, Path], 
                                 max_size_mb: float,
                                 file_patterns: List[str] = None,
                                 recursive: bool = True,
                                 strategy: str = "oldest_first") -> Dict:
        """按容量清理目录"""
        directory = Path(directory)
        if not directory.exists():
            logger.debug(f"目录不存在，跳过清理: {directory}")
            return {"files_deleted": 0, "bytes_freed": 0}
        
        logger.info(f"开始按容量清理目录: {directory}，最大容量 {max_size_mb} MB")
        
        max_size_bytes = max_size_mb * 1024 * 1024
        stats = {"files_deleted": 0, "bytes_freed": 0}
        
        if file_patterns is None:
            file_patterns = ['*']
        
        # 收集所有符合条件的文件
        all_files = []
        for pattern in file_patterns:
            files = directory.rglob(pattern) if recursive else directory.glob(pattern)
            
            for file_path in files:
                if file_path.is_file():
                    try:
                        file_stat = file_path.stat()
                        all_files.append({
                            'path': file_path,
                            'size': file_stat.st_size,
                            'mtime': file_stat.st_mtime
                        })
                    except Exception as e:
                        logger.warning(f"获取文件信息失败 {file_path}: {e}")
        
        # 计算当前总大小
        current_size = sum(f['size'] for f in all_files)
        logger.debug(f"目录当前大小: {current_size / 1024 / 1024:.2f} MB")
        
        if current_size <= max_size_bytes:
            logger.info("目录大小未超过限制，无需清理")
            return stats
        
        # 排序文件
        if strategy == "oldest_first":
            all_files.sort(key=lambda x: x['mtime'])
        elif strategy == "largest_first":
            all_files.sort(key=lambda x: x['size'], reverse=True)
        
        # 删除文件直到达到大小限制
        target_size = current_size
        for file_info in all_files:
            if target_size <= max_size_bytes:
                break
            
            try:
                file_info['path'].unlink()
                stats["files_deleted"] += 1
                stats["bytes_freed"] += file_info['size']
                target_size -= file_info['size']
                logger.debug(f"已删除文件: {file_info['path']}")
            except Exception as e:
                logger.warning(f"删除文件失败 {file_info['path']}: {e}")
                self.cleanup_stats["errors"].append(f"文件 {file_info['path']}: {e}")
        
        # 清理空目录（如果出错不影响主要统计结果）
        if recursive:
            try:
                self._remove_empty_dirs(directory, stats)
            except Exception as e:
                logger.warning(f"清理空目录时出错: {e}")
        
        final_size_mb = (target_size / 1024 / 1024)
        logger.info(f"目录容量清理完成: 删除 {stats['files_deleted']} 个文件，"
                   f"释放 {stats['bytes_freed'] / 1024 / 1024:.2f} MB，"
                   f"目录大小: {final_size_mb:.2f} MB")
        return stats
    
    def cleanup_directory_by_count(self,
                                   directory: Union[str, Path],
                                   max_files: int,
                                   file_patterns: List[str] = None,
                                   recursive: bool = True,
                                   strategy: str = "oldest_first") -> Dict:
        """按文件数量清理目录，超出部分按策略删除直到文件数不超过上限"""
        directory = Path(directory)
        if not directory.exists():
            logger.debug(f"目录不存在，跳过清理: {directory}")
            return {"files_deleted": 0, "bytes_freed": 0}

        if max_files < 0:
            max_files = 0

        logger.info(f"开始按数量清理目录: {directory}，最大文件数 {max_files}")
        stats = {"files_deleted": 0, "bytes_freed": 0}

        if file_patterns is None:
            file_patterns = ['*']

        # 收集所有文件
        all_files = []
        for pattern in file_patterns:
            files = directory.rglob(pattern) if recursive else directory.glob(pattern)
            for file_path in files:
                if file_path.is_file():
                    try:
                        st = file_path.stat()
                        all_files.append({
                            'path': file_path,
                            'size': st.st_size,
                            'mtime': st.st_mtime
                        })
                    except Exception as e:
                        logger.warning(f"获取文件信息失败 {file_path}: {e}")

        current_count = len(all_files)
        if current_count <= max_files:
            logger.info("目录文件数未超过限制，无需清理")
            return stats

        # 排序
        if strategy == "oldest_first":
            all_files.sort(key=lambda x: x['mtime'])
        elif strategy == "largest_first":
            all_files.sort(key=lambda x: x['size'], reverse=True)

        # 需要删除的数量
        to_delete = current_count - max_files
        deleted = 0
        for file_info in all_files:
            if deleted >= to_delete:
                break
            try:
                file_info['path'].unlink()
                stats["files_deleted"] += 1
                stats["bytes_freed"] += file_info['size']
                deleted += 1
                logger.debug(f"已删除文件: {file_info['path']}")
            except Exception as e:
                logger.warning(f"删除文件失败 {file_info['path']}: {e}")
                self.cleanup_stats["errors"].append(f"文件 {file_info['path']}: {e}")

        # 清理空目录
        if recursive:
            try:
                self._remove_empty_dirs(directory, stats)
            except Exception as e:
                logger.warning(f"清理空目录时出错: {e}")

        logger.info(f"目录数量清理完成: 删除 {stats['files_deleted']} 个文件，"
                    f"释放 {stats['bytes_freed'] / 1024 / 1024:.2f} MB，"
                    f"保留文件数: {max_files}")
        return stats
    
    # ==================== 单文件清理功能 ====================
    
    def cleanup_file_by_lines(self, log_file: str, keep_lines: int = 1000) -> Dict:
        """按行数清理单个文件"""
        log_path = Path(log_file)
        if not log_path.exists():
            return {"error": "文件不存在"}
        
        logger.info(f"开始按行数清理文件: {log_file}，保留最后 {keep_lines} 行")
        
        try:
            original_size = log_path.stat().st_size
            
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            if total_lines <= keep_lines:
                logger.info(f"文件行数 ({total_lines}) 未超过保留行数 ({keep_lines})，无需清理")
                return {"lines_removed": 0, "bytes_freed": 0}
            
            kept_lines = lines[-keep_lines:]
            
            with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as temp_file:
                temp_file.writelines(kept_lines)
                temp_path = temp_file.name
            
            shutil.move(temp_path, log_path)
            
            final_size = log_path.stat().st_size
            stats = {
                "lines_removed": total_lines - keep_lines,
                "bytes_freed": original_size - final_size,
                "original_size": original_size,
                "final_size": final_size
            }
            
            logger.info(f"文件行数清理完成: 删除 {stats['lines_removed']} 行，"
                       f"释放 {stats['bytes_freed']/1024:.2f} KB")
            
            return stats
            
        except Exception as e:
            logger.error(f"清理文件失败: {e}")
            return {"error": str(e)}
    
    def cleanup_file_by_size(self, log_file: str, max_size_mb: float = 10) -> Dict:
        """按文件大小清理单个文件"""
        log_path = Path(log_file)
        if not log_path.exists():
            return {"error": "文件不存在"}
        
        max_size_bytes = max_size_mb * 1024 * 1024
        current_size = log_path.stat().st_size
        
        logger.info(f"开始按大小清理文件: {log_file}，"
                   f"当前大小: {current_size/1024/1024:.2f} MB，最大限制: {max_size_mb} MB")
        
        if current_size <= max_size_bytes:
            logger.info("文件大小未超过限制，无需清理")
            return {"lines_removed": 0, "bytes_freed": 0}
        
        try:
            keep_bytes = int(max_size_bytes * 0.8)
            
            with open(log_path, 'rb') as f:
                f.seek(0, 2)
                file_size = f.tell()
                start_pos = file_size - keep_bytes
                f.seek(start_pos)
                f.readline()  # 跳过可能被截断的第一行
                content = f.read()
            
            with tempfile.NamedTemporaryFile(mode='wb', delete=False) as temp_file:
                temp_file.write(content)
                temp_path = temp_file.name
            
            shutil.move(temp_path, log_path)
            
            final_size = log_path.stat().st_size
            stats = {
                "original_size": current_size,
                "final_size": final_size,
                "bytes_freed": current_size - final_size
            }
            
            logger.info(f"文件大小清理完成: 释放 {stats['bytes_freed']/1024/1024:.2f} MB，"
                       f"文件大小: {final_size/1024/1024:.2f} MB")
            
            return stats
            
        except Exception as e:
            logger.error(f"清理文件失败: {e}")
            return {"error": str(e)}
    
    def cleanup_file_by_date(self, log_file: str, days_to_keep: int = 7, 
                           date_pattern: str = r'\d{4}-\d{2}-\d{2}') -> Dict:
        """按日期清理单个文件"""
        log_path = Path(log_file)
        if not log_path.exists():
            return {"error": "文件不存在"}
        
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        logger.info(f"开始按日期清理文件: {log_file}，保留 {cutoff_date.strftime('%Y-%m-%d')} 之后的日志")
        
        try:
            kept_lines = []
            removed_lines = 0
            
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    date_match = re.search(date_pattern, line)
                    if date_match:
                        try:
                            line_date = datetime.strptime(date_match.group(), '%Y-%m-%d')
                            if line_date >= cutoff_date:
                                kept_lines.append(line)
                            else:
                                removed_lines += 1
                        except ValueError:
                            kept_lines.append(line)
                    else:
                        kept_lines.append(line)
            
            if removed_lines == 0:
                logger.info("没有找到需要清理的过期日志")
                return {"lines_removed": 0, "bytes_freed": 0}
            
            original_size = log_path.stat().st_size
            
            with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as temp_file:
                temp_file.writelines(kept_lines)
                temp_path = temp_file.name
            
            shutil.move(temp_path, log_path)
            
            final_size = log_path.stat().st_size
            stats = {
                "lines_removed": removed_lines,
                "bytes_freed": original_size - final_size,
                "original_size": original_size,
                "final_size": final_size
            }
            
            logger.info(f"文件日期清理完成: 删除 {removed_lines} 行过期日志，"
                       f"释放 {stats['bytes_freed']/1024:.2f} KB")
            
            return stats
            
        except Exception as e:
            logger.error(f"清理文件失败: {e}")
            return {"error": str(e)}
    
    def rotate_file(self, log_file: str, backup_count: int = 5) -> Dict:
        """文件轮转"""
        log_path = Path(log_file)
        if not log_path.exists():
            return {"error": "文件不存在"}
        
        try:
            # 轮转现有备份文件
            for i in range(backup_count - 1, 0, -1):
                old_backup = log_path.with_suffix(f'{log_path.suffix}.{i}')
                new_backup = log_path.with_suffix(f'{log_path.suffix}.{i + 1}')
                
                if old_backup.exists():
                    if new_backup.exists():
                        new_backup.unlink()
                    old_backup.rename(new_backup)
            
            # 创建第一个备份
            first_backup = log_path.with_suffix(f'{log_path.suffix}.1')
            if first_backup.exists():
                first_backup.unlink()
            
            original_size = log_path.stat().st_size
            shutil.copy2(log_path, first_backup)
            
            # 清空原文件
            with open(log_path, 'w') as f:
                pass
            
            logger.info(f"文件轮转完成: {log_file} -> {first_backup}")
            
            return {
                "rotated": True,
                "backup_file": str(first_backup),
                "original_size": original_size,
                "bytes_freed": original_size
            }
            
        except Exception as e:
            logger.error(f"文件轮转失败: {e}")
            return {"error": str(e)}
    
    # ==================== 批量清理功能 ====================
    
    def cleanup_multiple_targets(self, cleanup_configs: List[Dict]) -> Dict:
        """批量清理多个目标（目录和文件）"""
        logger.info(f"开始批量清理 {len(cleanup_configs)} 个目标")
        
        total_stats = {
            "files_deleted": 0,
            "dirs_deleted": 0,
            "lines_removed": 0,
            "bytes_freed": 0,
            "targets_processed": 0,
            "errors": []
        }
        
        for config in cleanup_configs:
            try:
                target = config.get("target")
                target_type = config.get("target_type", "directory")  # "directory" 或 "file"
                cleanup_type = config.get("cleanup_type", "time")     # "time", "size", "lines", "date", "rotate"
                
                if target_type == "directory":
                    if cleanup_type == "time":
                        stats = self.cleanup_directory_by_time(
                            directory=target,
                            days_to_keep=config.get("days_to_keep", 7),
                            file_patterns=config.get("file_patterns"),
                            recursive=config.get("recursive", True)
                        )
                    elif cleanup_type == "size":
                        stats = self.cleanup_directory_by_size(
                            directory=target,
                            max_size_mb=config.get("max_size_mb", 100),
                            file_patterns=config.get("file_patterns"),
                            recursive=config.get("recursive", True),
                            strategy=config.get("strategy", "oldest_first")
                        )
                    elif cleanup_type == "count":
                        stats = self.cleanup_directory_by_count(
                            directory=target,
                            max_files=int(config.get("max_files", 0)),
                            file_patterns=config.get("file_patterns"),
                            recursive=config.get("recursive", True),
                            strategy=config.get("strategy", "oldest_first")
                        )
                    else:
                        logger.warning(f"目录不支持的清理类型: {cleanup_type}")
                        continue
                
                elif target_type == "file":
                    if cleanup_type == "lines":
                        stats = self.cleanup_file_by_lines(
                            log_file=target,
                            keep_lines=config.get("keep_lines", 1000)
                        )
                    elif cleanup_type == "size":
                        stats = self.cleanup_file_by_size(
                            log_file=target,
                            max_size_mb=config.get("max_size_mb", 10)
                        )
                    elif cleanup_type == "date":
                        stats = self.cleanup_file_by_date(
                            log_file=target,
                            days_to_keep=config.get("days_to_keep", 7),
                            date_pattern=config.get("date_pattern", r'\d{4}-\d{2}-\d{2}')
                        )
                    elif cleanup_type == "rotate":
                        stats = self.rotate_file(
                            log_file=target,
                            backup_count=config.get("backup_count", 5)
                        )
                    else:
                        logger.warning(f"文件不支持的清理类型: {cleanup_type}")
                        continue
                else:
                    logger.warning(f"未知目标类型: {target_type}")
                    continue
                
                # 累加统计信息
                if "error" not in stats:
                    total_stats["files_deleted"] += stats.get("files_deleted", 0)
                    total_stats["dirs_deleted"] += stats.get("dirs_deleted", 0)
                    total_stats["lines_removed"] += stats.get("lines_removed", 0)
                    total_stats["bytes_freed"] += stats.get("bytes_freed", 0)
                    total_stats["targets_processed"] += 1
                else:
                    total_stats["errors"].append(f"目标 {target}: {stats['error']}")
                
            except Exception as e:
                logger.error(f"清理目标失败 {config.get('target')}: {e}")
                total_stats["errors"].append(f"目标 {config.get('target')}: {e}")
        
        logger.info(f"批量清理完成: 处理 {total_stats['targets_processed']} 个目标，"
                   f"删除 {total_stats['files_deleted']} 个文件，"
                   f"删除 {total_stats['lines_removed']} 行，"
                   f"释放 {total_stats['bytes_freed'] / 1024 / 1024:.2f} MB")
        
        return total_stats

    # ==================== 信息查询 ====================
    def get_target_info(self, target: Union[str, Path]) -> Dict:
        """获取目标（目录/文件）的信息统计
        
        返回:
            {
              "exists": bool,
              "type": "directory"|"file"|"missing",
              "size_bytes": int,
              "files": int,        # 若为目录
              "dirs": int          # 若为目录
            }
        """
        p = Path(target)
        info = {
            "exists": p.exists(),
            "type": "missing",
            "size_bytes": 0,
            "files": 0,
            "dirs": 0,
        }
        if not p.exists():
            return info
        if p.is_file():
            try:
                info["type"] = "file"
                info["size_bytes"] = p.stat().st_size
            except Exception as e:
                logger.warning(f"获取文件信息失败 {p}: {e}")
            return info
        if p.is_dir():
            info["type"] = "directory"
            size = 0
            files = 0
            dirs = 0
            try:
                for root, dnames, fnames in os.walk(p):
                    dirs += len(dnames)
                    for fn in fnames:
                        fpath = Path(root) / fn
                        try:
                            if fpath.is_file():
                                files += 1
                                size += fpath.stat().st_size
                        except Exception:
                            # 忽略单个文件统计失败
                            pass
                info["size_bytes"] = size
                info["files"] = files
                info["dirs"] = dirs
            except Exception as e:
                logger.warning(f"遍历目录失败 {p}: {e}")
            return info
        return info


# 全局清理器实例
file_cleanup = FileCleanup()


# 便捷函数
def cleanup_directory_by_time(directory: str, days_to_keep: int = 7, 
                             file_patterns: List[str] = None) -> Dict:
    """按时间清理目录的便捷函数"""
    return file_cleanup.cleanup_directory_by_time(directory, days_to_keep, file_patterns)


def cleanup_directory_by_size(directory: str, max_size_mb: float,
                             strategy: str = "oldest_first") -> Dict:
    """按容量清理目录的便捷函数"""
    return file_cleanup.cleanup_directory_by_size(directory, max_size_mb, strategy=strategy)

def cleanup_directory_by_count(directory: str, max_files: int,
                               strategy: str = "oldest_first") -> Dict:
    """按数量清理目录的便捷函数"""
    return file_cleanup.cleanup_directory_by_count(directory, max_files, strategy=strategy)


def cleanup_file_by_lines(log_file: str, keep_lines: int = 1000) -> Dict:
    """按行数清理文件的便捷函数"""
    return file_cleanup.cleanup_file_by_lines(log_file, keep_lines)


def cleanup_file_by_size(log_file: str, max_size_mb: float = 10) -> Dict:
    """按大小清理文件的便捷函数"""
    return file_cleanup.cleanup_file_by_size(log_file, max_size_mb)


def get_target_info(target: str) -> Dict:
    """获取目标信息的便捷函数"""
    return file_cleanup.get_target_info(target)


def cleanup_multiple_targets(configs: List[Dict]) -> Dict:
    """批量清理多个目标的便捷函数"""
    return file_cleanup.cleanup_multiple_targets(configs)
