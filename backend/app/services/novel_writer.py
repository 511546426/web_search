"""AI 小说生成服务 — 世界观 → 分章大纲 → 逐章生成+评审+状态追踪."""
import json
import logging
from typing import Dict, List, Optional, Tuple

from app.services.deepseek_client import chat, chat_json, chat_fast

logger = logging.getLogger("novel_writer")

# ---- Prompt 模板 ----

WORLD_SYSTEM_PROMPT = """你是资深世界观架构师，擅长为长篇网络小说设计完整世界体系。

你的设计原则：
1. 每个设定都要有「冲突源」——为角色提供行动动机
2. 力量体系必须有「代价」和「限制」——没有免费的强大
3. 角色必须包含「内在矛盾」——让角色有血有肉，不是纸片人
4. 世界观要有延展性——能支撑长期连载不断被挖掘

重要：不要输出任何已知网文的照搬设定（如斗罗大陆的魂师体系、斗破苍穹的斗气体系等），必须是原创设计。

	JSON 规则（严格遵循）：
	- 数值只能写纯数字，不要加任何文字注释或单位
	- 字符串必须用双引号括起来
	- 最后一个字段后面不要加逗号"""

OUTLINE_SYSTEM_PROMPT = """你是有丰富经验的网文大纲策划人，擅长为长篇连载策划完整的情节结构。

策划原则：
1. 反套路设计：每卷的核心情节必须反转至少一个常见网文套路
2. 道德困境：主角必须面临真正的道德选择，好人也会做错事
3. 反派有理：每个反派有自己的合理逻辑，不是为坏而坏
4. 代价法则：角色获得任何东西都要付出真实代价
5. 节奏控制：小高潮每15-20章一次，大高潮每40-50章一次
6. 伏笔管理：前期埋下的伏笔必须在后期有合理的回收"""

CHAPTER_SYSTEM_PROMPT = """你是知名网络小说作家，正在创作长篇连载小说。

写作铁律：
1. 【一致性第一】角色状态必须与提供的"当前世界状态"一致
2. 【开篇即入戏】第一段直接进入场景，拒绝"话说""只见""让我们看看"等废话开头
3. 【画面感优先】用五感描写替代抽象形容词，不说"很美"而写"夕阳把她的影子拉得很长，裙摆被风吹起"

禁令（违反则整章不合格）：
✗ 禁止 "XXX 的心中掀起了惊涛骇浪" 类句式
✗ 禁止 "突然""就在这时" 等过渡词填充
✗ 禁止 "XXX 倒吸一口凉气" 类套路反应
✗ 禁止连续 3 句以上的内心独白
✗ 禁止整段的环境描写（超过 2 句就是灌水）
✗ 禁止无效比喻（"仿佛 XXX 一般"）

惊喜要求（必须满足）：
- 本章至少有一个让读者意想不到的情节转折
- 本章至少有一处新颖的细节描写
- 避免所有可预测桥段"""

REVIEW_SYSTEM_PROMPT = """你是网文平台的资深编辑，负责评审连载小说章节质量。

你的评审严格程度决定了连载的质量，标准对标起点中文网签约作品门槛。

评审要尖锐、具体、可执行：
- 不说"角色不够好"→ 说"第三段主角的反应不符合他自私的性格设定"
- 不说"情节太平"→ 说"本章没有实质推进，可以用 XXXXX 替代灌水段落"
- 不说"文笔需提升"→ 说"第二段的比喻是常见 AI 套路句" """

REVISE_SYSTEM_PROMPT = """你是网络小说作家，根据编辑的审稿意见修改章节。

修改原则：
1. 逐条回应每条编辑意见
2. 不修改没有问题的部分
3. 保持整体字数与原稿接近
4. 输出完整章节（不是只输出修改部分）"""

UPDATE_STATE_SYSTEM_PROMPT = """你是小说剧情分析师，负责维护长篇连载的故事状态追踪表。

你的任务是：阅读本章内容，对比上一章结束时的世界状态，产出更新后的状态表。
只更新有变化的部分，没有变化保留原样。"""


