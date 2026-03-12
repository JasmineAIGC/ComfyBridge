"""图像属性提取模块。

基于 InsightFace 的人脸属性分析，为 AIGC 流程提供参数选择依据。

提取属性:
    基础属性: 性别、年龄
    面部特征: 表情、肤色、发型
    配饰检测: 眼镜

Functions:
    extract_image_attributes: 提取图像中的人脸属性
"""

from processors.attribute_extractor.extractor import extract_image_attributes

__all__ = ['extract_image_attributes']
