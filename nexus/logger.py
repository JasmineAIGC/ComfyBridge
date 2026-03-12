"""日志配置模块。

提供统一的日志配置、记录和管理功能。

功能:
    日志配置: 支持标准/详细格式，可配置级别和输出目标
    执行跟踪: @log_execution_time 装饰器记录函数耗时
    请求日志: log_request 记录标准化的 API 请求信息
    上下文管理: log_context 跟踪代码块执行状态
    生命周期: log_startup_info/log_shutdown_info 记录启停信息

Functions:
    setup_logger: 配置日志记录器
    log_execution_time: 执行时间装饰器
    log_request: 请求日志记录
    log_context: 上下文管理器
    log_startup_info: 启动信息记录
    log_shutdown_info: 关闭信息记录

Global:
    logger: 默认日志记录器实例

Note:
    支持日志轮替（按大小），遵循日志最佳实践。
"""

import os
import sys
import logging
import logging.handlers
import time
import functools
import traceback
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, Dict, Any, Union, Callable, Generator, TypeVar, cast
import asyncio

# 设置时区为中国时区
os.environ['TZ'] = 'Asia/Shanghai'

import config

# 日志目录：从配置文件获取，默认为 "logs" 目录
LOG_DIR = getattr(config, "LOG_DIR", "logs")

# 日志文件名：主日志文件名称，系统将自动添加日期后缀进行轮替
LOG_FILE = "comfybridge.log"

# 日志文件大小限制：默认为10MB
LOG_MAX_SIZE = getattr(config, "LOG_MAX_SIZE", 10 * 1024 * 1024)  # 10MB

# 日志文件备份数量：默认保留10个备份文件
LOG_BACKUP_COUNT = getattr(config, "LOG_BACKUP_COUNT", 10)

# 标准日志格式：包含时间、级别、模块名和消息
LOG_FORMAT = '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'

# 详细日志格式：在标准格式基础上增加文件名和行号，用于调试和问题排查
DETAILED_LOG_FORMAT = '%(asctime)s - %(levelname)s - [%(name)s] - [%(filename)s:%(lineno)d] - %(message)s'

# 日志级别映射：将配置文件中的字符串级别映射到 logging 模块的常量
LOG_LEVELS = {
    "debug": logging.DEBUG,      # 调试级别：最详细的日志信息，用于开发和调试
    "info": logging.INFO,       # 信息级别：正常操作信息，默认级别
    "warning": logging.WARNING, # 警告级别：潜在问题或非关键性错误
    "error": logging.ERROR,     # 错误级别：影响功能但不影响系统运行的错误
    "critical": logging.CRITICAL # 严重级别：导致系统无法正常运行的错误
}

def get_log_level() -> int:
    """获取日志级别常量
    
    从配置文件中获取日志级别字符串，并转换为相应的 logging 模块常量。
    如果配置文件中未指定日志级别或指定了无效的级别，则默认使用 INFO 级别。
    
    返回:
        int: logging 模块定义的日志级别常量（DEBUG、INFO、WARNING、ERROR 或 CRITICAL）
    """
    # 从配置中获取日志级别字符串并转换为小写
    log_level_name = getattr(config, "LOG_LEVEL", "info").lower()
    # 将字符串级别映射到常量，如果映射失败则默认使用 INFO
    return LOG_LEVELS.get(log_level_name, logging.INFO)

def setup_logger(name: Optional[str] = None, detailed: bool = False) -> logging.Logger:
    """配置并初始化日志记录器
    
    创建一个新的日志记录器或返回已存在的记录器。配置包括日志级别、格式化器、
    控制台输出和文件输出。文件输出采用每日轮替策略，保留最近7天的日志。
    
    参数:
        name: 日志记录器名称，用于区分不同模块的日志。默认为 None，表示使用根记录器。
        detailed: 如果为 True，使用详细日志格式，包含文件名和行号信息，适用于调试环境。
                 如果为 False，使用标准格式，适用于生产环境。默认为 False。
        
    返回:
        logging.Logger: 配置好的日志记录器实例，可直接用于记录日志
    
    示例:
        >>> logger = setup_logger("comfybridge.api")
        >>> logger.info("服务启动")
        >>> debug_logger = setup_logger("comfybridge.debug", detailed=True)
        >>> debug_logger.debug("调试信息")
    """
    # 确保日志目录存在
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # 创建日志记录器
    logger = logging.getLogger(name)
    
    # 如果已经配置过，直接返回
    if logger.handlers:
        return logger
    
    # 获取日志级别
    log_level = get_log_level()
    
    # 设置日志级别
    logger.setLevel(log_level)
    
    # 选择日志格式
    log_format = DETAILED_LOG_FORMAT if detailed else LOG_FORMAT
    
    # 创建格式化器
    formatter = logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S')
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    
    # 添加控制台处理器
    logger.addHandler(console_handler)
    
    # 添加文件处理器 - 基于大小的日志轮转
    log_file = os.path.join(LOG_DIR, LOG_FILE)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=LOG_MAX_SIZE,  # 文件大小上限
        backupCount=LOG_BACKUP_COUNT,  # 保留的备份文件数量
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    
    # 添加文件处理器
    logger.addHandler(file_handler)
    
    return logger