def generate_world(topic: str, genre: str = "", total_chapters: int = 100, user_feedback: str = "") -> Dict:
    """Step 1：生成完整世界观和角色设定."""
    feedback_section = ""
    if user_feedback:
        feedback_section = f"""

===== 用户修改意见 =====
{user_feedback}
===== 请根据以上意见调整世界观和角色设定 =====
"""
    prompt = f"""请根据以下信息，设计一个可用于 {total_chapters}+ 章长篇连载的完整原创世界观：

题材：{topic}
类型：{genre or '未指定（请根据题材自行判断合适类型）'}
计划总章节：{total_chapters}

要求：
1. 世界观要有足够的延展性支撑长期连载
2. 力量体系/世界规则必须具体可量化，不能模糊
3. 设计 1 个主角 + 3-5 个主要角色 + 1-2 个反派
4. 每个主要角色必须有「内在矛盾」——例如：表面自信但内心自卑 / 追求正义但手段残忍
5. 设计至少 2 条可长期发展的伏笔线
6. 必须是原创设定，不能照搬已有作品的体系
{feedback_section}
输出 JSON：
{{
  "world": {{
    "name": "世界名称",
    "background": "世界背景（200字内）",
    "rules": ["具体规则1", "规则2"],
    "power_system": {{
      "name": "力量体系名称",
      "levels": ["等级1: 特征", "等级2: 特征"],
      "rules": ["约束规则"],
      "cost": "使用力量的代价"
    }},
    "key_locations": [
      {{"name": "地名", "description": "描述", "importance": "剧情作用"}}
    ]
  }},
  "characters": [
    {{
      "name": "角色名",
      "role": "主角/主要配角/反派",
      "personality": "用3个具体场景说明性格",
      "contradiction": "内在矛盾（此角色表面____，实则____）",
      "appearance": "外貌细节",
      "voice": "说话风格",
      "goal": "核心目标",
      "arc": "成长弧线",
      "limitations": "弱点/限制"
    }}
  ],
  "relationships": [
    {{"from": "A", "to": "B", "type": "关系", "detail": "描述"}}
  ],
  "plot_arcs": [
    {{"name": "主线", "description": "核心冲突", "expected_length": "贯穿全书"}}
  ]
}}"""

    return chat_json(prompt, system=WORLD_SYSTEM_PROMPT, temperature=0.85, max_tokens=8192, timeout=300)


def generate_outline(
    world_setting: Dict, character_profiles: List[Dict], total_chapters: int = 100, user_feedback: str = ""
) -> Dict:
    """Step 2：根据世界观生成完整分章大纲."""
    feedback_section = ""
    if user_feedback:
        feedback_section = f"""

===== 用户修改意见 =====
{user_feedback}
===== 请根据以上意见调整大纲结构 =====
"""
    world_json = json.dumps(world_setting, ensure_ascii=False)
    char_json = json.dumps(character_profiles, ensure_ascii=False)

    prompt = f"""已知完整世界观和角色设定：

【世界观】
{world_json}

【角色设定】
{char_json}

请策划一个 {total_chapters} 章的小说大纲：
1. 前 20 章为"黄金引入期"：展示世界观+核心角色登场+首个高潮
2. 每 15-20 章一个小高潮，每 40-50 章一个大高潮
3. 最后 30 章进入收尾，所有伏笔回收
4. 角色的成长要有递进感，不能第一章和第一百章一个样
5. 支线之间要有穿插，避免一条线走到底
6. 允许部分支线无果而终（真实故事中不是每条线都有结果）

⚠️ 反套路要求（至少满足 2 条）：
- 【反转期待】每卷核心情节反转至少一个常见网文套路
- 【道德困境】主角面临真正的道德选择
- 【反派有理】反派有自己的合理逻辑
- 【代价法则】获得任何东西都有真实代价
{feedback_section}
输出 JSON：
{{
  "structure": {{
    "opening": {{"chapters": "1-20", "title": "开篇卷", "summary": "..."}},
    "arc_2": {{"chapters": "...", "title": "卷名", "summary": "..."}}
  }},
  "chapters": [
    {{
      "number": 1,
      "title": "章名",
      "summary": "本章关键事件和转折点（100字内）",
      "pov": "视角角色",
      "key_scenes": ["场景1概述", "场景2概述"]
    }}
  ]
}}"""

    return chat_json(prompt, system=OUTLINE_SYSTEM_PROMPT, temperature=0.8, max_tokens=8192, timeout=300)


def _summarize_recent_chapters(chapters: List[Dict]) -> str:
    """用 Flash 模型压缩最近几章的内容为摘要."""
    if not chapters:
        return "（尚无前文）"
    texts = []
    for ch in chapters:
        content = ch.get("content", "")
        title = ch.get("title", f"第{ch['chapter_number']}章")
        texts.append(f"【{title}】\n{content[:600]}")
    combined = "\n\n".join(texts)

    prompt = f"""请将以下章节内容压缩为每章 150 字以内的摘要，保留关键情节转折和角色状态变化：

{combined}

输出格式：每章一行「第X章《章名》：摘要」"""
    try:
        result = chat_fast(prompt, temperature=0.3, max_tokens=1000)
        return result
    except Exception as e:
        logger.warning(f"Summarize failed, using truncation: {e}")
        parts = []
        for ch in chapters:
            c = ch.get("content", "")
            parts.append(f"第{ch['chapter_number']}章《{ch.get('title', '')}》：{c[:200]}")
        return "\n".join(parts)


