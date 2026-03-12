"""图像属性提取器

提供以下能力：
1) 性别检测  2) 年龄估计  3) 表情分析  4) 肤色检测  5) 发型特征  6) 眼镜检测

功能用于辅助后续 AIGC 流程的模板/参数选择。
"""

import io
import os
import time
import base64
import requests
from typing import Any, Dict, Optional

try:
    import torch.hub as hub
except Exception:
    hub = None

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from nexus.logger import logger

# Public API
__all__ = [
    "initialize",
    "extract_image_attributes",
]

# 配置常量
MODEL_DIR = os.path.join(os.path.dirname(__file__), ".")
FACE_DET_SIZE = (640, 640)  # 修复形状不匹配错误，使用标准检测尺寸
EDGE_DENSITY_THRESHOLD = 0.1
EDGE_CONFIDENCE_SCALE = 0.2

# 全局状态管理
class _ModelState:
    """统一的模型状态管理"""
    def __init__(self):
        self.face_analyzer = None
        self.face_initialized = False
        self.glasses_detector = None
        self.glasses_cascade = None
        self.glasses_initialized = False
        
    def is_face_ready(self) -> bool:
        return self.face_initialized and self.face_analyzer is not None
        
    def is_glasses_ready(self) -> bool:
        return self.glasses_initialized

_state = _ModelState()

# 移除 _init_glasses() 函数，逻辑已合并到 initialize() 中

def _load_glasses_detector():
    """加载 glasses-detector 的 GlassesClassifier（按官方 API）"""
    try:
        # 若设置了 TORCH_HOME，则让 hub 使用该目录（hub/checkpoints 下应已有权重文件）
        torch_home = os.environ.get("TORCH_HOME")
        if hub is not None and torch_home:
            try:
                hub.set_dir(torch_home)
                logger.info(f"Torch Hub 目录已设置为: {torch_home}")
            except Exception as he:
                logger.warning(f"设置 Torch Hub 目录失败: {he}")

        # 优先使用 AnyglassesClassifier(size="medium")，不可用时回退
        try:
            from glasses_detector import AnyglassesClassifier
            classifier = AnyglassesClassifier(size="medium")
            logger.info("glasses-detector 加载成功: AnyglassesClassifier, size=medium (shufflenet_v2_x1_0)")
        except Exception:
            from glasses_detector import GlassesClassifier
            classifier = GlassesClassifier(size="medium", kind="anyglasses")
            logger.info("glasses-detector 加载成功: GlassesClassifier, size=medium, kind=anyglasses")

        # 验证可用方法
        available_methods = [m for m in dir(classifier) if not m.startswith('_') and callable(getattr(classifier, m))]
        logger.info(f"glasses-detector 可用方法: {available_methods}")
        return classifier
        
    except Exception as e:
        logger.warning(f"加载 glasses-detector 失败: {e}")
        return None

def _load_cascade():
    """加载 OpenCV 级联分类器"""
    try:
        cascade_path = cv2.data.haarcascades + 'haarcascade_eye_tree_eyeglasses.xml'
        if not os.path.exists(cascade_path):
            cascade_path = cv2.data.haarcascades + 'haarcascade_eye.xml'
        cascade = cv2.CascadeClassifier(cascade_path)
        return cascade if not (hasattr(cascade, 'empty') and cascade.empty()) else None
    except Exception:
        return None


def initialize() -> None:
    """
    初始化模块，预加载所有需要的模型和资源
    """
    if _state.face_initialized and _state.glasses_initialized:
        logger.info("所有模型已初始化，跳过重复加载")
        return

    try:
        start_time = time.time()
        logger.info("开始加载图像属性提取模型...")

        # 初始化 InsightFace
        if not _state.face_initialized:
            _state.face_analyzer = _init_face_analyzer()
            _state.face_initialized = True
            logger.info("✅ InsightFace 初始化完成")

        # 使用共享眼镜检测器
        if not _state.glasses_initialized:
            from processors import get_shared_glasses_detector, get_shared_glasses_cascade
            _state.glasses_detector = get_shared_glasses_detector()
            _state.glasses_cascade = get_shared_glasses_cascade()
            _state.glasses_initialized = True

        logger.info(f"🎉 所有模型加载完成，总耗时: {time.time() - start_time:.2f}秒")
        
    except ImportError as e:
        logger.error(f"缺少依赖: {e}")
        _state.face_initialized = False
        _state.glasses_initialized = False
        raise
    except Exception as e:
        logger.error(f"模型加载失败: {e}")
        _state.face_initialized = False
        _state.glasses_initialized = False
        raise

