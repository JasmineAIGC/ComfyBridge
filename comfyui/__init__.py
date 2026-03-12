"""ComfyUI 集成模块。

提供与 ComfyUI 服务器交互的完整封装，包括 API 调用和工作流管理。

Classes:
    ComfyUIAPIWrapper: HTTP API 封装，处理所有与 ComfyUI 的通信
    ComfyUIError: ComfyUI 操作异常类
    ComfyUIWorkfowWrapper: 工作流 JSON 封装，支持节点参数读写
"""

from comfyui.api_wrapper_multi import ComfyUIAPIWrapper, ComfyUIError
from comfyui.workflow_wrapper import ComfyUIWorkfowWrapper

__all__ = ['ComfyUIAPIWrapper', 'ComfyUIError', 'ComfyUIWorkfowWrapper']