def generate_chapter_text(
    novel: Dict,
    chapter_num: int,
    chapter_info: Dict,
    recent_chapters: List[Dict],
    world_state: Optional[Dict] = None,
    word_count: int = 3000,
    user_feedback: str = "",
) -> str:
    """生成单章内容."""
    feedback_section = ""
    if user_feedback:
        feedback_section = f"""

===== 用户修改意见 =====
{user_feedback}
===== 请根据以上意见调整本章内容和写法 =====
"""
    world_setting = novel.get("world_setting", {})
    character_profiles = novel.get("character_profiles", [])
    outline = novel.get("outline", {})

    # 压缩各层 context
    world_short = json.dumps(
        {"rules": world_setting.get("world", {}).get("rules", []),
         "power_system": world_setting.get("world", {}).get("power_system", {})},
        ensure_ascii=False,
    )
    char_short = json.dumps(
        [{"name": c["name"], "personality": c.get("personality", ""),
          "contradiction": c.get("contradiction", ""),
          "voice": c.get("voice", ""), "limitations": c.get("limitations", "")}
         for c in character_profiles],
        ensure_ascii=False,
    )
    state_str = json.dumps(world_state, ensure_ascii=True) if world_state else "（尚无）"
    recent_summary = _summarize_recent_chapters(recent_chapters)

    title = chapter_info.get("title", f"第{chapter_num}章")
    summary = chapter_info.get("summary", "")
    scenes = chapter_info.get("key_scenes", [])

    prompt = f"""[世界设定]
{world_short}

[角色设定]
{char_short}

[当前世界状态——必须严格遵循]
{state_str}

[前情提要——最近几章]
{recent_summary}

[本章任务]
第 {chapter_num} 章《{title}》
概要：{summary}
关键场景：{', '.join(scenes) if scenes else '按概要自由发挥'}

要求：
1. 角色状态必须与"当前世界状态"完全一致
2. 本章至少有一个意想不到的情节转折
3. 结尾必须是悬念/转折/情感冲击
4. 字数约 {word_count} 字
	{feedback_section}"""

    return chat(prompt, system=CHAPTER_SYSTEM_PROMPT, temperature=0.85, max_tokens=4096, timeout=300)


def review_chapter(
    chapter_text: str,
    prev_world_state: Optional[Dict],
    character_profiles: List[Dict],
) -> Dict:
    """评审单章质量和跨章一致性."""
    state_str = json.dumps(prev_world_state, ensure_ascii=True) if prev_world_state else "（首章，无前一章状态）"
    char_str = json.dumps(
        [{"name": c["name"], "personality": c.get("personality", ""),
          "contradiction": c.get("contradiction", ""),
          "voice": c.get("voice", "")} for c in character_profiles],
        ensure_ascii=False,
    )

    prompt = f"""[角色设定]
{char_str}

[本章之前的"当前世界状态"——对照基准]
{state_str}

[本章内容]
{chapter_text}

请执行四步评审：

=== 第一步：跨章一致性检查 ===
对照"当前世界状态"，逐项检查角色状态/情节连续性/世界规则/时间线

=== 第二步：新颖性检查（抗同质化）===
这个写法读者在别的书里见过多少次？检查是否有被禁套路句式

=== 第三步：质量评分（1-10）===
1) 情节推进：有实质进展还是灌水？
2) 章末钩子：读者会想点下一章吗？
3) 角色在线：言行符合设定吗？
4) 文笔节奏：读起来顺吗？第一段抓人吗？
5) 场景描写：画面感够吗？

=== 第四步：结论 ===
输出 JSON：
{{
  "consistency_check": {{
    "passed": true/false,
    "character_state_issues": [],
    "plot_continuity_issues": [],
    "world_rule_issues": [],
    "timeline_issues": []
  }},
  "novelty_check": {{
    "score": 7,
    "banned_patterns_found": [],
    "note": ""
  }},
  "overall_score": 8.0,
  "dimensions": {{
    "plot_advancement": {{"score": 8, "note": ""}},
    "chapter_hook": {{"score": 9, "note": ""}},
    "character_consistency": {{"score": 7, "note": ""}},
    "writing_quality": {{"score": 8, "note": ""}},
    "scene_depiction": {{"score": 7, "note": ""}},
    "novelty": {{"score": 7, "note": ""}}
  }},
  "weaknesses": [],
  "suggestions": [],
  "verdict": "passed/revise/failed"
}}

判定规则：
- passed: overall_score >= 8 且 consistency_check.passed == true 且 novelty_check 无禁令违规
- revise: overall_score >= 6 且 consistency_check.passed == true 且 novelty_check 无禁令违规
- failed: 以上不满足"""

    return chat_json(prompt, system=REVIEW_SYSTEM_PROMPT, temperature=0.3, max_tokens=4096)


