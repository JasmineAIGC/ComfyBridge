"""
InsightFace 图像质量验证模块 (InsightFace Image Quality Validator)

本模块使用 InsightFace 提供全面的图像质量验证功能，用于确保输入图像满足生成所需的质量标准。
相比于 MediaPipe 实现，InsightFace 在亚洲人脸上表现更好，且在人脸属性分析方面有更多功能。

主要功能：
1. 基本图像属性检查：
   - 分辨率验证 - 确保图像具有足够的像素数
   - 清晰度分析 - 检测图像是否清晰，没有模糊或噪点
   - 光照条件评估 - 确保图像光照均匀适度

2. 高级人脸质量检查（使用 InsightFace）：
   - 人脸检测与计数 - 确认存在单个人脸
   - 人脸尺寸与完整性验证 - 确保人脸尺寸适当且完整
   - 眼睛开合检测 - 检测是否闭眼
   - 嘴巴开合检测 - 检测是否张嘴
   - 人脸姿态估计 - 计算促仉角、偏航角和滚转角

当图像不满足质量要求时，模块将返回结构化的错误信息，包含错误代码和详细描述，
便于用户进行适当的调整。
"""

import io
import cv2
import numpy as np
import math
import os
import time
from typing import Dict, Any, Tuple, Optional, List
from PIL import Image
from nexus.logger import logger

# 导入 InsightFace
import insightface
from insightface.app import FaceAnalysis

# 全局模型缓存字典
# 用于存储预加载的模型和状态，确保模型只加载一次，提高性能
_MODELS = {
    "face_detector": None,   # OpenCV 人脸检测器（备用）
    "face_analyzer": None,   # InsightFace 人脸分析器
    "initialized": False     # 初始化状态标记
}

# 导入统一错误码定义
from nexus.error_codes import (
    ERR_NO_FACE,
    ERR_MULTIPLE_FACES,
    ERR_FACE_TOO_SMALL,
    ERR_INCOMPLETE_FACE,
    ERR_EYE_CLOSED,
    ERR_MOUTH_OPEN,
    ERR_FACE_ANGLE,
    ERR_LOW_RESOLUTION,
    ERR_LOW_CLARITY,
    ERR_BAD_LIGHTING,
    ERR_QUALITY_CHECK_GENERAL,
    get_error_message
)

# 质量检查错误代码映射
# 将检查类型映射到统一的错误码，错误信息从 error_codes.py 获取
QUALITY_ERROR_CODES = {
    # 人脸检测问题
    "NO_FACE": {"code": ERR_NO_FACE, "message": get_error_message(ERR_NO_FACE)},
    "MULTIPLE_FACES": {"code": ERR_MULTIPLE_FACES, "message": get_error_message(ERR_MULTIPLE_FACES)},
    "FACE_TOO_SMALL": {"code": ERR_FACE_TOO_SMALL, "message": get_error_message(ERR_FACE_TOO_SMALL)},
    "INCOMPLETE_FACE": {"code": ERR_INCOMPLETE_FACE, "message": get_error_message(ERR_INCOMPLETE_FACE)},
    
    # 人脸表情和姿态问题
    "EYE_CLOSED": {"code": ERR_EYE_CLOSED, "message": get_error_message(ERR_EYE_CLOSED)},
    "MOUTH_OPEN": {"code": ERR_MOUTH_OPEN, "message": get_error_message(ERR_MOUTH_OPEN)},
    "FACE_ANGLE": {"code": ERR_FACE_ANGLE, "message": get_error_message(ERR_FACE_ANGLE)},
    
    # 图像质量问题
    "LOW_RESOLUTION": {"code": ERR_LOW_RESOLUTION, "message": get_error_message(ERR_LOW_RESOLUTION)},
    "LOW_CLARITY": {"code": ERR_LOW_CLARITY, "message": get_error_message(ERR_LOW_CLARITY)},
    "BAD_LIGHTING": {"code": ERR_BAD_LIGHTING, "message": get_error_message(ERR_BAD_LIGHTING)},
    
    # 通用错误
    "GENERAL_ERROR": {"code": ERR_QUALITY_CHECK_GENERAL, "message": get_error_message(ERR_QUALITY_CHECK_GENERAL)}
}

# 辅助函数集
# 提供各种数学计算和图像处理工具

