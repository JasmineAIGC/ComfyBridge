#!/usr/bin/env python
"""ComfyBridge Python 客户端。

提供与 ComfyBridge 服务器交互的完整客户端实现。

功能:
    系统状态: 健康检查、状态查询、版本信息
    图像生成: 上传图像并调用 AIGC 工作流
    模板管理: 获取可用模板列表

Classes:
    ComfyBridgeClient: API 客户端类

Example:
    >>> client = ComfyBridgeClient('http://localhost:6543')
    >>> health = client.check_health()
    >>> result = client.generate_image('input.jpg', gender='female', age=25)

Note:
    路由配置与服务器 config.py 保持一致。
"""


import os
import sys
import time
import json
import base64
import logging
import requests
from typing import Dict, Any, List, Optional, Union, Tuple
from PIL import Image
from io import BytesIO

# 客户端配置
# 服务器配置
DEFAULT_SERVER_HOST = "0.0.0.0"
DEFAULT_SERVER_PORT = 6543

# API 路由（与服务器 config.py 保持一致）
API_PREFIX = "/aigc"
FUNCTION_PREFIX = "/aging"

# 系统路由
HEALTH_ROUTE = f"{API_PREFIX}/system/health"
STATUS_ROUTE = f"{API_PREFIX}/system/status"
VERSION_ROUTE = f"{API_PREFIX}/system/version"

# 功能路由
TEMPLATE_ROUTE = f"{API_PREFIX}{FUNCTION_PREFIX}/templates"
GENERATE_ROUTE = f"{API_PREFIX}{FUNCTION_PREFIX}/generate"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("client.log", mode='a')
    ]
)
logger = logging.getLogger("comfybridge-client")

