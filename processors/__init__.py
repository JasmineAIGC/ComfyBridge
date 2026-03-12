"""ComfyBridge 图像处理工具集。

提供 AIGC 流程所需的图像分析和处理工具，采用共享模型实例设计以优化内存使用。

子模块:
    quality_check: 图像质量验证（分辨率、清晰度、人脸检测）
    attribute_extractor: 图像属性提取（性别、年龄、表情）
    prompt_templates: 提示词和权重模板选择
    image_utils: 图像合成和 AI 标记工具

共享资源:
    InsightFace: 人脸分析模型（CPU 模式）
    GlassesDetector: 眼镜检测模型

Functions:
    preload_all: 预加载所有模型
    get_shared_face_analyzer: 获取共享的人脸分析器
    get_shared_glasses_detector: 获取共享的眼镜检测器
"""

import time
import os
try:
    import torch.hub as hub
except Exception:
    hub = None
from nexus.logger import logger
from processors.prompt_templates import init_prompt_templates, init_weight_templates

# 共享的模型实例
_shared_face_analyzer = None
_shared_glasses_detector = None
_shared_glasses_cascade = None
_shared_initialized = False

def _init_shared_models():
    """初始化所有共享模型实例"""
    global _shared_face_analyzer, _shared_glasses_detector, _shared_glasses_cascade, _shared_initialized
    
    if _shared_initialized:
        return
    
    try:
        logger.info("开始初始化共享模型实例...")
        
        # 1. 初始化 InsightFace
        from insightface.app import FaceAnalysis
        model_dir = os.path.join(os.path.dirname(__file__), "attribute_extractor")
        
        logger.info("初始化共享 InsightFace 实例（CPU 模式）")
        analyzer = FaceAnalysis(
            name='buffalo_l',
            root=model_dir,
            providers=['CPUExecutionProvider'],  # 强制使用 CPU
            download=False
        )
        analyzer.prepare(ctx_id=0, det_size=(640, 640))
        _shared_face_analyzer = analyzer
        logger.info("共享 InsightFace 实例初始化完成")
        
        # 2. 初始化眼镜检测器
        logger.info("初始化共享眼镜检测器...")
        _shared_glasses_detector = _load_glasses_detector()
        _shared_glasses_cascade = _load_glasses_cascade()
        logger.info(f"共享眼镜检测器初始化完成: detector={_shared_glasses_detector is not None}, cascade={_shared_glasses_cascade is not None}")
        
        _shared_initialized = True
        logger.info("所有共享模型初始化完成")
        
    except Exception as e:
        logger.error(f"共享模型初始化失败: {e}")
        _shared_initialized = True  # 标记为已尝试，避免重复失败

def _load_glasses_detector():
    """加载 glasses-detector，优先使用本地 shufflenet_v2_x1_0 权重"""
    try:
        # 若提供了 TORCH_HOME，则让 hub 使用该目录（hub/checkpoints 下应已有权重）
        torch_home = os.environ.get("TORCH_HOME")
        if hub is not None and torch_home:
            try:
                hub.set_dir(torch_home)
                logger.info(f"Torch Hub 目录已设置为: {torch_home}")
            except Exception as he:
                logger.warning(f"设置 Torch Hub 目录失败: {he}")

        # 优先使用 AnyglassesClassifier(size="medium")，不可用时回退到 GlassesClassifier
        try:
            from glasses_detector import AnyglassesClassifier
            classifier = AnyglassesClassifier(size="medium")
            logger.info("glasses-detector 加载成功: AnyglassesClassifier, size=medium (shufflenet_v2_x1_0)")
        except Exception:
            from glasses_detector import GlassesClassifier
            classifier = GlassesClassifier(size="medium", kind="anyglasses")
            logger.info("glasses-detector 加载成功: GlassesClassifier, size=medium, kind=anyglasses")

        return classifier
    except Exception as e:
        logger.warning(f"加载 glasses-detector 失败: {e}")
        return None

def _load_glasses_cascade():
    """加载 OpenCV 眼镜级联分类器"""
    try:
        import cv2
        cascade_path = cv2.data.haarcascades + 'haarcascade_eye_tree_eyeglasses.xml'
        if not os.path.exists(cascade_path):
            cascade_path = cv2.data.haarcascades + 'haarcascade_eye.xml'
        cascade = cv2.CascadeClassifier(cascade_path)
        logger.info("OpenCV 眼镜级联分类器加载成功")
        return cascade
    except Exception as e:
        logger.warning(f"加载 OpenCV 眼镜级联失败: {e}")
        return None

def get_shared_face_analyzer():
    """获取共享的 InsightFace 实例"""
    if not _shared_initialized:
        _init_shared_models()
    return _shared_face_analyzer

def get_shared_glasses_detector():
    """获取共享的眼镜检测器实例"""
    if not _shared_initialized:
        _init_shared_models()
    return _shared_glasses_detector

def get_shared_glasses_cascade():
    """获取共享的 OpenCV 眼镜级联分类器"""
    if not _shared_initialized:
        _init_shared_models()
    return _shared_glasses_cascade

# 导入模块时使用共享实例
from processors.quality_check.validator import validate_image_quality
from processors.attribute_extractor.extractor import extract_image_attributes
from processors.image_utils import img_composite_bytes, add_ai_metadata_fast, verify_ai_metadata

__all__ = [
    'validate_image_quality', 
    'extract_image_attributes', 
    'initialize_tools', 
    'get_shared_face_analyzer',
    'img_composite_bytes',
    'add_ai_metadata_fast',
    'verify_ai_metadata',
]

def initialize_tools():
    """初始化所有处理器工具。
    
    应在应用启动时调用，预加载模型和模板以加快首次请求响应。
    """
    start_time = time.time()
    logger.info("处理器工具集预加载开始...")

    # 初始化共享模型实例
    _init_shared_models()

    # 预加载提示词模板
    init_prompt_templates()
    init_weight_templates()

    logger.info(f"处理器工具集预加载完成，耗时: {time.time() - start_time:.2f}秒")