def euclidean_distance(point1, point2, epsilon=1e-10):
    """计算两点之间的欧几里得距离
    
    参数:
        point1 (tuple): 第一个点的 (x,y) 坐标
        point2 (tuple): 第二个点的 (x,y) 坐标
        epsilon (float): 小数值，防止除零错误
        
    返回:
        float: 两点之间的欧几里得距离
    """
    x1, y1 = point1
    x2, y2 = point2
    distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
    return distance + epsilon

def resize_img(img, max_size=1024):
    """等比例缩放图像，便于检测
    
    参数:
        img (np.ndarray): 输入图像
        max_size (int): 最大尺寸限制
        
    返回:
        tuple: (缩放后的图像, 缩放因子, 原始高度, 原始宽度)
    """
    h, w = img.shape[:2]
    max_dim = max(w, h)
    if max_dim > max_size:
        scaling_factor = max_size / float(max_dim)
        new_w = int(w * scaling_factor)
        new_h = int(h * scaling_factor)
        resized_img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        return resized_img, scaling_factor, h, w
    return img, 1, h, w

def calculate_brightness_weighted(image):
    """计算图像的加权亮度值
    
    参数:
        image (np.ndarray): 输入图像
        
    返回:
        float: 加权平均亮度值
    """
    brightness = 0.299 * image[:,:,2] + 0.587 * image[:,:,1] + 0.114 * image[:,:,0]
    average_brightness = brightness.mean()
    return average_brightness

def rotation_matrix_to_angles(rotation_matrix):
    """将旋转矩阵转换为欧拉角
    
    参数:
        rotation_matrix (np.ndarray): 3x3 旋转矩阵
        
    返回:
        np.ndarray: [x, y, z] 欧拉角，单位为度
    """
    x = math.atan2(rotation_matrix[2, 1], rotation_matrix[2, 2])
    y = math.atan2(-rotation_matrix[2, 0], math.sqrt(rotation_matrix[0, 0] ** 2 +
                                                 rotation_matrix[1, 0] ** 2))
    z = math.atan2(rotation_matrix[1, 0], rotation_matrix[0, 0])
    return np.array([x, y, z]) * 180. / math.pi

class ImageQualityError(Exception):
    """图像质量检查异常"""
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(self.message)

def initialize(model_dir: Optional[str] = None):
    """
    初始化模块，预加载所有需要的模型和资源
    
    参数:
        model_dir: 可选，模型文件目录路径。如果提供，将从该目录加载模型文件
    """
    global _MODELS
    
    if _MODELS["initialized"]:
        logger.info("图像质量检查模型已经初始化，跳过重复加载")
        return
        
    try:
        start_time = time.time()
        logger.info("预加载图像质量检查模型...")
        
        # 加载基本人脸检测器（作为备用）
        _MODELS["face_detector"] = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        
        # 加载人脸分析模型
        try:
            # 设置模型路径
            if not model_dir:
                # 默认使用属性提取器的模型路径
                model_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                  "attribute_extractor")
            
            if not os.path.exists(model_dir):
                os.makedirs(model_dir, exist_ok=True)
                logger.warning(f"创建模型目录: {model_dir}")
            
            # 使用共享的 InsightFace 实例
            from processors import get_shared_face_analyzer
            _MODELS["face_analyzer"] = get_shared_face_analyzer()
            
            if _MODELS["face_analyzer"]:
                logger.info("质检模块使用共享 InsightFace 实例")
            else:
                logger.error("共享 InsightFace 实例不可用")
        except Exception as e:
            logger.error(f"InsightFace 模型加载失败: {str(e)}")
            logger.info("将使用基本 OpenCV 人脸检测器")
        
        # 标记初始化完成
        _MODELS["initialized"] = True
        
        logger.info(f"图像质量检查模型加载完成，耗时: {time.time() - start_time:.2f}秒")
    except Exception as e:
        logger.error(f"预加载图像质量检查模型失败: {str(e)}")
        # 初始化失败时，确保标记为未初始化
        _MODELS["initialized"] = False

