"""API 路由定义模块。

定义 ComfyBridge 的所有 RESTful 端点和请求处理逻辑。

路由分类:
    系统端点:
        GET /aigc/system/health: 健康检查
        GET /aigc/system/status: 系统状态
        GET /aigc/system/version: 版本信息

    功能端点:
        POST /aigc/aging/generate: 图像生成
        GET /aigc/aging/templates: 模板列表

增强特性:
    - @log_execution_time: 执行时间跟踪
    - log_request: 请求详情记录
    - log_context: 处理阶段跟踪
    - 标准化响应格式

Note:
    路由配置从 config.py 读取，遵循配置驱动设计。
"""

import os
import gc
import json
import time
import uuid
import traceback
from typing import Dict, Any, Optional, List

import requests as http_requests
from requests.exceptions import RequestException
import psutil

from fastapi import File, Form, UploadFile, Request
from pydantic import BaseModel, Field
from enum import Enum

import config
from nexus.app import app
from nexus.comfy import comfy_interface
from nexus.utils import create_success_response, create_error_response
from nexus.logger import logger, log_request, log_execution_time, log_context
from nexus.error_codes import (
    ERR_INVALID_JSON,
    ERR_MISSING_IMAGE,
    ERR_PARAM_VALIDATION,
    ERR_INTERNAL_SERVER,
    ERR_TEMPLATE_FORMAT,
    ERR_TEMPLATE_LOAD,
)
from comfyui.api_wrapper_multi import ComfyUIError

# 导入处理器工具集相关模块
from processors.quality_check.validator import validate_image_quality
from processors.attribute_extractor.extractor import extract_image_attributes
from processors.prompt_templates import get_prompt_for_target_age_from_attributes, all_weights_from_attributes

class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"


# Field 参数类型示例:
#   str:   Field(description="文本", min_length=1, max_length=100)
#   int:   Field(description="整数", ge=1, le=100)
#   float: Field(description="浮点数", ge=0.0, le=1.0)
#   bool:  Field(default=True, description="布尔值")

class AgingParams(BaseModel):
    gender: Gender = Field(description="性别")
    age: int = Field(description="年龄", ge=1, le=80)
    num: Optional[int] = Field(default=1, description="生成图像数量", ge=1, le=4)

