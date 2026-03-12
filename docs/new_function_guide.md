# 基于 ComfyBridge 封装新功能指南

本指南介绍如何基于 ComfyBridge 框架封装新的 AIGC 功能。

## 1. 配置文件修改 (config.py)

需要在 config.py 中添加新功能的配置：

```python
# 功能配置
FUNCTION_NAME = "your_function"  # 例如: "style_transfer"
FUNCTION_TITLE = "功能标题"      # 例如: "风格迁移"
FUNCTION_DESC = "功能描述"       # 例如: "将输入图像转换为特定艺术风格"

# ComfyUI 工作流配置
WORKFLOW_FILE = "workflows/your_workflow.json"  # 工作流文件路径
```

## 2. 路由处理修改 (routes.py)

### 2.1 修改模板获取函数

```python
@app.get(f"{config.API_PREFIX}/{config.FUNCTION_NAME}/templates")
async def get_function_templates():
    """获取功能模板信息"""
    try:
        # 从指定路径读取模板文件
        template_path = "templates/aging.json"  # 模板文件路径
        with open(template_path, 'r', encoding='utf-8') as f:
            templates = json.load(f)
            
        return create_success_response(templates)
        
    except FileNotFoundError:
        return create_error_response(500, "模板文件不存在")
    except json.JSONDecodeError:
        return create_error_response(500, "模板文件格式错误")
    except Exception as e:
        return create_error_response(500, f"获取模板失败: {str(e)}")
```

### 2.2 修改图像生成函数

```python
@app.post(f"{config.API_PREFIX}/{config.FUNCTION_NAME}/generate")
async def generate_image(request: Request, image: UploadFile = File(...), params: str = Form(...)):
    """处理图像生成请求"""
    try:
        # 解析参数
        params_dict = json.loads(params)
        request_id = params_dict.get("request_id", "")
        
        # 加载工作流模板
        workflow = comfy_interface._load_workflow_template(config.WORKFLOW_FILE)
        if not workflow:
            return create_error_response(500, "加载工作流模板失败")
            
        # 从工作流中获取参数节点
        param_node = comfy_interface._find_node_by_title(workflow, "StyleParams")
        if not param_node:
            return create_error_response(500, "未找到参数节点")
            
        # 验证必需参数
        required_params = set(param_node["required_inputs"])
        for param in required_params:
            if param not in params_dict:
                return create_error_response(400, f"缺少必需参数: {param}")
        
        # 验证图像
        if image.content_type not in ["image/jpeg", "image/png"]:
            return create_error_response(400, "不支持的图像格式，仅支持 JPEG 和 PNG")
            
        image_data = await image.read()
        if len(image_data) > 5 * 1024 * 1024:  # 5MB
            return create_error_response(400, "图像大小超出限制（5MB）")
        
        # 处理请求
        results = await comfy_interface.process_request(config.FUNCTION_NAME, params_dict)
        
        return create_success_response({
            "request_id": request_id,
            "images": results
        })
        
    except json.JSONDecodeError:
        return create_error_response(400, "参数解析错误：无效的 JSON 格式")
    except Exception as e:
        return create_error_response(500, f"处理请求失败: {str(e)}")
```

## 3. ComfyUI 接口修改 (comfy.py)

修改 _configure_workflow 方法以适配新功能：

```python
def _configure_workflow(self, function_name: str, params: Dict[str, Any], api: ComfyUIAPIWrapper) -> Dict:
    """配置工作流
    
    参数:
        function_name: 功能名称
        params: 请求参数
        api: ComfyUI API 包装器
        
    返回:
        配置好的工作流
    """
    try:
        # 加载工作流模板
        workflow = self._load_workflow_template(config.WORKFLOW_FILE)
        if not workflow:
            return None
            
        # 获取参数节点
        param_node = self._find_node_by_title(workflow, config.PARAM_NODE_TITLE)
        if not param_node:
            logger.error(f"未找到参数节点: {config.PARAM_NODE_TITLE}")
            return None
            
        # 设置参数
        for name, value in params.items():
            if name in config.PARAM_CONFIGS:
                param_node["inputs"][name] = value
                
        return workflow
        
    except Exception as e:
        logger.error(f"配置工作流失败: {str(e)}")
        return None
```
