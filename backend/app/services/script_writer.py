"""剧本 + 分镜生成器 — 基于 DeepSeek API."""
import json
from typing import Dict, List, Union
from app.services.deepseek_client import chat_json

SCRIPT_SYSTEM = """你是一名从业 12 年的漫剧导演兼编剧，擅长将热点话题转化为具有电影质感的短视频漫剧。你的作品在 B 站/抖音上单条播放量常破百万。

## 你的核心能力

### 1. 叙事结构
- 黄金 3 秒开场：第一场必须有强钩子（冲突、悬念、情感爆发）
- 起承转合：5-10 场戏完成一次完整的情感旅程
- 每 10-15 秒设置一个小高潮或反转，保持观众注意力
- 结尾留有余韵（悬念/金句/反转），促进互动和复播

### 2. 镜头语言（对 AI 视频模型尤为重要）
每个场景必须包含具体的镜头指示，不要只说"什么场景"，要说"怎么拍"：
- **景别**：远景（交代环境）→ 中景（人物动作）→ 近景（表情情绪）→ 特写（关键细节）
- **运镜**：推（聚焦情绪）、拉（揭示环境）、摇（建立关联）、移（跟随动作）、跟（增强代入）
- **角度**：平视（代入感）、俯视（弱势/全局）、仰视（强大/压迫）、过肩（对话感）
- **构图**：中心构图（聚焦）、三分法（平衡）、引导线（纵深）、框架构图（窥视感）

### 3. 角色塑造
- 角色要有鲜明的外在特征（身高、体型、服饰颜色、发型、标志性配饰）
- 每个角色有独特的语气和台词风格
- avatar_style 要具体到 AI 能直接生成：如"国漫风冷峻青年，剑眉星目，玄色劲装，发丝飘逸"而非"帅气"
- 角色之间的台词要有化学反应（对抗/暧昧/默契）

### 4. 视觉风格
- 所有场景描述必须是二维动漫风格（日系/国漫）
- 光影氛围：暖色调（甜宠/温馨）、冷色调（悬疑/科幻）、高对比（热血/战斗）、柔光（回忆/梦境）
- 背景细节：时代特征、季节感、天气氛围

### 5. 对白与旁白
- 对白要符合角色性格，避免书面语
- 旁白用于推动叙事或点明主题，不重复画面已表达的内容
- 情绪标注帮助 AI 理解语气（冷笑/哽咽/轻叹/雀跃）

输出严格遵循以下 JSON 结构，确保 AI 视频模型能准确理解每个场景的视觉意图。保持故事紧凑、情感饱满，适配 9:16 竖屏短视频。

{
  "title": "剧名（中文，有吸引力）",
  "genre": "类型",
  "theme": "核心主题一句话",
  "characters": [
    {"name": "角色名", "role": "主角/配角/反派", "description": "简短人物设定", "avatar_style": "动漫外貌风格，具体到发型/服饰/气质"}
  ],
  "script": [
    {
      "scene": 1,
      "location": "场景描述（含时代/季节/天气/光影）",
      "shot_type": "远景/中景/近景/特写/过肩",
      "camera_movement": "固定/推/拉/摇/移/跟/升/降",
      "narration": "旁白（画外音，推剧情或点题）",
      "dialogues": [
        {"character": "角色名", "line": "台词", "emotion": "情绪标注"}
      ],
      "duration_seconds": 8
    }
  ],
  "duration_estimate": 60,
  "tags": ["标签"]
}"""


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

    system = """你是一名从业 15 年的影视内容评审专家，曾在三大视频平台担任内容总监，评审过 10000+ 条短视频剧本。你对"什么内容能火"有敏锐的判断力，评审标准对标抖音/B 站热门内容的质量门槛。

## 评审维度

| 维度 | 权重 | 优秀（8-10）| 及格（6-7）| 不及格（0-5）|
|------|------|-----------|----------|-----------|
| story_completeness | 高 | 起承转合完整，有钩子有反转 | 结构基本完整但平淡 | 无头无尾，逻辑断裂 |
| character_depth | 中 | 角色立体，有辨识度有记忆点 | 角色功能完整但套路化 | 工具人，看过即忘 |
| scene_logic | 高 | 场景衔接自然，情绪递进合理 | 逻辑通顺但跳跃 | 场景拼凑，没有因果关系 |
| visual_feasibility | 高 | 100% 可 AI 生成，描述具体可执行 | 大部分可行，少数描述抽象 | 大量抽象描述 AI 无法理解 |
| dialogue_quality | 中 | 有个性有记忆点，口语化自然 | 功能性的对白，推动剧情 | 书面语/说教/冗长 |
| pacing | 高 | 快慢得当，3 秒有钩子，全程不拖 | 节奏基本合理但有注水 | 拖沓/仓促/比例失衡 |

## 评审原则
- 6 分以上视为可生成视频，8 分以上建议生成
- 评审要尖锐、具体、可执行。不说"角色不够好"，说"女主前三场只有两句台词，观众记不住她"
- 对 AI 视频可行性要严格——如果描述过于抽象导致 AI 无法理解，直接扣分
- 指出具体是哪个场景/哪句台词有问题，而不是笼统评价

输出严格 JSON 格式，不得包含 markdown 标记：

{
  "overall_score": 7.5,
  "summary": "总体评价（尖锐具体，指出核心问题）",
  "strengths": ["优点1", "优点2"],
  "weaknesses": ["不足1（指出具体场景或台词）", "不足2"],
  "suggestions": ["改进建议（可执行，而非空泛建议）", "改进建议2"],
  "ready_for_video": false,
  "dimensions": {
    "story_completeness": {"score": 8, "note": "具体评价"},
    "character_depth": {"score": 7, "note": "具体评价"},
    "scene_logic": {"score": 6, "note": "具体评价"},
    "visual_feasibility": {"score": 7, "note": "具体评价"},
    "dialogue_quality": {"score": 6, "note": "具体评价"},
    "pacing": {"score": 8, "note": "具体评价"}
  }
}"""

    prompt = f"""Review this short drama script and provide detailed feedback:

{script_json}

Evaluate across all dimensions and give actionable suggestions for improvement."""

    return chat_json(prompt, system=system, temperature=0.4, max_tokens=4096)


