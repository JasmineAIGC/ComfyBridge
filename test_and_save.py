#!/usr/bin/env python
"""ComfyBridge 批量测试脚本。

批量生成不同年龄的图像，并将输入图与生成图左右拼接保存。

用法:
    python test_and_save.py

配置:
    - DEFAULT_SERVER_HOSTS: 服务器地址列表（环境变量或默认值）
    - DEFAULT_SERVER_PORT: 服务器端口
    - image_dir: 输入图像目录
    - age_list: 要测试的年龄列表
"""


import os
import sys
import time
import json
import base64
import uuid
import logging
from io import BytesIO
from typing import Dict, Any, List, Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageFont

# =============================================================================
# 配置
# =============================================================================

# 服务器配置（支持多主机轮询）
DEFAULT_SERVER_HOSTS = [
    h.strip() for h in os.getenv("COMFYBRIDGE_HOSTS", "10.112.64.39").split(",") if h.strip()
]
DEFAULT_SERVER_PORT = int(os.getenv("COMFYBRIDGE_PORT", "3312"))

# API 路由
API_PREFIX = "/aigc"
GENERATE_ROUTE = f"{API_PREFIX}/aging/generate"
HEALTH_ROUTE = f"{API_PREFIX}/system/health"
STATUS_ROUTE = f"{API_PREFIX}/system/status"

# 日志配置
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/test_client.log", mode='a')
    ]
)
logger = logging.getLogger("comfybridge-test")

# =============================================================================
# 测试客户端
# =============================================================================

