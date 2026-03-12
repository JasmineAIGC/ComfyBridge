"""图像质量检查模块。

基于 InsightFace 的图像质量验证，确保输入图像满足 AIGC 处理要求。

检查项目:
    基础属性: 分辨率、清晰度、光照条件
    人脸质量: 检测、尺寸、完整性、姿态
    表情状态: 眼睛开合、嘴巴开合

Functions:
    validate_image_quality: 执行完整的图像质量检查
"""

from processors.quality_check.validator import validate_image_quality

__all__ = ['validate_image_quality']
