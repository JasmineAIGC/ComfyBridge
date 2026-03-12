# ComfyBridge

ComfyBridge 是一个基于 ComfyUI 的通用 AIGC API 封装框架，支持音频/图像/视频/3D模型生成。基于 FastAPI 构建，采用模块化设计，可作为各种 AIGC 服务的标准封装框架。只要是可以通过 ComfyUI 实现的功能，均可以快速封装为 API。

## 核心功能

### API 设计
- **路由规范**：`/aigc/{function}/{action}` 层次结构
- **请求格式**：Multipart/form-data，支持文件与 JSON 并发
- **响应标准**：统一 JSON 结构，包含 status/data/message

### 系统架构
- **请求跟踪**：基于 UUID 的 request_id 跟踪机制
- **状态监控**：标准健康检测端点，支持容器编排
- **异步处理**：Starlette/Uvicorn ASGI 框架，高并发支持
- **资源管理**：自动内存清理和文件系统维护

### 开发生态
- **类型安全**：Pydantic 驱动的参数验证，支持类型注解
- **模块化**：领域驱动设计原则，插件式扩展
- **共享模型**：InsightFace 和眼镜检测器共享实例，优化内存使用

### 视觉处理
- **属性提取**：InsightFace 模型提取人脸属性（性别、年龄、表情）
- **质量检测**：基于 InsightFace 引擎实现，优化性能和准确性
- **提示词生成**：基于属性生成结构化提示词，支持年龄、性别、眼镜自适应
- **图像工具**：图像合成和 AI 元数据标记功能

### 资源管理
- **文件清理**：支持按时间、大小、数量清理日志和输出文件
- **内存优化**：ComfyUI 缓存清理和显式内存释放
- **自动维护**：应用关闭时自动执行清理任务

## 快速开始