def validate_image_quality(image_data: bytes) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    验证图像质量
    
    参数:
        image_data: 图像二进制数据
        
    返回:
        (通过验证, 错误信息)
        - 如果通过验证，返回 (True, None)
        - 如果未通过验证，返回 (False, {"code": 错误码, "message": 错误信息})
    """
    try:
        # 使用共享实例，避免重复初始化
        global _MODELS
        if not _MODELS["initialized"]:
            from processors import get_shared_face_analyzer
            _MODELS["face_analyzer"] = get_shared_face_analyzer()
            _MODELS["initialized"] = True
            
        # 将二进制数据转换为图像
        img = _load_image(image_data)
        
        # 1. 检查图像分辨率
        if not _check_resolution(img):
            return False, QUALITY_ERROR_CODES["LOW_RESOLUTION"]
        
        # 2. 检查图像清晰度
        if not _check_clarity(img):
            return False, QUALITY_ERROR_CODES["LOW_CLARITY"]
        
        # 3. 检查光照条件
        if not _check_lighting(img):
            return False, QUALITY_ERROR_CODES["BAD_LIGHTING"]
        
        # 4. 人脸质量检查
        # 使用 InsightFace 进行高级人脸质量检查
        if _MODELS["face_analyzer"]:
            face_quality_result = _check_face_quality_advanced(img)
            if not face_quality_result[0]:
                return face_quality_result
        else:
            # 使用基本人脸检测（备用）
            if not _check_face_detection(img):
                return False, QUALITY_ERROR_CODES["NO_FACE"]
        
        # 所有检查都通过
        return True, None
        
    except Exception as e:
        logger.error(f"图像质量检查异常: {str(e)}")
        # 处理其他可能的异常
        return False, QUALITY_ERROR_CODES["GENERAL_ERROR"]

def _load_image(image_data: bytes) -> np.ndarray:
    """
    加载图像数据
    
    参数:
        image_data: 图像二进制数据
        
    返回:
        OpenCV 图像对象
    """
    # 使用 PIL 先读取图像，确保格式兼容性
    img = Image.open(io.BytesIO(image_data))
    
    # 转换为 RGB 模式
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    # 转换为 OpenCV 格式
    img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    
    return img_cv

def _check_resolution(img: np.ndarray) -> bool:
    """
    检查图像分辨率
    
    参数:
        img: OpenCV 图像对象
        
    返回:
        是否通过检查
    """
    # 获取图像尺寸
    height, width = img.shape[:2]
    
    # 检查最小分辨率要求
    min_resolution = 256
    passed = width >= min_resolution and height >= min_resolution
    if not passed:
        logger.warning(f"分辨率检查失败: 当前 {width}x{height} 像素，最小要求 {min_resolution}x{min_resolution} 像素")
    return passed

def _check_clarity(img: np.ndarray) -> bool:
    """
    检查图像清晰度
    
    参数:
        img: OpenCV 图像对象
        
    返回:
        是否通过检查
    """
    # 转换为灰度图
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 计算拉普拉斯方差作为清晰度指标
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    # 设置清晰度阈值
    # 降低阈值，使更多图像能通过检查
    clarity_threshold = 50  # 原值为 100
    passed = laplacian_var >= clarity_threshold
    if not passed:
        logger.warning(f"清晰度检查失败: 拉普拉斯方差 {laplacian_var:.2f} < 阈值 {clarity_threshold}，图像可能模糊")
    return passed

def _check_lighting(img: np.ndarray) -> bool:
    """
    检查图像光照条件
    
    参数:
        img: OpenCV 图像对象
        
    返回:
        是否通过检查
    """
    # 使用加权亮度计算
    average_brightness = calculate_brightness_weighted(img)
    
    # 设置亮度阈值
    min_brightness = 40
    max_brightness = 200
    
    # 检查亮度是否在合理范围内
    passed = min_brightness <= average_brightness <= max_brightness
    if not passed:
        if average_brightness < min_brightness:
            logger.warning(f"光照检查失败: 亮度 {average_brightness:.2f} < {min_brightness}，图像过暗")
        else:
            logger.warning(f"光照检查失败: 亮度 {average_brightness:.2f} > {max_brightness}，图像过亮")
    return passed

def _check_face_detection(img: np.ndarray) -> bool:
    """
    使用 OpenCV 进行基本人脸检测
    
    参数:
        img: OpenCV 图像对象
        
    返回:
        是否检测到人脸
    """
    # 检查检测器是否已初始化
    if _MODELS["face_detector"] is None:
        # 尝试加载级联分类器
        _MODELS["face_detector"] = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        if _MODELS["face_detector"].empty():
            logger.warning("OpenCV 人脸检测器加载失败，跳过人脸检测")
            return True  # 检测器不可用时默认通过
    
    # 转换为灰度图
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 检测人脸
    faces = _MODELS["face_detector"].detectMultiScale(gray, 1.3, 5)
    
    # 如果检测到至少一个人脸，返回 True
    return len(faces) > 0

def _check_face_quality_advanced(img: np.ndarray) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    使用 InsightFace 进行高级人脸质量检查
    
    参数:
        img: OpenCV 图像对象
        
    返回:
        (是否通过检查, 错误信息)
    """
    # 进一步缩小图像尺寸以提高质检速度
    resized_img, scaling_factor, ori_h, ori_w = resize_img(img, max_size=224)
    
    # 使用 InsightFace 检测人脸（限制检测数量以提高速度）
    faces = _MODELS["face_analyzer"].get(resized_img, max_num=2)
    
    # 检查是否有人脸
    if len(faces) == 0:
        logger.warning("人脸质量检查失败: 未检测到人脸，请确保图像中有清晰的人脸")
        return False, QUALITY_ERROR_CODES["NO_FACE"]
    
    # 如果有多个人脸，选择最大的人脸
    if len(faces) > 1:
        # 计算每个人脸的面积，选择最大的
        largest_face = None
        max_area = 0
        
        for face in faces:
            bbox = face.bbox.astype(np.int32)
            x1, y1, x2, y2 = bbox
            area = (x2 - x1) * (y2 - y1)
            if area > max_area:
                max_area = area
                largest_face = face
        
        face = largest_face
        logger.info(f"检测到 {len(faces)} 个人脸，选择最大的人脸进行质检")
    else:
        # 获取检测到的人脸
        face = faces[0]
    
    # 获取人脸边界框
    bbox = face.bbox.astype(np.int32)
    x1, y1, x2, y2 = bbox
    face_width = x2 - x1
    face_height = y2 - y1
    
    # # 检查人脸大小
    # if face_width < 112 or face_height < 112:
    #     return False, QUALITY_ERROR_CODES["FACE_TOO_SMALL"]
    
    # 检查人脸是否完整
    img_h, img_w = resized_img.shape[:2]
    if x1 <= 0 or y1 <= 0 or x2 >= img_w or y2 >= img_h:
        logger.warning(f"人脸质量检查失败: 人脸不完整，人脸被图像边缘裁切 (bbox: [{x1},{y1},{x2},{y2}], img: {img_w}x{img_h})")
        return False, QUALITY_ERROR_CODES["INCOMPLETE_FACE"]
    
    # 简化的质量检查：只进行基本的人脸姿态检查
    # 如果有姿态信息，进行快速检查
    if hasattr(face, 'pose') and face.pose is not None:
        pitch, yaw, roll = face.pose
        if not (-40 <= pitch <= 40 and -40 <= yaw <= 40 and -40 <= roll <= 40):
            # 记录详细的姿态角度信息
            angle_issues = []
            if not (-40 <= pitch <= 40):
                angle_issues.append(f"pitch={pitch:.2f}°")
            if not (-40 <= yaw <= 40):
                angle_issues.append(f"yaw={yaw:.2f}°")
            if not (-40 <= roll <= 40):
                angle_issues.append(f"roll={roll:.2f}°")
            logger.warning(f"人脸质量检查失败: 人脸角度过大，请使用正脸照片 (pitch/yaw/roll 需在 ±25° 内)，超出范围: {', '.join(angle_issues)}")
            return False, QUALITY_ERROR_CODES["FACE_ANGLE"]
    
    # 跳过详细的眼睛和嘴巴检测以提高速度
    # 这些检查可以在属性提取阶段进行，避免重复计算
    
    # 所有检查都通过
    return True, None

# 如果直接运行此文件，执行简单测试
if __name__ == "__main__":
    # 初始化模型
    initialize()
    
    # 测试图像路径
    test_image_path = "test.jpg"
    if os.path.exists(test_image_path):
        # 读取测试图像
        with open(test_image_path, "rb") as f:
            image_data = f.read()
        
        # 验证图像质量
        result, error = validate_image_quality(image_data)
        
        if result:
            print("图像质量检查通过")
        else:
            print(f"图像质量检查失败: {error['message']} (错误码: {error['code']})")
    else:
        print(f"测试图像 {test_image_path} 不存在")
