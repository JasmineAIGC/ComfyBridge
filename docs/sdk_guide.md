# ComfyBridge Python SDK 指南

## 安装

```bash
pip install -r requirements.txt
```

## 基础用法

### 初始化客户端
```python
from client import ComfyBridgeClient

# 使用默认配置
client = ComfyBridgeClient()

# 自定义服务器地址
client = ComfyBridgeClient(base_url="http://custom-host:port")
```

### 图像生成
```python
# 准备请求数据
with open("input.jpg", "rb") as f:
    image_data = f.read()

files = {"image": ("input.jpg", image_data, "image/jpeg")}
data = {
    "params": json.dumps({
        "request_id": "unique-id-123",  # 必选
        "gender": "male",              # 必选
        "age": 30,                    # 必选
        "num": 1                      # 可选，默认 1
    })
}

# 发送请求
success, output_files = client.generate_images(files, data)

# 处理结果
if success:
    print(f"生成的图像保存在: {output_files}")
else:
    print(f"生成失败")
```

### 获取模板
```python
templates = client.get_templates()
```

### 系统 API
```python
# 健康检查
health_info = client.check_health()

# 系统状态
system_info = client.get_system_status()

# 版本信息
version_info = client.get_version_info()
```

## 最佳实践

1. 使用请求 ID 跟踪
```python
import uuid

request_id = str(uuid.uuid4())
data = {
    "params": json.dumps({
        "request_id": request_id,
        "gender": "male",
        "age": 30
    })
}
```

2. 处理大文件
```python
# 设置足够的超时时间
response = requests.post(url, files=files, data=data, timeout=300)
```
