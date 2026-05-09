"""DeepSeek API 客户端 — 兼容 Anthropic Messages API 协议."""
import os
import json
import base64
import httpx
from typing import Dict, List, Optional

from dotenv import load_dotenv
_ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), ".env")
load_dotenv(_ENV_FILE)

DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-eaeb7e024a654d42ac04bcffbf0fc4ec")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
DEEPSEEK_FLASH_MODEL = os.getenv("DEEPSEEK_FLASH_MODEL", "deepseek-v4-flash")

SYSTEM_PROMPT = "You are a professional comic drama scriptwriter and storyboard artist. Always respond with valid JSON."


def _build_messages(user_text: str) -> List[Dict]:
    return [{"role": "user", "content": [{"type": "text", "text": user_text}]}]


def _build_multimodal_messages(user_text: str, image_paths: List[str]) -> List[Dict]:
    """构建多模态消息（文本 + 图片 base64）."""
    content_blocks = [{"type": "text", "text": user_text}]
    for path in image_paths:
        if not os.path.exists(path):
            continue
        ext = os.path.splitext(path)[1].lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        with open(path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode()
        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime,
                "data": b64_data,
            },
        })
    return [{"role": "user", "content": content_blocks}]


def chat(
    user_message: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: float = 120.0,
    image_paths: Optional[List[str]] = None,
) -> str:
    """发送对话请求，返回模型文本响应（Anthropic Messages API 格式）.

    支持通过 image_paths 传入图片 base64，让模型基于图片内容进行分析。
    """
    url = f"{DEEPSEEK_BASE_URL}/v1/messages"
    headers = {
        "x-api-key": DEEPSEEK_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    messages = _build_multimodal_messages(user_message, image_paths) if image_paths else _build_messages(user_message)

    body: Dict = {
        "model": model or DEEPSEEK_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
        "thinking": {"type": "disabled"},
    }
    sys_text = system or SYSTEM_PROMPT
    body["system"] = [{"type": "text", "text": sys_text}]

    resp = httpx.post(url, headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"]


def chat_json(
    user_message: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: float = 120.0,
    image_paths: Optional[List[str]] = None,
) -> Dict:
    """发送对话请求，返回解析后的 JSON。支持 image_paths 多模态."""
    text = chat(user_message, system, model, temperature, max_tokens, timeout=timeout, image_paths=image_paths)
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]) if len(lines) > 1 else text
    if text.endswith("```"):
        text = text[: text.rfind("```")].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 轻量修复：去掉数字后的中文注释 1（但实际战力可达3阶水平）→ 1
    import re
    text = re.sub(r'(?<=[0-9])（[^）]*）', '', text)
    # 移除 trailing comma before } or ]
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*\]', ']', text)
    # 尝试闭合被截断的 JSON（补全缺失的 } 和 ]）
    open_braces = text.count('{') - text.count('}')
    open_brackets = text.count('[') - text.count(']')
    # 先补方括号再补花括号，顺序不能反
    if open_brackets > 0:
        text += ']' * open_brackets
    if open_braces > 0:
        text += '}' * open_braces
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 最后一搏：找到第一个 { 和最后一个 }，截取中间内容
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]
        return json.loads(text)
    raise


def chat_fast(
    user_message: str,
    system: Optional[str] = None,
    temperature: float = 0.8,
    max_tokens: int = 2048,
) -> str:
    """使用快速模型 (flash) 进行轻量任务."""
    return chat(user_message, system, DEEPSEEK_FLASH_MODEL, temperature, max_tokens)
