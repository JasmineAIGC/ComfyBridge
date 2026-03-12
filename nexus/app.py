"""FastAPI 应用配置模块。

负责 FastAPI 应用的初始化、配置和生命周期管理。

功能:
    应用初始化: 创建 FastAPI 实例，配置元数据
    中间件: CORS 跨域支持、Gzip 压缩
    生命周期: 启动时预加载模型，关闭时清理资源

Functions:
    create_app: 创建并配置 FastAPI 应用

Global:
    app: FastAPI 应用实例

Note:
    配置从 config.py 读取，遵循配置驱动设计。
"""

import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

import config
from nexus.logger import logger, log_execution_time, log_context, log_startup_info, log_shutdown_info

def create_app():
    """创建并配置 FastAPI 应用实例
    
    创建一个新的 FastAPI 应用实例，并进行必要的配置，包括添加中间件、注册事件处理程序等。
    这个工厂函数模式允许在测试中创建隔离的应用实例，并且使得应用配置集中在一个位置。
    
    返回:
        FastAPI: 配置好的 FastAPI 应用实例，包含所有必要的中间件和事件处理程序
    
    示例:
        >>> app = create_app()
        >>> # 现在可以使用 app 注册路由或进行其他配置
        >>> @app.get("/custom-route")
        >>> def custom_route():
        >>>     return {"message": "Hello World"}
    """
    # 创建 FastAPI 应用实例，设置基本元数据
    app = FastAPI(
        title="ComfyBridge",                      # API 标题，用于生成文档
        description="基于 ComfyUI 的通用 AIGC API 封装框架",  # API 描述
        version=config.API_VERSION,               # API 版本号，从配置文件读取
        docs_url="/docs",                         # Swagger UI 文档路径
        redoc_url="/redoc"                        # ReDoc 文档路径
    )
    
    # 添加 CORS 中间件，允许跨域请求
    # 注意：在生产环境中应限制 allow_origins 为特定域名
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],                # 允许的源地址，* 表示允许所有源
        allow_credentials=True,             # 允许发送认证信息（cookies）
        allow_methods=["*"],                # 允许的 HTTP 方法
        allow_headers=["*"],                # 允许的 HTTP 头部
    )
    
    # 添加 Gzip 压缩中间件，减少响应体积
    # minimum_size 参数指定了触发压缩的最小响应大小（字节）
    app.add_middleware(GZipMiddleware, minimum_size=config.GZIP_MIN_SIZE)
    
    # 添加启动事件
    @app.on_event("startup")
    @log_execution_time
    async def startup_event():
        """应用启动事件处理函数
        
        在 FastAPI 应用启动时自动执行的事件处理函数。负责执行以下关键任务：
        1. 记录应用启动时间和详细的配置信息
        2. 创建必要的目录结构，确保应用运行环境完整
        3. 预加载关键资源，提高首次请求响应速度
        
        该函数使用 @log_execution_time 装饰器进行性能监控，并使用结构化日志记录启动过程中的关键信息。
        对于每个主要初始化步骤，使用 log_context 上下文管理器进行分组和性能跟踪。
        
        返回:
            None: 该函数不返回任何值，仅执行初始化操作。
        
        异常处理:
            如果初始化过程中发生异常，将被 log_execution_time 装饰器捕获并记录，
            但不会阻止应用启动失败。严重错误应在实现中抛出异常以防止应用在不完整状态下运行。
        """
        # 记录启动时间，存储在应用状态中供关闭时计算总运行时间
        app.state.start_time = time.time()
        
        # 记录标准化的启动信息，包括应用名称、版本和关键配置项
        # 这些信息对于系统监控和问题排查非常重要
        log_startup_info(
            app_name="ComfyBridge", 
            version=config.API_VERSION,
            config_items={
                "服务器": f"{config.SERVER_HOST}:{config.SERVER_PORT}",  # 服务器监听地址
                "调试模式": config.DEBUG_MODE,                      # 是否启用调试模式
                "日志级别": config.LOG_LEVEL,                      # 日志记录级别
                "ComfyUI服务器": config.COMFY_SERVERS,                # ComfyUI 服务器列表
                "功能名称": config.FUNCTION_NAME,                  # 当前功能名称
                "工作流路径": config.WORKFLOW_PATH              # 工作流配置路径
            }
        )
        
        # 检查并创建必要的目录结构
        with log_context("目录结构检查"):
            for dir_path in [config.LOG_DIR, config.TEMPLATE_DIR, config.WORKFLOW_DIR, config.OUTPUT_DIR]:
                os.makedirs(dir_path, exist_ok=True)
            logger.debug("目录检查完成")
        
        # 预加载关键资源，提高首次请求响应速度
        # 这一步骤将在应用启动时加载常用资源，而不是在首次请求时加载
        with log_context("资源预加载"):
            # 加载 ComfyUI 接口和工作流配置
            from nexus.comfy import comfy_interface
            # 记录工作流加载结果
            logger.info(f"已加载 {len(comfy_interface.workflows)} 个工作流")
            
            # 预加载处理器工具集
            from processors import initialize_tools
            initialize_tools()
        
        logger.info("ComfyBridge 启动完成，准备就绪")
    
    # 添加关闭事件
    @app.on_event("shutdown")
    @log_execution_time
    async def shutdown_event():
        """应用关闭事件处理函数
        
        在 FastAPI 应用关闭时自动执行的事件处理函数。负责执行以下关键任务：
        1. 安全地清理应用资源，如关闭数据库连接、释放内存等
        2. 记录应用关闭信息和总运行时间统计
        3. 确保所有进行中的任务安全终止
        
        该函数使用 @log_execution_time 装饰器进行性能监控，并使用 log_context 上下文管理器
        对清理过程进行分组和性能跟踪。关闭信息通过 log_shutdown_info 函数记录，
        包括应用名称、关闭时间和总运行时间统计。
        
        返回:
            None: 该函数不返回任何值，仅执行清理操作。
        
        注意:
            关闭事件处理函数应尽可能地处理所有异常情况，以确保应用能够优雅地关闭。
            即使在清理过程中发生错误，也应确保关闭信息能够被记录。
        """
        logger.info("服务正在关闭...")
        
        # 清理应用资源，确保所有连接和临时文件被正确关闭和处理
        # 这一步骤对于防止资源泄漏和确保系统正常运行至关键
        with log_context("资源清理"):
            cleanup_success = True
            cleanup_errors = []
            
            # 导入统一清理工具
            import sys
            from pathlib import Path
            
            # 确保清理工具路径在 sys.path 中
            cleanup_path = Path(__file__).parent.parent / "cleanup"
            if str(cleanup_path) not in sys.path:
                sys.path.append(str(cleanup_path))
            
            # 确保目录存在（目录创建失败不应影响清理流程）
            try:
                os.makedirs(config.LOG_DIR, exist_ok=True)
                os.makedirs(config.OUTPUT_DIR, exist_ok=True)
            except Exception as e:
                logger.warning(f"创建清理目录失败: {e}，将跳过相关清理")
            
            # 尝试文件系统清理
            try:
                from file_cleanup import cleanup_multiple_targets
                
                # 清理配置
                cleanup_configs = [
                    {
                        "target": config.LOG_DIR,
                        "target_type": "directory",
                        "cleanup_type": "time",
                        "days_to_keep": 7,
                        "file_patterns": ["*.log", "*.txt"],
                        "recursive": True
                    },
                    {
                        "target": config.OUTPUT_DIR,
                        "target_type": "directory", 
                        "cleanup_type": "size",
                        "max_size_mb": 500,
                        "strategy": "oldest_first",
                        "recursive": True
                    }
                ]
                
                # 执行批量清理
                cleanup_result = cleanup_multiple_targets(cleanup_configs)
                logger.info(f"文件系统清理完成: 处理了 {cleanup_result.get('targets_processed', 0)} 个目标，"
                           f"删除了 {cleanup_result.get('files_deleted', 0)} 个文件，"
                           f"释放了 {cleanup_result.get('bytes_freed', 0) / 1024 / 1024:.2f} MB")
            except ImportError as e:
                cleanup_success = False
                error_msg = f"无法导入文件清理工具: {e}"
                cleanup_errors.append(error_msg)
                logger.error(error_msg)
            except Exception as e:
                cleanup_success = False
                error_msg = f"文件系统清理失败: {e}"
                cleanup_errors.append(error_msg)
                logger.error(error_msg)
            
            # 尝试 ComfyUI 缓存清理
            try:
                from memory_cleanup import cleanup_comfyui_cache
                
                comfy_result = await cleanup_comfyui_cache()
                if "error" not in comfy_result:
                    logger.info(f"ComfyUI 缓存清理完成: 处理了 {comfy_result.get('servers_processed', 0)} 个服务器，"
                               f"成功 {comfy_result.get('servers_success', 0)} 个")
                else:
                    cleanup_success = False
                    error_msg = f"ComfyUI 缓存清理失败: {comfy_result.get('error')}"
                    cleanup_errors.append(error_msg)
                    logger.error(error_msg)
            except ImportError as e:
                cleanup_success = False
                error_msg = f"无法导入内存清理工具: {e}"
                cleanup_errors.append(error_msg)
                logger.error(error_msg)
            except Exception as e:
                cleanup_success = False
                error_msg = f"ComfyUI 缓存清理失败: {e}"
            
            # 记录关闭信息
            if hasattr(app.state, "start_time"):
                log_shutdown_info("ComfyBridge", app.state.start_time)
    
    return app

# 创建 FastAPI 应用实例
app = create_app()