```bash
# 安装
pip install -r requirements.txt
```bash
# 运行
python server.py
```

## 使用方式

ComfyBridge 提供两种使用方式：

### 直接调用 ComfyUI 服务

如果只需要调用 ComfyUI 服务的实现代码，可以参考 `comfyui/` 目录下的代码。该目录提供了 ComfyUI 服务的完整调用实现，包括多服务器负载均衡、工作流加载和执行、WebSocket 实时状态监听等功能，可作为独立的 ComfyUI 客户端库使用。

### 部署完整的 API 服务

ComfyBridge 不仅仅是调用 ComfyUI 服务，而且把整个调用服务又封装为了一个新的 API，可以直接部署。封装 API 的时候只需要几个简单的操作，代码量极少：

1. 在 `config.py` 中配置工作流路径和功能名称
2. 在 `routes.py` 中定义参数验证模型
3. 在 `routes.py` 中添加 API 路由端点

框架提供了完整的请求处理、日志记录、错误处理、健康检查、资源清理、并发控制等生产特性，开箱即用，易于扩展。

## 项目结构

```
ComfyBridge/
├─ nexus/                    # 核心包
│   ├─ app.py               # FastAPI 应用配置和生命周期管理
│   ├─ routes.py            # API 路由定义
│   ├─ comfy.py             # ComfyUI 接口封装
│   ├─ logger.py            # 日志配置
│   ├─ utils.py             # 工具函数
│   └─ error_codes.py       # 错误码定义
├─ processors/               # 处理器模块
│   ├─ attribute_extractor/  # 图像属性提取
│   │   ├─ extractor.py     # InsightFace 属性提取实现
│   │   └─ requirements.txt  # 依赖包
│   ├─ quality_check/       # 图像质量检查
│   │   └─ validator.py     # 质量验证实现
│   ├─ prompt_templates/    # 提示词和权重模板
│   │   ├─ prompt_selector.py    # 提示词选择器
│   │   ├─ weight_selector.py     # 权重选择器
│   │   ├─ prompt_template.json   # 提示词模板
│   │   └─ weight_template.json   # 权重模板
│   ├─ image_utils/         # 图像工具
│   │   ├─ compose_image.py # 图像合成
│   │   └─ add_ai_tag.py    # AI 元数据标记
│   └─ __init__.py          # 处理器初始化和共享模型管理
├─ cleanup/                  # 资源清理模块
│   ├─ file_cleanup.py      # 文件系统清理工具
│   ├─ memory_cleanup.py    # ComfyUI 缓存清理工具
│   └─ cleanup_scheduler.sh # 清理调度脚本
├─ comfyui/                  # ComfyUI 接口封装
│   ├─ api_wrapper_multi.py # 多服务器 API 封装
│   └─ workflow_wrapper.py  # 工作流封装
├─ workflow/                 # 工作流程定义
│   └─ aging-api-coding-v1.json # 年龄转换工作流
├─ data/                     # 数据文件
├─ logs/                     # 日志文件
├─ output/                   # 输出文件
├─ sh/                       # Shell 脚本
│   ├─ check_memory.sh      # 内存检查
│   ├─ safe_cleanup.sh      # 安全清理
│   └─ start_with_cleanup.sh # 启动并清理
├─ deploy/                   # 部署相关
│   ├─ run_deploy.sh        # 部署脚本
│   └─ 新要求-示例.md       # 部署示例
├─ docs/                     # 文档目录
│   ├─ api_reference.md     # API 参考
│   ├─ sdk_guide.md         # SDK 指南
│   ├─ new_function_guide.md # 新功能开发指南
│   ├─ framework_architecture.md # 框架架构
│   ├─ aging_api_guide.md   # 年龄转换 API 指南
│   └─ ERROR_CODES_FINAL.md # 错误码文档
├─ client.py                # Python 客户端 SDK
├─ server.py                # 服务器入口
├─ server_deploy.py         # 部署服务器入口
├─ config.py                # 配置文件
├─ config_deploy.py         # 部署配置文件
├─ requirements.txt         # Python 依赖
├─ test_and_save.py        # 测试脚本
└─ test_quality_check.py   # 质量检查测试
```

## API 端点

### 系统端点
- `GET /aigc/system/health` - 健康检查
- `GET /aigc/system/status` - 系统状态（包含资源使用情况）
- `GET /aigc/system/version` - 版本信息

### 功能端点
- `POST /aigc/aging/generate` - 图像生成（年龄转换）
- `GET /aigc/aging/templates` - 模板列表

## 文档

### 用户指南
- [API 参考](docs/api_reference.md) - 详细的 API 文档
- [SDK 指南](docs/sdk_guide.md) - Python SDK 使用指南

### 开发指南
- [新功能开发](docs/new_function_guide.md) - 如何基于 ComfyBridge 开发新功能
- [框架架构](docs/framework_architecture.md) - 系统架构设计说明
- [错误码文档](docs/ERROR_CODES_FINAL.md) - 完整错误码列表

## 配置说明

主要配置项在 [config.py](config.py) 中：

- `SERVER_HOST` / `SERVER_PORT` - 服务器监听地址
- `COMFY_SERVERS` - ComfyUI 服务器列表（支持负载均衡）
- `FUNCTION_NAME` - 当前功能名称
- `WORKFLOW_PATH` - 工作流配置文件路径
- `LOG_LEVEL` - 日志级别
- `MAX_CONCURRENT_REQUESTS` - 最大并发请求数

## 资源清理策略

系统提供自动和手动两种资源清理方式：

### 自动清理
- 应用关闭时自动执行文件和内存清理
- 支持按时间（保留天数）、大小（最大容量）、数量（最大文件数）清理
- ComfyUI 缓存自动清理，保留最近 N 条历史记录

### 手动清理
- 使用 `sh/safe_cleanup.sh` 执行安全清理
- 使用 `sh/check_memory.sh` 检查内存使用情况
- 使用 `cleanup/` 模块中的工具进行精细控制