def revise_chapter_text(
    chapter_text: str,
    review_result: Dict,
    character_profiles: List[Dict],
    world_state: Optional[Dict],
    user_feedback: str = "",
) -> str:
    """根据评审意见和用户反馈修改章节."""
    state_str = json.dumps(world_state, ensure_ascii=True) if world_state else "（无）"
    char_str = json.dumps(
        [{"name": c["name"], "personality": c.get("personality", ""),
          "contradiction": c.get("contradiction", "")} for c in character_profiles],
        ensure_ascii=False,
    )
    feedback_section = ""
    if user_feedback:
        feedback_section = f"""

[用户修改意见]
{user_feedback}
"""

    prompt = f"""[角色设定]
{char_str}

[世界状态]
{state_str}

[原稿]
{chapter_text}

[编辑意见]
{json.dumps(review_result, ensure_ascii=True)}
{feedback_section}
请修改本章，逐条回应意见和用户要求。输出修改后的完整章节，在修改处标注 [修改说明]。"""

    return chat(prompt, system=REVISE_SYSTEM_PROMPT, temperature=0.7, max_tokens=4096, timeout=300)


def update_world_state(
    prev_world_state: Optional[Dict],
    chapter_text: str,
    character_profiles: List[Dict],
) -> Dict:
    """根据本章内容更新世界状态追踪表."""
    prev = json.dumps(prev_world_state, ensure_ascii=True) if prev_world_state else "{}"
    char_str = json.dumps(
        [{"name": c["name"]} for c in character_profiles],
        ensure_ascii=False,
    )

    prompt = f"""[上一章结束时的世界状态]
{prev}

[本章内容]
{chapter_text}

[角色列表]
{char_str}

输出更新后的世界状态 JSON，只更新有变化的部分：
{{
  "character_states": {{
    "角色名": {{"location": "", "status": "", "inventory": [], "notes": ""}}
  }},
  "active_plot_threads": {{"主线": "当前进展"}},
  "resolved_threads": [],
  "new_hooks": ["新悬念/伏笔"],
  "world_changes": []
}}"""

    return chat_json(prompt, system=UPDATE_STATE_SYSTEM_PROMPT, temperature=0.3, max_tokens=4096)


def auto_review_chapter_loop(
    novel: Dict,
    chapter_num: int,
    chapter_info: Dict,
    recent_chapters: List[Dict],
    prev_world_state: Optional[Dict] = None,
    max_iterations: int = 3,
    target_score: float = 8.0,
    user_feedback: str = "",
) -> Tuple[str, Dict]:
    """完整评审循环：生成 → 评审 → 修改 → 再评审 → 直到达标.

    Returns:
        (final_text, review_result)
    """
    character_profiles = novel.get("character_profiles", [])

    # 第一版：生成
    if chapter_num == 1 and not recent_chapters:
        text = generate_chapter_text(novel, chapter_num, chapter_info, [], None, user_feedback=user_feedback)
    else:
        text = generate_chapter_text(
            novel, chapter_num, chapter_info, recent_chapters, prev_world_state, user_feedback=user_feedback
        )

    for i in range(max_iterations):
        review = review_chapter(text, prev_world_state, character_profiles)

        score = review.get("overall_score", 0)
        verdict = review.get("verdict", "failed")
        logger.info(
            f"Chapter {chapter_num} review attempt {i + 1}: "
            f"score={score}, verdict={verdict}"
        )

        if verdict == "passed":
            return text, review

        if verdict == "revise" and score >= 7.5:
            # 7.5 分以上直接过，不触发修改循环以节省时间
            return text, review

        if verdict == "revise":
            text = revise_chapter_text(text, review, character_profiles, prev_world_state, user_feedback=user_feedback)
            continue

        # failed: 不再修改，返回当前版本
        if i == max_iterations - 1:
            return text, review
        text = revise_chapter_text(text, review, character_profiles, prev_world_state, user_feedback=user_feedback)

    return text, {"overall_score": 0, "verdict": "failed", "error": "Max iterations exceeded"}


def collect_recent_chapters(db_session, novel_id: int, before_chapter: int, count: int = 5) -> List[Dict]:
    """从数据库读取最近 N 章已完成的内容."""
    from app.models import NovelChapter
    chapters = (
        db_session.query(NovelChapter)
        .filter(
            NovelChapter.novel_id == novel_id,
            NovelChapter.chapter_number < before_chapter,
            NovelChapter.status == "done",
        )
        .order_by(NovelChapter.chapter_number.desc())
        .limit(count)
        .all()
    )
    return [
        {
            "chapter_number": c.chapter_number,
            "title": c.title or f"第{c.chapter_number}章",
            "content": c.content or "",
        }
        for c in reversed(chapters)
    ]