@app.post(config.FULL_GENERATE_ROUTE)
@log_execution_time
async def generate_image(
    request: Request,
    image: List[UploadFile] = File(...),
    params: str = Form(...)
):
    """图像生成 API 端点
    
    接收输入图像和参数，调用 ComfyUI 生成新图像。该端点是 ComfyBridge 的核心功能，
    支持各种图像处理和生成操作，如人像编辑、风格转换、图像修复等。
    
    处理流程：
    1. 验证并解析输入参数
    2. 将上传的图像保存到临时目录
    3. 根据参数选择并执行适当的 ComfyUI 工作流
    4. 处理生成结果并返回响应
    
    整个过程都有详细的日志记录，包括执行时间、异常情况和结果统计。
    
    参数:
        request (Request): FastAPI 请求对象，用于获取客户端信息和请求头。
        image (List[UploadFile]): 上传的输入图像文件列表（同名字段 'image' 可重复），第一个作为主图；支持常见图像格式（JPG、PNG 等）。
        params (str): JSON 格式的参数字符串，包含生成设置和选项。
        
    返回:
        Dict[str, Any]: 包含生成结果的 JSON 响应，成功时包含生成图像的路径和元数据，
                      失败时包含错误信息和状态码。
    
    异常处理:
        所有异常都会被捕获并记录，并返回标准化的错误响应。常见异常包括：
        - 参数解析错误：当 params 不是有效的 JSON 格式
        - 文件处理错误：当图像文件无法读取或处理
        - ComfyUI 调用错误：当与 ComfyUI 服务器通信失败
    """
    # 解析参数
    try:
        params_dict = json.loads(params) if params else {}
    except json.JSONDecodeError:
        return create_error_response(ERR_INVALID_JSON)
    
    # 优先使用客户端传入的 request_id，如果没有则生成新的
    request_id = params_dict.get('request_id', str(uuid.uuid4()))
    start_time = time.time()
    function_name = config.FUNCTION_NAME
    client_ip = request.client.host if request.client else "unknown"
    
    # 记录请求开始
    log_request(
        request_id=request_id,
        function_name=function_name,
        message="请求开始处理",
        extra={
            "client_ip": client_ip,
            "content_length": request.headers.get("content-length", "unknown"),
            "user_agent": request.headers.get("user-agent", "unknown"),
            "params": str(params_dict)[:100] + "..." if len(str(params_dict)) > 100 else str(params_dict)
        }
    )
    
    try:
        # 选择主图像（同名字段 'image' 支持多文件，使用第一个作为主图）
        main_image: Optional[UploadFile] = image[0] if isinstance(image, list) and len(image) > 0 else None
        if not main_image:
            return create_error_response(ERR_MISSING_IMAGE, data={"request_id": request_id})
        
        # # DEBUG: 临时保存上传的图片用于调试
        # try:
        #     import os
        #     from datetime import datetime
        #     debug_dir = "/tmp/comfy_debug_uploads"
        #     os.makedirs(debug_dir, exist_ok=True)
        #     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        #     debug_filename = f"{debug_dir}/{timestamp}_{request_id}_{main_image.filename}"
        #     debug_content = await main_image.read()
        #     with open(debug_filename, "wb") as f:
        #         f.write(debug_content)
        #     await main_image.seek(0)  # 重置文件指针，以便后续代码继续读取
        #     log_request(request_id, function_name, f"DEBUG: 图片已保存到 {debug_filename}", "info")
        # except Exception as e:
        #     log_request(request_id, function_name, f"DEBUG: 保存图片失败 {e}", "warning")

        # 验证参数
        with log_context("验证请求参数", level="info"):
            try:
                aging_params = AgingParams(**params_dict)
                params_dict = aging_params.model_dump()
            except Exception as e:
                error_msg = f"参数验证失败: {str(e)}"
                log_request(request_id, function_name, error_msg, "error")
                return create_error_response(ERR_PARAM_VALIDATION, data={"request_id": request_id})
        
        # 读取输入数据
        with log_context("读取输入数据", level="info"):
            image_data = await main_image.read()
            image_size = len(image_data)
            log_request(request_id, function_name, f"读取图像数据", "debug", {"size": image_size, "filename": main_image.filename})

        # 图像质量检查
        with log_context("图像质量检查", level="info"):
            log_request(request_id, function_name, f"开始图像质量检查")
            quality_passed, quality_error = validate_image_quality(image_data)
            if not quality_passed:
                warn_msg = f"图像质量检查未通过: {quality_error['message']}"
                log_request(request_id, function_name, warn_msg, "warning")
                # 图像质量错误，HTTP 200（业务错误）
                return create_error_response(quality_error['code'], data={"request_id": request_id})
            log_request(request_id, function_name, f"图像质量检查通过")

        # 图像属性提取
        with log_context("图像属性提取", level="info"):
            log_request(request_id, function_name, f"开始提取图像属性")
            image_attributes = extract_image_attributes(image_data)
            # 检查属性提取是否有错误
            if 'error_code' in image_attributes:
                warn_msg = f"图像属性提取失败: {image_attributes.get('error_message', '未知错误')}"
                log_request(request_id, function_name, warn_msg, "warning")
                # 属性提取失败不阻止请求，但记录警告，继续使用默认值
            log_request(request_id, function_name, "图像属性提取完成", "debug", {"attributes": str(image_attributes)})

        # 从固定的JSON模板中获取提示词和权重
        with log_context("获取模板参数", level="info"):
            log_request(request_id, function_name, f"根据图像属性和目标年龄获取模板参数")

            # 基于每张的属性计算目标年龄；每张使用参数副本，避免相互污染
            per_params = dict(params_dict)
            target_age = per_params.get('age', image_attributes.get('age', 30))

            # 获取提示词（基于目标年龄）
            prompt = get_prompt_for_target_age_from_attributes(image_attributes, target_age)
            if prompt and ('prompt' not in per_params or not per_params['prompt']):
                # 添加自适应前缀，包含年龄、性别和眼镜信息
                gender = image_attributes.get('gender', 'person')
                current_age = image_attributes.get('age', 30)
                has_glasses = image_attributes.get('has_glasses', False)

                # 构建年龄性别描述
                if gender == 'male':
                    descriptor = 'boy' if target_age <= 12 else 'teenage boy' if target_age <= 19 else 'man'
                elif gender == 'female':
                    descriptor = 'girl' if target_age <= 12 else 'teenage girl' if target_age <= 19 else 'woman'
                else:
                    descriptor = 'person'

                # 眼镜逻辑
                glasses_desc = ""
                if has_glasses:
                    if current_age >= 25:
                        if target_age <= 16:
                            pass
                        elif target_age >= 45:
                            glasses_desc = " wearing glasses"
                        else:
                            glasses_desc = " wearing glasses"
                    else:
                        if target_age <= 10:
                            pass
                        else:
                            glasses_desc = " wearing glasses"

                age_prefix = f"A {target_age}-year-old {descriptor}{glasses_desc}, "
                composition_suffix = "single person only, no other people, no crowd, no group, solo subject, bust portrait, shoulders-up, no arms in frame, no hands in frame, crop above elbows, not a close-up, not a headshot"
                per_params['prompt'] = f"{age_prefix}{prompt}. {composition_suffix}"
                log_request(request_id, function_name, f"使用模板提示词(含年龄性别眼镜前缀): prompt={per_params['prompt'][:50]}...")

                # 获取权重参数（基于目标年龄）
                weight_params = all_weights_from_attributes(image_attributes, target_age)
                if weight_params:
                    for key, value in weight_params.items():
                        if key not in per_params or not per_params[key]:
                            per_params[key] = value
                            log_request(request_id, function_name, f"使用模板权重: {key}={value}")

                log_request(request_id, function_name, "模板参数获取完成", "debug", {"updated_params": str(per_params)})

            suffix = "single person only, no other people, no crowd, no group, solo subject, bust portrait, shoulders-up, no arms in frame, no hands in frame, crop above elbows, not a close-up, not a headshot"
            if per_params.get('prompt'):
                if "single person only" not in per_params['prompt']:
                    per_params['prompt'] = f"{per_params['prompt'].rstrip('. ')}. {suffix}"

        # 准备处理参数（单任务）
        process_params = {
            "request_id": request_id,  # 使用明确的键名
            "imageData": image_data,
            **per_params
        }

        # 处理请求
        with log_context(f"处理 {function_name} 请求"):
            log_request(request_id, function_name, "开始处理请求")
            result_images = await comfy_interface.process_request(function_name, process_params)
            image_count = len(result_images)
            log_request(request_id, function_name, f"生成了 {image_count} 张图像")
            
            # 显式释放大对象，避免内存泄漏
            # image_data 已经上传到 ComfyUI，不再需要保留在内存中
            del process_params['imageData']
            del image_data
            gc.collect(0)  # 只回收年轻代，快速释放内存

        # 记录处理时间
        processing_time = time.time() - start_time
        log_request(
            request_id=request_id,
            function_name=function_name,
            message=f"请求处理完成",
            extra={
                "processing_time": f"{processing_time:.2f}s",
                "image_count": image_count
            }
        )
        
        # 返回结果
        return create_success_response({
            "request_id": request_id,
            "processing_time": processing_time,
            "images": result_images
        })
    except json.JSONDecodeError as e:
        log_request(request_id, function_name, f"参数解析失败: {str(e)}", "error")
        return create_error_response(ERR_INVALID_JSON, data={"request_id": request_id})
    except ComfyUIError as e:
        # ComfyUI 相关错误，详细信息只记录日志，不返回给客户端
        log_request(request_id, function_name, f"ComfyUI错误 [{e.code}]: {e.message}", "error")
        return create_error_response(e.code, data={"request_id": request_id})
    except Exception as e:
        # 内部错误，详细信息只记录日志，不返回给客户端
        log_request(request_id, function_name, f"处理请求时发生异常: {str(e)}", "error")
        logger.debug(traceback.format_exc())
        return create_error_response(ERR_INTERNAL_SERVER, data={"request_id": request_id})

