"""ComfyBridge 服务器入口。

系统主入口点，负责初始化和启动 Uvicorn ASGI 服务器。

功能:
    信号处理: 捕获 SIGINT/SIGTERM 实现优雅关闭
    服务器启动: 配置并启动 Uvicorn 服务器
    模块集成: 导入 FastAPI 应用和路由

Usage:
    python server.py

Note:
    所有配置参数集中在 config.py 中管理。
"""


import sys
import signal
import uvicorn

import config
from nexus.logger import logger

# 导入应用和路由
from nexus.app import app
import nexus.routes

# 信号处理
def signal_handler(sig, frame):
    """处理系统信号并实现优雅关闭
    
    捕获 SIGINT（Ctrl+C）和 SIGTERM（系统终止）信号，记录相关日志并实现服务的优雅关闭。
    这确保了服务在终止前能够完成必要的清理工作。
    
    参数:
        sig: 收到的信号编号
        frame: 当前栈帧
    """
    logger.info(f"收到系统信号: {sig}")
    logger.info("正在优雅关闭服务...")
    sys.exit(0)

# 只有在直接运行 server.py 时才注册信号处理程序
def register_signal_handlers():
    """注册系统信号处理程序
    
    只有在直接运行 server.py 时才会注册这些处理程序，
    避免在导入模块时触发。
    """
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    logger.debug("已注册系统信号处理程序")

if __name__ == "__main__":
    # 注册信号处理程序
    register_signal_handlers()
    
    # 打印启动信息
    logger.info(f"ComfyBridge v{config.API_VERSION} 服务器启动")
    logger.info(f"监听地址: {config.SERVER_HOST}:{config.SERVER_PORT}")
    
    # 启动 Uvicorn 服务器
    # 使用字符串路径以支持 reload 模式
    uvicorn.run(
        "nexus.app:app",
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        reload=config.DEBUG_MODE,
        workers=1,  # 单进程模式，生产环境可增加
        log_level=config.LOG_LEVEL.lower()
    )
