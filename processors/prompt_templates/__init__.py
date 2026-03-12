"""提示词和权重模板模块。

根据图像属性（性别、年龄）选择合适的提示词和权重参数。

模板文件:
    prompt_template.json: 提示词模板（character/clothing/scene）
    weight_template.json: 权重模板（slider/pulid/instantid）

Functions:
    init_prompt_templates: 初始化提示词模板
    init_weight_templates: 初始化权重模板
    get_prompt_for_target_age_from_attributes: 根据属性获取提示词
    all_weights_from_attributes: 根据属性计算权重
"""

from processors.prompt_templates.prompt_selector import (
    initialize as init_prompt_templates,
    get_prompt_for_target_age_from_attributes
)
from processors.prompt_templates.weight_selector import (
    initialize as init_weight_templates,
    all_weights_from_attributes
)

__all__ = [
    'init_prompt_templates',
    'init_weight_templates',
    'get_prompt_for_target_age_from_attributes',
    'all_weights_from_attributes'
]
