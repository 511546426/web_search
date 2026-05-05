"""豆包视觉模型客户端 — 用于商品图片识别分析.

DeepSeek 不支持图片识别，商品带货场景中使用 Doubao-Seed-1.6-Vision
模型对上传的商品照片进行视觉分析，输出文字描述后再交给 DeepSeek 生成剧本。
"""
import os
import json
import base64
import logging
import httpx
from typing import Dict, List, Optional

from dotenv import load_dotenv

_ENV_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    ".env",
)
load_dotenv(_ENV_FILE)

logger = logging.getLogger("doubao_vision")

DOUBAO_VISION_BASE_URL = os.getenv(
    "DOUBAO_VISION_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
)
DOUBAO_VISION_API_KEY = os.getenv("DOUBAO_VISION_API_KEY", "")
DOUBAO_VISION_ENDPOINT = os.getenv("DOUBAO_VISION_ENDPOINT", "ep-20260505204810-fvqlh")


def _build_vision_messages(prompt: str, image_paths: List[str]) -> List[Dict]:
    """构建 OpenAI 兼容的多模态消息（文本 + 图片 base64）."""
    content_blocks = []
    for path in image_paths:
        if not os.path.exists(path):
            logger.warning(f"Image not found, skipping: {path}")
            continue
        ext = os.path.splitext(path)[1].lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        with open(path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode()
        content_blocks.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime};base64,{b64_data}",
            },
        })
    content_blocks.append({"type": "text", "text": prompt})
    return [{"role": "user", "content": content_blocks}]


def analyze_product_images(
    image_paths: List[str],
    product_name: str = "",
    product_category: str = "",
    timeout: float = 120.0,
) -> str:
    """使用 doubao-1.5-vision-lite 分析商品图片，返回详细文字描述.

    该描述将作为 DeepSeek 生成带货剧本的输入，替代直接传图给 DeepSeek。
    """
    api_key = DOUBAO_VISION_API_KEY or os.getenv("SEEDANCE_API_KEY", "")
    if not api_key:
        raise RuntimeError("DOUBAO_VISION_API_KEY 或 SEEDANCE_API_KEY 未配置")

    prompt = f"""请仔细分析以下商品图片，给出极其详细的文字描述。你需要从以下维度进行全面分析：

1. **外观特征**：商品的整体形状、尺寸比例、轮廓线条
2. **颜色与配色**：主色调、辅助色、渐变、撞色等具体色彩描述（用具体颜色名称，如"珊瑚粉"而非"粉色"）
3. **材质与质感**：面料/材料类型、表面光泽度、纹理细节（哑光/高光/磨砂/透明等）
4. **设计细节**：图案、印花、Logo、缝线、拉链、纽扣、标签等细节元素
5. **包装与展示**：产品包装样式、摆放角度、背景环境
6. **使用场景暗示**：从图片中可推断的适用场景
7. **品质感受**：从图片中感受到的做工精细程度和品质等级

{f'商品名称：{product_name}' if product_name else ''}
{f'商品品类：{product_category}' if product_category else ''}

请用中文输出，描述要足够详细具体，能让没看过图片的人在脑海中精确还原商品的样子。
每张图片单独描述，最后给出综合总结。"""

    url = f"{DOUBAO_VISION_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    messages = _build_vision_messages(prompt, image_paths)
    body = {
        "model": DOUBAO_VISION_ENDPOINT,
        "messages": messages,
        "max_tokens": 4096,
        "temperature": 0.3,
    }

    logger.info(
        f"Analyzing {len(image_paths)} product images with doubao-vision, "
        f"endpoint={DOUBAO_VISION_ENDPOINT}"
    )

    resp = httpx.post(url, headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    result = data["choices"][0]["message"]["content"]
    logger.info(f"Vision analysis complete, output length: {len(result)} chars")
    return result