def _init_face_analyzer():
    """初始化 InsightFace 分析器 - 使用共享实例"""
    try:
        from processors import get_shared_face_analyzer
        analyzer = get_shared_face_analyzer()
        
        if analyzer:
            logger.info("属性提取器使用共享 InsightFace 实例")
            return analyzer
        else:
            logger.error("共享 InsightFace 实例不可用")
            return None
            
    except Exception as e:
        logger.error(f"获取共享 InsightFace 实例失败: {e}")
        return None

def _call_face_api(image_data: bytes) -> Optional[Dict[str, Any]]:
    """调用外部 API 获取人脸属性（性别、年龄）
    
    API 地址: http://10.112.64.39:9005/face/faceattribute
    参数: {"ImageBase64": "..."}
    结果: val age: Int, val sex: Int, val sex_score: Float
    """
    try:
        api_url = "http://10.112.64.39:9005/face/faceattribute"
        img_base64 = base64.b64encode(image_data).decode('utf-8')
        payload = {"ImageBase64": img_base64}
        
        # 设置超时时间
        response = requests.post(api_url, json=payload, timeout=3)
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Face API 检测结果: {result}")
            
            data = result.get("data", {})
            if not data:
                 logger.warning("Face API 返回数据为空")
                 return None
                 
            age = data.get("age", 25)
            sex = data.get("sex")
            
            # 映射性别: 假设 1=Male, 0=Female
            gender = "unknown"
            if sex == 1:
                gender = "male"
            elif sex == 0:
                gender = "female"
            
            return {
                "age": age,
                "gender": gender
            }
        else:
            logger.warning(f"Face API 返回非 200 状态码: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Face API 调用失败: {str(e)}")
        return None

def extract_image_attributes(image_data: bytes) -> Dict[str, Any]:
    """
    提取图像属性
    
    参数:
        image_data: 图像二进制数据
        
    返回:
        包含提取属性的字典，例如：
        {
            "gender": "male",
            "age": 30,
            "expression": "neutral",
            "skin_tone": "medium",
            "hair_color": "black",
            "hair_length": "short",
            "has_glasses": False,
            "has_beard": False
        }
    """
    try:
        # 使用共享实例，避免重复初始化
        if not _state.face_initialized:
            from processors import get_shared_face_analyzer
            _state.face_analyzer = get_shared_face_analyzer()
            _state.face_initialized = True
            
        if not _state.glasses_initialized:
            from processors import get_shared_glasses_detector, get_shared_glasses_cascade
            _state.glasses_detector = get_shared_glasses_detector()
            _state.glasses_cascade = get_shared_glasses_cascade()
            _state.glasses_initialized = True
            
        # 将二进制数据转换为图像
        img = _load_image(image_data)
        
        # 初始化结果字典
        attributes = {}
        
        # 先做一次人脸检测，复用主脸
        main_face = _get_main_face(img)

        # 尝试调用 API 获取性别和年龄
        api_result = _call_face_api(image_data)
        
        if api_result and api_result.get("gender") != "unknown":
            attributes["gender"] = api_result["gender"]
            attributes["age"] = api_result["age"]
            logger.info(f"使用 API 提取属性: gender={attributes['gender']}, age={attributes['age']}")
        else:
            logger.info("API 调用失败或结果无效，回退到本地模型")
            # 1. 检测性别 - 使用预加载的模型
            attributes["gender"] = _detect_gender(img, main_face)
            
            # 2. 估计年龄 - 使用预加载的模型
            attributes["age"] = _estimate_age(img, main_face)
        
        # 3. 分析表情 - 使用预加载的模型
        attributes["expression"] = _analyze_expression(img)
        
        # 4. 检测肤色
        attributes["skin_tone"] = _detect_skin_tone(img)
        
        # 5. 提取头发特征
        hair_features = _extract_hair_features(img)
        attributes.update(hair_features)
        
        # 6. 检测是否戴眼镜：优先 Python 本地模型，失败则 CV 回退；复用主脸 ROI
        gd = _detect_glasses_info(img, main_face)
        attributes.update(gd)
        
        # 7. 检测是否有胡须
        attributes["has_beard"] = _detect_beard(img)
        
        return attributes
        
    except Exception as e:
        logger.error(f"提取图像属性时发生错误: {str(e)}")
        # 处理可能的异常，返回基本属性
        return {
            "gender": "unknown",
            "age": 25,
            "expression": "neutral",
            "skin_tone": "medium",
            "hair_color": "black",
            "hair_length": "short",
            "has_glasses": False,
            "glasses_type": "no_glasses",
            "glasses_confidence": None,
            "has_beard": False,
            "error": str(e),
        }

