#!/usr/bin/env python3
"""
图像质量检查测试脚本

用法:
    python test_quality_check.py <图片路径>
    python test_quality_check.py test.jpg
    python test_quality_check.py /path/to/image.png

输出:
    - 检查结果（通过/失败）
    - 详细的检查项目和数值
    - 如果失败，显示具体原因
"""

import sys
import os
import io
import cv2
import numpy as np
import math
from PIL import Image
from typing import Dict, Any, Tuple, Optional

# ==================== 错误码定义 ====================
ERR_NO_FACE = 1001
ERR_MULTIPLE_FACES = 1002
ERR_FACE_TOO_SMALL = 1003
ERR_INCOMPLETE_FACE = 1004
ERR_EYE_CLOSED = 1005
ERR_MOUTH_OPEN = 1006
ERR_FACE_ANGLE = 1007
ERR_LOW_RESOLUTION = 1008
ERR_LOW_CLARITY = 1009
ERR_BAD_LIGHTING = 1010
ERR_QUALITY_CHECK_GENERAL = 1099

ERROR_MESSAGES = {
    ERR_NO_FACE: "未检测到人脸",
    ERR_MULTIPLE_FACES: "检测到多张脸",
    ERR_FACE_TOO_SMALL: "人脸过小",
    ERR_INCOMPLETE_FACE: "人脸不完整",
    ERR_EYE_CLOSED: "检测到闭眼",
    ERR_MOUTH_OPEN: "检测到张嘴",
    ERR_FACE_ANGLE: "人脸角度不正",
    ERR_LOW_RESOLUTION: "分辨率过低",
    ERR_LOW_CLARITY: "图像不清晰",
    ERR_BAD_LIGHTING: "光照不佳",
    ERR_QUALITY_CHECK_GENERAL: "质量检查失败",
}

def get_error_message(code: int) -> str:
    return ERROR_MESSAGES.get(code, "未知错误")

QUALITY_ERROR_CODES = {
    "NO_FACE": {"code": ERR_NO_FACE, "message": get_error_message(ERR_NO_FACE)},
    "MULTIPLE_FACES": {"code": ERR_MULTIPLE_FACES, "message": get_error_message(ERR_MULTIPLE_FACES)},
    "FACE_TOO_SMALL": {"code": ERR_FACE_TOO_SMALL, "message": get_error_message(ERR_FACE_TOO_SMALL)},
    "INCOMPLETE_FACE": {"code": ERR_INCOMPLETE_FACE, "message": get_error_message(ERR_INCOMPLETE_FACE)},
    "EYE_CLOSED": {"code": ERR_EYE_CLOSED, "message": get_error_message(ERR_EYE_CLOSED)},
    "MOUTH_OPEN": {"code": ERR_MOUTH_OPEN, "message": get_error_message(ERR_MOUTH_OPEN)},
    "FACE_ANGLE": {"code": ERR_FACE_ANGLE, "message": get_error_message(ERR_FACE_ANGLE)},
    "LOW_RESOLUTION": {"code": ERR_LOW_RESOLUTION, "message": get_error_message(ERR_LOW_RESOLUTION)},
    "LOW_CLARITY": {"code": ERR_LOW_CLARITY, "message": get_error_message(ERR_LOW_CLARITY)},
    "BAD_LIGHTING": {"code": ERR_BAD_LIGHTING, "message": get_error_message(ERR_BAD_LIGHTING)},
    "GENERAL_ERROR": {"code": ERR_QUALITY_CHECK_GENERAL, "message": get_error_message(ERR_QUALITY_CHECK_GENERAL)}
}

# ==================== 辅助函数 ====================

def euclidean_distance(point1, point2, epsilon=1e-10):
    """计算两点之间的欧几里得距离"""
    x1, y1 = point1
    x2, y2 = point2
    distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
    return distance + epsilon

def resize_img(img, max_size=1024):
    """等比例缩放图像"""
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
    """计算图像的加权亮度值"""
    brightness = 0.299 * image[:,:,2] + 0.587 * image[:,:,1] + 0.114 * image[:,:,0]
    average_brightness = brightness.mean()
    return average_brightness

