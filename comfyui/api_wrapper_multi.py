"""ComfyUI HTTP API 封装模块。

提供与 ComfyUI 服务器交互的完整 HTTP API 封装。

功能分类:
    工作流管理: queue_prompt, get_history
    媒体下载: get_media, get_image, get_video, get_audio
    媒体上传: upload_file, upload_file_data, upload_mask
    服务器状态: get_status, get_queue
    服务器管理: clear_history, delete_history, free_memory, interrupt, clear_queue

Classes:
    ComfyUIError: API 操作异常，包含错误码和消息
    ComfyUIAPIWrapper: HTTP API 封装类

Example:
    >>> api = ComfyUIAPIWrapper('http://localhost:8188')
    >>> result = api.queue_prompt(workflow_dict)
    >>> history = api.get_history(result['prompt_id'])
"""

import json
import requests
from requests.auth import HTTPBasicAuth
from requests.compat import urljoin, urlencode
from typing import Optional

from nexus.logger import logger
from nexus.error_codes import (
    ERR_COMFY_QUEUE_PROMPT,
    ERR_COMFY_GET_HISTORY,
    ERR_COMFY_GET_IMAGE,
    ERR_COMFY_UPLOAD_IMAGE,
    ERR_COMFY_UPLOAD_IMAGE_DATA,
    ERR_COMFY_GET_STATUS,
)

# ============================================================================
# 常量配置
# ============================================================================

DEFAULT_TIMEOUT = 30        # 默认请求超时（秒）
DEFAULT_UPLOAD_TIMEOUT = 120  # 上传超时（秒）

# ============================================================================
# 异常类
# ============================================================================

class ComfyUIError(Exception):
    """ComfyUI API 操作异常。

    Attributes:
        code: 错误码，对应 error_codes 模块中的定义。
        message: 错误描述信息。
    """

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")

# ============================================================================
# API 包装器
# ============================================================================

