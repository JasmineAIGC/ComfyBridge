"""
权重选择器

从 weight_template.json 中读取配置，基于当前年龄与目标年龄的等级差，
计算 slider、pulid、instantid 三种权重。

规则：
1) slider: 基于 base；每相差一个年龄等级（目标>当前为正，<当前为负）调整 1 个 step，可叠加。
2) pulid/instantid: 基于 base；与当前年龄相差 N 个等级，则权重减少 N 个 step（绝对值），end_at 同样减少 N 个 step；下限为 0。
"""
import os
import json
import math
from typing import Any, Dict, List, Optional, Tuple
from nexus.logger import logger

TEMPLATE_FILE = os.path.join(os.path.dirname(__file__), "weight_template.json")
_TEMPLATE: Optional[Dict[str, Any]] = None


# 在代码中配置递减曲线参数（无需额外文件）
#
# 目的：让“年龄等级差(abs_diff)”越大时，对权重的影响越平滑（边际变化更小）。
#
# 字段说明：
# - type: 曲线类型
#   * 'log1p'（默认）：magnitude = log(1 + k*abs_diff)，随 abs_diff 增长而逐渐变缓；稳定通用。
#   * 'sqrt'：magnitude = sqrt(k*abs_diff)，比 log 更“猛”，但也随差距增大而放缓；曲线更抬头。
#   * 'linear'：magnitude = k*abs_diff，线性，不递减；一般不推荐，只作备用。
# - k: 曲线强度系数（>0）。k 越大，相同 abs_diff 下的 magnitude 越大（影响更强）。
#
# 快速直觉（以 log1p 为例，k=1）：
#   abs_diff = 0 -> 0.000
#   abs_diff = 1 -> 0.693
#   abs_diff = 2 -> 1.099
#   abs_diff = 3 -> 1.386
# 与线性(1,2,3,...)相比，log1p 增长变慢，从而“差距越大，变化越平滑”。
#
# 调参建议：
# - 需要更温和：降低 k（例如 0.7 或 0.5）。
# - 需要更敏感：提高 k（例如 1.5 或 2.0）。
# - 想要更“抬头”的递减：尝试 type='sqrt' 并适当调 k。
#
# 概念说明：
# - “更温和”= 对同样的年龄差(abs_diff)，权重变化更小（不容易大幅波动）。实现方式：减小 k。
# - “更敏感”= 对同样的年龄差(abs_diff)，权重变化更大（反应更激进）。实现方式：增大 k。
#
# 同参对比（以 log1p 曲线、abs_diff=3 为例）：
#   magnitude = log(1 + k * 3)
#   - k=0.5（更温和）: log(1 + 1.5) ≈ 0.916
#   - k=1.0（默认）  : log(1 + 3.0) ≈ 1.386
#   - k=2.0（更敏感）: log(1 + 6.0) ≈ 1.946
#
# 这个 magnitude 会进入：
# - slider:  result = base + sign * step * magnitude
# - consistency: result = base - step * magnitude（并做 0 下限）
# 所以同样 abs_diff 下，k 越大，slider 调整幅度越大；consistency 的衰减越多。
_CURVE_CONFIG: Dict[str, Dict[str, Any]] = {
    # 将 k 从 1.0 调整为 0.7，使大年龄差下的变化更“温和”一些
    "slider": {"type": "log1p", "k": 0.7},
    "consistency": {"type": "log1p", "k": 0.7},
}


def _curve_magnitude(kind: str, abs_diff: int) -> float:
    """根据曲线配置计算“递减幅度” magnitude。

    影响：
      - 在 slider_weight 中：最终值 = base + sign * step * magnitude
      - 在 consistency（pulid/instantid）中：最终值 = base - step * magnitude（并做下限裁剪）

    参数：
      - kind: 'slider' | 'consistency'（使用不同的曲线配置）
      - abs_diff: 年龄等级差的绝对值（>=0）

    输出：
      - magnitude >= 0，随 abs_diff 增大单调不减，但增长速度取决于曲线类型和 k。
    """
    cfg = _CURVE_CONFIG.get(kind, {"type": "log1p", "k": 1.0})
    t = str(cfg.get("type", "log1p")).lower()
    try:
        k = float(cfg.get("k", 1.0))
        k = max(1e-6, k)
    except Exception:
        k = 1.0

    x = float(abs(abs_diff))
    if t == "sqrt":
        # sqrt(k * x)
        return math.sqrt(k * x)
    elif t == "linear":
        # k * x（不建议用于递减，但保留作为备选）
        return k * x
    else:
        # 默认 log1p(k * x)
        return math.log1p(k * x)