def _get_main_face(img: np.ndarray) -> Optional[Any]:
    """获取置信度最高的人脸对象"""
    try:
        if not _state.is_face_ready():
            logger.debug("InsightFace 分析器未就绪")
            return None
        
        # 确保图像格式正确
        if img is None or img.size == 0:
            logger.debug("输入图像为空")
            return None
            
        faces = _state.face_analyzer.get(img, max_num=0)
        if not faces:
            logger.debug("未检测到任何人脸")
            return None
            
        main_face = max(faces, key=lambda x: x.det_score)
        logger.debug(f"检测到 {len(faces)} 个人脸，选择置信度最高的: {main_face.det_score:.3f}")
        return main_face
        
    except Exception as e:
        logger.debug(f"人脸检测失败: {e}")
        # 如果是形状不匹配错误，提供更详细的信息
        if "broadcast" in str(e) or "shape" in str(e):
            logger.warning(f"人脸检测形状不匹配错误，请检查 FACE_DET_SIZE 配置: {e}")
        return None

def _crop_face(img: np.ndarray, main_face: Optional[Any]) -> np.ndarray:
    """根据 InsightFace 返回的人脸对象裁剪 ROI；若不可用则返回原图。

    优先使用 `bbox` 属性，格式约为 [x1, y1, x2, y2]。坐标进行边界裁剪。
    """
    if main_face is None:
        return img
    try:
        bbox = getattr(main_face, 'bbox', None)
        if bbox is None:
            return img
        x1, y1, x2, y2 = [int(max(0, v)) for v in bbox[:4]]
        h, w = img.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w - 1, x2), min(h - 1, y2)
        if x2 <= x1 or y2 <= y1:
            return img
        return img[y1:y2, x1:x2]
    except Exception:
        return img

def _load_image(image_data: bytes) -> np.ndarray:
    """
    加载图像数据
    
    参数:
        image_data: 图像二进制数据
        
    返回:
        OpenCV 图像对象
    """
    try:
        # 使用 PIL 先读取图像，确保格式兼容性
        img = Image.open(io.BytesIO(image_data))
    except UnidentifiedImageError as e:
        raise ValueError(f"无法识别的图像数据: {e}")
    # 转换为 RGB 模式
    if img.mode != 'RGB':
        img = img.convert('RGB')
    # 转换为 OpenCV BGR 格式
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

def _detect_gender(img: np.ndarray, main_face: Optional[Any] = None) -> str:
    """
    检测图像中人物的性别
    
    参数:
        img: OpenCV 图像对象
        main_face: 可选的预检测人脸对象，避免重复检测
        
    返回:
        性别: "male" 或 "female" 或 "unknown"
    """
    try:
        if main_face is None:
            main_face = _get_main_face(img)
        if main_face is None:
            logger.warning("未检测到人脸，无法检测性别")
            return "unknown"
        return 'female' if getattr(main_face, 'gender', 1) == 0 else 'male'
    except Exception as e:
        logger.error(f"性别检测失败: {str(e)}")
        return "unknown"

def _estimate_age(img: np.ndarray, main_face: Optional[Any] = None) -> int:
    """
    估计图像中人物的年龄
    
    参数:
        img: OpenCV 图像对象
        main_face: 可选的预检测人脸对象，避免重复检测
        
    返回:
        估计的年龄
    """
    try:
        if main_face is None:
            main_face = _get_main_face(img)
        if main_face is None:
            logger.warning("未检测到人脸，使用默认年龄")
            return 25
        return int(getattr(main_face, 'age', 25))
    except Exception as e:
        logger.error(f"年龄估计失败: {str(e)}")
        return 25  # 默认中年