# ==================== 全局模型缓存 ====================
_MODELS = {
    "face_detector": None,
    "face_analyzer": None,
    "initialized": False
}

def initialize():
    """初始化模型"""
    global _MODELS
    
    if _MODELS["initialized"]:
        return
    
    print("正在加载模型...")
    
    # 加载 OpenCV 人脸检测器（备用）
    _MODELS["face_detector"] = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    )
    
    # 加载 InsightFace
    try:
        import insightface
        from insightface.app import FaceAnalysis
        
        face_analyzer = FaceAnalysis(
            name='buffalo_l',
            providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
        )
        face_analyzer.prepare(ctx_id=0, det_size=(640, 640))
        _MODELS["face_analyzer"] = face_analyzer
        print("✓ InsightFace 模型加载成功")
    except Exception as e:
        print(f"✗ InsightFace 加载失败: {e}")
        print("  将使用 OpenCV 基础人脸检测")
    
    _MODELS["initialized"] = True
    print("模型加载完成\n")

# ==================== 检查函数 ====================

def _load_image(image_data: bytes) -> np.ndarray:
    """加载图像数据"""
    img = Image.open(io.BytesIO(image_data))
    if img.mode != 'RGB':
        img = img.convert('RGB')
    img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    return img_cv

def _check_resolution(img: np.ndarray) -> Tuple[bool, dict]:
    """检查图像分辨率"""
    height, width = img.shape[:2]
    min_resolution = 256
    passed = width >= min_resolution and height >= min_resolution
    return passed, {
        "width": width,
        "height": height,
        "min_required": min_resolution,
        "passed": passed
    }

