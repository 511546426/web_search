"""DeepSeek API 客户端 — 兼容 Anthropic Messages API 协议."""
import os
import json
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


def chat(
    user_message: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: float = 120.0,
) -> str:
    """发送对话请求，返回模型文本响应（Anthropic Messages API 格式）."""
    url = f"{DEEPSEEK_BASE_URL}/v1/messages"
    headers = {
        "x-api-key": DEEPSEEK_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body: Dict = {
        "model": model or DEEPSEEK_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": _build_messages(user_message),
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
) -> Dict:
    """发送对话请求，返回解析后的 JSON."""
    text = chat(user_message, system, model, temperature, max_tokens)
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]) if len(lines) > 1 else text
    if text.endswith("```"):
        text = text[: text.rfind("```")].strip()
    return json.loads(text)


def chat_fast(
    user_message: str,
    system: Optional[str] = None,
    temperature: float = 0.8,
    max_tokens: int = 2048,
) -> str:
    """使用快速模型 (flash) 进行轻量任务."""
    return chat(user_message, system, DEEPSEEK_FLASH_MODEL, temperature, max_tokens)