def _analyze_expression(img: np.ndarray) -> str:
    """
    分析图像中人物的表情
    
    参数:
        img: OpenCV 图像对象
        
    返回:
        表情类型: "happy", "sad", "angry", "surprised", "neutral" 等
    """
    # TODO: 实现实际的表情分析算法
    # 可以使用 FER2013 训练的模型或其他表情识别模型
    return "neutral"  # 默认返回中性表情

def _detect_skin_tone(img: np.ndarray) -> str:
    """
    检测图像中人物的肤色
    
    参数:
        img: OpenCV 图像对象
        
    返回:
        肤色类型: "fair", "medium", "dark" 等
    """
    # TODO: 实现基于HSV色彩空间的肤色检测算法
    # 可以使用人脸区域的平均色值进行分类
    return "medium"  # 默认返回中等肤色

def _extract_hair_features(img: np.ndarray) -> Dict[str, Any]:
    """
    提取图像中人物的头发特征
    
    参数:
        img: OpenCV 图像对象
        
    返回:
        头发特征字典，包含颜色和长度
    """
    # TODO: 实现头发区域分割和特征提取
    # 可以使用语义分割模型识别头发区域，然后分析颜色和长度
    return {
        "hair_color": "black",
        "hair_length": "short"
    }

def _detect_glasses(img: np.ndarray) -> bool:
    """兼容旧接口：仅返回是否戴眼镜"""
    return _detect_glasses_info(img).get("has_glasses", False)