# 定义类型变量用于装饰器，确保类型检查和代码提示正常工作
_F = TypeVar('_F', bound=Callable[..., Any])

def log_execution_time(func: Optional[_F] = None, *, logger: Optional[logging.Logger] = None, level: str = "info") -> Union[_F, Callable[[_F], _F]]:
    """装饰器：自动记录函数的执行时间和状态
    
    该装饰器可以应用于任何函数或方法，将自动记录其开始执行、执行完成和执行时间。
    如果函数执行过程中抛出异常，将记录异常信息并重新抛出异常。支持两种使用方式：
    1. 作为普通装饰器：@log_execution_time
    2. 带参数的装饰器：@log_execution_time(level="debug")
    
    参数:
        func: 被装饰的函数或方法。当作为普通装饰器使用时，该参数会被自动传入。
        logger: 用于记录日志的 Logger 实例。如果为 None，将尝试使用全局 logger 变量
               或创建一个新的根记录器。默认为 None。
        level: 日志级别，可以是 "debug"、"info"、"warning"、"error" 或 "critical"。
               如果指定了无效的级别，将默认使用 "info"。默认为 "info"。
        
    返回:
        Union[_F, Callable[[_F], _F]]: 如果直接作为装饰器使用，返回装饰后的函数。
                                      如果使用参数调用，返回一个接受函数并返回装饰后函数的装饰器。
    
    示例:
        >>> @log_execution_time
        ... def example_function(x, y):
        ...     return x + y
        ...
        >>> @log_execution_time(level="debug")
        ... def debug_function(x, y):
        ...     return x * y
    """
    def decorator(func: _F) -> _F:
        # 检查是否为异步函数
        is_async = asyncio.iscoroutinefunction(func)
        
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            func_name = func.__qualname__
            log = logger or globals().get('logger') or logging.getLogger()
            log_method = getattr(log, level.lower(), log.info)
            
            log_method(f"开始执行异步函数: {func_name}")
            start_time = time.time()
            
            try:
                # 异步调用函数
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time
                log_method(f"异步函数 {func_name} 执行成功，耗时: {execution_time:.4f} 秒")
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                log.error(f"异步函数 {func_name} 执行失败，耗时: {execution_time:.4f} 秒，异常: {str(e)}")
                log.debug(traceback.format_exc())
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            func_name = func.__qualname__
            log = logger or globals().get('logger') or logging.getLogger()
            log_method = getattr(log, level.lower(), log.info)
            
            log_method(f"开始执行函数: {func_name}")
            start_time = time.time()
            
            try:
                # 同步调用函数
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                log_method(f"函数 {func_name} 执行成功，耗时: {execution_time:.4f} 秒")
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                log.error(f"函数 {func_name} 执行失败，耗时: {execution_time:.4f} 秒，异常: {str(e)}")
                log.debug(traceback.format_exc())
                raise
        
        # 根据函数类型返回相应的装饰器
        if is_async:
            return cast(_F, async_wrapper)
        else:
            return cast(_F, sync_wrapper)
    
    if func is None:
        return decorator
    
    return decorator(func)

# 创建默认日志记录器
logger = setup_logger("comfybridge")

# 辅助日志函数
def log_request(request_id: str, function_name: str, message: str, level: str = "info", extra: Optional[Dict[str, Any]] = None):
    """记录标准化的 API 请求日志
    
    使用一致的格式记录 API 请求的处理过程。日志格式为 "[request_id] [function_name] message | extra_info"，
    其中 extra_info 是可选的额外元数据。这种标准化的格式便于日志分析和请求跟踪。
    
    参数:
        request_id: 请求的唯一标识符，通常是 UUID 格式，用于跟踪整个请求的生命周期。
        function_name: 处理请求的功能或服务名称，用于区分不同的 API 端点。
        message: 主要的日志消息内容，应简洁清晰地描述当前操作或状态。
        level: 日志级别，可以是 "debug"、"info"、"warning"、"error" 或 "critical"。
               默认为 "info"，表示正常的请求处理信息。
        extra: 可选的额外元数据字典，可以包含客户端 IP、请求参数、处理时间等信息。
               这些信息将以 "key=value" 格式附加在日志消息后面。
    
    示例:
        >>> log_request("req-123", "image_generation", "开始处理请求")
        >>> log_request(
        ...     "req-456", 
        ...     "user_auth", 
        ...     "验证失败", 
        ...     "error", 
        ...     {"ip": "192.168.1.1", "reason": "密码错误"}
        ... )
    """
    log_method = getattr(logger, level.lower(), logger.info)
    log_message = f"[{request_id}] [{function_name}] {message}"
    
    if extra:
        extra_info = ", ".join([f"{k}={v}" for k, v in extra.items()])
        log_message += f" | {extra_info}"
    
    log_method(log_message)

