"""
Prompt选择器

从 prompt_template.json 中按 性别→目标年龄 选择 character/clothing/scene 片段，
并拼接为一个 prompt 字符串。
"""
import os
import json
import random
from datetime import datetime
from typing import Any, Dict, List, Optional
from nexus.logger import logger

TEMPLATE_FILE = os.path.join(os.path.dirname(__file__), "prompt_template.json")
_TEMPLATES_CACHE: Optional[Dict[str, Any]] = None


def initialize() -> None:
    global _TEMPLATES_CACHE
    if _TEMPLATES_CACHE is not None:
        return
    try:
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            _TEMPLATES_CACHE = json.load(f)
        logger.info("prompt_template 载入完成")
    except Exception as e:
        _TEMPLATES_CACHE = {}
        logger.error(f"读取 {TEMPLATE_FILE} 失败: {e}")


def _ensure_loaded() -> Dict[str, Any]:
    global _TEMPLATES_CACHE
    if _TEMPLATES_CACHE is None:
        initialize()
    return _TEMPLATES_CACHE or {}


def _normalize_gender(gender: Any) -> str:
    g = str(gender).lower() if isinstance(gender, (str, bytes)) else "male"
    if g not in ("male", "female"):
        logger.warning(f"未知 gender={g}，使用 'male'")
        return "male"
    return g


def _available_ages(templates: Dict[str, Any], gender: str) -> List[int]:
    """获取指定性别下所有可用的年龄"""
    ages: List[int] = []
    try:
        gender_data = templates.get(gender, {})
        for k in gender_data.keys():
            try:
                ages.append(int(k))
            except Exception:
                continue
    except Exception:
        pass
    return sorted(ages)


def _get_chunks(templates: Dict[str, Any], gender: str, target_age: int) -> Dict[str, List[str]]:
    """
    获取指定性别和目标年龄的 prompt 片段
    如果目标年龄不存在，则使用最近的年龄
    """
    # 先尝试精确命中
    try:
        data = templates[gender][str(target_age)]
        # return {
        #     "character": data.get("character", []) or [],
        #     "clothing": [],
        #     "scene": [],
        # }
        return {
            "character": data.get("character", []) or [],
            "clothing": data.get("clothing", []) or [],
            "scene": data.get("scene", []) or [],
        }
    except Exception:
        pass

    # 最近年龄回退逻辑
    try:
        gender_bucket = templates.get(gender, {})
        # 可用年龄键（字符串->整数）
        available_ages = []
        for k in gender_bucket.keys():
            try:
                available_ages.append(int(k))
            except Exception:
                continue
        
        if not available_ages:
            logger.info(f"无模板: gender={gender}（无可用年龄键）")
            return {"character": [], "clothing": [], "scene": []}

        # 选择与 target_age 最近的年龄键，若距离相同，选择较小的年龄
        nearest_age = min(available_ages, key=lambda x: (abs(x - int(target_age)), x))
        data = gender_bucket.get(str(nearest_age), {})
        logger.debug(f"使用最近年龄回退: gender={gender}, target_age={target_age} -> nearest_age={nearest_age}")
        return {
            "character": (data.get("character", []) or []),
            "clothing": (data.get("clothing", []) or []),
            "scene": (data.get("scene", []) or []),
        }
    except Exception as e:
        logger.info(f"无模板: gender={gender}, age={target_age}, error={e}")
        return {"character": [], "clothing": [], "scene": []}


def _build_prompt(chunks: Dict[str, List[str]], sep: str = ". ") -> Optional[str]:
    parts: List[str] = []
    for key in ("character", "clothing", "scene"):
        arr = chunks.get(key, [])
        if arr:
            s = random.choice(arr)
            s = (s or "").strip()
            if s:
                parts.append(s.rstrip(". "))
    if not parts:
        return None
    return sep.join(parts).strip()


def get_prompt_for_target_age(
    gender: str,
    current_age: int,
    target_age: int,
    current_year: Optional[int] = None,
    separator: str = ". ",
) -> Optional[str]:
    """
    根据性别和目标年龄获取 prompt
    
    参数:
        gender: 性别 ("male" 或 "female")
        current_age: 当前年龄（已废弃，保留参数以兼容旧代码）
        target_age: 目标年龄
        current_year: 当前年份（已废弃，保留参数以兼容旧代码）
        separator: prompt 片段之间的分隔符
        
    返回:
        拼接好的 prompt 字符串，如果失败则返回 None
    """
    templates = _ensure_loaded()
    if not templates:
        return None
    g = _normalize_gender(gender)

    # 直接使用性别和目标年龄获取 chunks
    chunks = _get_chunks(templates, g, int(target_age))
    prompt = _build_prompt(chunks, sep=separator)
    if prompt is None:
        logger.info(f"拼接失败: gender={g}, target_age={target_age}")
    return prompt


def get_prompt_for_target_age_from_attributes(
    image_attributes: Dict[str, Any],
    target_age: int,
    current_year: Optional[int] = None,
    separator: str = ". ",
) -> Optional[str]:
    gender = image_attributes.get("gender", "male")
    current_age = image_attributes.get("age", 30)
    return get_prompt_for_target_age(gender, current_age, target_age, current_year, separator)
