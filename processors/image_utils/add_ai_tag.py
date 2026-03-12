"""AI 生成标记工具。

为媒体文件添加 AI 生成元数据标记，符合法规要求。

支持格式:
    图像: PNG、JPEG、WEBP、GIF、BMP、TIFF
    视频: MP4、MOV、AVI

标记方式:
    PNG: tEXt chunk (AI_Generated, Description)
    JPEG: EXIF APP1 段
    MP4/MOV: udta atom

Functions:
    add_ai_metadata_fast: 快速添加 AI 标记
    verify_ai_metadata: 验证是否包含 AI 标记
    detect_format: 检测媒体格式
"""

import base64
import zlib
import struct
import io
import numpy as np
import cv2
from PIL import Image, PngImagePlugin
from typing import Union, Optional, Tuple

AI_MARKER_TEXT = "此内容为AI生成"  # 统一常量
AI_MARKER_BYTES = AI_MARKER_TEXT.encode('utf-8')  # UTF-8 bytes
AI_TEXT_BYTES = (f"AI Generated: True; Description: {AI_MARKER_TEXT}").encode('utf-8')  # For ICCP/其他

def detect_format(media_data: bytes) -> str:
    """检测图像/视频格式（复用magic bytes逻辑）"""
    if media_data.startswith(b'\x89PNG\r\n\x1a\n'): return 'PNG'
    if media_data.startswith(b'\xff\xd8\xff'): return 'JPEG'
    if media_data.startswith(b'RIFF') and b'WEBP' in media_data[:12]: return 'WEBP'
    if media_data.startswith(b'GIF8') or media_data.startswith(b'GIF87'): return 'GIF'
    if media_data.startswith(b'BM'): return 'BMP'
    if media_data.startswith(b'\x49\x49') or media_data.startswith(b'MM'): return 'TIFF'
    if media_data[4:8] == b'ftyp': return 'MOV' if b'qt  ' in media_data else 'MP4'
    if media_data.startswith(b'RIFF') and b'AVI ' in media_data[8:12]: return 'AVI'
    return 'UNKNOWN'

def create_text_chunk(keyword: bytes, text: bytes) -> bytes:
    """通用函数：创建PNG tEXt chunk（复用CRC计算）"""
    data_chunk = keyword + b'\x00' + text
    length = len(data_chunk).to_bytes(4, 'big')
    crc_input = b'tEXt' + data_chunk
    crc = zlib.crc32(crc_input).to_bytes(4, 'big')
    return length + b'tEXt' + data_chunk + crc

def insert_bytes_metadata(data: bytes, fmt: str, ai_bytes: bytes) -> Optional[bytes]:
    """通用字节插入元数据（复用位置计算和atom/chunk构建）"""
    try:
        if fmt == 'PNG':
            iend_pos = data.find(b'IEND')
            if iend_pos != -1:
                chunks = create_text_chunk(b'AI_Generated', b'True') + create_text_chunk(b'Description', ai_bytes)
                return data[:iend_pos] + chunks + data[iend_pos:]
        
        if fmt == 'JPEG':
            sof_pos = next((i for i in range(2, len(data)) if data[i] == 0xff and data[i+1] in (0xc0, 0xc2, 0xc1, 0xc3)), len(data))
            exif_header = b'Exif\x00\x00'
            ifd_count = struct.pack('>H', 1)
            tag = struct.pack('>H', 0x010e)
            typ = struct.pack('>H', 2)
            count = struct.pack('>I', len(ai_bytes) + 1)
            offset = struct.pack('>I', 8)
            entry = tag + typ + count + offset
            next_ifd = struct.pack('>I', 0)
            ifd = ifd_count + entry + next_ifd
            desc = ai_bytes + b'\x00'
            exif_data = exif_header + ifd + desc
            app1_len = struct.pack('>H', len(exif_data) + 2)
            app1 = b'\xff\xe1' + app1_len + exif_data
            return data[:sof_pos] + app1 + data[sof_pos:]
        
        if fmt in ['MP4', 'MOV']:
            moov_pos = data.find(b'moov')
            if moov_pos != -1:
                name_atom = b'\xa9nam' + struct.pack('>I', len(ai_bytes) + 8) + ai_bytes + b'\x00\x00'
                desc_atom = b'\xa9des' + struct.pack('>I', len(ai_bytes) + 8) + ai_bytes + b'\x00\x00'
                udta_size = struct.pack('>I', 8 + len(name_atom) + len(desc_atom))
                udta = b'udta' + udta_size + name_atom + desc_atom
                moov_end = data.rfind(b'mvhd', moov_pos, moov_pos + 200) + 20
                return data[:moov_end] + udta + data[moov_end:]
        
        if fmt == 'AVI':
            info_pos = data.rfind(b'idx1') + 4 if b'idx1' in data else len(data) - 8
            ai_text = ai_bytes + b'\x00'
            isft = b'ISFT' + struct.pack('<I', len(ai_text) + 4) + ai_text
            icmt = b'ICMT' + struct.pack('<I', len(ai_text) + 4) + ai_text
            info_data = isft + icmt
            list_size = struct.pack('<I', 4 + len(info_data) + 4)
            info_list = b'LIST' + list_size + b'INFO' + info_data
            return data[:info_pos] + info_list + data[info_pos:]
    
    except Exception:
        pass  # 失败返回None，fallback处理
    return None

