"""商品图片商标合成服务.

将商标照片合成到服装照片的指定位置，为 Seedance 提供已带标的参考图。

当前实现：当没有配图图像编辑 API 时采用简单的 PIL 叠加作为预览占位。
当配置了 DOUBAO_IMAGE_ENDPOINT 时，优先调用豆包图像编辑模型。
"""
import os
import json
import base64
import logging
import httpx
from typing import List, Optional, Tuple

logger = logging.getLogger("compositor")

from dotenv import load_dotenv
_ENV_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    ".env",
)
load_dotenv(_ENV_FILE)

DOUBAO_IMAGE_ENDPOINT = os.getenv("DOUBAO_IMAGE_ENDPOINT", "")
DOUBAO_IMAGE_API_KEY = os.getenv("DOUBAO_IMAGE_API_KEY", "") or os.getenv("DOUBAO_VISION_API_KEY", "") or os.getenv("SEEDANCE_API_KEY", "")
DOUBAO_IMAGE_BASE_URL = os.getenv("DOUBAO_VISION_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")

# 预定义落标位置（相对服装照片的百分比坐标）
POSITION_MAP = {
    "左胸前": (0.25, 0.35),
    "右胸前": (0.75, 0.35),
    "领口": (0.5, 0.12),
    "左袖口": (0.08, 0.5),
    "右袖口": (0.92, 0.5),
    "背部中央": (0.5, 0.45),
    "下摆": (0.5, 0.85),
    "后领口": (0.5, 0.08),
}


def _has_image_api() -> bool:
    """检查是否配置了图像编辑 API."""
    return bool(DOUBAO_IMAGE_ENDPOINT and DOUBAO_IMAGE_API_KEY)


def _composite_via_pil(
    garment_path: str,
    logo_path: str,
    position: str,
    output_path: str,
) -> bool:
    """使用 PIL 简单叠加商标到服装（占位方案，效果有限）。"""
    try:
        from PIL import Image
    except ImportError:
        logger.warning("PIL not available, cannot composite via PIL")
        return False

    try:
        garment = Image.open(garment_path).convert("RGBA")
        logo = Image.open(logo_path).convert("RGBA")

        # 缩放商标到服装宽度的 15-20%
        logo_width = int(garment.width * 0.18)
        logo_height = int(logo.height * (logo_width / logo.width))
        logo = logo.resize((logo_width, logo_height), Image.LANCZOS)

        # 计算位置
        rel_x, rel_y = POSITION_MAP.get(position, (0.5, 0.5))
        x = int(garment.width * rel_x - logo.width // 2)
        y = int(garment.height * rel_y - logo.height // 2)

        # 合成
        result = garment.copy()
        result.paste(logo, (x, y), logo)
        result.convert("RGB").save(output_path, quality=92)
        logger.info(f"PIL composite done: {output_path} (pos={position})")
        return True
    except Exception as e:
        logger.warning(f"PIL composite failed: {e}")
        return False


def _composite_via_doubao(
    garment_path: str,
    logo_path: str,
    position: str,
    garment_type: str,
    output_path: str,
) -> bool:
    """使用豆包图像编辑模型合成商标到服装."""
    api_key = DOUBAO_IMAGE_API_KEY
    if not api_key:
        return False

    def _img_to_b64(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    garment_b64 = _img_to_b64(garment_path)
    logo_b64 = _img_to_b64(logo_path)

    prompt = (
        f"将商标图中的图案/文字，自然地合成到服装的{position}位置。"
        f"保持服装原有的材质纹理、褶皱光影不变。"
        f"商标的透视角度与服装一致，颜色和亮度要贴合服装面料的质感。"
        f"看起来像是服装本身的设计元素，而不是后期贴上去的。"
        f"只修改服装上的商标区域，不要改变服装的其他部分。"
    )

    url = f"{DOUBAO_IMAGE_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    body = {
        "model": DOUBAO_IMAGE_ENDPOINT,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{garment_b64}"},
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{logo_b64}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "max_tokens": 4096,
    }

    try:
        resp = httpx.post(url, headers=headers, json=body, timeout=120.0)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        # 输出可能是图片 base64 或图片 URL
        if content.startswith("data:image"):
            _, b64_data = content.split(",", 1)
            img_bytes = base64.b64decode(b64_data)
            with open(output_path, "wb") as f:
                f.write(img_bytes)
            logger.info(f"Doubao image composite done: {output_path}")
            return True
        elif content.startswith("http"):
            resp2 = httpx.get(content, timeout=60.0)
            resp2.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(resp2.content)
            logger.info(f"Doubao image composite (from URL) done: {output_path}")
            return True
        else:
            logger.warning(f"Doubao image unexpected response: {content[:100]}")
            return False
    except Exception as e:
        logger.warning(f"Doubao image composite failed: {e}")
        return False


def composite_logo_to_garment(
    garment_path: str,
    logo_path: str,
    position: str,
    garment_type: str = "",
    output_dir: str = "",
) -> Optional[str]:
    """将商标合成到服装照片上。

    Args:
        garment_path: 服装照片路径
        logo_path: 商标照片路径
        position: 落标位置（如"左胸前"）
        garment_type: 服装类型（如"外套正面"）
        output_dir: 输出目录，默认与 garment 同目录

    Returns:
        合成后的图片路径，失败返回 None
    """
    if not output_dir:
        output_dir = os.path.dirname(garment_path)

    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(garment_path))[0]
    ext = os.path.splitext(garment_path)[1] or ".jpg"
    output_name = f"{base}_logo_{position}.jpg"
    output_path = os.path.join(output_dir, output_name)

    # 优先调用豆包图像编辑
    if _has_image_api():
        if _composite_via_doubao(garment_path, logo_path, position, garment_type, output_path):
            return output_path
        logger.warning("Doubao image API failed, falling back to PIL")

    # 降级到 PIL
    if _composite_via_pil(garment_path, logo_path, position, output_path):
        return output_path

    # 都失败则返回原图
    logger.warning("All compositing methods failed, returning original")
    import shutil
    shutil.copy2(garment_path, output_path)
    return output_path


def batch_composite(
    garment_photos: List[dict],
    logo_photo_path: str,
    output_dir: str,
) -> List[dict]:
    """批量合成：将商标合成到多件服装上。

    Args:
        garment_photos: [{"path": str, "position": str, "garment_type": str}, ...]
        logo_photo_path: 商标照片路径
        output_dir: 输出目录

    Returns:
        [{"photo_id": str, "path": str, "position": str, "garment_type": str}, ...]
    """
    results = []
    for gp in garment_photos:
        out = composite_logo_to_garment(
            garment_path=gp["path"],
            logo_path=logo_photo_path,
            position=gp.get("position", "左胸前"),
            garment_type=gp.get("garment_type", ""),
            output_dir=output_dir,
        )
        if out:
            results.append({
                "photo_id": os.path.basename(out),
                "path": out,
                "position": gp.get("position", "左胸前"),
                "garment_type": gp.get("garment_type", ""),
            })
    return results
