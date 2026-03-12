"""ComfyBridge 统一错误码定义。

本模块定义了系统中所有错误码及其对应的错误消息，提供统一的错误处理机制。

错误码分段规则:
    0: 成功
    1001-1099: 图像质量错误（业务错误，HTTP 200，用户可修正）
    1101-1199: 音频质量错误（业务错误，HTTP 200，用户可修正）
    1201-1299: 视频质量错误（业务错误，HTTP 200，用户可修正）
    2001-2099: 参数验证错误（业务错误，HTTP 200，用户可修正）
    3001-3099: ComfyUI 服务错误（系统错误，HTTP 500，需运维介入）
    9001-9099: 系统内部错误（系统错误，HTTP 500，需运维介入）

Functions:
    get_error_message: 根据错误码获取错误描述
    is_business_error: 判断是否为业务错误
    is_system_error: 判断是否为系统错误
    is_temporary_error: 判断是否为临时错误（可重试）
    get_http_status_code: 根据错误码获取 HTTP 状态码
"""

# ==================== 成功码 ====================
SUCCESS = 0

# ==================== 参数验证错误 (2001-2099) ====================
# HTTP 200，业务错误
ERR_INVALID_JSON = 2001
ERR_MISSING_IMAGE = 2002
ERR_PARAM_VALIDATION = 2003
ERR_PARAM_OUT_OF_RANGE = 2004  # 参数值超出范围
ERR_MISSING_AUDIO = 2005      # 缺少音频文件
ERR_MISSING_VIDEO = 2006      # 缺少视频文件
ERR_MISSING_TEXT = 2007       # 缺少文本内容

# ==================== 算法内部错误码 ====================

# 图像质量错误 (1001-1099)
# 基本图像属性问题
ERR_LOW_RESOLUTION = 1001
ERR_LOW_CLARITY = 1002
ERR_BAD_LIGHTING = 1004

# 人脸检测问题
ERR_NO_FACE = 1003
ERR_MULTIPLE_FACES = 1005
ERR_FACE_TOO_SMALL = 1006
ERR_INCOMPLETE_FACE = 1007

# 人脸表情和姿态问题
ERR_EYE_CLOSED = 1008
ERR_MOUTH_OPEN = 1009
ERR_FACE_ANGLE = 1010

# 属性提取错误 (1011-1020)
ERR_ATTRIBUTE_EXTRACT_FAILED = 1011  # 属性提取失败
ERR_IMAGE_LOAD_FAILED = 1012         # 图像加载失败
ERR_GENDER_DETECT_FAILED = 1013      # 性别检测失败
ERR_AGE_ESTIMATE_FAILED = 1014       # 年龄估计失败
ERR_GLASSES_DETECT_FAILED = 1015     # 眼镜检测失败

# 通用错误
ERR_QUALITY_CHECK_GENERAL = 1099

# ==================== 音频质量错误 (1101-1199) ====================
# TTS 相关业务错误
ERR_AUDIO_FORMAT_INVALID = 1101      # 音频格式不支持
ERR_AUDIO_TOO_SHORT = 1102           # 音频时长过短
ERR_AUDIO_TOO_LONG = 1103            # 音频时长过长
ERR_AUDIO_QUALITY_LOW = 1104         # 音频质量过低
ERR_AUDIO_NO_VOICE = 1105            # 未检测到人声
ERR_AUDIO_MULTIPLE_VOICES = 1106     # 检测到多个说话人
ERR_AUDIO_TOO_NOISY = 1107           # 背景噪音过大
ERR_AUDIO_LOAD_FAILED = 1108         # 音频加载失败
ERR_TTS_TEXT_TOO_LONG = 1109         # 合成文本过长
ERR_TTS_LANGUAGE_UNSUPPORTED = 1110  # 不支持的语言
ERR_AUDIO_QUALITY_GENERAL = 1199     # 音频质量检查通用错误

