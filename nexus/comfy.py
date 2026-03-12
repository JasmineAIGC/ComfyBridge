"""ComfyUI 服务器交互模块。

提供与 ComfyUI 服务器的完整集成接口。

功能:
    工作流管理: 加载、配置和执行工作流
    负载均衡: 多服务器轮询和健康检查
    故障转移: 自动重试和服务器切换
    结果解析: 获取和处理生成结果

Classes:
    ComfyInterface: ComfyUI 服务器交互接口

Global:
    comfy_interface: 全局单例实例
"""

import os
import time
import hashlib
import asyncio
import traceback
import threading
import uuid
import gc
import base64
from typing import Dict, Any, List, Optional

import config
from nexus.logger import logger
from nexus.error_codes import (
    ERR_WORKFLOW_CONFIG_FAILED,
    ERR_WORKFLOW_EXECUTION_FAILED,
    ERR_WORKFLOW_NO_PROMPT_ID,
    ERR_MAX_CONSECUTIVE_FAILURES,
    ERR_MAX_RETRIES_EXCEEDED,
    ERR_ALL_SERVERS_FAILED,
    ERR_COMFY_QUEUE_PROMPT,
    ERR_COMFY_EXECUTION_ERROR
)
from comfyui.api_wrapper_multi import ComfyUIAPIWrapper, ComfyUIError
from comfyui.workflow_wrapper import ComfyUIWorkfowWrapper

# ============================================================================
# ComfyInterface - ComfyUI 服务器交互接口
# ============================================================================

