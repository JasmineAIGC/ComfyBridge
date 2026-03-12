# ComfyBridge 接口文档

## API 端点

### 1. 图像生成接口

**路径**: `/aigc/{function}/generate`

**方法**: POST

**Content-Type**: `multipart/form-data`

**请求参数**:

| 参数名 | 类型 | 必选 | 说明 |
|------------|------|--------|--------|
| image | File | 是 | 输入图像文件（支持 JPEG、PNG） |
| params | JSON String | 是 | 处理参数，包含以下字段 |

**params 参数说明**:
```json
{
    "request_id": "unique-id",      // 必选，用于跟踪请求
    "gender": "male|female",       // 必选，性别
    "age": 1-80,                  // 必选，年龄可选 4、7、12、20、30、40、50
    "num": 1-4                    // 可选，生成图像数量，默认 1
}
```

**响应格式**:
```json
{
    "status": "success",
    "errCode": 0,
    "errMsg": "",
    "data": {
        "request_id": "xxx",
        "processing_time": 1.23,    // 处理时间（秒）
        "images": [{               // 生成的图像列表
            "format": "base64",
            "data": "..."
        }]
    }
}
```

### 2. 模板获取接口

**路径**: `/aigc/{function}/templates`

**方法**: GET

**响应格式**:
```json
{
    "status": "success",
    "errCode": 0,
    "errMsg": "",
    "data": {
        "templates": [{
            "id": "template-id",
            "name": "模板名称",
            "description": "模板描述"
        }]
    }
}
```

### 3. 系统接口

#### 健康检查
- **路径**: `/health`
- **方法**: GET
- **响应**: 返回系统基本健康状态

#### 系统状态
- **路径**: `/api/system/status`
- **方法**: GET
- **响应**: 返回详细的系统状态信息，包括：
  - 总体状态（healthy/degraded/unhealthy）
  - API 版本
  - 运行时间
  - ComfyUI 服务器状态
  - 系统资源使用情况

#### 版本信息
- **路径**: `/api/system/version`
- **方法**: GET
- **响应**: 返回 API 版本信息

## 错误处理

### 错误响应格式
```json
{
    "status": "error",
    "errCode": 400,
    "errMsg": "错误描述",
    "data": {
        "request_id": "xxx"
    }
}
```


## Python SDK 使用

### 基础用法
```python
from client import ComfyBridgeClient

client = ComfyBridgeClient()

# 生成图像
result = client.generate_images(
    image_path="input.jpg",
    params={
        "gender": "male",
        "age": 30
    }
)

# 获取模板
templates = client.get_templates()
```

### 高级配置
```python
client = ComfyBridgeClient(
    base_url="http://custom-host:port",
    timeout=30,
    max_retries=3
)