# ==================== 视频质量错误 (1201-1299) ====================
# 视频生成相关业务错误
ERR_VIDEO_FORMAT_INVALID = 1201      # 视频格式不支持
ERR_VIDEO_TOO_SHORT = 1202           # 视频时长过短
ERR_VIDEO_TOO_LONG = 1203            # 视频时长过长
ERR_VIDEO_RESOLUTION_LOW = 1204      # 视频分辨率过低
ERR_VIDEO_RESOLUTION_HIGH = 1205     # 视频分辨率过高
ERR_VIDEO_FPS_INVALID = 1206         # 视频帧率不支持
ERR_VIDEO_LOAD_FAILED = 1207         # 视频加载失败
ERR_VIDEO_NO_FACE = 1208             # 视频中未检测到人脸
ERR_VIDEO_FACE_LOST = 1209           # 视频中人脸丢失
ERR_VIDEO_QUALITY_GENERAL = 1299     # 视频质量检查通用错误

# ==================== ComfyUI 服务错误 (3001-3099) ====================
# HTTP 500，系统错误

# 工作流相关错误 (3001-3010)
ERR_WORKFLOW_NOT_FOUND = 3001
ERR_WORKFLOW_CONFIG_FAILED = 3002
ERR_WORKFLOW_SUBMIT_FAILED = 3003
ERR_WORKFLOW_NO_PROMPT_ID = 3004
ERR_WORKFLOW_EXECUTION_ERROR = 3005
ERR_WORKFLOW_NODE_NOT_FOUND = 3006  # 工作流节点不存在

# 超时和重试错误 (3011-3020)
ERR_MAX_CONSECUTIVE_FAILURES = 3011
ERR_MAX_RETRIES_EXCEEDED = 3012
ERR_IMAGE_DOWNLOAD_FAILED = 3013

# 服务器连接错误 (3021-3030)
ERR_SERVER_FAILED = 3021
ERR_ALL_SERVERS_FAILED = 3022
ERR_WORKFLOW_EXECUTION_FAILED = 3023

# ComfyUI API 错误 (3031-3040)
ERR_COMFY_QUEUE_PROMPT = 3031
ERR_COMFY_EXECUTION_ERROR = 3032
ERR_COMFY_GET_HISTORY = 3033
ERR_COMFY_GET_IMAGE = 3034
ERR_COMFY_UPLOAD_IMAGE = 3035
ERR_COMFY_UPLOAD_IMAGE_DATA = 3036
ERR_COMFY_GET_STATUS = 3037
ERR_COMFY_UPLOAD_AUDIO = 3038        # 上传音频失败
ERR_COMFY_UPLOAD_VIDEO = 3039        # 上传视频失败
ERR_COMFY_GET_AUDIO = 3040           # 获取音频失败
ERR_COMFY_GET_VIDEO = 3041           # 获取视频失败
ERR_TTS_SYNTHESIS_FAILED = 3042      # TTS 合成失败
ERR_VIDEO_GENERATION_FAILED = 3043   # 视频生成失败

# ==================== 系统内部错误 (9001-9099) ====================
# HTTP 500，系统错误
ERR_INTERNAL_SERVER = 9001
ERR_TEMPLATE_FORMAT = 9002
ERR_TEMPLATE_LOAD = 9003
ERR_UNKNOWN_ERROR = 9099

# ==================== 错误信息映射 ====================