@contextmanager
def log_context(context_name: str, level: str = "info", log_start: bool = True, log_end: bool = True) -> Generator[None, None, None]:
    """上下文管理器：跟踪代码块的执行时间和状态
    
    该上下文管理器用于跟踪代码块的执行过程，自动记录开始时间、结束时间、总耗时
    以及可能发生的异常。这对于性能分析和问题排查非常有用。当代码块正常完成时，
    会记录成功信息和耗时；当发生异常时，会记录错误信息和堆栈跟踪，然后重新抛出异常。
    
    参数:
        context_name: 上下文名称，用于在日志中标识该代码块的用途或功能。
        level: 日志级别，可以是 "debug"、"info"、"warning"、"error" 或 "critical"。
               默认为 "info"，表示正常的操作信息。
        log_start: 如果为 True，在上下文开始时记录日志。如果为 False，不记录开始日志。
                  默认为 True。
        log_end: 如果为 True，在上下文结束时记录日志。如果为 False，不记录结束日志。
                默认为 True。
    
    返回:
        Generator[None, None, None]: 上下文管理器生成器。
    
    示例:
        >>> with log_context("处理图像数据"):
        ...     # 代码块内容
        ...     process_image(data)
        ...
        >>> with log_context("数据库查询", level="debug", log_start=False):
        ...     # 只记录结束时间和耗时
        ...     result = db.execute_query(query)
    
    异常处理:
        如果代码块内抛出异常，将以 ERROR 级别记录异常信息和执行时间，
        并以 DEBUG 级别记录异常堆栈跟踪，然后重新抛出异常。
    """
    log_method = getattr(logger, level.lower(), logger.info)
    start_time = time.time()
    
    if log_start:
        log_method(f"开始 {context_name}")
    
    try:
        yield
    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"{context_name} 失败，耗时: {execution_time:.4f} 秒，异常: {str(e)}")
        logger.debug(traceback.format_exc())
        raise
    finally:
        if log_end:
            execution_time = time.time() - start_time
            log_method(f"完成 {context_name}，耗时: {execution_time:.4f} 秒")

def log_startup_info(app_name: str, version: str, config_items: Optional[Dict[str, Any]] = None):
    """记录应用启动信息和关键配置
    
    在应用程序启动时记录标准化的启动信息，包括应用名称、版本、启动时间、
    日志级别以及关键配置项。这些信息对于系统监控和问题排查非常重要，可以帮助
    识别不同版本和配置下的系统行为。
    
    对于包含多个项目的列表类型配置，会自动进行缩略处理，仅显示前几项并标注总数。
    
    参数:
        app_name: 应用程序的名称，用于在日志中标识应用。
        version: 应用程序的版本号，通常采用语义化版本号格式（如 "1.0.0"）。
        config_items: 可选的配置项字典，包含需要记录的关键配置信息。
                     如果为 None，则仅记录基本启动信息。默认为 None。
    
    示例:
        >>> log_startup_info(
        ...     "ComfyBridge", 
        ...     "1.0.0", 
        ...     {
        ...         "服务器": "0.0.0.0:8000",
        ...         "调试模式": True,
        ...         "支持的功能": ["image_gen", "text_gen", "audio_gen"]
        ...     }
        ... )
    """
    logger.info(f"===== {app_name} v{version} 启动 =====")
    logger.info(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"日志级别: {config.LOG_LEVEL}")
    
    if config_items:
        logger.info("配置信息:")
        for key, value in config_items.items():
            if isinstance(value, list) and len(value) > 5:
                logger.info(f"  - {key}: {value[:5]} ... (共 {len(value)} 项)")
            else:
                logger.info(f"  - {key}: {value}")

def log_shutdown_info(app_name: str, start_time: float):
    """记录应用关闭信息和运行时间统计
    
    在应用程序关闭时记录标准化的关闭信息，包括应用名称、关闭时间和总运行时间。
    运行时间会自动计算并格式化为人类可读的形式（天、小时、分钟、秒）。
    这些信息对于系统监控、性能分析和服务稳定性评估非常有用。
    
    参数:
        app_name: 应用程序的名称，用于在日志中标识应用。
        start_time: 应用程序的启动时间戳（Unix 时间戳，浮点数），用于计算总运行时间。
                  通常在应用启动时使用 time.time() 获取并存储。
    
    返回:
        None: 该函数仅记录日志，不返回任何值。
    
    示例:
        >>> # 在应用启动时
        >>> start_time = time.time()
        >>> # 在应用关闭时
        >>> log_shutdown_info("ComfyBridge", start_time)
    """
    uptime = time.time() - start_time
    days, remainder = divmod(uptime, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    uptime_str = ""
    if days > 0:
        uptime_str += f"{int(days)} 天 "
    if hours > 0 or days > 0:
        uptime_str += f"{int(hours)} 小时 "
    if minutes > 0 or hours > 0 or days > 0:
        uptime_str += f"{int(minutes)} 分钟 "
    uptime_str += f"{seconds:.2f} 秒"
    
    logger.info(f"===== {app_name} 关闭 =====")
    logger.info(f"关闭时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"运行时间: {uptime_str}")
