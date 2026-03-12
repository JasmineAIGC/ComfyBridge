"""ComfyBridge 推理平台部署配置文件。

使用方法：部署时将此文件重命名为 config.py
    mv config.py config_backup.py
    mv config_deploy.py config.py
"""

import os

#######################
# 1. API 基本信息
#######################

API_VERSION = "1.0.0"
API_RELEASE_DATE = "2025-04-15"
API_STATUS = "stable"

#######################
# 2. 服务器配置（环境变量覆盖）
#######################

SERVER_HOST = os.environ.get('COMFYBRIDGE_HOST', '0.0.0.0')
SERVER_PORT = int(os.environ.get('COMFYBRIDGE_PORT', '6543'))
DEBUG_MODE = os.environ.get('COMFYBRIDGE_DEBUG', 'false').lower() == 'true'

LOG_DIR = os.environ.get('COMFYBRIDGE_LOG_DIR', '/home/finance/Logs')
LOG_LEVEL = 'DEBUG' if DEBUG_MODE else 'INFO'
GZIP_MIN_SIZE = 1000
MAX_CONCURRENT_REQUESTS = 5

TEMPLATE_DIR = './template'
WORKFLOW_DIR = './workflow'
OUTPUT_DIR = './output'

#######################
# 3. API 路由配置
#######################

API_PREFIX = '/aigc'
SYSTEM_PREFIX = '/system'
HEALTH_ROUTE = '/health'
STATUS_ROUTE = '/status'
VERSION_ROUTE = '/version'

FUNCTION_PREFIX = "/aging"
GENERATE_ROUTE = '/generate'
TEMPLATE_ROUTE = '/templates'

FULL_HEALTH_ROUTE = f"{API_PREFIX}{SYSTEM_PREFIX}{HEALTH_ROUTE}"
FULL_STATUS_ROUTE = f"{API_PREFIX}{SYSTEM_PREFIX}{STATUS_ROUTE}"
FULL_VERSION_ROUTE = f"{API_PREFIX}{SYSTEM_PREFIX}{VERSION_ROUTE}"
FULL_GENERATE_ROUTE = f"{API_PREFIX}{FUNCTION_PREFIX}{GENERATE_ROUTE}"
FULL_TEMPLATE_ROUTE = f"{API_PREFIX}{FUNCTION_PREFIX}{TEMPLATE_ROUTE}"

#######################
# 4. ComfyUI 配置（环境变量覆盖）
#######################

_comfy_servers_env = os.environ.get('COMFY_SERVERS', '')
if _comfy_servers_env:
    COMFY_SERVERS = [s.strip() for s in _comfy_servers_env.split(',') if s.strip()]
else:
    COMFY_SERVERS = ['http://127.0.0.1:7111/']

COMFY_CLEANUP_INTERVAL = 10
COMFY_CLEANUP_HISTORY = True
COMFY_CLEANUP_MEMORY = True
COMFY_KEEP_HISTORY_COUNT = 5

#######################
# 5. 功能配置
#######################

FUNCTION_NAME = "aging"
WORKFLOW_PATH = "./workflow/aging-api-coding-v6.json"
IMAGE_NODE_TITLE = "SaveImage"
OUTPUT_NODES = None

AIGC_FUNCTIONS = {
    FUNCTION_NAME: {
        "workflow_path": WORKFLOW_PATH,
        "servers": COMFY_SERVERS,
        "image_node_title": IMAGE_NODE_TITLE,
        "output_nodes": OUTPUT_NODES,
        "prefix": FUNCTION_PREFIX,
        "description": "年龄转换功能"
    }
}

#######################
# 6. Pinpoint 配置（推理平台要求）
#######################

PINPOINT_ENABLED = os.environ.get('PINPOINT_ENABLED', 'true').lower() == 'true'
PINPOINT_APP_ID = os.environ.get('PINPOINT_APP_ID', f'0.0.0.0:{SERVER_PORT}')
PINPOINT_APP_NAME = os.environ.get('PINPOINT_APP_NAME', 'comfybridge_aging')
# TODO: 向 @王棚 询问 COLLECTOR_HOST
PINPOINT_COLLECTOR_HOST = os.environ.get('PINPOINT_COLLECTOR_HOST', 'tcp:10.245.15.173:9999')