class ComfyUIAPIWrapper:
    """ComfyUI HTTP API 包装器"""
    
    def __init__(self, url: str = 'http://127.0.0.1:8188', 
                 user: str = '', password: str = ''):
        """初始化 API 包装器
        
        Args:
            url: ComfyUI 服务器地址
            user: 用户名（可选）
            password: 密码（可选）
        """
        self.url = url
        self.auth = HTTPBasicAuth(user, password) if user else None
    
    # ========================================================================
    # 工作流管理
    # ========================================================================
    
    def queue_prompt(self, prompt: dict, client_id: Optional[str] = None) -> dict:
        """提交工作流到执行队列
        
        Args:
            prompt: 工作流定义
            client_id: 客户端标识（可选）
            
        Returns:
            包含 prompt_id 的响应
        """
        payload = {'prompt': prompt}
        if client_id:
            payload['client_id'] = client_id
        
        data = json.dumps(payload).encode('utf-8')
        logger.info(f"提交工作流到 {self.url}/prompt")
        
        resp = requests.post(
            urljoin(self.url, '/prompt'), 
            data=data, 
            auth=self.auth, 
            timeout=DEFAULT_TIMEOUT
        )
        
        if resp.status_code == 200:
            return resp.json()
        
        # 记录详细错误信息用于调试
        error_msg = f"提交失败: {resp.status_code} - {resp.reason}"
        try:
            error_detail = resp.text[:500]  # 限制长度
            logger.error(f"{error_msg}, 响应: {error_detail}")
        except Exception:
            logger.error(error_msg)
        raise ComfyUIError(ERR_COMFY_QUEUE_PROMPT, error_msg)
    
    def get_history(self, prompt_id: Optional[str] = None) -> dict:
        """获取工作流执行历史
        
        Args:
            prompt_id: 工作流 ID，为 None 时返回所有历史
            
        Returns:
            执行历史数据
        """
        if prompt_id:
            url = urljoin(self.url, f"/history/{prompt_id}")
        else:
            url = urljoin(self.url, "/history")
        
        resp = requests.get(url, auth=self.auth, timeout=DEFAULT_TIMEOUT)
        
        if resp.status_code == 200:
            return resp.json()
        
        error_msg = f"获取历史失败: {resp.status_code} - {resp.reason}"
        logger.error(error_msg)
        raise ComfyUIError(ERR_COMFY_GET_HISTORY, error_msg)
    
    # ========================================================================
    # 媒体下载
    # ========================================================================
    
    def get_media(self, filename: str, subfolder: str, folder_type: str,
                   preview: Optional[str] = None, channel: Optional[str] = None) -> bytes:
        """下载媒体文件（通用方法）
        
        Args:
            filename: 文件名
            subfolder: 子文件夹
            folder_type: 文件夹类型 (input/temp/output)
            preview: 预览格式，如 "webp;90" 或 "jpeg;80"
            channel: 通道选择 (rgba/rgb/a)
            
        Returns:
            文件二进制数据
        """
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        if preview:
            params["preview"] = preview
        if channel:
            params["channel"] = channel
        url = urljoin(self.url, f"/view?{urlencode(params)}")
        
        resp = requests.get(url, auth=self.auth, stream=True, timeout=DEFAULT_TIMEOUT)
        
        if resp.status_code == 200:
            return resp.content
        
        error_msg = f"下载失败: {resp.status_code} - {resp.reason}"
        logger.error(error_msg)
        raise ComfyUIError(ERR_COMFY_GET_IMAGE, error_msg)
    
    # 媒体下载别名
    def get_image(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        """下载图像"""
        return self.get_media(filename, subfolder, folder_type)
    
    def get_video(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        """下载视频"""
        return self.get_media(filename, subfolder, folder_type)
    
    def get_audio(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        """下载音频"""
        return self.get_media(filename, subfolder, folder_type)
    
    # ========================================================================
    # 媒体上传
    # ========================================================================
    
    def upload_file(self, filename: str, subfolder: str = '', 
                    overwrite: bool = True, upload_type: str = 'input') -> dict:
        """上传本地文件
        
        Args:
            filename: 本地文件路径
            subfolder: 目标子文件夹
            overwrite: 是否覆盖
            upload_type: 上传目录类型 (input/temp/output)
            
        Returns:
            上传结果（包含 name, subfolder, type）
        """
        url = urljoin(self.url, '/upload/image')
        server_file = filename.split('/')[-1]
        data = {
            'subfolder': subfolder, 
            'overwrite': str(overwrite).lower(),
            'type': upload_type
        }
        
        with open(filename, 'rb') as f:
            files = {'image': (server_file, f.read())}
        
        resp = requests.post(url, files=files, data=data, auth=self.auth, 
                            timeout=DEFAULT_UPLOAD_TIMEOUT)
        
        if resp.status_code == 200:
            return resp.json()
        
        error_msg = f"上传失败: {resp.status_code} - {resp.reason}"
        logger.error(error_msg)
        raise ComfyUIError(ERR_COMFY_UPLOAD_IMAGE, error_msg)
    
    def upload_file_data(self, file_id: str, filedata: bytes, 
                         subfolder: str = '', 
                         overwrite: bool = True,
                         upload_type: str = 'input') -> dict:
        """上传二进制数据
        
        Args:
            file_id: 文件标识（作为文件名，应包含扩展名如 .png）
            filedata: 文件二进制数据
            subfolder: 目标子文件夹
            overwrite: 是否覆盖
            upload_type: 上传目录类型 (input/temp/output)
            
        Returns:
            上传结果（包含 name, subfolder, type）
        """
        url = urljoin(self.url, '/upload/image')
        # 确保文件名有扩展名
        if '.' not in file_id:
            file_id = f"{file_id}.png"
        data = {
            'subfolder': subfolder, 
            'overwrite': str(overwrite).lower(),
            'type': upload_type
        }
        files = {'image': (file_id, filedata)}
        
        resp = requests.post(url, files=files, data=data, auth=self.auth, 
                            timeout=DEFAULT_UPLOAD_TIMEOUT)
        
        if resp.status_code == 200:
            return resp.json()
        
        error_msg = f"上传失败: {resp.status_code} - {resp.reason}"
        logger.error(error_msg)
        raise ComfyUIError(ERR_COMFY_UPLOAD_IMAGE_DATA, error_msg)
    
    def upload_mask(self, file_id: str, filedata: bytes, 
                    original_ref: dict, subfolder: str = '') -> dict:
        """上传遮罩图像
        
        Args:
            file_id: 文件标识（作为文件名）
            filedata: 遮罩图像二进制数据
            original_ref: 原始图像引用 {"filename": "xxx", "subfolder": "", "type": "input"}
            subfolder: 目标子文件夹
            
        Returns:
            上传结果（包含 name, subfolder, type）
        """
        import json as json_module
        url = urljoin(self.url, '/upload/mask')
        if '.' not in file_id:
            file_id = f"{file_id}.png"
        data = {
            'subfolder': subfolder,
            'original_ref': json_module.dumps(original_ref)
        }
        files = {'image': (file_id, filedata)}
        
        resp = requests.post(url, files=files, data=data, auth=self.auth, 
                            timeout=DEFAULT_UPLOAD_TIMEOUT)
        
        if resp.status_code == 200:
            return resp.json()
        
        error_msg = f"上传遮罩失败: {resp.status_code} - {resp.reason}"
        logger.error(error_msg)
        raise ComfyUIError(ERR_COMFY_UPLOAD_IMAGE, error_msg)
    
    # 上传别名（保持向后兼容）
    def upload_image(self, filename: str, subfolder: str = '') -> dict:
        """上传图像文件"""
        return self.upload_file(filename, subfolder)
    
    def upload_image_data(self, file_id: str, filedata: bytes, 
                          subfolder: str = '') -> dict:
        """上传图像数据"""
        return self.upload_file_data(file_id, filedata, subfolder)
    
    # ========================================================================
    # 服务器状态
    # ========================================================================
    
    def get_status(self) -> dict:
        """获取服务器状态
        
        Returns:
            服务器状态信息
        """
        url = urljoin(self.url, '/system_stats')
        resp = requests.get(url, auth=self.auth, timeout=DEFAULT_TIMEOUT)
        
        if resp.status_code == 200:
            return resp.json()
        
        raise ComfyUIError(ERR_COMFY_GET_STATUS, 
                          f"获取状态失败: {resp.status_code} - {resp.reason}")
    
    def get_queue(self) -> dict:
        """获取队列状态
        
        Returns:
            队列信息（queue_running, queue_pending）
        """
        url = urljoin(self.url, '/queue')
        resp = requests.get(url, auth=self.auth, timeout=DEFAULT_TIMEOUT)
        
        if resp.status_code == 200:
            return resp.json()
        return {}
    
    # ========================================================================
    # 服务器管理
    # ========================================================================
    
    def clear_history(self) -> bool:
        """清理所有执行历史
        
        Returns:
            是否成功
        """
        url = urljoin(self.url, '/history')
        resp = requests.post(url, json={"clear": True}, auth=self.auth, timeout=DEFAULT_TIMEOUT)
        return resp.status_code == 200
    
    def delete_history(self, prompt_ids: list) -> bool:
        """删除指定的执行历史
        
        Args:
            prompt_ids: 要删除的 prompt_id 列表
            
        Returns:
            是否成功
        """
        url = urljoin(self.url, '/history')
        resp = requests.post(url, json={"delete": prompt_ids}, auth=self.auth, timeout=DEFAULT_TIMEOUT)
        return resp.status_code == 200
    
    def free_memory(self, unload_models: bool = False, free_memory: bool = True) -> bool:
        """释放 ComfyUI 内存
        
        Args:
            unload_models: 是否卸载模型
            free_memory: 是否释放内存缓存
            
        Returns:
            是否成功
        """
        url = urljoin(self.url, '/free')
        payload = {"unload_models": unload_models, "free_memory": free_memory}
        resp = requests.post(url, json=payload, auth=self.auth, timeout=DEFAULT_TIMEOUT)
        return resp.status_code == 200
    
    def interrupt(self, prompt_id: Optional[str] = None) -> bool:
        """中断执行
        
        Args:
            prompt_id: 指定要中断的 prompt_id，不指定则中断当前执行
            
        Returns:
            是否成功
        """
        url = urljoin(self.url, '/interrupt')
        payload = {"prompt_id": prompt_id} if prompt_id else {}
        resp = requests.post(url, json=payload, auth=self.auth, timeout=DEFAULT_TIMEOUT)
        return resp.status_code == 200
    
    def clear_queue(self) -> bool:
        """清空执行队列
        
        Returns:
            是否成功
        """
        url = urljoin(self.url, '/queue')
        resp = requests.post(url, json={"clear": True}, auth=self.auth, timeout=DEFAULT_TIMEOUT)
        return resp.status_code == 200