class TestClient:
    """ComfyBridge 测试客户端，支持多主机轮询。"""
    
    def __init__(self, base_url: Optional[str] = None):
        self._fixed_base_url = base_url
        self._hosts = DEFAULT_SERVER_HOSTS
        self._port = DEFAULT_SERVER_PORT
        self._host_idx = 0
        
        if base_url:
            logger.info(f"测试客户端连接到: {base_url}")
        else:
            logger.info(f"测试客户端主机池: {self._hosts}, 端口: {self._port}")
    
    def _get_base_url(self) -> str:
        """轮询获取基础 URL。"""
        if self._fixed_base_url:
            return self._fixed_base_url
        if not self._hosts:
            raise RuntimeError("主机列表为空")
        host = self._hosts[self._host_idx % len(self._hosts)]
        self._host_idx += 1
        return f"http://{host}:{self._port}"

    def check_health(self) -> bool:
        """检查服务健康状态。"""
        url = f"{self._get_base_url()}{HEALTH_ROUTE}"
        try:
            resp = requests.get(url, timeout=10)
            return resp.status_code == 200 and resp.json().get("status") == "success"
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return False
    
    def generate(self, files: Dict[str, tuple], data: Dict[str, str], 
                 output_dir: str = "./output") -> Tuple[bool, List[str]]:
        """生成图像并保存（输入图与生成图左右拼接）。
        
        Args:
            files: 请求文件，格式 {'image': (filename, bytes, 'image/jpeg')}
            data: 请求参数，格式 {'params': json.dumps({...})}
            output_dir: 输出目录
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # 解析参数
        params = json.loads(data.get('params', '{}'))
        request_id = params.get('request_id', f"req-{int(time.time())}-{uuid.uuid4().hex[:5]}")
        age = params.get('age', 0)
        
        # 缓存输入图用于拼接
        input_img = None
        if 'image' in files and len(files['image']) >= 2:
            try:
                image_bytes = files['image'][1]
                input_img = Image.open(BytesIO(image_bytes)).convert('RGB')
                scale = 720 / max(input_img.size)
                input_img = input_img.resize((int(input_img.width * scale), int(input_img.height * scale)), Image.LANCZOS)
            except Exception:
                pass
        
        url = f"{self._get_base_url()}{GENERATE_ROUTE}"
        logger.info(f"[{request_id}] 请求: {params}")
        
        try:
            start = time.time()
            resp = requests.post(url, files=files, data=data, timeout=300)
            elapsed = time.time() - start
            
            # 尝试解析响应
            try:
                result = resp.json()
            except Exception:
                result = {"raw": resp.text[:500]}
            
            # 检查 HTTP 状态码
            if resp.status_code != 200:
                logger.error(f"[{request_id}] HTTP {resp.status_code}: {result}")
                return False, []
            
            # 检查业务状态
            if result.get("status") != "success":
                err_code = result.get("errCode", "unknown")
                err_msg = result.get("errMsg", "未知错误")
                logger.error(f"[{request_id}] 失败 [{err_code}]: {err_msg}")
                return False, []
            
            # 保存生成的图像
            output_files = []
            for i, img_obj in enumerate(result["data"].get("images", [])):
                if img_obj.get("format") != "base64":
                    continue
                
                gen_img = Image.open(BytesIO(base64.b64decode(img_obj["data"]))).convert('RGB')
                
                # 左右拼接
                if input_img:
                    combined = Image.new('RGB', (input_img.width + gen_img.width, max(input_img.height, gen_img.height)), 'white')
                    combined.paste(input_img, (0, 0))
                    combined.paste(gen_img, (input_img.width, 0))
                else:
                    combined = gen_img
                
                # 标注年龄
                self._draw_label(combined, f"age: {age}")
                
                # 保存
                out_path = os.path.join(output_dir, f"{request_id}_{i}_age{age}.png")
                combined.save(out_path)
                output_files.append(out_path)
            
            logger.info(f"[{request_id}] 完成: {len(output_files)} 张, 耗时 {elapsed:.2f}s")
            return True, output_files
            
        except requests.exceptions.RequestException as e:
            # 网络/HTTP 异常，尝试获取响应内容
            if hasattr(e, 'response') and e.response is not None:
                try:
                    err_detail = e.response.json()
                except Exception:
                    err_detail = e.response.text[:500] if e.response.text else str(e)
                logger.error(f"[{request_id}] 请求异常: {err_detail}")
            else:
                logger.error(f"[{request_id}] 网络异常: {e}")
            return False, []
        except Exception as e:
            logger.error(f"[{request_id}] 未知异常: {e}")
            return False, []
    
    @staticmethod
    def _draw_label(img: Image.Image, text: str):
        """在图像左上角绘制标签。"""
        try:
            draw = ImageDraw.Draw(img)
            font = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), text, font=font)
            pad = 6
            draw.rectangle((0, 0, bbox[2] + pad * 2, bbox[3] + pad * 2), fill='white')
            draw.text((pad, pad), text, fill='black', font=font)
        except Exception:
            pass


# =============================================================================
# 主函数
# =============================================================================

def main():
    """批量测试不同年龄的图像生成。"""
    # 配置
    image_dir = "data"           # 输入图像目录
    output_dir = "output"        # 输出目录
    age_list = [10, 20, 30, 40, 50, 60, 70, 80]
    gender = "male"
    
    # 创建客户端
    client = TestClient()
    
    # 健康检查
    if not client.check_health():
        logger.error("服务不可用，退出")
        return
    logger.info("服务健康检查通过")
    
    # 获取测试图像
    if not os.path.isdir(image_dir):
        logger.error(f"图像目录不存在: {image_dir}")
        return
    
    image_files = [f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    if not image_files:
        logger.error(f"目录中没有图像文件: {image_dir}")
        return
    
    logger.info(f"找到 {len(image_files)} 张测试图像")
    
    # 批量测试
    for img_file in image_files:
        image_path = os.path.join(image_dir, img_file)
        logger.info(f"处理图像: {img_file}")
        
        # 读取图像数据
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
        
        for age in age_list:
            # 构建请求
            files = {'image': (os.path.basename(image_path), image_bytes, 'image/jpeg')}
            data = {'params': json.dumps({
                'gender': gender,
                'age': age,
                'num': 1,
                'request_id': f"req-{int(time.time())}-{uuid.uuid4().hex[:5]}"
            })}
            
            success, outputs = client.generate(files, data, output_dir=output_dir)
            if success:
                print(f"  ✓ age={age}: {outputs}")
            else:
                print(f"  ✗ age={age}: 失败")


if __name__ == "__main__":
    main()
