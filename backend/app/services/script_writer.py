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
    visual_style = script.get("visual_style", "anime")
    style_prefix = "Realistic, live-action,真人影视风格, photorealistic, cinematic lighting: " if visual_style == "realistic" else "Anime style, 2D animation: "
    storyboard = []
    for scene_item in scenes:
        scene_desc = scene_item.get("location", "")
        dialogues = scene_item.get("dialogues", [])
        narration = scene_item.get("narration", "")

        dialogue_text = " ".join(
            f"{d['character']}: {d['line']}" for d in dialogues
        )

        sb_prompt = (
            f"{style_prefix}{narration} {dialogue_text}".strip()
            or f"{style_prefix}scene {scene_item['scene']}: {scene_desc}"
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


def format_raw_script(raw_text: str, visual_style: str = "anime") -> Dict:
    """将用户提供的纯文本剧本解析为结构化 JSON 格式。

    visual_style: "anime"（动漫）或 "realistic"（真人）.
    """
    if visual_style == "realistic":
        system = """You are a professional short drama scriptwriter.
Given a script concept, create a compelling short drama script in Chinese.

CRITICAL: This is for REALISTIC/LIVE-ACTION video production. All visual descriptions must be photorealistic, NOT anime/cartoon style.
- Character avatar_style must describe realistic appearance: 真人风格, 写实
- Scene locations must be described as real-world settings

Your output MUST be valid JSON with this structure:
{
  "title": "剧名",
  "genre": "类型",
  "theme": "核心主题，一句话",
  "characters": [
    {"name": "角色名", "role": "主角/配角/反派", "description": "简短描述", "avatar_style": "写实外貌描述，如：清秀鹅蛋脸，柳叶眉，披肩长发"}
  ],
  "script": [
    {
      "scene": 1,
      "location": "实景场景描述",
      "narration": "旁白文字",
      "dialogues": [
        {"character": "角色名", "line": "台词", "emotion": "情绪"}
      ]
    }
  ],
  "duration_estimate": 60,
  "tags": ["标签1", "标签2"]
}

Make the story dramatic, fast-paced, and suitable for vertical video (9:16). Keep total scenes between 5-10."""
        style_desc = "realistic真人影视"
    else:
        system = SCRIPT_SYSTEM
        style_desc = "anime动漫"

    prompt = f"""Convert the following raw script text into the standard structured JSON format for {style_desc} style short video production.

Raw script:
{raw_text}

Parse the text and extract: title, genre, theme, characters (with name/role/description/avatar_style), script scenes (with scene number, location, narration, dialogues with character/line/emotion), duration_estimate, and tags.

If the text doesn't specify something, make reasonable inferences. For characters without explicit descriptions, describe their appearance.

Return ONLY the JSON, no markdown fences, no extra text."""

    result = chat_json(prompt, system=system, temperature=0.6, max_tokens=4096)
    result["visual_style"] = visual_style
    return result


def review_script(script_data: Dict) -> Dict:
    """评审剧本质量和可行性，返回评分和改进建议。

    Returns:
      { score, summary, strengths, weaknesses, suggestions, ready_for_video }
    """
    script_json = json.dumps(script_data, ensure_ascii=False)

    system = """You are a professional short drama script reviewer and editor.
Evaluate the given script JSON and provide constructive feedback.

Rate these dimensions (1-10):
- Story completeness: does it have a clear beginning, middle, end?
- Character depth: are characters well-defined with distinct personalities?
- Scene logic: does each scene flow naturally to the next?
- Visual feasibility: can the described scenes be reasonably generated as video?
- Dialogue quality: is the dialogue natural and engaging?
- Pacing: is the rhythm appropriate for short vertical video (9:16)?

Output ONLY valid JSON with this structure:
{
  "overall_score": 7.5,
  "summary": "一段总体评价",
  "strengths": ["优点1", "优点2"],
  "weaknesses": ["不足1", "不足2"],
  "suggestions": ["改进建议1", "改进建议2"],
  "ready_for_video": true,
  "dimensions": {
    "story_completeness": {"score": 8, "note": "..."},
    "character_depth": {"score": 7, "note": "..."},
    "scene_logic": {"score": 8, "note": "..."},
    "visual_feasibility": {"score": 7, "note": "..."},
    "dialogue_quality": {"score": 6, "note": "..."},
    "pacing": {"score": 8, "note": "..."}
  }
}

Be constructive and specific. Score 6+ means acceptable for video generation.
If ready_for_video is false, the user should revise before generating video."""

    prompt = f"""Review this short drama script and provide detailed feedback:

{script_json}

Evaluate across all dimensions and give actionable suggestions for improvement."""

    return chat_json(prompt, system=system, temperature=0.4, max_tokens=4096)


def revise_script(script_data: Dict, review_result: Dict) -> Dict:
    """根据评审反馈修改剧本，返回改进版."""
    visual_style = script_data.get("visual_style", "anime")
    system = SCRIPT_SYSTEM if visual_style == "anime" else """You are a professional short drama scriptwriter.
Your output MUST be valid JSON. CRITICAL: This is for REALISTIC/LIVE-ACTION video production.
All visual descriptions must be photorealistic, NOT anime/cartoon style."""
    if visual_style == "realistic":
        system += "\nCharacter avatar_style must describe realistic appearance. Scene locations must be described as real-world settings."

    prompt = f"""You are tasked with improving a short drama script based on review feedback.

Original script:
{json.dumps(script_data, ensure_ascii=True)}

Review weaknesses:
{json.dumps(review_result.get('weaknesses', []), ensure_ascii=True)}

Review suggestions:
{json.dumps(review_result.get('suggestions', []), ensure_ascii=True)}

Revise the script to address ALL weaknesses and incorporate the suggestions.
IMPORTANT: Keep the same JSON structure (title, genre, theme, characters, script, duration_estimate, tags, visual_style).
Improve character depth, dialogue naturalness, scene transitions, and overall quality.
Make the story more engaging and compelling.
Return ONLY the revised JSON, no markdown fences, no extra text."""

    result = chat_json(prompt, system=system, temperature=0.7, max_tokens=4096)
    result["visual_style"] = visual_style
    return result


def auto_review_loop(script_data: Dict, max_iterations: int = 5, target_score: float = 8.0) -> Dict:
    """自动评审循环：评审 → 不达标则修改 → 再评审 → 直到达标或达上限.

    返回 { "script": 最终剧本, "review": 最终评审, "iterations": 实际轮次, "achieved_target": 是否达标 }
    """
    current = dict(script_data)
    for i in range(max_iterations):
        review = review_script(current)
        score = review.get("overall_score", 0)
        if score >= target_score or i == max_iterations - 1:
            return {
                "script": current,
                "review": review,
                "iterations": i + 1,
                "achieved_target": score >= target_score,
            }
        # 修改
        current = revise_script(current, review)
    return {
        "script": current,
        "review": review_script(current),
        "iterations": max_iterations,
        "achieved_target": False,
    }


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
