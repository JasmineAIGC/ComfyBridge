"""ComfyBridge 推理平台部署入口。

集成 Pinpoint 链路追踪和 concurrent_log_handler 日志。

Usage:
    python server_deploy.py
    
流程：
    1. 配置日志（concurrent_log_handler）
    2. 配置 Pinpoint 链路追踪
    3. 创建 FastAPI 应用
    4. 注册路由
    5. 启动服务
"""

import os
import sys
import time
import signal
import logging
import logging.config

# ============================================================================
# 1. 日志配置（必须最先执行，使用 concurrent_log_handler）
# ============================================================================

LOG_DIR = os.environ.get('COMFYBRIDGE_LOG_DIR', '/home/finance/Logs')
os.makedirs(LOG_DIR, exist_ok=True)

timestamp = time.strftime("%Y%m%d%H%M%S")
log_file = f'{LOG_DIR}/comfybridge_{timestamp}.log'

# 配置根日志和 comfybridge 日志
logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(levelname)s %(asctime)s %(name)s %(filename)s#%(lineno)d: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'service': {
            'level': 'INFO',
            'class': 'concurrent_log_handler.ConcurrentTimedRotatingFileHandler',
            'when': 'H',
            'interval': 12,
            'backupCount': 60,
            'maxBytes': 512 * 1024 * 1024,
            'delay': True,
            'formatter': 'standard',
            'filename': log_file,
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'loggers': {
        '': {
            'handlers': ['service', 'console'],
            'level': 'INFO',
        },
        'comfybridge': {
            'handlers': ['service', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
})

logger = logging.getLogger('comfybridge')
logger.info(f"日志初始化完成: {log_file}")

# ============================================================================
# 2. Pinpoint 链路追踪配置（注意：set_agent 必须在创建 FastAPI 应用之后调用）
# ============================================================================

import config

PINPOINT_ENABLED = getattr(config, 'PINPOINT_ENABLED', True)
PINPOINT_MIDDLEWARE = []

logger.info(f"[Pinpoint] PINPOINT_ENABLED from config: {PINPOINT_ENABLED}")

if PINPOINT_ENABLED:
    try:
        import pinpointPy
        from pinpointPy import use_thread_local_context
        from pinpointPy.Fastapi import asyn_monkey_patch_for_pinpoint
        from pinpointPy.Fastapi.middleware import PinPointMiddleWare
        from starlette.middleware import Middleware
        from starlette_context.middleware import ContextMiddleware

        # 步骤 1: 设置线程上下文和 monkey patch
        use_thread_local_context()
        asyn_monkey_patch_for_pinpoint()
        logger.info("[Pinpoint] use_thread_local_context 和 asyn_monkey_patch_for_pinpoint 已调用")
        
        # 步骤 2: 准备中间件（在创建 FastAPI 时使用）
        PINPOINT_MIDDLEWARE = [
            Middleware(ContextMiddleware),
            Middleware(PinPointMiddleWare)
        ]
        
        # 步骤 3: 读取配置（set_agent 将在创建 app 之后调用）
        PINPOINT_APP_ID = getattr(config, 'PINPOINT_APP_ID', f'0.0.0.0:{config.SERVER_PORT}')
        PINPOINT_APP_NAME = getattr(config, 'PINPOINT_APP_NAME', 'comfybridge_aging')
        PINPOINT_COLLECTOR_HOST = getattr(config, 'PINPOINT_COLLECTOR_HOST', 'tcp:10.245.15.173:9999')
        
    except ImportError as e:
        logger.warning(f"[Pinpoint] 导入失败，将禁用链路追踪: {e}")
        PINPOINT_ENABLED = False
    except Exception as e:
        logger.error(f"[Pinpoint] 初始化异常: {e}")
        PINPOINT_ENABLED = False
else:
    logger.info("[Pinpoint] 已禁用")

# ============================================================================
# 3. 创建 FastAPI 应用（带 Pinpoint 中间件）
# ============================================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

app = FastAPI(
    title="ComfyBridge",
    description="基于 ComfyUI 的通用 AIGC API 封装框架",
    version=getattr(config, 'API_VERSION', '1.0.0'),
    docs_url="/docs",
    redoc_url="/redoc",
    middleware=PINPOINT_MIDDLEWARE
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=getattr(config, 'GZIP_MIN_SIZE', 1000))

# 步骤 4: 创建 app 之后调用 set_agent（按照示例要求的顺序）
if PINPOINT_ENABLED:
    pinpointPy.set_agent(PINPOINT_APP_ID, PINPOINT_APP_NAME, PINPOINT_COLLECTOR_HOST, log_level=logging.WARNING)
    logger.info(f"[Pinpoint] set_agent 已调用: APP_ID={PINPOINT_APP_ID}, APP_NAME={PINPOINT_APP_NAME}, COLLECTOR={PINPOINT_COLLECTOR_HOST}")

# ============================================================================
# 4. 生命周期事件
# ============================================================================

@app.on_event("startup")
async def startup_event():
    logger.info(f"===== ComfyBridge v{config.API_VERSION} 启动 =====")
    logger.info(f"服务地址: {config.SERVER_HOST}:{config.SERVER_PORT}")
    logger.info(f"ComfyUI 服务器: {config.COMFY_SERVERS}")
    
    for dir_path in [config.LOG_DIR, config.TEMPLATE_DIR, config.WORKFLOW_DIR, config.OUTPUT_DIR]:
        os.makedirs(dir_path, exist_ok=True)
    
    from nexus.comfy import comfy_interface
    logger.info(f"已加载 {len(comfy_interface.workflows)} 个工作流")
    
    from processors import initialize_tools
    initialize_tools()
    
    logger.info("ComfyBridge 启动完成")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("===== ComfyBridge 关闭 =====")

# ============================================================================
# 5. 注册路由
# ============================================================================

# 重要：routes.py 使用 `from nexus.app import app` 导入 app
# 这是一个引用绑定，我们需要在导入 routes 之前替换 nexus.app 模块中的 app

# 先导入 nexus.app 模块（但不导入 routes）
import nexus.app as nexus_app_module

# 替换模块中的 app 变量
nexus_app_module.app = app

# 现在导入 routes，它会从 nexus.app 获取我们替换后的 app
# 注意：如果 routes 已被其他模块导入过，这里不会重新执行
if 'nexus.routes' in sys.modules:
    # 如果已导入，需要重新加载
    import importlib
    importlib.reload(sys.modules['nexus.routes'])
    logger.info("重新加载 nexus.routes 模块")
else:
    import nexus.routes

# 验证路由是否注册成功
route_paths = [r.path for r in app.routes if hasattr(r, 'path')]
logger.info(f"路由注册完成，共 {len(route_paths)} 个路由: {route_paths}")

# ============================================================================
# 6. 信号处理
# ============================================================================

def signal_handler(sig, frame):
    logger.info(f"收到信号: {sig}，正在关闭...")
    sys.exit(0)

# ============================================================================
# 7. 主入口
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info(f"启动服务: {config.SERVER_HOST}:{config.SERVER_PORT}")
    
    uvicorn.run(
        app=app,
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        workers=1,
        loop="asyncio",
        access_log=os.environ.get("UVICORN_ACCESS_LOG", "false").lower() == "true",
    )