ERROR_MESSAGES = {
    # 成功
    SUCCESS: "成功",
    
    # 参数验证错误
    ERR_INVALID_JSON: "JSON格式错误",
    ERR_MISSING_IMAGE: "缺少图像文件",
    ERR_PARAM_VALIDATION: "参数验证失败",
    ERR_PARAM_OUT_OF_RANGE: "参数超出范围",
    ERR_MISSING_AUDIO: "缺少音频文件",
    ERR_MISSING_VIDEO: "缺少视频文件",
    ERR_MISSING_TEXT: "缺少文本内容",
    
    # 图像质量错误
    ERR_LOW_RESOLUTION: "分辨率过低",
    ERR_LOW_CLARITY: "图像不清晰",
    ERR_BAD_LIGHTING: "光照不佳",
    ERR_NO_FACE: "未检测到人脸",
    ERR_MULTIPLE_FACES: "检测到多张脸",
    ERR_FACE_TOO_SMALL: "人脸过小",
    ERR_INCOMPLETE_FACE: "人脸不完整",
    ERR_EYE_CLOSED: "检测到闭眼",
    ERR_MOUTH_OPEN: "检测到张嘴",
    ERR_FACE_ANGLE: "人脸角度不正",
    ERR_ATTRIBUTE_EXTRACT_FAILED: "属性提取失败",
    ERR_IMAGE_LOAD_FAILED: "图像加载失败",
    ERR_GENDER_DETECT_FAILED: "性别检测失败",
    ERR_AGE_ESTIMATE_FAILED: "年龄估计失败",
    ERR_GLASSES_DETECT_FAILED: "眼镜检测失败",
    ERR_QUALITY_CHECK_GENERAL: "质量检查失败",
    
    # 音频质量错误
    ERR_AUDIO_FORMAT_INVALID: "音频格式不支持",
    ERR_AUDIO_TOO_SHORT: "音频时长过短",
    ERR_AUDIO_TOO_LONG: "音频时长过长",
    ERR_AUDIO_QUALITY_LOW: "音频质量过低",
    ERR_AUDIO_NO_VOICE: "未检测到人声",
    ERR_AUDIO_MULTIPLE_VOICES: "检测到多个说话人",
    ERR_AUDIO_TOO_NOISY: "背景噪音过大",
    ERR_AUDIO_LOAD_FAILED: "音频加载失败",
    ERR_TTS_TEXT_TOO_LONG: "合成文本过长",
    ERR_TTS_LANGUAGE_UNSUPPORTED: "不支持的语言",
    ERR_AUDIO_QUALITY_GENERAL: "音频质量检查失败",
    
    # 视频质量错误
    ERR_VIDEO_FORMAT_INVALID: "视频格式不支持",
    ERR_VIDEO_TOO_SHORT: "视频时长过短",
    ERR_VIDEO_TOO_LONG: "视频时长过长",
    ERR_VIDEO_RESOLUTION_LOW: "视频分辨率过低",
    ERR_VIDEO_RESOLUTION_HIGH: "视频分辨率过高",
    ERR_VIDEO_FPS_INVALID: "视频帧率不支持",
    ERR_VIDEO_LOAD_FAILED: "视频加载失败",
    ERR_VIDEO_NO_FACE: "视频中未检测到人脸",
    ERR_VIDEO_FACE_LOST: "视频中人脸丢失",
    ERR_VIDEO_QUALITY_GENERAL: "视频质量检查失败",
    
    # ComfyUI 服务错误
    ERR_WORKFLOW_NOT_FOUND: "工作流不存在",
    ERR_WORKFLOW_CONFIG_FAILED: "配置失败",
    ERR_WORKFLOW_SUBMIT_FAILED: "提交失败",
    ERR_WORKFLOW_NO_PROMPT_ID: "获取ID失败",
    ERR_WORKFLOW_EXECUTION_ERROR: "执行错误",
    ERR_WORKFLOW_NODE_NOT_FOUND: "工作流节点不存在",
    ERR_MAX_CONSECUTIVE_FAILURES: "连续失败过多",
    ERR_MAX_RETRIES_EXCEEDED: "重试次数超限",
    ERR_IMAGE_DOWNLOAD_FAILED: "图像下载失败",
    ERR_SERVER_FAILED: "服务器失败",
    ERR_ALL_SERVERS_FAILED: "所有服务器失败",
    ERR_WORKFLOW_EXECUTION_FAILED: "工作流失败",
    ERR_COMFY_QUEUE_PROMPT: "任务提交失败",
    ERR_COMFY_EXECUTION_ERROR: "执行错误",
    ERR_COMFY_GET_HISTORY: "获取历史失败",
    ERR_COMFY_GET_IMAGE: "获取图像失败",
    ERR_COMFY_UPLOAD_IMAGE: "上传图像失败",
    ERR_COMFY_UPLOAD_IMAGE_DATA: "上传数据失败",
    ERR_COMFY_GET_STATUS: "获取状态失败",
    ERR_COMFY_UPLOAD_AUDIO: "上传音频失败",
    ERR_COMFY_UPLOAD_VIDEO: "上传视频失败",
    ERR_COMFY_GET_AUDIO: "获取音频失败",
    ERR_COMFY_GET_VIDEO: "获取视频失败",
    ERR_TTS_SYNTHESIS_FAILED: "语音合成失败",
    ERR_VIDEO_GENERATION_FAILED: "视频生成失败",
    
    # 系统内部错误
    ERR_INTERNAL_SERVER: "服务器错误",
    ERR_TEMPLATE_FORMAT: "模板格式错误",
    ERR_TEMPLATE_LOAD: "模板加载失败",
    ERR_UNKNOWN_ERROR: "未知错误",
}