def _detect_glasses_with_python(img: np.ndarray, main_face: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """使用 glasses-detector 包进行眼镜检测（按官方 API）"""
    if _state.glasses_detector is None:
        logger.debug("glasses-detector 未加载，跳过")
        return None
        
    try:
        roi = _crop_face(img, main_face)
        if roi is None or roi.size == 0:
            logger.debug("ROI 为空，无法检测")
            return None
        
        # 转换为 PIL Image
        from PIL import Image
        pil_img = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
        logger.debug(f"转换 ROI 为 PIL 图像，尺寸: {pil_img.size}")
        
        # 按官方文档，尝试不同的推理方法
        result = None
        
        # 方法1: 尝试 process_dir 的单图版本
        if hasattr(_state.glasses_detector, 'process'):
            try:
                result = _state.glasses_detector.process(pil_img)
                logger.debug(f"process() 返回: {result}")
            except Exception as e:
                logger.debug(f"process() 调用失败: {e}")
        
        # 方法2: 尝试直接调用模型
        if result is None and hasattr(_state.glasses_detector, '__call__'):
            try:
                result = _state.glasses_detector(pil_img)
                logger.debug(f"__call__() 返回: {result}")
            except Exception as e:
                logger.debug(f"__call__() 调用失败: {e}")
        
        # 方法3: 尝试 predict 方法
        if result is None and hasattr(_state.glasses_detector, 'predict'):
            try:
                result = _state.glasses_detector.predict(pil_img)
                logger.debug(f"predict() 返回: {result}")
            except Exception as e:
                logger.debug(f"predict() 调用失败: {e}")
        
        if result is not None:
            parsed_result = _parse_glasses_result(result)
            if parsed_result is not None:
                logger.debug(f"检测成功: {parsed_result}")
                return parsed_result
        
        logger.debug("所有推理方法均失败")
            
    except Exception as e:
        logger.warning(f"glasses-detector 检测异常: {e}")
    
    return None

def _parse_glasses_result(result) -> Optional[Dict[str, Any]]:
    """解析眼镜检测结果"""
    try:
        # 处理字典格式返回值
        if isinstance(result, dict):
            label = str(result.get("class") or result.get("label") or result.get("type") or "").lower()
            conf = result.get("confidence") or result.get("score") or result.get("prob")
            conf = float(conf) if conf is not None else None
            has_glasses = label in ("eyeglasses", "sunglasses", "glasses", "present")
            return _normalize_glasses_result(has_glasses, label, conf)
        
        # 处理字符串格式返回值（glasses-detector 包的实际返回格式）
        elif isinstance(result, str):
            result_str = result.lower().strip()
            logger.debug(f"解析字符串结果: '{result_str}'")
            
            # glasses-detector 包返回 'present' 表示有眼镜，'absent' 表示无眼镜
            if result_str == "present":
                return _normalize_glasses_result(True, "eyeglasses", None)
            elif result_str == "absent":
                return _normalize_glasses_result(False, "no_glasses", None)
            elif result_str in ("eyeglasses", "sunglasses", "glasses"):
                return _normalize_glasses_result(True, result_str, None)
            elif result_str in ("no_glasses", "none", "no"):
                return _normalize_glasses_result(False, "no_glasses", None)
        
        # 处理列表/元组格式
        elif isinstance(result, (list, tuple)) and len(result) >= 1:
            label = str(result[0]).lower()
            score = float(result[1]) if len(result) > 1 else None
            has_glasses = label in ("eyeglasses", "sunglasses", "glasses", "present")
            return _normalize_glasses_result(has_glasses, label, score)
        
        # 处理布尔值
        elif isinstance(result, bool):
            glasses_type = "eyeglasses" if result else "no_glasses"
            return _normalize_glasses_result(result, glasses_type, None)
            
    except Exception as e:
        logger.debug(f"结果解析异常: {e}")
    
    return None

def _detect_glasses_with_opencv(img: np.ndarray) -> Dict[str, Any]:
    """使用 OpenCV 启发式检测眼镜"""
    try:
        if _state.glasses_cascade is None:
            return _normalize_glasses_result(False, "no_glasses", None)
            
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        eyes = _state.glasses_cascade.detectMultiScale(gray, 1.3, 5)
        
        has_glasses = False
        best_conf = 0.0
        
        for (x, y, w, h) in eyes[:2]:  # 只检查前两个眼部区域
            roi = gray[y:y + h, x:x + w]
            edges = cv2.Canny(roi, 30, 100)
            edge_density = float(np.sum(edges > 0)) / max(1.0, float(w * h))
            
            if edge_density > EDGE_DENSITY_THRESHOLD:
                has_glasses = True
                confidence = min(1.0, (edge_density - EDGE_DENSITY_THRESHOLD) / EDGE_CONFIDENCE_SCALE)
                best_conf = max(best_conf, confidence)
        
        glasses_type = "eyeglasses" if has_glasses else "no_glasses"
        confidence = best_conf if has_glasses else None
        
        return _normalize_glasses_result(has_glasses, glasses_type, confidence)
        
    except Exception as e:
        logger.debug(f"OpenCV 眼镜检测失败: {e}")
        return _normalize_glasses_result(False, "no_glasses", None)

def _normalize_glasses_result(has_glasses: bool, type_value: Optional[str], confidence: Optional[float]) -> Dict[str, Any]:
    """将眼镜检测结果规范化为统一字段。"""
    t = (type_value or "").lower() if isinstance(type_value, str) else None
    if not has_glasses:
        t = "no_glasses"
        confidence = None  # 对于无眼镜的情况，统一为 None
    else:
        t = t or "eyeglasses"
        confidence = None if confidence is None else float(confidence)
    return {
        "has_glasses": bool(has_glasses),
        "glasses_type": t,
        "glasses_confidence": confidence,
    }

def _detect_glasses_info(img: np.ndarray, main_face: Optional[Any] = None) -> Dict[str, Any]:
    """检测眼镜信息，优先使用 glasses-detector 包，失败时回退到 OpenCV"""
    if not _state.glasses_initialized:
        logger.warning("眼镜检测器未初始化，请先调用 initialize()")
        return _normalize_glasses_result(False, "no_glasses", None)
    
    # 方法1: 优先使用 glasses-detector 包
    logger.debug("尝试使用 glasses-detector 包进行眼镜检测")
    result = _detect_glasses_with_python(img, main_face)
    if result is not None:
        logger.info(f"glasses-detector 包检测完成: {result['has_glasses']}")
        return result
    
    # 方法2: 回退到 OpenCV 检测
    logger.info("glasses-detector 包不可用，回退到 OpenCV 检测")
    roi = _crop_face(img, main_face)
    opencv_result = _detect_glasses_with_opencv(roi)
    logger.info(f"OpenCV 检测完成: {opencv_result['has_glasses']}")
    return opencv_result

def _detect_beard(img: np.ndarray) -> bool:
    """
    检测图像中人物是否有胡须
    
    参数:
        img: OpenCV 图像对象
        
    返回:
        是否有胡须
    """
    # TODO: 实现胡须检测算法
    # 可以使用面部关键点检测，分析下巴和嘴部区域的纹理特征
    return False  # 默认返回没有胡须
