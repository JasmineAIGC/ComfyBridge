"""图像合成工具。

将生成的图像与背景/模板进行合成。

功能:
    图像叠加: 将前景图像叠加到背景上
    区域粘贴: 在指定区域内粘贴图像
    缩放模式: contain（适应）、cover（覆盖）、width（按宽度）

Functions:
    img_composite_bytes: 图像合成，返回字节数据
    paste_within_region: 在区域内粘贴图像
    fit_overlay: 按模式缩放图像
"""

import json
import sys
from PIL import Image, ImageDraw, ImageChops
from io import BytesIO

from nexus.error_codes import ERR_PARAM_VALIDATION, get_error_message


class ParamValidationError(Exception):
    """参数验证错误，包含统一错误码"""
    def __init__(self, detail: str):
        self.code = ERR_PARAM_VALIDATION
        self.message = get_error_message(ERR_PARAM_VALIDATION)
        self.detail = detail
        super().__init__(detail)


def rect_points_to_xywh(points):
    xs = [int(round(p.get("x", 0))) for p in points]
    ys = [int(round(p.get("y", 0))) for p in points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    return x0, y0, max(0, x1 - x0), max(0, y1 - y0)


def parse_rect_points_string(s: str):
    arr = json.loads(s)
    if not isinstance(arr, list) or len(arr) < 4:
        raise ParamValidationError('rect-points must be a JSON array of 4 points objects with x/y')
    return rect_points_to_xywh(arr[:4])


def prepare_overlay(src: Image.Image) -> Image.Image:
    return src


def fit_overlay(overlay: Image.Image, region_w: int, region_h: int, fit: str) -> Image.Image:
    ow, oh = overlay.size
    if fit == 'none':
        return overlay
    if region_w <= 0 or region_h <= 0 or ow == 0 or oh == 0:
        return overlay
    if fit == 'contain':
        scale = min(region_w / ow, region_h / oh)
    elif fit == 'cover':
        scale = max(region_w / ow, region_h / oh)
    elif fit == 'width':
        scale = region_w / ow
    else:
        scale = region_w / ow
    new_w = max(1, int(round(ow * scale)))
    new_h = max(1, int(round(oh * scale)))
    if (new_w, new_h) == (ow, oh):
        return overlay
    return overlay.resize((new_w, new_h), Image.LANCZOS)


def paste_within_region(base: Image.Image, overlay: Image.Image, region, anchor: str):
    x, y, rw, rh = region
    ow, oh = overlay.size
    if anchor == 'bottom_center':
        px = x + (rw - ow) // 2
        py = y + rh - oh
    elif anchor == 'center':
        px = x + (rw - ow) // 2
        py = y + (rh - oh) // 2
    else:  # 'top_center'
        px = x + (rw - ow) // 2
        py = y
    # Clamp to keep inside region
    px = max(x, min(px, x + rw - ow))
    py = max(y, min(py, y + rh - oh))

    layer = Image.new('RGBA', base.size, (0, 0, 0, 0))
    layer.paste(overlay, (px, py), overlay)
    alpha = layer.split()[-1]
    mask = Image.new('L', base.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle([x, y, x + rw, y + rh], fill=255)
    masked_alpha = ImageChops.multiply(alpha, mask)
    layer.putalpha(masked_alpha)
    return Image.alpha_composite(base, layer), (px, py)


def process_one(bg_src: Image.Image, overlay_src: Image.Image, rects, foot_protect_ratio: float, anchor: str) -> bytes:
    base = bg_src
    boxes = rects or []
    for b in boxes:
        # Clip region to base bounds on all sides for stable alignment basis
        bx, by, bw, bh = b
        base_w, base_h = base.size
        x0 = max(0, min(bx, base_w))
        y0 = max(0, min(by, base_h))
        x1 = max(0, min(bx + bw, base_w))
        y1 = max(0, min(by + bh, base_h))
        eff_w = max(0, x1 - x0)
        eff_h = max(0, y1 - y0)
        if eff_w <= 0 or eff_h <= 0:
            continue

        ov0 = prepare_overlay(overlay_src)
        # Step 1: width-based scale
        ov = fit_overlay(ov0, eff_w, eff_h, 'width')
        use_anchor = anchor
        # Step 2: if not reaching bottom, bottom-center align without extra scaling
        if ov.size[1] < eff_h:
            use_anchor = 'bottom_center'
        # Step 3: if overflow bottom, decide crop vs contain by content cut ratio
        elif ov.size[1] > eff_h:
            alpha = ov0.split()[-1]
            bbox = alpha.getbbox()
            content_h = (bbox[3] - bbox[1]) if bbox else ov0.size[1]
            scale_w = ov.size[0] / max(ov0.size[0], 1)
            content_h_scaled = content_h * scale_w
            cut_ratio_content = 0.0
            if content_h_scaled > 0:
                cut_ratio_content = max(0.0, (content_h_scaled - eff_h) / content_h_scaled)
            if cut_ratio_content > foot_protect_ratio:
                ov = ov.crop((0, 0, ov.size[0], eff_h))
                use_anchor = anchor
            else:
                ov = fit_overlay(ov0, eff_w, eff_h, 'contain')
                use_anchor = anchor
        base, (px, py) = paste_within_region(base, ov, (x0, y0, eff_w, eff_h), use_anchor)
    buffer = BytesIO()
    base.convert('RGB').save(buffer, format="PNG") 
    return buffer.getvalue()


def img_composite_bytes(bg_data, clothes_data, location_json):
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    rect = parse_rect_points_string(location_json)
    anchor = 'top_center'
    foot_protect_ratio = 0.0
    overlay_src = Image.open(BytesIO(clothes_data)).convert('RGBA') 
    bg_src = Image.open(BytesIO(bg_data)).convert('RGBA') 

    return process_one(bg_src, overlay_src, [rect], foot_protect_ratio, anchor)





# if __name__ == '__main__':
#     main()