class ComfyInterface:
    """处理与 ComfyUI 服务器的交互，支持负载均衡和故障转移"""
    
    # 清理计数器（类级别）
    _cleanup_counter = 0
    
    def __init__(self):
        """初始化 ComfyInterface"""
        self.workflows = {}
        self.server_loads = {s: 0 for s in config.COMFY_SERVERS}
        self.server_health = {s: True for s in config.COMFY_SERVERS}
        self.server_response_times = {s: [] for s in config.COMFY_SERVERS}
        self.last_health_check = {s: 0 for s in config.COMFY_SERVERS}
        self._load_workflows()
    
    # ========================================================================
    # 工作流管理
    # ========================================================================
    
    def _load_workflows(self) -> None:
        """加载配置文件中定义的所有工作流"""
        for function_name, function_config in config.AIGC_FUNCTIONS.items():
            try:
                workflow_path = function_config.get("workflow_path")
                if workflow_path:
                    # 转换为绝对路径
                    if not os.path.isabs(workflow_path):
                        workflow_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), workflow_path)
                    
                    logger.info(f"加载工作流: {workflow_path}")
                    self.workflows[function_name] = ComfyUIWorkfowWrapper(workflow_path)
                    logger.info(f"功能 {function_name} 的工作流加载成功")
            except Exception as e:
                logger.error(f"加载功能 {function_name} 的工作流失败: {str(e)}")
                logger.debug(traceback.format_exc())
    
    def get_workflow(self, function_name: str) -> Optional[ComfyUIWorkfowWrapper]:
        """获取指定功能的工作流"""
        return self.workflows.get(function_name)
    
    def _get_function_config(self, function_name: str) -> Dict[str, Any]:
        """获取功能配置"""
        return config.AIGC_FUNCTIONS.get(function_name, {})
    
    # ========================================================================
    # 服务器管理与负载均衡
    # ========================================================================
    
    def _check_server_health_sync(self, server_url: str) -> bool:
        """同步检查服务器健康状态"""
        try:
            ComfyUIAPIWrapper(server_url).get_status()
            self.server_health[server_url] = True
            self.last_health_check[server_url] = time.time()
            return True
        except Exception:
            self.server_health[server_url] = False
            self.last_health_check[server_url] = time.time()
            return False
    
    def _maybe_recover_unhealthy_servers(self):
        """尝试恢复不健康的服务器（每60秒最多检查一次）"""
        now = time.time()
        for server_url in config.COMFY_SERVERS:
            if not self.server_health.get(server_url, True):
                if now - self.last_health_check.get(server_url, 0) >= 60:
                    if self._check_server_health_sync(server_url):
                        logger.info(f"服务器已恢复: {server_url}")
    
    def get_server_url(self, function_name: str) -> str:
        """获取服务器 URL，使用最少连接数负载均衡"""
        self._maybe_recover_unhealthy_servers()
        
        servers = self._get_function_config(function_name).get("servers", config.COMFY_SERVERS)
        if not servers:
            raise ComfyUIError(ERR_ALL_SERVERS_FAILED, f"功能 {function_name} 没有可用的服务器")
        
        healthy_servers = [s for s in servers if self.server_health.get(s, True)] or servers
        selected = min(healthy_servers, key=lambda s: self.server_loads.get(s, 0))
        self.server_loads[selected] = self.server_loads.get(selected, 0) + 1
        
        logger.info(f"选择服务器 {selected}，负载: {self.server_loads[selected]}")
        return selected
    
    def _release_server(self, server_url: str, success: bool = True):
        """释放服务器负载"""
        self.server_loads[server_url] = max(0, self.server_loads.get(server_url, 1) - 1)
        if not success:
            self.server_health[server_url] = False
    
    # ========================================================================
    # 工作流配置
    # ========================================================================
    
    def _clone_workflow(self, original: ComfyUIWorkfowWrapper) -> ComfyUIWorkfowWrapper:
        """创建工作流副本（优化内存，只深拷贝 inputs）"""
        workflow = ComfyUIWorkfowWrapper.__new__(ComfyUIWorkfowWrapper)
        dict.__init__(workflow)
        for node_id, node_data in original.items():
            workflow[node_id] = {
                '_meta': node_data['_meta'],
                'class_type': node_data['class_type'],
                'inputs': dict(node_data['inputs'])
            }
        return workflow
    
    def _configure_workflow(self, function_name: str, params: Dict[str, Any], api: ComfyUIAPIWrapper) -> Optional[ComfyUIWorkfowWrapper]:
        """配置工作流：上传图像、设置参数"""
        try:
            original = self.get_workflow(function_name)
            if not original:
                logger.error(f"功能 {function_name} 没有可用的工作流")
                return None
            
            workflow = self._clone_workflow(original)
            request_id = params.get('request_id', str(uuid.uuid4()))
            
            # 上传图像
            image_meta = api.upload_image_data(request_id, params.get('imageData', b''))
            # 构建图像路径：有 subfolder 时用 subfolder/name，否则只用 name
            if image_meta.get('subfolder'):
                image_path = f"{image_meta['subfolder']}/{image_meta['name']}"
            else:
                image_path = image_meta['name']
            workflow.set_node_param_by_artificial("290", "Load Image", "image", image_path)
            
            # 设置随机种子（并发安全：基于请求ID生成唯一种子）
            base_seed = int(hashlib.md5(
                f"{request_id}_{time.time()}_{os.getpid()}".encode()
            ).hexdigest()[:8], 16)
            
            for i, node_id in enumerate(["2472", "2473"]):
                # 每个节点使用不同的种子
                node_seed = (base_seed + i * 12345 + int(time.time() * 1000000) % 10000) % (10**10)
                workflow.set_node_param_by_artificial(
                    node_id, "EasySeed", "seed", str(node_seed)
                )
            
            # 设置业务参数
             # 设置 positive prompt
            workflow.set_node_param_by_artificial('2466', "positive prompt", "text", params.get('prompt'))
            # 设置 age_slider 权重
            workflow.set_node_param_by_artificial('2474', "slider weight", "value", params.get('slider_weight'))
            # 设置 PulID 权重
            workflow.set_node_param_by_artificial('2475', "pulid weight", "value", params.get('pulid_weight'))
            workflow.set_node_param_by_artificial('2476', "pulid end_at", "value", params.get('pulid_end_at'))
            # 设置 InstantID 权重
            workflow.set_node_param_by_artificial('2469', "instantid weight", "value", params.get('instantid_weight'))
            workflow.set_node_param_by_artificial('2470', "instantid end_at", "value", params.get('instantid_end_at'))
            
            logger.info(f"工作流配置成功: {function_name}")
            return workflow
        except Exception as e:
            logger.error(f"配置工作流失败: {e}")
            return None
    
    # ========================================================================
    # 请求处理
    # ========================================================================
    
    def _get_output_node_config(self, function_name: str):
        """获取输出节点配置
        
        优先使用多节点配置 (output_nodes)，如果未配置则回退到单节点配置 (image_node_title)。
        
        Args:
            function_name: 功能名称
            
        Returns:
            输出节点配置：
            - List[Dict]: 多节点配置
            - str: 单节点标题（向后兼容）
        """
        func_config = self._get_function_config(function_name)
        
        # 优先使用多节点配置
        output_nodes = func_config.get("output_nodes")
        if output_nodes:
            return output_nodes
        
        # 回退到单节点配置
        return func_config.get("image_node_title", config.IMAGE_NODE_TITLE)
    
    async def process_request(self, function_name: str, params: Dict[str, Any]) -> List[Dict]:
        """处理请求，支持故障转移
        
        尝试在可用服务器上执行工作流，失败时自动切换到下一个服务器。
        支持多输出节点配置，可以从多个不同的节点获取输出结果。
        """
        all_servers = self._get_function_config(function_name).get("servers", config.COMFY_SERVERS)
        tried_servers = set()
        last_exception = None
        
        # 获取输出节点配置（支持多节点）
        output_node_config = self._get_output_node_config(function_name)
        
        # 最多尝试所有服务器
        for attempt in range(len(all_servers)):
            # 获取负载最低的服务器
            server_url = self.get_server_url(function_name)
            
            # 如果服务器已尝试过，跳过
            if server_url in tried_servers:
                self._release_server(server_url)
                # 检查是否所有服务器都已尝试
                if len(tried_servers) >= len(all_servers):
                    break
                continue
            
            tried_servers.add(server_url)
            logger.info(f"尝试服务器 {server_url} [{len(tried_servers)}/{len(all_servers)}]")
            
            try:
                api = ComfyUIAPIWrapper(server_url)
                workflow = self._configure_workflow(function_name, params, api)
                
                if not workflow:
                    self._release_server(server_url, success=False)
                    last_exception = ComfyUIError(ERR_WORKFLOW_CONFIG_FAILED, "工作流配置失败")
                    continue
                
                start_time = time.time()
                result = await asyncio.to_thread(
                    self._run_workflow, api, workflow, output_node_config, start_time, params
                )
                
                self._release_server(server_url, success=True)
                logger.info(f"工作流完成，耗时: {time.time() - start_time:.2f}s")
                return result
                
            except Exception as e:
                last_exception = e
                self._release_server(server_url, success=False)
                logger.error(f"服务器 {server_url} 失败: {e}")
        
        # 所有服务器都失败
        if last_exception:
            raise last_exception
        raise ComfyUIError(ERR_ALL_SERVERS_FAILED, "所有服务器尝试失败")
    
    # ========================================================================
    # 工作流执行
    # ========================================================================
    
    def _run_workflow(self, api: ComfyUIAPIWrapper, workflow, output_node_config, 
                      start_time: float, params: Dict = None) -> List[Dict]:
        """执行工作流并获取结果
        
        Args:
            api: ComfyUI API 包装器
            workflow: 工作流对象
            output_node_config: 输出节点配置，支持以下格式：
                - str: 单个节点标题（向后兼容）
                - List[Dict]: 多节点配置，每个 Dict 包含 {"title": "节点标题", "name": "输出名称"}
            start_time: 开始时间
            params: 请求参数
            
        Returns:
            媒体文件列表
        """
        params = params or {}
        request_id = params.get('request_id', str(uuid.uuid4()))
        client_id = f"{request_id}_{int(time.time() * 1000000)}"
        
        # 提交工作流
        response = api.queue_prompt(workflow, client_id)
        if not response:
            raise ComfyUIError(ERR_COMFY_QUEUE_PROMPT, "提交工作流失败")
        
        prompt_id = response.get('prompt_id')
        if not prompt_id:
            raise ComfyUIError(ERR_WORKFLOW_NO_PROMPT_ID, f"无法获取 prompt_id")
        
        logger.info(f"工作流已提交: prompt_id={prompt_id}")
        
        # 等待执行完成
        outputs = self._wait_for_completion(api, prompt_id, start_time)
        
        # 获取结果（支持多节点）
        result_media = self._fetch_outputs(api, workflow, output_node_config, outputs)
        
        # 异步清理
        self._maybe_cleanup(api)
        
        return result_media
    
    def _wait_for_completion(self, api: ComfyUIAPIWrapper, prompt_id: str, start_time: float) -> Dict:
        """轮询等待工作流执行完成"""
        retry_interval = 0.5
        max_interval = 10
        backoff_factor = 1.5
        max_retries = 180
        consecutive_failures = 0
        max_consecutive_failures = 10
        outputs = {}
        
        for retry_count in range(1, max_retries + 1):
            try:
                history = api.get_history(prompt_id)
                if history and prompt_id in history:
                    consecutive_failures = 0
                    history_data = history[prompt_id]
                    status = history_data.get('status', {})
                    outputs = history_data.get('outputs', {})
                    
                    # 检查错误
                    error = self._check_execution_error(history_data, status, outputs)
                    if error:
                        logger.error(f"ComfyUI 工作流执行失败: {error}")
                        raise ComfyUIError(ERR_COMFY_EXECUTION_ERROR, error)
                    
                    # 检查完成
                    if outputs:
                        logger.info(f"工作流完成，耗时: {time.time() - start_time:.2f}s，重试: {retry_count}")
                        return outputs
                        
            except ComfyUIError:
                raise
            except Exception:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    raise ComfyUIError(ERR_MAX_CONSECUTIVE_FAILURES, 
                                      f"连续失败 {max_consecutive_failures} 次")
            
            # 指数退避
            wait_time = min(retry_interval, max_interval)
            time.sleep(wait_time)
            retry_interval = min(retry_interval * backoff_factor, max_interval)
        
        raise ComfyUIError(ERR_MAX_RETRIES_EXCEEDED, f"超时: 重试 {max_retries} 次")
    
    def _check_execution_error(self, history_data: Dict, status: Dict, outputs: Dict) -> Optional[str]:
        """检查执行错误"""
        # 检查 status_str
        if status.get('status_str') == 'error':
            return history_data.get('error', 'Execution error')
        
        # 检查 error 字段
        if 'error' in history_data:
            return history_data['error']
        
        # 检查完成但无输出
        if status.get('completed', False) and not outputs:
            return 'Workflow completed but no outputs'
        
        # 从 messages 提取错误
        messages = status.get('messages', [])
        for msg in messages:
            if isinstance(msg, list) and len(msg) >= 2 and msg[0] == 'execution_error':
                data = msg[1]
                return f"{data.get('node_type', 'Unknown')}: {data.get('exception_message', '')}"
        
        return None
    
    def _fetch_outputs_from_node(self, api: ComfyUIAPIWrapper, workflow,
                                   node_title: str, outputs: Dict, 
                                   output_name: Optional[str] = None) -> List[Dict]:
        """从单个节点获取输出媒体文件
        
        Args:
            api: ComfyUI API 包装器
            workflow: 工作流对象
            node_title: 节点标题
            outputs: ComfyUI 返回的输出数据
            output_name: 输出分组名称（可选，用于标识来源）
            
        Returns:
            媒体文件列表
        """
        try:
            node_id = workflow.get_node_id(node_title)
        except Exception as e:
            logger.warning(f"节点 '{node_title}' 不存在，跳过: {e}")
            return []
            
        node_outputs = outputs.get(node_id, {})
        result = []
        
        # 媒体类型映射
        media_type_map = {
            'images': 'image',
            'gifs': 'video',
            'videos': 'video',
            'audio': 'audio',
            'audios': 'audio'
        }
        
        for output_key, media_type in media_type_map.items():
            items = node_outputs.get(output_key, [])
            for item in items:
                # 构建缓存地址
                cache_path = f"{api.url}/view?filename={item['filename']}&subfolder={item['subfolder']}&type={item['type']}"
                logger.info(f"拉取生成结果: {cache_path}")
                for attempt in range(3):
                    try:
                        data = api.get_media(item['filename'], item['subfolder'], item['type'])
                        media_item = {
                            'data': base64.b64encode(data).decode('utf-8'),
                            'format': 'base64',
                            'type': media_type,
                            'filename': item['filename']
                        }
                        # 如果指定了输出名称，添加来源标识
                        if output_name:
                            media_item['source'] = output_name
                        result.append(media_item)
                        break
                    except Exception as e:
                        if attempt == 2:
                            logger.error(f"获取 {media_type} 失败: {item['filename']}, {e}")
                        time.sleep(1)
        
        return result
    
    def _fetch_outputs(self, api: ComfyUIAPIWrapper, workflow, 
                       output_node_config, outputs: Dict) -> List[Dict]:
        """获取输出媒体文件（支持单节点和多节点）
        
        Args:
            api: ComfyUI API 包装器
            workflow: 工作流对象
            output_node_config: 输出节点配置，支持以下格式：
                - str: 单个节点标题（向后兼容）
                - List[Dict]: 多节点配置，每个 Dict 包含 {"title": "节点标题", "name": "输出名称"}
                - None: 使用默认配置
            outputs: ComfyUI 返回的输出数据
            
        Returns:
            媒体文件列表，每个元素包含 data, format, type, filename, 以及可选的 source
        """
        result = []
        
        # 处理 None 的情况，使用默认配置
        if output_node_config is None:
            output_node_config = config.IMAGE_NODE_TITLE
        
        # 向后兼容：如果是字符串，直接从单节点获取
        if isinstance(output_node_config, str):
            return self._fetch_outputs_from_node(api, workflow, output_node_config, outputs)
        
        # 多节点配置
        if isinstance(output_node_config, list):
            for node_config in output_node_config:
                if isinstance(node_config, dict):
                    node_title = node_config.get('title')
                    output_name = node_config.get('name')
                    if node_title:
                        node_results = self._fetch_outputs_from_node(
                            api, workflow, node_title, outputs, output_name
                        )
                        result.extend(node_results)
                elif isinstance(node_config, str):
                    # 支持简化的字符串列表格式
                    node_results = self._fetch_outputs_from_node(
                        api, workflow, node_config, outputs
                    )
                    result.extend(node_results)
        
        return result
    
    # ========================================================================
    # 清理
    # ========================================================================
    
    def _maybe_cleanup(self, api: ComfyUIAPIWrapper):
        """定期执行异步清理"""
        ComfyInterface._cleanup_counter += 1
        
        if ComfyInterface._cleanup_counter % config.COMFY_CLEANUP_INTERVAL != 0:
            return
        
        def cleanup():
            try:
                if config.COMFY_CLEANUP_HISTORY:
                    self._cleanup_history(api)
                if config.COMFY_CLEANUP_MEMORY:
                    self._cleanup_memory(api)
                gc.collect()
                logger.info("定期清理完成")
            except Exception as e:
                logger.debug(f"清理异常: {e}")
        
        threading.Thread(target=cleanup, daemon=True).start()
    
    def _cleanup_history(self, api: ComfyUIAPIWrapper):
        """清理历史记录"""
        try:
            # 使用 API 封装获取历史
            history = api.get_history()  # 获取所有历史
            if not isinstance(history, dict):
                return
            
            keep = config.COMFY_KEEP_HISTORY_COUNT
            if len(history) <= keep:
                return
            
            to_delete = list(history.keys())[:-keep]
            if to_delete:
                api.delete_history(to_delete)
                logger.info(f"已清理 {len(to_delete)} 条历史记录")
        except Exception as e:
            logger.debug(f"清理历史异常: {e}")
    
    def _cleanup_memory(self, api: ComfyUIAPIWrapper):
        """释放 ComfyUI 内存"""
        try:
            api.free_memory(unload_models=False, free_memory=True)
        except Exception:
            pass

# 创建 ComfyUI 接口实例
comfy_interface = ComfyInterface()