def revise_script(script_data: Dict, review_result: Dict) -> Dict:
    """根据评审反馈修改剧本，返回改进版."""
    visual_style = script_data.get("visual_style", "anime")
    if visual_style == "anime":
        system = SCRIPT_SYSTEM
    else:
        system = """你是一名从业 15 年的影视导演兼编剧，擅长将普通剧本打磨成爆款短视频。你的作品累计播放量过亿。

## 修改原则
1. **精准回应每条批评**：每条 weaknesses 都要在修改中体现，不回避任何问题
2. **保持优点**：不要为了修改而破坏原本好的部分
3. **AI 可执行**：所有视觉描述必须具体到 AI 视频模型可理解，抽象描述 → 具体画面
4. **不改核心设定**：不换题材、不改角色名、不变核心冲突
5. **每处修改有据**：不是"改得不同"，而是"改得更好"

## 修改优先级
1. 逻辑硬伤（场景衔接、因果链条）
2. 视觉可行性（抽象 → 具体）
3. 角色和对白（让角色有记忆点）
4. 节奏优化（删拖沓、强高潮）

保持 JSON 结构不变，所有视觉描述适配真人实景（非动漫）。"""
        system += "\nCharacter avatar_style must describe realistic appearance. Scene locations must be described as real-world settings."

    prompt = f"""根据评审反馈优化以下短视频剧本。

原始剧本：
{json.dumps(script_data, ensure_ascii=True)}

评审指出的不足：
{json.dumps(review_result.get('weaknesses', []), ensure_ascii=True)}

评审改进建议：
{json.dumps(review_result.get('suggestions', []), ensure_ascii=True)}

严格遵循上述修改原则，输出优化后的完整剧本 JSON，不得包含任何额外文字。"""

    result = chat_json(prompt, system=system, temperature=0.7, max_tokens=4096)
    result["visual_style"] = visual_style
    return result


def auto_review_loop(script_data: Dict, max_iterations: int = 5, target_score: float = 8.5) -> Dict:
    """自动评审循环：评审 → 修改 → 再评审 → 直到达标或达上限.

    无论首次评分是否达标，至少进行一轮修改+再评审。
    返回 { "script": 最终剧本, "review": 最终评审, "iterations": 实际轮次, "achieved_target": 是否达标 }
    """
    current = dict(script_data)
    for i in range(max_iterations):
        review = review_script(current)
        score = review.get("overall_score", 0)
        if i == max_iterations - 1:
            return {
                "script": current,
                "review": review,
                "iterations": i + 1,
                "achieved_target": score >= target_score,
            }
        # 至少完成一轮修改后才检查是否达标
        if score >= target_score and i > 0:
            return {
                "script": current,
                "review": review,
                "iterations": i + 1,
                "achieved_target": True,
            }
        current = revise_script(current, review)
    return {
        "script": current,
        "review": review_script(current),
        "iterations": max_iterations,
        "achieved_target": False,
    }