def save_with_metadata(pil_img: Image.Image, fmt: str, ai_text: bytes) -> bytes:
    """通用PIL保存函数（复用优化参数和元数据添加）"""
    output = io.BytesIO()
    if fmt == 'WEBP':
        pil_img.save(output, format='WEBP', icc_profile=ai_text, lossless=False, optimize=False, quality=95)
    elif fmt == 'TIFF':
        pil_img.save(output, format='TIFF', tiffinfo=pil_img.info, compression='none')
    elif fmt == 'GIF':
        pil_img.save(output, format='GIF', comment=AI_MARKER_TEXT, optimize=False)
    else:  # BMP
        pil_img.save(output, format='BMP', optimize=False)
    return output.getvalue()

def add_ai_metadata_fast(input_data: Union[bytes, str]) -> str:
    """主函数：添加'AI生成'标识（支持bytes或base64输入，返回base64）"""
    if not input_data: return ""
    if isinstance(input_data, str):  # base64输入
        data = base64.b64decode(input_data)
    else:  # bytes输入
        data = input_data
    fmt = detect_format(data)
    if fmt == 'UNKNOWN': return base64.b64encode(data).decode('utf-8')
    ai_bytes = AI_MARKER_BYTES
    ai_text = AI_TEXT_BYTES
    
    # 优先字节插入（复用）
    result = insert_bytes_metadata(data, fmt, ai_bytes)
    if result is not None:
        return base64.b64encode(result).decode('utf-8')
    
    # Fallback: cv2 decode + PIL add/save (复用)
    try:
        nparr = np.frombuffer(data, np.uint8)
        cv_img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
        if cv_img is None: return base64.b64encode(data).decode('utf-8')
        # 转换到PIL（复用条件）
        if len(cv_img.shape) == 3 and cv_img.shape[2] == 3:
            pil_img = Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB))
        else:
            pil_img = Image.fromarray(cv_img)
        pil_img.info['AI_Generated'] = 'True'
        pil_img.info['Description'] = AI_MARKER_TEXT
        modified_bytes = save_with_metadata(pil_img, fmt, ai_text)
        return base64.b64encode(modified_bytes).decode('utf-8')
    except Exception:
        return base64.b64encode(data).decode('utf-8')

# 示例使用
# modified_base64 = add_ai_metadata_fast(your_binary_or_base64_data)


AI_ICC_MARKER = b'AI Generated'  # For ICCP

def parse_image_info(data: bytes, fmt: str) -> str:
    """通用图像解析（复用cv2解码尺寸/通道）"""
    desc = f"格式: {fmt}, 大小: {len(data)} bytes"
    nparr = np.frombuffer(data, np.uint8)
    cv_img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
    if cv_img is not None:
        height, width = cv_img.shape[:2]
        desc += f", 尺寸: ({width}, {height})"
        if len(cv_img.shape) == 3:
            desc += f", 通道: {cv_img.shape[2]} (彩色)" if cv_img.shape[2] == 3 else " (灰度/alpha)"
    return desc

def parse_video_info(data: bytes, fmt: str) -> str:
    """通用视频解析（复用字节检查）"""
    desc = f"格式: {fmt}, 大小: {len(data)} bytes"
    if b'moov' in data: desc += ", 包含moov (视频轨道)"
    if b'udta' in data or b'INFO' in data: desc += ", 包含元数据"
    if b'avc1' in data or b'H264' in data: desc += ", 编码: H.264"
    return desc

def check_ai_marker(data: bytes, fmt: str, info: dict) -> Tuple[bool, Optional[str]]:
    """通用AI标识检查（复用字节+info/EXIF逻辑）"""
    if AI_MARKER_BYTES in data or AI_ICC_MARKER in data:
        return True, '字节中检测到'
    if 'AI_Generated' in info and info['AI_Generated'] == 'True':
        return True, 'True (info)'
    if 'Description' in info and AI_MARKER_TEXT in info['Description']:
        return True, info['Description']
    if fmt == 'JPEG':
        exif = info.get('_getexif', lambda: {})()
        if exif and 0x010e in exif:
            exif_desc = exif[0x010e] if isinstance(exif[0x010e], bytes) else exif[0x010e].encode('utf-8')
            if AI_MARKER_BYTES in exif_desc:
                return True, exif_desc.decode('utf-8', errors='ignore')
    if fmt == 'WEBP' and 'icc_profile' in info and AI_ICC_MARKER in info['icc_profile']:
        return True, info['icc_profile'].decode('utf-8', errors='ignore')[:30] + '...'
    return False, None

def verify_ai_metadata(input_data: Union[bytes, str]) -> dict:
    """主验证函数（复用解析和检查）"""
    if not input_data: return {'verified': False, 'media_desc': '空数据', 'ai_marker': None}
    if isinstance(input_data, str):  # base64输入
        data = base64.b64decode(input_data)
    else:  # bytes输入
        data = input_data
    fmt = detect_format(data)
    media_desc = ""
    ai_found = None
    verified = False
    
    try:
        if fmt in ['PNG', 'JPEG', 'WEBP', 'GIF', 'BMP', 'TIFF']:
            media_desc = parse_image_info(data, fmt)
            pil_img = Image.open(io.BytesIO(data))
            info = pil_img.info
            verified, ai_found = check_ai_marker(data, fmt, {'_getexif': pil_img._getexif, **info})
        elif fmt in ['MP4', 'MOV', 'AVI']:
            media_desc = parse_video_info(data, fmt)
            verified, ai_found = check_ai_marker(data, fmt, {})
        
        # 验证结果已在返回值中
    
    except Exception as e:
        media_desc += f", 解析错误: {e}"
    
    return {'verified': verified, 'media_desc': media_desc, 'ai_marker': ai_found}

# 示例使用
# result = verify_ai_metadata(your_binary_or_base64_data)
# print(result)