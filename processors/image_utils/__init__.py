"""图像处理工具模块。

提供图像后处理功能，包括合成和元数据标记。

功能:
    图像合成: 将生成图像与背景/模板合成
    AI 标记: 为输出添加 AI 生成元数据（符合法规要求）

Functions:
    img_composite_bytes: 图像合成，返回字节数据
    add_ai_metadata_fast: 快速添加 AI 生成标记
    verify_ai_metadata: 验证图像是否包含 AI 标记
"""

from processors.image_utils.compose_image import img_composite_bytes
from processors.image_utils.add_ai_tag import add_ai_metadata_fast, verify_ai_metadata

__all__ = ['img_composite_bytes', 'add_ai_metadata_fast', 'verify_ai_metadata']