class ComfyBridgeClient:
    """ComfyBridge 客户端类
    
    提供与 ComfyBridge 服务器交互的完整客户端实现，封装了所有 API 调用和数据处理逻辑。
    该类采用面向对象的设计，提供了简洁易用的方法，使用户可以轻松地调用 ComfyBridge 的各种功能。
    
    主要功能：
    1. 系统状态查询：检查 API 服务器健康状态和系统运行指标
    2. 图像生成：上传输入图像并调用 API 生成新图像
    3. 模板管理：获取可用模板列表和详细信息
    4. 版本信息：获取 API 版本和兼容性信息
    
    所有方法都设计为返回标准化的结果，便于集成和错误处理。每个方法都包含详细的异常
    处理机制，确保在网络问题或服务器错误时能够提供有意义的错误信息。
    
    示例用法：
        >>> client = ComfyBridgeClient()
        >>> # 检查服务器健康状态
        >>> health_info = client.check_health()
        >>> # 生成图像
        >>> success, output_files = client.generate_images("input.jpg", {"gender": "male", "age": 30})
    """
    
    def __init__(self, base_url: Optional[str] = None):
        """初始化 ComfyBridge 客户端
        
        创建一个新的 ComfyBridgeClient 实例，并设置与 ComfyBridge 服务器的连接参数。
        如果未指定 base_url，将使用配置文件中的服务器地址和端口构建 URL。
        初始化过程中会创建输出目录，用于存储生成的图像和其他结果文件。
        
        参数:
            base_url (Optional[str]): API 基础 URL，如 "http://localhost:8000"。
                                      如果为 None，则使用配置文件中的服务器地址和端口。
                                      默认为 None。
        
        注意:
            客户端会自动创建 "output" 目录用于存储生成的图像和其他输出文件。
            确保当前用户对该目录有写入权限。
        """
        self.base_url = base_url or f"http://{DEFAULT_SERVER_HOST}:{DEFAULT_SERVER_PORT}"
        logger.info(f"初始化 ComfyBridge 客户端，连接到 {self.base_url}")
        
        # 确保输出目录存在
        os.makedirs("output", exist_ok=True)
    
    def check_health(self) -> Dict[str, Any]:
        """
        检查 API 服务健康状态
        
        返回:
            健康状态信息
        """
        url = f"{self.base_url}{HEALTH_ROUTE}"
        logger.info(f"检查服务健康状态: {url}")
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if result["status"] == "success":
                logger.info("服务健康状态正常")
                return result["data"]
            else:
                logger.error(f"服务健康状态异常: {result['errMsg']}")
                return {"status": "unhealthy", "error": result["errMsg"]}
        
        except Exception as e:
            logger.error(f"健康检查失败: {str(e)}")
            return {"status": "unhealthy", "error": str(e)}
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        获取系统状态信息
        
        返回:
            系统状态信息
        """
        url = f"{self.base_url}{STATUS_ROUTE}"
        logger.info(f"获取系统状态: {url}")
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if result["status"] == "success":
                logger.info("获取系统状态成功")
                return result["data"]
            else:
                logger.error(f"获取系统状态失败: {result['errMsg']}")
                return {"error": result["errMsg"]}
        
        except Exception as e:
            logger.error(f"获取系统状态失败: {str(e)}")
            return {"error": str(e)}
    
    def get_version_info(self) -> Dict[str, Any]:
        """
        获取 API 版本信息
        
        返回:
            版本信息
        """
        url = f"{self.base_url}{VERSION_ROUTE}"
        logger.info(f"获取版本信息: {url}")
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if result["status"] == "success":
                logger.info(f"获取版本信息成功: {result['data']['version']}")
                return result["data"]
            else:
                logger.error(f"获取版本信息失败: {result['errMsg']}")
                return {"error": result["errMsg"]}
        
        except Exception as e:
            logger.error(f"获取版本信息失败: {str(e)}")
            return {"error": str(e)}
    
    def get_templates(self) -> Dict[str, Any]:
        """
        获取功能模板信息
        
        返回:
            模板信息
        """
        url = f"{self.base_url}{TEMPLATE_ROUTE}"
        logger.info(f"获取模板信息: {url}")
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if result["status"] == "success":
                logger.info("获取模板信息成功")
                return result["data"]
            else:
                logger.error(f"获取模板信息失败: {result['errMsg']}")
                return {"error": result["errMsg"]}
        
        except Exception as e:
            logger.error(f"获取模板信息失败: {str(e)}")
            return {"error": str(e)}
    
    def generate_images(self, files: Union[Dict[str, Tuple], List[Tuple[str, Tuple]]], data: Dict[str, str], 
                        output_dir: Optional[str] = None) -> Tuple[bool, List[str]]:
        """
        生成图像（支持单图与多图）
        
        参数:
            files: 请求文件数据
                - 单图：{'image': (filename, bytes, 'image/jpeg')}
                - 多图：[('image', (filename1, bytes1, 'image/jpeg')), ('image', (filename2, bytes2, 'image/jpeg')), ...]
            data: 请求参数数据
            output_dir: 输出目录，默认为 ./output
            
        返回:
            (成功标志, 生成的图像路径列表)
        """
        url = f"{self.base_url}{GENERATE_ROUTE}"
        output_dir = output_dir or "./output"
        os.makedirs(output_dir, exist_ok=True)
        
        # 从参数中获取请求 ID
        params = json.loads(data.get('params', '{}'))
        request_id = params.get('request_id', '')
        logger.info(f"生成图像请求 [{request_id}]: {url}")
        
        try:
            # 发送请求
            logger.info(f"发送请求: 参数: {params}")
            start_time = time.time()
            response = requests.post(url, files=files, data=data, timeout=300)
            response.raise_for_status()
            result = response.json()
            
            processing_time = time.time() - start_time
            logger.info(f"请求处理完成，耗时: {processing_time:.2f}s")
            
            # 处理响应
            if result["status"] == "success":
                # 保存生成的图像
                output_files = []
                for i, image_obj in enumerate(result["data"]["images"]):
                    # 解码 base64 数据
                    if image_obj.get('format') == 'base64':
                        image_data = base64.b64decode(image_obj['data'])
                        # 将二进制数据转换为图像
                        image = Image.open(BytesIO(image_data))
                        
                        # 保存图像
                        output_file = os.path.join(output_dir, f"{request_id}_image_{i}.png")
                        image.save(output_file)
                        output_files.append(output_file)
                        logger.info(f"保存图像: {output_file}")
                    else:
                        logger.warning(f"不支持的图像格式: {image_obj.get('format')}")
                
                logger.info(f"成功生成 {len(output_files)} 张图像")
                return True, output_files
            else:
                logger.error(f"生成图像失败: {result['errMsg']}")
                return False, []
        
        except Exception as e:
            logger.error(f"生成图像异常: {str(e)}", exc_info=True)
            return False, []


def main():
    """主函数"""
    # 创建客户端实例
    client = ComfyBridgeClient()
    
    # 检查服务健康状态
    health_status = client.check_health()
    print(f"服务健康状态: {health_status}")
    
    # 获取版本信息
    version_info = client.get_version_info()
    print(f"API 版本信息: {version_info}")
    
    # 获取模板信息
    templates = client.get_templates()
    print(f"\n可用模板信息: {json.dumps(templates, indent=2, ensure_ascii=False)}")
    
    # 测试图像生成
    test_image = "./data/man_12.jpg"
    if not os.path.exists(test_image):
        print(f"测试图像不存在: {test_image}")
        print("请先准备测试图像，或修改测试图像路径")
        return
    
    # 准备请求数据
    # 1. 准备参数
    params = {
        "gender": "male",
        "age": 30,
        "num": 1,
        "request_id": f"req-{int(time.time())}"  # 生成请求 ID
    }
    
    # 2. 读取图像数据
    with open(test_image, 'rb') as f:
        image_data = f.read()
    
    # 3. 准备请求数据
    files = {
        'image': (os.path.basename(test_image), image_data, 'image/jpeg')
    }
    data = {
        'params': json.dumps(params)
    }
    
    # 4. 生成图像
    success, output_files = client.generate_images(files, data)
    if success:
        print(f"成功生成 {len(output_files)} 张图像:")
        for file in output_files:
            print(f"  - {file}")
    else:
        print("图像生成失败")


if __name__ == "__main__":
    main()