@app.get(config.FULL_HEALTH_ROUTE)
@log_execution_time(level="debug")
async def health_check(request: Request):
    """健康检查端点
    
    参数:
        request: 请求对象
        
    返回:
        包含系统健康状态的 JSON 响应
    """
    client_ip = request.client.host if request.client else "unknown"
    logger.debug(f"健康检查请求来自: {client_ip}")
    
    return create_success_response({
        "status": "healthy",
        "version": config.API_VERSION,
        "timestamp": time.time()
    })

@app.get(config.FULL_STATUS_ROUTE)
@log_execution_time
async def system_status(request: Request):
    """系统状态监控 API 端点
    
    提供实时的系统状态信息，包括应用运行状态、ComfyUI 服务器连接状态、
    系统资源使用情况和关键指标。该端点可用于监控系统健康状态、故障排查
    和性能分析。
    
    处理流程：
    1. 检查并记录请求来源
    2. 检查所有配置的 ComfyUI 服务器连接状态
    3. 收集系统资源使用指标（CPU、内存、GPU 等）
    4. 汇总并返回状态信息
    
    该端点使用并发请求检查多个 ComfyUI 服务器，并设置了超时机制以确保响应时间稳定。
    
    参数:
        request (Request): FastAPI 请求对象，用于获取客户端信息和请求头。
        
    返回:
        Dict[str, Any]: 包含系统状态信息的 JSON 响应，包括：
            - status: 总体状态（"healthy", "degraded", "unhealthy"）
            - api_version: API 版本号
            - uptime: 系统运行时间（秒）
            - comfy_servers: ComfyUI 服务器状态列表
            - resources: 系统资源使用情况
            - timestamp: 响应生成时间戳
    
    异常处理:
        即使部分 ComfyUI 服务器无法连接，该端点仍将返回有效响应，但会将状态标记为 "degraded"。
        只有当全部服务器无法连接或发生其他严重错误时，状态才会标记为 "unhealthy"。
    """
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"系统状态请求来自: {client_ip}")
    
    # 获取 ComfyUI 服务器状态
    comfy_status = []
    with log_context("检查 ComfyUI 服务器状态"):
        for server in config.COMFY_SERVERS:
            try:
                timeout = getattr(config, "COMFY_TIMEOUT", 5)
                logger.debug(f"正在检查 ComfyUI 服务器: {server}")
                
                with log_context(f"连接到 {server}", level="debug", log_start=False):
                    response = http_requests.get(f"{server.rstrip('/')}/system_stats", timeout=timeout)
                
                # 检查响应状态
                if response.status_code == 200:
                    logger.debug(f"ComfyUI 服务器在线: {server}")
                    comfy_status.append({"url": server, "status": "online"})
                else:
                    logger.warning(f"ComfyUI 服务器响应状态异常: {server}, 状态码: {response.status_code}")
                    comfy_status.append({"url": server, "status": "error", "code": response.status_code})
            except RequestException as e:
                logger.error(f"ComfyUI 服务器连接失败: {server}, 错误: {str(e)}")
                comfy_status.append({"url": server, "status": "offline", "error": str(e)})
    
    # 获取系统资源状态
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
    except Exception:
        gpus = []

    cpu_percent = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    mem_percent = mem.percent
    mem_total = mem.total
    mem_used = mem.used
    mem_available = mem.available

    gpu_infos = []
    gpu_abnormal = False
    for gpu in gpus:
        gpu_info = {
            "id": gpu.id,
            "name": gpu.name,
            "load": round(gpu.load * 100, 2),
            "memoryTotal": gpu.memoryTotal,
            "memoryUsed": gpu.memoryUsed,
            "memoryUtil": round(gpu.memoryUtil * 100, 2)
        }
        if gpu_info["load"] > 90 or gpu_info["memoryUtil"] > 90:
            gpu_info["abnormal"] = True
            gpu_abnormal = True
        else:
            gpu_info["abnormal"] = False
        gpu_infos.append(gpu_info)

    # 资源异常标志
    resource_abnormal = False
    resource_alerts = []
    if cpu_percent > 90:
        resource_abnormal = True
        resource_alerts.append(f"CPU 占用率过高: {cpu_percent}%")
    if mem_percent > 90:
        resource_abnormal = True
        resource_alerts.append(f"内存占用率过高: {mem_percent}%")
    if gpu_abnormal:
        resource_abnormal = True
        resource_alerts.append("GPU 资源占用率过高")
    if resource_abnormal:
        logger.warning(f"资源异常: {'; '.join(resource_alerts)}")

    uptime = 0
    if hasattr(app.state, "start_time"):
        uptime = time.time() - app.state.start_time
        logger.debug(f"系统运行时间: {uptime:.2f} 秒")

    # 返回系统状态信息
    return create_success_response({
        "api": {
            "version": config.API_VERSION,
            "status": config.API_STATUS,
            "uptime": uptime
        },
        "comfy_servers": comfy_status,
        "resources": {
            "cpu_percent": cpu_percent,
            "mem_percent": mem_percent,
            "mem_total": mem_total,
            "mem_used": mem_used,
            "mem_available": mem_available,
            "gpus": gpu_infos,
            "abnormal": resource_abnormal,
            "alerts": resource_alerts
        }
    })