def _check_clarity(img: np.ndarray) -> Tuple[bool, dict]:
    """检查图像清晰度"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    clarity_threshold = 50
    passed = laplacian_var >= clarity_threshold
    return passed, {
        "laplacian_variance": round(laplacian_var, 2),
        "threshold": clarity_threshold,
        "passed": passed
    }

def _check_lighting(img: np.ndarray) -> Tuple[bool, dict]:
    """检查图像光照条件"""
    average_brightness = calculate_brightness_weighted(img)
    min_brightness = 40
    max_brightness = 200
    passed = min_brightness <= average_brightness <= max_brightness
    return passed, {
        "brightness": round(average_brightness, 2),
        "min_threshold": min_brightness,
        "max_threshold": max_brightness,
        "passed": passed
    }

def _check_face_detection(img: np.ndarray) -> Tuple[bool, dict]:
    """使用 OpenCV 进行基本人脸检测"""
    if _MODELS["face_detector"] is None or _MODELS["face_detector"].empty():
        return True, {"message": "检测器不可用，跳过检查", "passed": True}
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = _MODELS["face_detector"].detectMultiScale(gray, 1.3, 5)
    passed = len(faces) > 0
    return passed, {
        "face_count": len(faces),
        "passed": passed
    }

def _check_face_quality_advanced(img: np.ndarray) -> Tuple[bool, Optional[Dict], dict]:
    """使用 InsightFace 进行高级人脸质量检查"""
    details = {}
    
    # 缩放图像
    resized_img, scaling_factor, ori_h, ori_w = resize_img(img, max_size=224)
    details["resized_size"] = f"{resized_img.shape[1]}x{resized_img.shape[0]}"
    details["scaling_factor"] = round(scaling_factor, 3)
    
    # 检测人脸
    faces = _MODELS["face_analyzer"].get(resized_img, max_num=5)
    details["face_count"] = len(faces)
    
    if len(faces) == 0:
        details["error"] = "NO_FACE"
        return False, QUALITY_ERROR_CODES["NO_FACE"], details
    
    # 选择最大的人脸
    if len(faces) > 1:
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
        details["selected_face"] = "largest"
    else:
        face = faces[0]
    
    # 获取人脸边界框
    bbox = face.bbox.astype(np.int32)
    x1, y1, x2, y2 = bbox
    face_width = x2 - x1
    face_height = y2 - y1
    details["face_bbox"] = {"x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2)}
    details["face_size"] = {"width": int(face_width), "height": int(face_height)}
    
    # 检查人脸是否完整
    img_h, img_w = resized_img.shape[:2]
    is_complete = not (x1 <= 0 or y1 <= 0 or x2 >= img_w or y2 >= img_h)
    details["face_complete"] = is_complete
    if not is_complete:
        details["error"] = "INCOMPLETE_FACE"
        return False, QUALITY_ERROR_CODES["INCOMPLETE_FACE"], details
    
    # 检查人脸姿态
    if hasattr(face, 'pose') and face.pose is not None:
        pitch, yaw, roll = face.pose
        details["pose"] = {
            "pitch": round(float(pitch), 2),
            "yaw": round(float(yaw), 2),
            "roll": round(float(roll), 2)
        }
        pose_ok = -25 <= pitch <= 25 and -25 <= yaw <= 25 and -25 <= roll <= 25
        details["pose_ok"] = pose_ok
        if not pose_ok:
            details["error"] = "FACE_ANGLE"
            return False, QUALITY_ERROR_CODES["FACE_ANGLE"], details
    else:
        details["pose"] = "not available"
    
    # 检测分数
    if hasattr(face, 'det_score'):
        details["detection_score"] = round(float(face.det_score), 3)
    
    details["passed"] = True
    return True, None, details

def validate_image_quality_verbose(image_data: bytes) -> Tuple[bool, Optional[Dict], Dict]:
    """
    详细的图像质量验证
    
    返回:
        (是否通过, 错误信息, 详细检查结果)
    """
    initialize()
    
    all_details = {}
    
    try:
        # 加载图像
        img = _load_image(image_data)
        all_details["image_size"] = f"{img.shape[1]}x{img.shape[0]}"
        
        # 1. 检查分辨率
        passed, details = _check_resolution(img)
        all_details["resolution"] = details
        if not passed:
            return False, QUALITY_ERROR_CODES["LOW_RESOLUTION"], all_details
        
        # 2. 检查清晰度
        passed, details = _check_clarity(img)
        all_details["clarity"] = details
        if not passed:
            return False, QUALITY_ERROR_CODES["LOW_CLARITY"], all_details
        
        # 3. 检查光照
        passed, details = _check_lighting(img)
        all_details["lighting"] = details
        if not passed:
            return False, QUALITY_ERROR_CODES["BAD_LIGHTING"], all_details
        
        # 4. 人脸质量检查
        if _MODELS["face_analyzer"]:
            passed, error, details = _check_face_quality_advanced(img)
            all_details["face_quality"] = details
            if not passed:
                return False, error, all_details
        else:
            passed, details = _check_face_detection(img)
            all_details["face_detection"] = details
            if not passed:
                return False, QUALITY_ERROR_CODES["NO_FACE"], all_details
        
        return True, None, all_details
        
    except Exception as e:
        all_details["exception"] = str(e)
        return False, QUALITY_ERROR_CODES["GENERAL_ERROR"], all_details

def print_check_result(name: str, details: Dict):
    """打印单项检查结果"""
    passed = details.get("passed", False)
    status = "✓ 通过" if passed else "✗ 失败"
    print(f"\n【{name}】 {status}")
    print("-" * 40)
    
    if name == "分辨率检查":
        print(f"  当前值: {details.get('width')}x{details.get('height')} 像素")
        print(f"  最小要求: {details.get('min_required')}x{details.get('min_required')} 像素")
        if not passed:
            print(f"  ⚠ 失败原因: 图像分辨率低于最小要求 {details.get('min_required')} 像素")
    
    elif name == "清晰度检查":
        print(f"  当前值: {details.get('laplacian_variance')} (拉普拉斯方差)")
        print(f"  最小阈值: {details.get('threshold')}")
        if not passed:
            print(f"  ⚠ 失败原因: 清晰度 {details.get('laplacian_variance')} < 阈值 {details.get('threshold')}，图像可能模糊")
    
    elif name == "光照检查":
        print(f"  当前值: {details.get('brightness')} (加权亮度)")
        print(f"  合理范围: {details.get('min_threshold')} ~ {details.get('max_threshold')}")
        brightness = details.get('brightness', 0)
        if not passed:
            if brightness < details.get('min_threshold', 40):
                print(f"  ⚠ 失败原因: 亮度 {brightness} < {details.get('min_threshold')}，图像过暗")
            else:
                print(f"  ⚠ 失败原因: 亮度 {brightness} > {details.get('max_threshold')}，图像过亮")
    
    elif name == "人脸质量检查":
        print(f"  检测到人脸数: {details.get('face_count', 0)}")
        if details.get('face_bbox'):
            bbox = details['face_bbox']
            print(f"  人脸位置: ({bbox['x1']}, {bbox['y1']}) - ({bbox['x2']}, {bbox['y2']})")
        if details.get('face_size'):
            size = details['face_size']
            print(f"  人脸尺寸: {size['width']}x{size['height']} 像素")
        print(f"  人脸完整: {'是' if details.get('face_complete', False) else '否'}")
        
        if details.get('pose'):
            if isinstance(details['pose'], dict):
                pose = details['pose']
                print(f"  姿态角度:")
                print(f"    - pitch (俯仰): {pose.get('pitch', 'N/A')}° (标准: -25° ~ 25°)")
                print(f"    - yaw (偏航): {pose.get('yaw', 'N/A')}° (标准: -25° ~ 25°)")
                print(f"    - roll (翻滚): {pose.get('roll', 'N/A')}° (标准: -25° ~ 25°)")
            else:
                print(f"  姿态角度: {details['pose']}")
        
        if details.get('detection_score'):
            print(f"  检测置信度: {details['detection_score']}")
        
        error = details.get('error')
        if error:
            error_messages = {
                'NO_FACE': '未检测到人脸，请确保图像中有清晰的人脸',
                'MULTIPLE_FACES': '检测到多张人脸，请使用单人照片',
                'FACE_TOO_SMALL': '人脸区域过小，请使用更近距离的照片',
                'INCOMPLETE_FACE': '人脸不完整，人脸被图像边缘裁切',
                'FACE_ANGLE': '人脸角度过大，请使用正脸照片（pitch/yaw/roll 需在 ±25° 内）',
            }
            print(f"  ⚠ 失败原因: {error_messages.get(error, error)}")
            if error == 'FACE_ANGLE' and isinstance(details.get('pose'), dict):
                pose = details['pose']
                for angle_name, angle_val in [('pitch', pose.get('pitch')), ('yaw', pose.get('yaw')), ('roll', pose.get('roll'))]:
                    if angle_val is not None and (angle_val < -25 or angle_val > 25):
                        print(f"      - {angle_name} = {angle_val}° 超出范围")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    if not os.path.exists(image_path):
        print(f"错误: 文件不存在 - {image_path}")
        sys.exit(1)
    
    print(f"\n{'=' * 60}")
    print(f"图像质量检查测试")
    print(f"{'=' * 60}")
    print(f"文件: {image_path}")
    print(f"大小: {os.path.getsize(image_path) / 1024:.2f} KB")
    
    # 读取图像
    with open(image_path, "rb") as f:
        image_data = f.read()
    
    # 执行质量检查
    passed, error, details = validate_image_quality_verbose(image_data)
    
    # 打印基本信息
    print(f"\n图像尺寸: {details.get('image_size', 'N/A')}")
    
    # 打印各项检查结果
    if 'resolution' in details:
        print_check_result("分辨率检查", details['resolution'])
    
    if 'clarity' in details:
        print_check_result("清晰度检查", details['clarity'])
    
    if 'lighting' in details:
        print_check_result("光照检查", details['lighting'])
    
    if 'face_quality' in details:
        print_check_result("人脸质量检查", details['face_quality'])
    elif 'face_detection' in details:
        print(f"\n【人脸检测（基础）】")
        print("-" * 40)
        fd = details['face_detection']
        print(f"  检测到人脸数: {fd.get('face_count', 0)}")
        print(f"  结果: {'✓ 通过' if fd.get('passed') else '✗ 失败'}")
    
    # 打印最终结果
    print(f"\n{'=' * 60}")
    if passed:
        print("【最终结果】 ✓ 图像质量检查通过")
    else:
        print("【最终结果】 ✗ 图像质量检查失败")
        print(f"  错误码: {error['code']}")
        print(f"  错误信息: {error['message']}")
    print(f"{'=' * 60}\n")
    
    sys.exit(0 if passed else 1)

if __name__ == "__main__":
    main()