def initialize() -> None:
    """预加载模板"""
    global _TEMPLATE
    if _TEMPLATE is not None:
        return
    try:
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            _TEMPLATE = json.load(f)
        logger.info("weight_template 载入完成")
    except Exception as e:
        _TEMPLATE = {}
        logger.error(f"读取 {TEMPLATE_FILE} 失败: {e}")


def _cfg() -> Dict[str, Any]:
    global _TEMPLATE
    if _TEMPLATE is None:
        initialize()
    return _TEMPLATE or {}


def _normalize_gender(gender: Any) -> str:
    g = str(gender).lower() if isinstance(gender, (str, bytes)) else "male"
    if g not in ("male", "female"):
        logger.warning(f"未知 gender={g}，使用 'male'")
        return "male"
    return g


def _age_levels(cfg: Dict[str, Any]) -> List[int]:
    try:
        arr = cfg.get("age", [])
        return sorted(int(x) for x in arr)
    except Exception:
        # 回退到固定等级
        return [4, 7, 12, 20, 30, 40, 50]


def _nearest_index(levels: List[int], age: int) -> int:
    if age in levels:
        return levels.index(age)
    # 向下靠：找小于等于age的最大值
    candidates = [x for x in levels if x <= age]
    if candidates:
        closest = max(candidates)
    else:
        # 如果age小于所有等级，取最小等级
        closest = min(levels)
    return levels.index(closest)


def _level_diff(cfg: Dict[str, Any], current_age: int, target_age: int) -> int:
    levels = _age_levels(cfg)
    ci = _nearest_index(levels, int(current_age))
    ti = _nearest_index(levels, int(target_age))
    return ti - ci


def slider_weight(gender: str, current_age: int, target_age: int) -> float:
    """计算 slider 权重。

    正确逻辑：
      1. 真实年龄时 base = 0
      2. 目标年龄 > 真实年龄 → 正值（变老）
      3. 目标年龄 < 真实年龄 → 负值（变年轻）

    公式：
      base = 0  # 真实年龄时总是0
      diff_levels = target_level_index - current_level_index
      sign = sign(diff_levels)
      magnitude = curve("slider", |diff_levels|)
      result = base + sign * step * magnitude = sign * step * magnitude

    取值范围：[-5, 5]
    """
    cfg = _cfg()
    g = _normalize_gender(gender)
    try:
        sw = cfg["slider_weight"][g]
        
        # 1. base 总是 0（真实年龄为参考点）
        base = float(sw.get("base", 0.0))
        
        # 2. 根据年龄差距调整权重
        step = float(sw.get("weight_step", 1.0))
        diff = _level_diff(cfg, current_age, target_age)
        sign = 1.0 if diff > 0 else (-1.0 if diff < 0 else 0.0)
        magnitude = _curve_magnitude("slider", abs(diff))
        val = base + sign * step * magnitude
        
        # 限制在 [-5, 5] 范围内
        val = max(-5.0, min(5.0, val))
        
        logger.debug(
            f"slider: gender={g}, current={current_age}, target={target_age}, "
            f"base={base}, diff={diff}, step={step}, magnitude={magnitude}, val={val}"
        )
        return val
    except Exception as e:
        logger.error(f"计算 slider 失败: {e}")
        logger.debug(traceback.format_exc())
        return 0.0


def _get_age_phase(age: int) -> str:
    """根据年龄返回所属阶段
    
    阶段划分基于人脸老化研究：
    - 10-30: 青春期到成年早期，面部结构变化快
    - 30-50: 成年期，面部结构稳定
    - 50-60: 中老年过渡期
    - 60+: 老年期，骨骼结构固定
    """
    if age < 30:
        return "10-30"
    elif age < 50:
        return "30-50"
    elif age < 60:
        return "50-60"
    else:
        return "60+"


