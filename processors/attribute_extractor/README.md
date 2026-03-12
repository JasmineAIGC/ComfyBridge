# 图像属性提取器

## 概述

图像属性提取器是 ComfyBridge 的核心组件之一，用于从人脸图像中提取各种属性，如性别、年龄、表情等。这些属性可用于个性化图像生成和处理。

## 实现版本

本目录包含两个不同的属性提取器实现：

1. **原始实现 (extractor.py)**：
   - 基于 InsightFace 和自定义模型
   - 提供基本的属性提取功能

2. **DeepFace 实现 (deepface_extractor.py)**：
   - 基于 DeepFace 库
   - 提供更全面的属性分析
   - 支持多种属性检测（性别、年龄、表情、肤色等）

## 功能对比

| 功能 | 原始实现 | DeepFace 实现 |
|------|---------|--------------|
| 性别检测 | ✓ | ✓ |
| 年龄估计 | ✓ | ✓ |
| 表情分析 | ✓ | ✓ |
| 肤色检测 | ✓ | ✓ |
| 眼镜检测 | ✓ | ✓ |
| 胡须检测 | ✓ | ✓ |
| 情绪分析 | 部分支持 | 完全支持 |
| 种族识别 | 不支持 | 支持 |
| 多人脸处理 | 不支持 | 支持 |

## 使用方法

### 原始实现

```python
from processors.attribute_extractor.extractor import extract_image_attributes

# 从文件中提取属性
with open("image.jpg", "rb") as f:
    image_data = f.read()
    attributes = extract_image_attributes(image_data)
    
print(attributes)
```

### DeepFace 实现

```python
from processors.attribute_extractor.deepface_extractor import extract_image_attributes

# 方法 1：从文件路径提取
attributes = extract_image_attributes("image.jpg")

# 方法 2：从二进制数据提取
with open("image.jpg", "rb") as f:
    image_data = f.read()
    attributes = extract_image_attributes(image_data)
    
print(attributes)
```

## 安装依赖

DeepFace 实现需要安装以下依赖：

```bash
pip install deepface opencv-python numpy
```

## 注意事项

1. 首次运行时，DeepFace 会自动下载所需的模型文件
2. 建议在使用前调用 `initialize()` 函数预热模型，以避免首次调用时的延迟
3. 对于生产环境，可能需要调整 `enforce_detection` 参数以处理无法检测到人脸的情况
