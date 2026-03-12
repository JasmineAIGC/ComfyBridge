"""ComfyBridge 配置文件。

集中管理系统运行所需的所有配置参数，支持不同环境的快速切换。

配置分类:
    1. API 基本信息: 版本号、发布日期、状态
    2. 服务器配置: 监听地址、端口、日志设置
    3. API 路由配置: 路由前缀和端点定义
    4. 外部服务配置: ComfyUI 服务器列表和清理策略
    5. 功能配置: 工作流路径、输出节点等

ID 管理说明:
    request_id: API 请求唯一标识，用于跟踪请求生命周期
    client_id: ComfyUI WebSocket 连接标识，格式 {request_id}_{timestamp}
    prompt_id: ComfyUI 任务标识，由服务器返回，用于查询状态和结果
"""

#######################
# 1. API 基本信息
#######################

# 版本信息
API_VERSION = "1.0.0"      # API 版本号
API_RELEASE_DATE = "2025-04-15"  # API 发布日期
API_STATUS = "stable"      # API 状态：stable/beta/alpha

#######################
# 2. 服务器配置
#######################

# 基本服务器设置
SERVER_HOST = '0.0.0.0'     # 监听所有网络接口
SERVER_PORT = 6543          # 服务端口
DEBUG_MODE = False           # 调试模式

LOG_DIR = "logs/"
LOG_LEVEL = "debug" 
GZIP_MIN_SIZE = 1000        # 启用 Gzip 压缩的最小数据大小（字节）
MAX_CONCURRENT_REQUESTS = 5  # 最大并发请求数

# 模板配置
TEMPLATE_DIR = './template'  # 算法模板数据存放目录
WORKFLOW_DIR = './workflow'
OUTPUT_DIR = './output'      # 输出文件存放目录

#######################
# 3. API 路由配置
#######################

# 通用路由前缀
API_PREFIX = '/aigc'         # API 前缀

# 系统类路由
SYSTEM_PREFIX = '/system' # 系统类功能前缀
HEALTH_ROUTE = '/health' # 健康检查路由
STATUS_ROUTE = '/status' # 状态检查路由
VERSION_ROUTE = '/version' # 版本检查路由

# 功能操作路由
FUNCTION_PREFIX = "/aging" # 功能路由前缀
GENERATE_ROUTE = '/generate' # 生成图像操作
TEMPLATE_ROUTE = '/templates' # 模板信息操作

# 完整路由
FULL_HEALTH_ROUTE = f"{API_PREFIX}{SYSTEM_PREFIX}{HEALTH_ROUTE}" # /aigc/system/health
FULL_STATUS_ROUTE = f"{API_PREFIX}{SYSTEM_PREFIX}{STATUS_ROUTE}" # /aigc/system/status
FULL_VERSION_ROUTE = f"{API_PREFIX}{SYSTEM_PREFIX}{VERSION_ROUTE}" # /aigc/system/version
FULL_GENERATE_ROUTE = f"{API_PREFIX}{FUNCTION_PREFIX}{GENERATE_ROUTE}" # /aigc/aging/generate
FULL_TEMPLATE_ROUTE = f"{API_PREFIX}{FUNCTION_PREFIX}{TEMPLATE_ROUTE}" # /aigc/aging/templates

#######################
# 4. 外部服务配置
#######################

# ComfyUI 配置
COMFY_SERVERS = ['http://0.0.0.0:12374/']  # ComfyUI 服务器列表（支持多服务器负载均衡）

# ComfyUI 清理配置
COMFY_CLEANUP_INTERVAL = 10      # 每 N 次请求执行一次深度清理
COMFY_CLEANUP_HISTORY = True     # 是否清理历史记录（异步执行，不影响请求）
COMFY_CLEANUP_MEMORY = True      # 是否释放缓存内存（不卸载模型，不影响性能）
COMFY_KEEP_HISTORY_COUNT = 5     # 保留最近 N 条历史记录（用于节点缓存复用）

#######################
# 5. 功能配置
#######################

# 年轻转换功能配置
FUNCTION_NAME = "aging"      # 功能名称，用于代码中引用
WORKFLOW_PATH = "./workflow/aging-api-coding-v1.json"  # 工作流路径
IMAGE_NODE_TITLE = "SaveImage"  # 图像输出节点标题（向后兼容，单节点场景）

# 多输出节点配置（可选）
# 如果工作流有多个输出节点，可以在这里配置
# 格式: [{"title": "节点标题", "name": "输出名称（可选，用于响应分组）"}, ...]
# 示例: OUTPUT_NODES = [
#     {"title": "SaveImage", "name": "images"},
#     {"title": "SaveAudio", "name": "audio"},
#     {"title": "SaveVideo", "name": "video"}
# ]
# 如果不配置，将使用 IMAGE_NODE_TITLE 作为唯一输出节点
OUTPUT_NODES = None

# 9. 功能配置字典
#######################

# 使用结构化的配置字典，直接引用上面定义的变量
AIGC_FUNCTIONS = {
    # 使用功能名称作为键
    FUNCTION_NAME: {
        # 工作流相关配置
        "workflow_path": WORKFLOW_PATH,
        "servers": COMFY_SERVERS,
        "image_node_title": IMAGE_NODE_TITLE,
        "output_nodes": OUTPUT_NODES,  # 多输出节点配置（可选）
        
        # API 路由配置
        "prefix": FUNCTION_PREFIX,  # 功能路径前缀
        
        # 功能描述
        "description": "年龄转换功能，可以将人脸图像转换为不同年龄的效果"
    }
}
