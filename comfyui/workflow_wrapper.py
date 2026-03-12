"""ComfyUI 工作流封装模块。

提供对 ComfyUI 工作流 JSON 的面向对象封装，简化节点操作。

功能:
    节点查询: list_nodes, get_node_id, get_node_ids
    参数操作: get_node_param, set_node_param, set_node_param_by_artificial

Example:
    >>> workflow = ComfyUIWorkfowWrapper('workflow.json')
    >>> workflow.set_node_param_by_artificial('123', 'KSampler', 'seed', 42)
    >>> node_id = workflow.get_node_id('SaveImage')
"""

import json
from typing import Any, List, Optional

from nexus.logger import logger
from nexus.error_codes import ERR_WORKFLOW_NODE_NOT_FOUND, get_error_message


class WorkflowNodeError(Exception):
    """工作流节点错误，包含统一错误码"""
    def __init__(self, detail: str):
        self.code = ERR_WORKFLOW_NODE_NOT_FOUND
        self.message = get_error_message(ERR_WORKFLOW_NODE_NOT_FOUND)
        self.detail = detail
        super().__init__(detail)


class ComfyUIWorkfowWrapper(dict):
    """ComfyUI 工作流封装类。

    继承自 dict，可直接作为字典使用，同时提供便捷的节点操作方法。

    Attributes:
        继承 dict 的所有属性，键为节点 ID，值为节点配置字典。
    """

    def __init__(self, path: str):
        """从 JSON 文件加载工作流。

        Args:
            path: 工作流 JSON 文件的绝对或相对路径。
        """
        with open(path, encoding='utf-8') as f:
            super().__init__(json.load(f))
    
    # ========================================================================
    # 节点查询
    # ========================================================================
    
    def list_nodes(self) -> List[str]:
        """获取所有节点标题"""
        return [node['_meta']['title'] for node in self.values()]
    
    def get_node_id(self, title: str) -> str:
        """根据标题获取节点 ID（返回第一个匹配）
        
        Args:
            title: 节点标题
            
        Returns:
            节点 ID
            
        Raises:
            WorkflowNodeError: 节点不存在
        """
        for node_id, node in self.items():
            if node['_meta']['title'] == title:
                return node_id
        raise WorkflowNodeError(f"节点 '{title}' 不存在")
    
    def get_node_ids(self, title: str) -> List[str]:
        """根据标题获取所有匹配的节点 ID
        
        Args:
            title: 节点标题
            
        Returns:
            节点 ID 列表
            
        Raises:
            WorkflowNodeError: 节点不存在
        """
        ids = [nid for nid, node in self.items() if node['_meta']['title'] == title]
        if not ids:
            raise WorkflowNodeError(f"节点 '{title}' 不存在")
        return ids
    
    def _find_node(self, node_id: str, title: str) -> Optional[dict]:
        """查找指定 ID 和标题的节点"""
        node = self.get(node_id)
        if node and node['_meta']['title'] == title:
            return node
        return None
    
    # ========================================================================
    # 参数操作
    # ========================================================================
    
    def get_node_param(self, title: str, param: str) -> Any:
        """获取节点参数值（返回第一个匹配节点的值）
        
        Args:
            title: 节点标题
            param: 参数名
            
        Returns:
            参数值
            
        Raises:
            WorkflowNodeError: 节点不存在
        """
        for node in self.values():
            if node['_meta']['title'] == title:
                return node['inputs'][param]
        raise WorkflowNodeError(f"节点 '{title}' 不存在")
    
    def set_node_param(self, title: str, param: str, value: Any) -> None:
        """设置节点参数值（所有匹配节点）
        
        Args:
            title: 节点标题
            param: 参数名
            value: 参数值
            
        Raises:
            WorkflowNodeError: 节点不存在
        """
        found = False
        for node in self.values():
            if node['_meta']['title'] == title:
                node['inputs'][param] = value
                found = True
        
        if not found:
            raise WorkflowNodeError(f"节点 '{title}' 不存在")
    
    def set_node_param_by_artificial(self, node_id: str, title: str, 
                                      param: str, value: Any) -> None:
        """精确设置指定节点的参数值
        
        Args:
            node_id: 节点 ID
            title: 节点标题（用于验证）
            param: 参数名
            value: 参数值
            
        Raises:
            WorkflowNodeError: 节点不存在或标题不匹配
        """
        node = self._find_node(node_id, title)
        if node:
            node['inputs'][param] = value
        else:
            raise WorkflowNodeError(f"节点 '{title}' (ID: {node_id}) 不存在")
    
    # ========================================================================
    # 文件操作
    # ========================================================================
    
    def save_to_file(self, path: str) -> None:
        """保存工作流到文件
        
        Args:
            path: 目标文件路径
        """
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self, f, indent=4, ensure_ascii=False)