#!/usr/bin/env python3
"""ComfyUI 服务器内存清理工具。

提供 ComfyUI 服务器的远程缓存清理功能，通过 HTTP API 释放服务器资源。

清理模式:
    history-only: 仅清理执行历史，保留模型缓存（推荐，不影响性能）
    full: 完整清理，包括卸载模型和释放内存（会影响下次请求速度）

Classes:
    MemoryCleanup: 异步内存清理工具类

便捷函数:
    cleanup_comfyui_cache: 清理 ComfyUI 缓存
    smart_cleanup_comfyui: 智能清理策略

Note:
    本模块使用 aiohttp 进行异步 HTTP 请求，支持并发清理多个服务器。
    本地文件清理请使用 file_cleanup.py。
"""

import asyncio
import aiohttp
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from nexus.logger import logger


class MemoryCleanup:
    """ComfyUI 服务器内存清理工具。

    异步清理工具，支持并发处理多个 ComfyUI 服务器。
    使用异步上下文管理器确保连接正确关闭。

    Attributes:
        servers: ComfyUI 服务器地址列表。
        session: aiohttp 会话对象。
        stats: 清理统计信息。

    Example:
        >>> async with MemoryCleanup(['http://localhost:8188']) as cleaner:
        ...     result = await cleaner.clear_history_cache()
    """

    def __init__(self, servers: List[str] = None):
        """初始化内存清理工具。

        Args:
            servers: ComfyUI 服务器地址列表，默认为 ['http://localhost:8188']。
        """
        self.servers = servers or ['http://localhost:8188']
        self.session = None
        self.stats = {
            "last_cleanup": None,
            "total_cleanups": 0,
            "servers_processed": 0,
            "errors": []
        }

    async def __aenter__(self):
        """异步上下文管理器入口，创建 HTTP 会话。"""
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口，关闭 HTTP 会话。"""
        if self.session:
            await self.session.close()
    
    # ==================== 内存缓存清理 ====================
    
    async def clear_history_cache(self, server_url: str = None, mode: str = "history-only") -> Dict:
        """清理执行历史和任务数据
        
        Args:
            server_url: 指定服务器，None 则清理所有服务器
            mode: 清理模式
                - "history-only": 仅清理历史，保留模型与缓存（推荐，适合 --gpu-only 模式）
                - "full": 完整清理，包括卸载模型与清空缓存（会影响性能）
            
        Returns:
            Dict: 清理结果
        """
        targets = [server_url] if server_url else self.servers
        results = {
            "servers_processed": 0,
            "servers_success": 0,
            "servers_failed": 0,
            "details": {},
            "errors": []
        }
        
        for server in targets:
            try:
                logger.info(f"开始清理服务器缓存: {server} (模式: {mode})")
                
                # 1. 根据模式决定是否释放内存
                if mode == "full":
                    logger.info(f"[完整模式] 释放 CPU 内存（模型、缓存）...")
                    memory_result = await self._free_memory(server)
                else:
                    logger.info(f"[仅历史模式] 跳过模型与缓存清理，保留以提升性能")
                    memory_result = {"freed": False, "skipped": True, "reason": "history-only mode"}
                
                # 2. 清理执行历史（总是执行）
                logger.info(f"清理执行历史记录...")
                history_result = await self._clear_history(server)
                
                results["details"][server] = {
                    "memory_freed": memory_result.get("freed", False),
                    "history_cleared": history_result.get("cleared", False),
                    "timestamp": datetime.now().isoformat()
                }
                
                # 只要有一个成功就算成功
                if memory_result.get("freed", False) or history_result.get("cleared", False):
                    results["servers_success"] += 1
                    logger.info(f"服务器缓存清理完成: {server}")
                else:
                    results["servers_failed"] += 1
                    error_msg = f"服务器 {server} 清理失败"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
                
            except Exception as e:
                error_msg = f"服务器 {server} 清理失败: {str(e)}"
                logger.error(error_msg)
                results["errors"].append(error_msg)
                results["servers_failed"] += 1
            
            results["servers_processed"] += 1
        
        self.stats["last_cleanup"] = datetime.now().isoformat()
        self.stats["total_cleanups"] += 1
        self.stats["servers_processed"] += results["servers_processed"]
        
        return results
    
    async def _free_memory(self, server_url: str) -> Dict:
        """释放 ComfyUI CPU 内存（最重要！）
        
        调用 /free 端点释放：
        - 未使用的模型（CPU 内存）
        - PyTorch CPU 缓存
        - 图像缓存
        - 历史数据
        """
        try:
            url = f"{server_url.rstrip('/')}/free"
            payload = {"unload_models": True, "free_memory": True}
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    # 某些版本的 /free 返回空响应体或非 JSON 内容
                    try:
                        _ = await response.text()
                    except Exception:
                        pass
                    logger.info(f"CPU 内存释放请求已发送成功: {server_url}")
                    return {"freed": True}
                else:
                    logger.warning(f"CPU 内存释放失败: {server_url}, HTTP {response.status}")
                    return {"freed": False, "error": f"HTTP {response.status}"}
        except Exception as e:
            logger.debug(f"CPU 内存释放失败: {e}")
            return {"freed": False, "error": str(e)}
    
    async def _clear_history(self, server_url: str) -> Dict:
        """清理执行历史
        
        使用 ComfyUI 标准 API：POST /history {"clear": True}
        参考: https://github.com/comfyanonymous/ComfyUI/blob/master/server.py
        """
        try:
            url = f"{server_url.rstrip('/')}/history"
            payload = {"clear": True}
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    logger.info(f"执行历史已清理: {server_url}")
                    return {"cleared": True, "method": "POST /history"}
                else:
                    logger.warning(f"清理历史失败: {server_url}, HTTP {response.status}")
                    return {"cleared": False, "error": f"HTTP {response.status}"}
        except Exception as e:
            logger.debug(f"清理历史异常: {e}")
            return {"cleared": False, "error": str(e)}
    
    
    
    # ==================== 智能清理策略 ====================
    
    async def smart_cleanup(self, mode: str = "history-only") -> Dict:
        """智能清理策略 - 清理服务器缓存
        
        Args:
            mode: 清理模式
                - "history-only": 仅清理历史，保留模型与缓存（默认，推荐）
                - "full": 完整清理，包括卸载模型与清空缓存
        
        清理内容（根据模式）：
        - 执行历史数据（总是清理）
        - CPU 内存/模型/缓存（仅 full 模式）
        
        Returns:
            Dict: 清理结果，包含 servers_processed 等字段
        """
        logger.info(f"开始 ComfyUI 缓存清理 (模式: {mode})")
        
        # 清理执行历史缓存（根据模式决定是否包含 CPU 内存释放）
        if mode == "history-only":
            logger.info("清理服务器历史（保留模型与缓存）")
        else:
            logger.info("清理服务器缓存（CPU 内存 + 历史）")
        cleanup_result = await self.clear_history_cache(mode=mode)
        
        # 返回扁平化的结果，方便 shell 脚本使用
        results = {
            "servers_processed": cleanup_result.get("servers_processed", 0),
            "servers_success": cleanup_result.get("servers_success", 0),
            "servers_failed": cleanup_result.get("servers_failed", 0),
            "details": cleanup_result.get("details", {}),
            "errors": cleanup_result.get("errors", []),
            "mode": mode,
            "strategy": "history_only" if mode == "history-only" else "memory_and_history",
            "timestamp": datetime.now().isoformat(),
            # 保留原始结果供调试
            "cleanup_result": cleanup_result
        }
        
        return results
    
    # ==================== 状态监控 ====================
    
    async def get_servers_status(self) -> Dict:
        """获取所有服务器状态"""
        status_results = {}
        
        for server in self.servers:
            try:
                status = await self._get_server_status(server)
                status_results[server] = status
            except Exception as e:
                logger.error(f"获取服务器状态失败 {server}: {e}")
                status_results[server] = {"error": str(e)}
        
        return status_results
    
    async def _get_server_status(self, server_url: str) -> Dict:
        """获取单个服务器状态"""
        try:
            # 简单的健康检查
            url = f"{server_url}/history"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    history_count = len(data.get("History", {}))
                    return {
                        "status": "online",
                        "history_count": history_count,
                        "last_check": datetime.now().isoformat()
                    }
                else:
                    return {"status": "error", "error": f"HTTP {response.status}"}
        except Exception as e:
            return {"status": "offline", "error": str(e)}
    
    # ==================== 定时清理 ====================
    
    async def schedule_cleanup(self, interval_hours: int = 24) -> None:
        """定时清理任务
        
        Args:
            interval_hours: 清理间隔（小时）
        """
        logger.info(f"启动定时清理任务，间隔: {interval_hours} 小时")
        
        while True:
            try:
                await self.smart_cleanup()
                logger.info(f"定时清理完成，下次清理时间: {datetime.now() + timedelta(hours=interval_hours)}")
                
            except Exception as e:
                logger.error(f"定时清理失败: {e}")
            
            # 等待下次清理
            await asyncio.sleep(interval_hours * 3600)
    
    def get_stats(self) -> Dict:
        """获取清理统计信息"""
        return self.stats.copy()


# 便捷函数
async def cleanup_comfyui_history(servers: List[str] = None) -> Dict:
    """清理 ComfyUI 执行历史的便捷函数"""
    async with MemoryCleanup(servers) as manager:
        return await manager.clear_history_cache()


async def smart_cleanup_comfyui(servers: List[str] = None, mode: str = "history-only") -> Dict:
    """智能清理 ComfyUI 缓存的便捷函数
    
    Args:
        servers: ComfyUI 服务器列表
        mode: 清理模式 ("history-only" | "full")
    """
    async with MemoryCleanup(servers) as manager:
        return await manager.smart_cleanup(mode=mode)


# 全局内存清理器实例
memory_cleanup = MemoryCleanup()


async def cleanup_comfyui_cache() -> Dict:
    """清理 ComfyUI 缓存的便捷函数"""
    return await smart_cleanup_comfyui()