@app.get(config.FULL_VERSION_ROUTE)
@log_execution_time(level="debug")
async def version_info(request: Request):
    """版本信息端点
    
    参数:
        request: 请求对象
        
    返回:
        包含 API 版本信息的 JSON 响应
    """
    client_ip = request.client.host if request.client else "unknown"
    logger.debug(f"版本信息请求来自: {client_ip}")
    
    return create_success_response({
        "version": config.API_VERSION,
        "release_date": config.API_RELEASE_DATE,
        "status": config.API_STATUS,
        "functions": [config.FUNCTION_NAME]
    })

@app.get(config.FULL_TEMPLATE_ROUTE)
async def get_function_templates():
    """获取功能模板
    
    返回:
        包含功能模板的 JSON 响应
    """
    try:
        # 使用配置中定义的功能名称
        actual_function_name = config.FUNCTION_NAME
        
        # 尝试从模板文件中读取
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "template",
            actual_function_name,
            "default_template.json"
        )
        
        if os.path.exists(template_path):
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    template_data = json.load(f)
                
                logger.info(f"从文件加载模板成功: {template_path}")
                return create_success_response({"template": template_data})
            except json.JSONDecodeError as e:
                logger.error(f"模板文件格式错误: {template_path}, {str(e)}")
                return create_error_response(ERR_TEMPLATE_FORMAT)
        else:
            logger.warning(f"模板文件不存在: {template_path}, 使用默认配置")
            
            # 获取功能配置
            function_config = config.AIGC_FUNCTIONS.get(actual_function_name, {})
            
            # 提取模板信息
            template = {
                "id": actual_function_name,
                "name": function_config.get("name", actual_function_name),
                "description": function_config.get("description", ""),
                "prefix": function_config.get("prefix", actual_function_name),
                "params": []
            }
            
            # 添加参数信息
            if "params_mapping" in function_config:
                for param_name, mapping in function_config["params_mapping"].items():
                    param_info = {
                        "name": param_name,
                        "description": mapping.get("description", ""),
                        "type": mapping.get("type", "string"),
                        "default": mapping.get("default", None),
                        "required": param_name in function_config.get("api_params", {}).get("required_params", [])
                    }
                    template["params"].append(param_info)
            
            return create_success_response({"template": template})
    except Exception as e:
        logger.error(f"获取功能模板失败: {str(e)}")
        logger.debug(traceback.format_exc())
        return create_error_response(ERR_TEMPLATE_LOAD)