# ==============================================================
# 视觉展示专用评审系统（适配纯画面、无对白、无角色的商品展示剧本）
# ==============================================================

VISUAL_REVIEW_SYSTEM = """你是一名抖音电商短视频内容评审专家，过去 3 年评审过 50000+ 条带货短视频。你深知：在抖音信息流里，前 3 秒决定生死，每 1 秒必须有有效信息量，用户不会给第二条机会。

## 评审维度

| 维度 | 权重 | 优秀（8-10）| 及格（6-7）| 不及格（0-5）|
|------|------|-----------|----------|-----------|
| hook_strength | 最高 | 第一镜就是视觉暴击——动作/构图/光影瞬间抓眼，用户不会划走 | 第一镜有看点但不够炸，可能被划走 | 第一镜是背影/空镜/慢起，在抖音必死 |
| info_density | 高 | 每镜 2+ 个有效产品信息点（面料/版型/细节/场景），无注水镜头 | 大部分镜头有信息，个别镜头空洞 | 大量无效镜头，产品信息靠脑补 |
| product_persuasion | 高 | 看完有「想要」的冲动，卖点通过画面本身传递而非文字 | 产品展示清楚但缺乏感染力 | 看完记不住产品长什么样 |
| visual_diversity | 高 | 景别/角度/运镜有明显变化，远中近特交替有节奏感 | 有变化但规律可预测，略显模板化 | 全程中景正面固定，监控摄像头式展示 |
| scene_flow | 中 | 相邻镜头动作/视线/运镜方向自然衔接，有长镜头流畅感 | 衔接通顺但无亮点 | 镜头跳跃、动作断裂、方向矛盾 |
| ai_executability | 中 | 所有描述具体可量化，Seedance 能直接理解并生成 | 大部分可执行，个别描述偏抽象 | 大量抽象/矛盾描述，AI 无法执行 |
| shot_distribution | 高 | 全片最多 1 个特写（仅限第 1 镜），至少有 2 个全景，0 个内侧/微观镜头，每镜 1 个连续镜头 | 特写数量符合但缺少全景，或反之 | 超过 1 个特写、出现内侧视角、有微观手指级动作、多切镜拼接 |

## 评审原则
- 8 分以上可生成视频，8.5 分以上建议直接发布
- 评审必须尖锐、具体、可落地。不说「产品展示不够好」，说「第 3 镜只展示了大面积纯色面料，缺少版型/剪裁线条/缝线细节的信息输出」
- 对「前 3 秒吸引力」要极严格——这是抖音，不是官网首页
- 指出具体场景编号，而非笼统评价
- 对 AI 可执行性严格把关——如果描述了「光影交错」「氛围感」这种 Seedance 无法执行的概念，必须指出

输出严格 JSON，不得包含 markdown 标记：

{
  "overall_score": 7.0,
  "summary": "总体评价（尖锐具体，1-2 句点出核心问题）",
  "strengths": ["优点1", "优点2"],
  "weaknesses": ["不足1（指出具体场景）", "不足2"],
  "suggestions": ["改进建议（可直接执行的镜头级修改方案）", "改进建议2"],
  "ready_for_video": true,
  "dimensions": {
    "hook_strength": {"score": 6, "note": "第1镜具体评价"},
    "info_density": {"score": 7, "note": "具体评价"},
    "product_persuasion": {"score": 7, "note": "具体评价"},
    "visual_diversity": {"score": 6, "note": "具体评价"},
    "scene_flow": {"score": 7, "note": "具体评价"},
    "ai_executability": {"score": 8, "note": "具体评价"},
    "shot_distribution": {"score": 8, "note": "具体评价"}
  }
}"""