def _consistency(model: str, gender: str, current_age: int, target_age: int) -> Tuple[float, float]:
    """计算一致性权重（pulid/instantid）及 end_at。

    优化逻辑：
      1. 真实年龄时，weight = 1.0（最高相似度）
      2. 年龄差距越大，权重衰减越快（非线性）
      3. 使用 min_weight 保证始终有相似性

    公式：
      base_w = 1.0  # 真实年龄时最高相似度
      diff = |target_age - current_age|
      magnitude = curve("consistency", diff)  # 非线性曲线
      weight = base_w - step_w * magnitude
      weight = max(min_weight, min(1.0, weight))  # 保证相似性

    参数含义：
      - weight: ID相似度权重
        * 1.0: 真实年龄，最高相似度
        * 0.6-0.7: 大年龄差距，仍保持相似性
      - end_at: 特征应用的结束时间步
        * 越小越早结束（更注重结构）

    取值范围：[min_weight, 1.0]
    """
    cfg = _cfg()
    g = _normalize_gender(gender)
    try:
        m = cfg["consistency_weight"][g][model]
        
        # 1. 获取基础权重（真实年龄时 = 1.0）
        base_w = float(m.get("base_weight", 1.0))
        base_e = float(m.get("base_end_at", 0.5 if model == "pulid" else 0.95))
        
        # 2. 根据真实年龄所属阶段获取特定参数
        age_phase = _get_age_phase(current_age)
        age_specific_config = m.get("age_specific_config", {})
        
        if age_phase in age_specific_config:
            phase_config = age_specific_config[age_phase]
            step_w = float(phase_config.get("weight_step", 0.12))
            step_e = float(phase_config.get("end_at_step", 0.025))
            min_w = float(phase_config.get("min_weight", 0.60))
        else:
            # 回退到默认值
            step_w = float(m.get("weight_step", 0.12))
            step_e = float(m.get("end_at_step", 0.025))
            min_w = float(m.get("min_weight", 0.60))
        
        # 3. 根据年龄差距调整权重（非线性衰减）
        diff = abs(_level_diff(cfg, current_age, target_age))
        
        # 使用非线性曲线：差距越大，衰减越快
        magnitude = _curve_magnitude("consistency", diff)
        
        # 计算最终权重
        w = base_w - magnitude * step_w
        e = base_e - magnitude * step_e
        
        # 限制范围：使用 min_weight 保证相似性
        w = max(min_w, min(1.0, w))
        e = max(0.0, min(1.0, e))
        
        logger.debug(
            f"{model}: gender={g}, current={current_age}(phase={age_phase}), target={target_age}, "
            f"step_w={step_w}, min_w={min_w}, |diff|={diff}, magnitude={magnitude}, w={w}, e={e}"
        )
        return w, e
    except Exception as e:
        logger.error(f"计算 {model} 失败: {e}")
        logger.debug(traceback.format_exc())
        # 默认回退
        if model == "pulid":
            return 1.0, 0.5
        return 1.0, 0.95


def pulid_weight(gender: str, current_age: int, target_age: int) -> Tuple[float, float]:
    return _consistency("pulid", gender, current_age, target_age)


def instantid_weight(gender: str, current_age: int, target_age: int) -> Tuple[float, float]:
    return _consistency("instantid", gender, current_age, target_age)


def all_weights(gender: str, current_age: int, target_age: int) -> Dict[str, Any]:
    w_slider = slider_weight(gender, current_age, target_age)
    w_pulid, pulid_end = pulid_weight(gender, current_age, target_age)
    w_instant, instant_end = instantid_weight(gender, current_age, target_age)
    return {
        "slider_weight": w_slider,
        "pulid_weight": w_pulid,
        "pulid_end_at": pulid_end,
        "instantid_weight": w_instant,
        "instantid_end_at": instant_end,
    }


def all_weights_from_attributes(attrs: Dict[str, Any], target_age: int) -> Dict[str, Any]:
    gender = attrs.get("gender", "male")
    current = attrs.get("age", 30)
    return all_weights(gender, int(current), int(target_age))
