"""剧本 + 分镜生成器 — 基于 DeepSeek API."""
import json
from typing import Dict, List, Union
from app.services.deepseek_client import chat_json

SCRIPT_SYSTEM = """You are a professional anime comic drama (漫剧) scriptwriter.
Given a trending topic, create a compelling short anime comic drama script in Chinese.

CRITICAL: This is for ANIME/MANGA style video production. All visual descriptions must be in 2D anime/manga art style, NOT realistic/photorealistic.
- Character avatar_style must describe anime-style appearance: 动漫风, 二次元, 日系/国漫风
- Scene locations must be described as anime backgrounds

Your output MUST be valid JSON with this structure:
{
  "title": "剧名 (catchy Chinese title)",
  "genre": "类型 (e.g. 都市/古装/悬疑/甜宠/搞笑)",
  "theme": "核心主题，一句话",
  "characters": [
    {"name": "角色名", "role": "主角/配角/反派", "description": "简短描述", "avatar_style": "动漫外貌风格描述，如：国漫风美少女，凤眼柳眉，红衣似火"}
  ],
  "script": [
    {
      "scene": 1,
      "location": "动漫场景描述",
      "narration": "旁白文字",
      "dialogues": [
        {"character": "角色名", "line": "台词", "emotion": "情绪"}
      ]
    }
  ],
  "duration_estimate": 60,
  "tags": ["标签1", "标签2"]
}

Make the story dramatic, fast-paced, and suitable for vertical video (9:16). Keep total scenes between 5-10. Make dialogue snappy and emotional."""


def generate_script(topic: Union[Dict, str], style: str = "dramatic") -> Dict:
    """根据热点话题生成漫剧剧本."""
    if isinstance(topic, dict):
        title = topic.get("title", topic.get("name", ""))
        platform = topic.get("platform", "trending")
        topic_text = f"热点标题: {title}\n来源平台: {platform}\n热度: {topic.get('hot_score', 'N/A')}"
    else:
        topic_text = str(topic)

    prompt = f"""Create a comic drama script based on this trending topic:

{topic_text}

Style preference: {style}

Return ONLY the JSON, no markdown fences, no extra text."""

    return chat_json(prompt, system=SCRIPT_SYSTEM, temperature=0.85, max_tokens=4096)


def generate_storyboard(script: Dict) -> List[Dict]:
    """根据剧本生成分镜描述，用于 Seedance 视频生成."""
    scenes = script.get("script", [])
    storyboard = []
    for scene_item in scenes:
        scene_desc = scene_item.get("location", "")
        dialogues = scene_item.get("dialogues", [])
        narration = scene_item.get("narration", "")

        dialogue_text = " ".join(
            f"{d['character']}: {d['line']}" for d in dialogues
        )

        sb_prompt = (
            f"Anime style, 2D animation: {narration} {dialogue_text}".strip()
            or f"Anime style scene {scene_item['scene']}: {scene_desc}"
        )

        storyboard.append({
            "scene": scene_item["scene"],
            "location": scene_desc,
            "video_prompt": sb_prompt,
            "duration_seconds": max(8, len(dialogue_text) // 3),
            "narration": narration,
            "dialogues": dialogues,
        })
    return storyboard


def extract_title_suggestions(trending_topics: List[Dict], count: int = 5) -> List[str]:
    """从热点列表中提取适合做漫剧的题材建议."""
    prompt = f"""Given these trending topics, pick the {count} best ones that could become great short comic drama videos.
Consider: emotional impact, visual potential, dramatic tension.

Topics:
{json.dumps(trending_topics, ensure_ascii=False, indent=2)}

Return ONLY a JSON array of strings, each being the selected topic title."""

    result = chat_json(
        prompt,
        system="You are a content curator for short drama videos. Always output JSON arrays.",
        temperature=0.6,
    )
    if isinstance(result, list):
        return result[:count]
    return []