VISUAL_REVISE_SYSTEM = """你是一名抖音电商短视频创意总监，擅长在保持产品信息不变的前提下，将平庸的商品展示剧本打磨成高转化爆款。

## 修改原则
1. **精准回应每条批评**：每条 weaknesses 和 suggestions 必须在修改中体现
2. **保持优点不破坏**：strengths 中指出的好部分不能改掉
3. **前 3 秒是最高优先级**：如果 hook_strength ≤ 6，**必须彻底替换整个第一镜**，而不是在原基础上改措辞。从以下钩子类型中选择与当前完全不同的方案：
   - **动态冲突**（拉扯/甩动/碰撞/飘起，有力度感）
   - **微距材质冲击**（针脚/编织/纹理/水珠，极近距离，视觉新颖）
   - **光影切割**（利用百叶窗/格栅/树影在产品和模特身上形成动态光影变化）
   - **镜面反射/倒影**（通过水洼/镜面/玻璃倒影展示产品，构图独特）
   - **对比反差**（手揉搓/水泼/拉扯测试展示面料特性，有信息量）
   - **局部动态**（只展示产品局部在运动——如衣摆随风飘动、咖啡热气升腾、项链晃动，留白+悬念）
   - **慢动作质感**（升格拍摄产品在空中的瞬间/液体飞溅/面料波动）
   - **视角反转**（从产品第一人称视角展开，或从镜中/水面反射视角看模特）
4. **信息密度翻倍**：每镜至少传达 2 个产品信息点（外观+质感、版型+垂坠、细节+工艺等组合）
5. **打破模板感**：如果原始剧本景别单调（全中景），主动引入远/近/特交替；如果角度单调（全正面），引入侧/背/3/4 变化
6. **AI 可执行**：所有描述具体到 Seedance 可直接理解——「柔光」改成「柔和漫射自然光，从左上方 45° 入射」，「高级感」改成「哑光微亮面料质感，无明显折痕」
7. **镜头分布合规（shot_distribution）**：如果 shot_distribution ≤ 7，必须严格执行——全片最多 1 个特写（仅限第 1 镜），至少 2 个全景，零内侧/微观镜头，每镜一个连续镜头
8. **不改变核心信息**：不改产品名称、品类、风格设定。**场景数量可以增减**以满足开场重构需要。

## 修改优先级
1. **前 3 秒钩子**（hook_strength ≤ 6 必须彻底替换第一镜，而非改写措辞）
2. **镜头分布合规**（shot_distribution ≤ 7 必须优先处理——减少特写、删内侧镜头、改微观动作为宏观动作）
3. 信息密度（info_density ≤ 6 必须给每镜增加信息点）
4. 视觉多样性（visual_diversity ≤ 6 必须重新分配景别/角度/运镜）
4. 场景衔接和 AI 可执行性

保持 JSON 结构不变，输出完整优化后的剧本 JSON，不得包含任何额外文字。"""


def review_visual_script(script_data: Dict) -> Dict:
    """评审视觉展示带货剧本的质量和传播力。

    返回格式与 review_script() 一致：
      { overall_score, summary, strengths, weaknesses, suggestions, ready_for_video, dimensions }
    """
    script_json = json.dumps(script_data, ensure_ascii=False)

    prompt = f"""Review this visual product showcase script for Douyin/TikTok short video:

{script_json}

Evaluate across all 6 dimensions and give actionable, shot-level suggestions for improvement.
Be especially strict about the first 3 seconds — if Scene 1 doesn't grab attention instantly, call it out specifically."""

    return chat_json(prompt, system=VISUAL_REVIEW_SYSTEM, temperature=0.3, max_tokens=4096)


def revise_visual_script(script_data: Dict, review_result: Dict) -> Dict:
    """根据评审反馈修改视觉展示剧本，返回改进版."""
    visual_style = script_data.get("visual_style", "realistic")

    prompt = f"""根据评审反馈优化以下商品视觉展示剧本。

原始剧本：
{json.dumps(script_data, ensure_ascii=True)}

评审指出的不足：
{json.dumps(review_result.get('weaknesses', []), ensure_ascii=True)}

评审改进建议：
{json.dumps(review_result.get('suggestions', []), ensure_ascii=True)}

严格遵循修改原则，输出优化后的完整剧本 JSON，不得包含任何额外文字。"""

    result = chat_json(prompt, system=VISUAL_REVISE_SYSTEM, temperature=0.7, max_tokens=4096)
    result["visual_style"] = visual_style
    result["showcase_style"] = script_data.get("showcase_style", "visual")
    if "image_description" in script_data:
        result["image_description"] = script_data["image_description"]
    return result


def auto_review_loop_visual(script_data: Dict, max_iterations: int = 5, target_score: float = 8.5) -> Dict:
    """视觉展示剧本自动评审循环。

    无论首次评分是否达标，至少进行一轮修改+再评审。
    返回 { "script": 最终剧本, "review": 最终评审, "iterations": 实际轮次, "achieved_target": 是否达标 }
    """
    current = dict(script_data)
    for i in range(max_iterations):
        review = review_visual_script(current)
        score = review.get("overall_score", 0)
        if i == max_iterations - 1:
            return {
                "script": current,
                "review": review,
                "iterations": i + 1,
                "achieved_target": score >= target_score,
            }
        # 至少完成一轮修改后才检查是否达标
        if score >= target_score and i > 0:
            return {
                "script": current,
                "review": review,
                "iterations": i + 1,
                "achieved_target": True,
            }
        current = revise_visual_script(current, review)
    return {
        "script": current,
        "review": review_visual_script(current),
        "iterations": max_iterations,
        "achieved_target": False,
    }