# ==================== 辅助函数 ====================

def get_error_message(error_code: int, default: str = "未知错误") -> str:
    """根据错误码获取错误描述。

    Args:
        error_code: 错误码。
        default: 默认错误描述。

    Returns:
        错误描述字符串。
    """
    return ERROR_MESSAGES.get(error_code, default)

def is_business_error(error_code: int) -> bool:
    """判断是否为业务错误（用户可修正，HTTP 200）。

    Args:
        error_code: 错误码。

    Returns:
        True 表示是业务错误。
    """
    return (1001 <= error_code <= 1299) or (2001 <= error_code <= 2099)

def is_system_error(error_code: int) -> bool:
    """判断是否为系统错误（需运维介入，HTTP 500）。

    Args:
        error_code: 错误码。

    Returns:
        True 表示是系统错误。
    """
    return (3001 <= error_code <= 3099) or (9001 <= error_code <= 9099)

def is_temporary_error(error_code: int) -> bool:
    """判断是否为临时错误（可重试）。

    Args:
        error_code: 错误码。

    Returns:
        True 表示是临时错误，建议重试。
    """
    temporary_errors = [
        ERR_MAX_CONSECUTIVE_FAILURES,
        ERR_MAX_RETRIES_EXCEEDED,
        ERR_IMAGE_DOWNLOAD_FAILED,
        ERR_SERVER_FAILED,
        ERR_ALL_SERVERS_FAILED,
    ]
    return error_code in temporary_errors

def get_http_status_code(error_code: int) -> int:
    """根据错误码获取 HTTP 状态码。

    Args:
        error_code: 错误码。

    Returns:
        HTTP 状态码（200 或 500）。
    """
    # 成功返回 200
    if error_code == SUCCESS:
        return 200
    
    # 业务错误返回 200（便于客户端统一解析 JSON）
    if is_business_error(error_code):
        return 200
    
    # 系统错误返回 500
    if is_system_error(error_code):
        return 500
    
    # 默认返回 500
    return 500

# ==================== 错误码分类 ====================

# 按来源分类
ERROR_SOURCES = {
    "image_quality": list(range(1001, 1100)),   # 图像质量检查
    "audio_quality": list(range(1101, 1200)),   # 音频质量检查
    "video_quality": list(range(1201, 1300)),   # 视频质量检查
    "param_validation": list(range(2001, 2100)),  # 参数验证
    "comfyui": list(range(3001, 3100)),  # ComfyUI 服务
    "system": list(range(9001, 9100)),  # 系统内部
}

# 按严重程度分类
ERROR_SEVERITY = {
    "business": list(range(1001, 1300)) + list(range(2001, 2100)),  # 业务错误，用户可修正
    "system": list(range(3001, 3100)) + list(range(9001, 9100)),  # 系统错误，需要运维介入
    "temporary": [3011, 3012, 3013, 3021, 3022],  # 临时错误，可重试
}
