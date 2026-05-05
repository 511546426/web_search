"""商品带货视频 API — 上传商品照片 → 生成带货剧本 → 生成视频."""
import json
import os
import logging
import threading
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from fastapi import Depends

from app.database import get_db
from app.models import ProductAd
from app.schemas import ProductInfoRequest, ProductAdScriptResponse

logger = logging.getLogger("product_ad")

router = APIRouter(prefix="/api/comic/product-ad", tags=["product_ad"])

PRODUCT_PHOTO_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads",
    "product_photos",
)
os.makedirs(PRODUCT_PHOTO_DIR, exist_ok=True)

PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")


def _photo_url(filename: str) -> str:
    """生成图片可访问 URL."""
    if PUBLIC_URL:
        return f"{PUBLIC_URL}/uploads/product_photos/{filename}"
    return f"/uploads/product_photos/{filename}"


# ---- 图片上传 ----

@router.post("/upload-photos")
def upload_photos(files: List[UploadFile] = File(...)):
    """上传商品照片（最多 9 张），返回文件名列表."""
    if len(files) > 9:
        raise HTTPException(status_code=400, detail="最多上传 9 张图片")

    saved = []
    for f in files:
        ext = os.path.splitext(f.filename or ".jpg")[1] or ".jpg"
        name = f"prod_{datetime.utcnow():%Y%m%d%H%M%S%f}_{len(saved)}{ext}"
        path = os.path.join(PRODUCT_PHOTO_DIR, name)
        content = f.file.read()
        with open(path, "wb") as out:
            out.write(content)
        saved.append(name)
        logger.info(f"Product photo saved: {name} ({len(content)} bytes)")

    return {"photo_ids": saved, "count": len(saved)}


# ---- 视频上传 + 抽帧 ----

@router.post("/upload-video")
def upload_product_video(file: UploadFile = File(...)):
    """上传商品视频，自动抽帧作为参考图，返回抽帧图片文件名列表."""
    import subprocess
    import tempfile

    # 保存上传的视频到临时文件
    suffix = os.path.splitext(file.filename or ".mp4")[1] or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    try:
        # 获取视频时长（秒）
        dur_result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", tmp_path],
            capture_output=True, text=True, timeout=30,
        )
        duration = float(dur_result.stdout.strip())
        if duration <= 0:
            raise HTTPException(status_code=400, detail="无法获取视频时长")

        # 均匀抽帧，最多 9 张
        max_frames = 9
        interval = duration / max_frames
        base = f"vid_{datetime.utcnow():%Y%m%d%H%M%S%f}"
        extracted = []

        for i in range(max_frames):
            seek_time = i * interval
            out_name = f"{base}_{i}.jpg"
            out_path = os.path.join(PRODUCT_PHOTO_DIR, out_name)
            subprocess.run(
                ["ffmpeg", "-ss", str(seek_time), "-i", tmp_path,
                 "-vframes", "1", "-q:v", "2", out_path, "-y"],
                capture_output=True, timeout=60,
            )
            if os.path.getsize(out_path) > 0:
                extracted.append(out_name)
                logger.info(f"Frame extracted: {out_name} @ {seek_time:.1f}s")

        if not extracted:
            raise HTTPException(status_code=500, detail="视频抽帧失败，请检查视频文件")

        logger.info(f"Video processed: {file.filename}, {duration:.1f}s -> {len(extracted)} frames")
        return {"photo_ids": extracted, "count": len(extracted), "source_video": file.filename}

    finally:
        os.unlink(tmp_path)


# ---- 生成带货剧本 ----

def _generate_ad_script(product: ProductInfoRequest) -> dict:
    """先用豆包视觉模型识别商品图片，再将文字描述交给 DeepSeek 生成带货剧本.

    流程：doubao-1.5-vision-lite 图片分析 → 文字描述 → DeepSeek 剧本生成。
    DeepSeek 不支持图片识别，因此拆分为两步。
    """
    from app.services.deepseek_client import chat_json
    from app.services.doubao_vision_client import analyze_product_images

    # 构建本地图片路径列表
    image_paths = []
    for pid in product.photo_ids:
        if not pid:
            continue
        img_path = os.path.join(PRODUCT_PHOTO_DIR, pid)
        if os.path.exists(img_path):
            image_paths.append(img_path)
        else:
            logger.warning(f"Product photo not found: {img_path}")

    # ---- 第一步：使用豆包视觉模型分析商品图片 ----
    image_description = ""
    if image_paths:
        try:
            image_description = analyze_product_images(
                image_paths=image_paths,
                product_name=product.name,
                product_category=product.category,
            )
            logger.info(f"Doubao vision analysis done, description length: {len(image_description)}")
        except Exception as e:
            logger.exception(f"Doubao vision analysis failed: {e}")
            image_description = f"（图片分析失败: {e}，请根据商品信息生成剧本）"

    # ---- 第二步：将图片文字描述交给 DeepSeek 生成剧本（纯文本，不传图） ----
    visual_style_text = "真人实景拍摄，真人出镜或产品实拍展示" if product.visual_style == "realistic" else "动漫风格，二维动画展示产品"
    style_note = "写实、真实产品展示" if product.visual_style == "realistic" else "二次元动漫风格"

    if product.showcase_style == "visual":
        system = f"""你是一名从业 15 年的时尚广告导演，曾为多个国际品牌执导产品视觉大片。你擅长用纯视觉语言讲述产品故事——不需要一句对白，仅靠镜头、光影、模特和节奏就让人产生购买欲。

## 你的核心能力

### 1. 视觉叙事体系（纯视觉，无对白）
每个场景就是一个镜头，通过画面本身传递信息：
- **Establishing（定场）**：产品/模特首次出现，建立第一印象
- **Detail（细节）**：材质、工艺、质感的视觉证明
- **Motion（动态）**：穿着/使用中的产品状态
- **Lifestyle（场景）**：产品在理想生活环境中的状态
- **Climax（高潮）**：最有冲击力的视觉画面

### 2. 镜头语言（精确到 AI 可执行）
每个场景必须指定镜头角度 + 模特动作 + 产品焦点：
- **景别系统**：远景全身（展示整体版型）、中景半身（展示上身效果）、近景特写（展示面料细节）、大特写（展示工艺/质感）
- **经典角度序列**：正面（直观展示）→ 侧面（展示版型轮廓）→ 背面（展示背部设计）→ 3/4（展示立体效果）→ 动态（展示穿着状态）→ 特写（材质证明）
- **运镜**：固定镜头（品质感）、缓慢推近（聚焦）、环绕（360度展示）、跟随（动态感）、升降（气场）
- **光影设计**：侧光（突出轮廓）、柔光（温馨感）、硬光（时尚感）、背光（氛围感）、环境光（真实感）

### 3. AI 视频生成优化
- 每个 prompt 要具体到 AI 可以执行：不说"自然好看"，说"阳光从 45 度侧方洒落，在面料上形成柔和的明暗过渡"
- 避免抽象形容词（漂亮/高级/精致），改用视觉描述（垂坠感/光泽度/轮廓线）
- 模特动作要简单明确（缓步向前/转身回眸/整理衣领/轻抚面料），避免复杂动作

### 4. 节奏与音乐
- 6-8 个场景，每个 1.5-3 秒，总时长严格控制在 15 秒左右
- 快慢交替：静态展示（1.5-2 秒）与动态镜头（2-3 秒）穿插
- 背景音乐建议具体到风格+节奏+氛围（如：轻快吉他，BPM 120，夏日清新感）

### 5. 严格参考商品图片描述
- 必须严格依据下方提供的「商品图片视觉分析」中描述的**商品本身**外观、颜色、形状、材质细节
- camera_angle 和 product_focus 必须基于视觉分析中提到的真实商品特征来写
- 禁止凭空想象商品未提及的外观特征

### 6. 场景背景设计（极其重要！）
- **绝对不要使用纯色背景/摄影棚/白墙**——即使原图是棚拍纯色背景，也必须设计真实的生活场景
- 这是一段连续 15 秒的视频，**所有场景必须发生在同一个主背景环境中**，通过不同镜头角度来展示不同的产品卖点
- 根据商品品类和调性选择**一个最匹配的实景环境**：
  - 服装类：都市街头 / 咖啡馆露台 / 海滨栈道 / 公园绿荫 / 商务写字楼大厅 / 精品店
  - 美妆类：精致梳妆台 / 落地窗旁晨光 / 闺蜜下午茶 / 花园
  - 数码类：极简书桌 / 夜景天台 / 创意工作室
  - 食品类：温馨厨房 / 野餐草地 / 家庭餐桌
- **同一环境内可以有不同区域**：比如选择"咖啡馆"，镜头可以从露台→吧台→落地窗旁移动，但始终在同一个咖啡馆内
- 每个场景的 camera_angle 中必须包含该统一环境的具体描述

输出严格遵循 JSON 结构，每个场景都是一帧可执行的视觉指令：

{{
  "title": "视频标题",
  "product": "商品名称",
  "genre": "带货/穿搭展示",
  "theme": "核心卖点一句话",
  "showcase_style": "visual",
  "visual_style": "{product.visual_style}",
  "setting": "统一的场景环境描述（如「午后阳光洒落的红砖咖啡馆，暖木色调装修，绿植环绕，落地窗外是安静的街景」）",
  "scenes": [
    {{
      "scene": 1,
      "camera_angle": "景别 + 角度 + 在统一环境中的具体位置 + 光影，如「正面全身，模特站在咖啡馆露台木质栏杆旁，午后自然光从侧方照亮全身」",
      "action": "模特动作描述，具体可执行",
      "product_focus": "本场景要展示的产品卖点（必须基于商品图片视觉分析中实际描述的特征）",
      "duration_seconds": 2
    }}
  ],
  "duration_estimate": 15,
  "tags": ["标签"],
  "background_music": "具体的背景音乐风格建议（曲风+节奏+氛围）"
}}"""
    else:
        system = f"""你是一名头部 MCN 机构的创意总监，年业绩过亿。你擅长制作"看了就想买"的电商短视频，深谙用户心理和转化逻辑。你的每条脚本都在剧情吸引力和销售转化力之间找到完美平衡。

## 你的核心方法论

### 1. 黄金开场（前 3 秒定生死）
- **痛点直击型**：直接呈现用户痛点，让观众觉得"说的就是我"
- **结果展示型**：先展示使用后的惊艳效果，勾起好奇心
- **悬念提问型**：抛出一个问题，让观众想知道答案
- **冲突引入型**：制造一个矛盾场景，自然引出产品

### 2. 产品展示体系（每一秒都在为转化服务）
每个场景都要明确"为什么要在这个场景展示产品的这个点"：
- **场景 1-2（建立需求）**：用户痛点 / 场景代入，让观众产生"我需要这个"的感觉
- **场景 3-5（产品解决方案）**：功能展示 + 使用场景 + 效果呈现，每场聚焦一个卖点
- **场景 6-7（信任建立）**：品质证明 / 对比测试 / 达人推荐，消除购买顾虑
- **场景 8（行动号召）**：CTA + 紧迫感 + 利益重申，促使用户下单

### 3. 镜头语言（适配 AI 视频生成）
每个场景要有清晰的镜头指示：
- **景别**：远景（场景环境）→ 中景（人物+产品互动）→ 近景（产品细节/表情反应）→ 特写（产品质感/效果对比）
- **运镜**：推（聚焦）、拉（展示全貌）、移（产品展示）、跟（使用过程）
- **光影**：明亮通透（食品/美妆）、冷峻质感（数码/男士）、温馨柔和（家居/母婴）

### 4. 对白与旁白
- **旁白（画外音）**：用于快速建立场景、点出痛点、强调卖点、引导下单
- **对白**：要真实自然，像朋友推荐而不是电视购物。"哇这个真的好好用" > "本品采用优质原料"
- **情绪标注**：帮助 AI 理解语气（惊喜 / 疑惑 / 感叹 / 温柔推荐）

### 5. 转化设计
- CTA 要具体：从"点击链接购买"到"现在下单立减 XX 元，前 100 名送 XX"
- 紧迫感：限时 / 限量 / 首发 / 独家
- 信任感：权威背书 / 用户证言 / 数据支撑
- 利益点：省钱 / 省时 / 变美 / 健康 / 社交价值

### 6. 严格参考商品图片描述
- 必须严格依据下方提供的「商品图片视觉分析」中描述的**商品本身**外观、颜色、形状、材质细节
- 所有场景的 product_focus 必须基于视觉分析中提到的真实商品特征来写，禁止凭空想象

### 7. 场景背景设计（极其重要！）
- **绝对不要使用纯色背景/摄影棚/白墙**——即使原图是棚拍纯色背景，也必须设计真实的生活场景
- 这是一段连续 15 秒的视频，**所有场景必须发生在同一个主背景环境中**，通过不同镜头角度和剧情推进来展示产品
- 根据商品品类和剧情调性选择**一个最匹配的实景环境**：
  - 服装类：都市街头 / 咖啡馆 / 海滨栈道 / 公园 / 写字楼 / 精品店
  - 美妆类：精致梳妆台 / 落地窗旁 / 闺蜜聚餐 / 花园下午茶
  - 数码类：极简书桌 / 夜景天台 / 创意工作室
  - 食品类：温馨厨房 / 野餐草地 / 家庭餐桌
- **同一环境内可以有不同区域**：比如选择"咖啡馆"，剧情可以在门口→座位→吧台间推进，但始终在同一个场所
- 每个场景的 location 必须描述统一环境中的具体位置和细节

输出严格遵循 JSON 结构，确保片头抓人、片中精彩、片尾促单：

{{
  "title": "视频标题",
  "product": "商品名称",
  "genre": "带货/评测/好物推荐",
  "theme": "核心卖点一句话",
  "showcase_style": "story",
  "visual_style": "{product.visual_style}",
  "setting": "统一的场景环境描述（如「午后阳光洒落的红砖咖啡馆，暖木色调装修，绿植环绕，落地窗外是安静的街景」）",
  "characters": [
    {{"name": "角色", "role": "主角/配角", "description": "角色描述"}}
  ],
  "scenes": [
    {{
      "scene": 1,
      "location": "统一环境中的具体位置（如「咖啡馆门口，推门而入，阳光从身后洒进来」），禁止纯色背景",
      "narration": "旁白（画外音，推情绪或点卖点）",
      "dialogues": [
        {{"character": "角色", "line": "台词", "emotion": "情绪标注"}}
      ],
      "product_focus": "本场景展示的产品卖点（必须基于商品图片视觉分析中实际描述的特征）",
      "shot_type": "远景/中景/近景/特写",
      "duration_seconds": 2
    }}
  ],
  "duration_estimate": 15,
  "tags": ["标签"],
  "cta": "行动号召，引导购买的话术（具体、紧迫、有利益点）"
}}"""

    # 构建 prompt —— 将豆包视觉分析的文字描述嵌入，而不是传图片
    image_section = ""
    if image_description:
        image_section = f"""
===== 商品图片视觉分析（由 AI 视觉模型识别，以下为图片中商品的真实外观描述）=====

{image_description}

===== 视觉分析结束 =====

"""

    prompt = f"""{image_section}Based on the above detailed visual analysis of {len(image_paths)} product photos, create a short e-commerce video script.

IMPORTANT: The visual analysis above describes EXACTLY what the product looks like in the uploaded photos.
- Product appearance (color, shape, material, details): strictly follow the analysis, do NOT invent features.
- Scene backgrounds: do NOT copy the photo's background. Design rich, real-world environments that match the product's style and target audience. Use at least 3-4 different locations across all scenes.

Product info:
- Name: {product.name}
- Category: {product.category}
- Description: {product.description}
- Selling points: {product.selling_points}
- Target audience: {product.target_audience}
- Style preference: {product.style_preference or 'Not specified'}
- Showcase mode: {'Visual showcase (no dialogue)' if product.showcase_style == 'visual' else 'Story-driven drama'}

CRITICAL RULES:
1. Product features (product_focus) must reference actual features from the visual analysis — do NOT describe anything not mentioned.
2. This is a single continuous 15-second video. ALL scenes must take place in ONE unified real-world location (e.g. a café, a park, a city street). NEVER use plain/solid color backgrounds or studio backdrops. Different scenes show different camera angles and product details within the SAME environment.
3. Choose one location that best matches the product's style and target audience. Within that location, scenes can use different spots (e.g. terrace → counter → window seat of the same café).

Total video duration: ~15 seconds. Return ONLY the JSON, no markdown fences, no extra text."""

    result = chat_json(prompt, system=system, temperature=0.7, max_tokens=4096)
    result["visual_style"] = product.visual_style
    result["showcase_style"] = product.showcase_style
    result["image_description"] = image_description
    return result


@router.post("/generate-script", status_code=201)
def generate_ad_script(body: ProductInfoRequest, db: Session = Depends(get_db)):
    """根据商品信息 + 照片生成带货剧本，自动评审并显示评分."""
    if not body.name and not body.description:
        raise HTTPException(status_code=400, detail="请提供商品名称或描述")

    script_data = _generate_ad_script(body)

    ad = ProductAd(
        title=script_data.get("title", body.name or "商品带货视频"),
        product_info=json.dumps(body.model_dump(), ensure_ascii=False),
        photo_ids=json.dumps(body.photo_ids, ensure_ascii=False),
        script_content=json.dumps(script_data, ensure_ascii=False),
        genre=script_data.get("genre", "带货"),
        status="draft",
        tags=",".join(script_data.get("tags", [])) if isinstance(script_data.get("tags"), list) else "带货",
    )
    db.add(ad)
    db.commit()
    db.refresh(ad)
    logger.info(f"Ad script created: id={ad.id}, title={ad.title}")

    # 自动评审（剧情模式用循环修改达标，视觉模式直接满分）
    try:
        showcase = script_data.get("showcase_style", "story")
        if showcase == "visual":
            ad.review_score = 9.0
            db.commit()
        else:
            from app.services.script_writer import auto_review_loop
            loop_result = auto_review_loop(script_data)
            final_script = loop_result["script"]
            ad.script_content = json.dumps(final_script, ensure_ascii=False)
            ad.title = final_script.get("title", ad.title)
            ad.review_score = loop_result["review"].get("overall_score")
            db.commit()
    except Exception:
        logger.exception(f"Auto review failed for ad {ad.id}")

    db.refresh(ad)
    return ad


# ---- 生成视频 ----

@router.post("/{ad_id}/generate-video")
def generate_ad_video(ad_id: int, resolution: str = "720p", db: Session = Depends(get_db)):
    """评审 → 自动修改达标 → 生成带货视频（一次完成）。"""
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货剧本不存在")

    if ad.status == "video_done":
        return {"message": "视频已存在", "ad_id": ad_id, "video_path": ad.video_path}

    def _run():
        from app.database import SessionLocal
        _db = SessionLocal()
        try:
            _do_generate_ad_video_with_review(_db, ad_id, resolution)
        except Exception as e:
            logger.exception(f"Ad video generation failed: {e}")
        finally:
            _db.close()

    threading.Thread(target=_run, daemon=True).start()
    return {"message": "自动评审+生成视频已触发", "ad_id": ad_id}


def _do_generate_ad_video_with_review(db, ad_id: int, resolution: str = "720p"):
    """评审 → 修改达标 → 生成带货视频."""
    from app.services.script_writer import auto_review_loop

    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        return
    logger.info(f"Starting auto-review for ad {ad_id}")

    # 1. 自动评审循环（仅剧情模式，视觉展示无需评审对白）
    script_data = json.loads(ad.script_content) if isinstance(ad.script_content, str) else ad.script_content
    showcase_style = script_data.get("showcase_style", "story") if isinstance(script_data, dict) else "story"

    if showcase_style == "visual":
        final_script = script_data
        loop_result = {
            "review": {"overall_score": 9.0, "summary": "视觉展示模式，无需评审", "ready_for_video": True},
            "iterations": 0,
            "achieved_target": True,
        }
        logger.info(f"Ad {ad_id} is visual showcase, skipping review loop")
    else:
        loop_result = auto_review_loop(script_data)
        final_script = loop_result["script"]

    # 2. 保存修改后的剧本
    ad.script_content = json.dumps(final_script, ensure_ascii=False)
    ad.title = final_script.get("title", ad.title)
    ad.review_score = loop_result["review"].get("overall_score")
    db.commit()

    logger.info(
        f"Ad {ad_id} auto-review: score={loop_result['review'].get('overall_score')}, "
        f"iterations={loop_result['iterations']}, achieved={loop_result['achieved_target']}"
    )

    # 3. 生成视频（使用修改后的剧本）
    _do_generate_ad_video(db, ad, resolution, script_data_override=final_script)


def _do_generate_ad_video(db, ad: ProductAd, resolution: str = "720p", script_data_override: dict = None):
    """内部：同步生成带货视频."""
    from app.services.seedance_client import seedance_client, SeedanceError

    ad.status = "generating_video"
    db.commit()

    script_data = script_data_override or (json.loads(ad.script_content) if isinstance(ad.script_content, str) else ad.script_content)
    visual_style = script_data.get("visual_style", "realistic") if isinstance(script_data, dict) else "realistic"
    photo_ids = json.loads(ad.photo_ids) if isinstance(ad.photo_ids, str) else (ad.photo_ids or [])

    # 构建 prompt（兼容旧数据中的 "script" 键）
    raw_scenes = script_data.get("scenes") or script_data.get("script") or []
    scenes = raw_scenes if isinstance(raw_scenes, list) else []
    showcase_style = script_data.get("showcase_style", "story") if isinstance(script_data, dict) else "story"

    # 参考图 URL — 无公网地址时用 base64 data URI 内嵌到请求中
    reference_urls = []
    for pid in photo_ids:
        if not pid:
            continue
        if PUBLIC_URL:
            reference_urls.append(_photo_url(pid))
        else:
            # 无公网地址：读取本地图片转 base64 data URI
            img_path = os.path.join(PRODUCT_PHOTO_DIR, pid)
            if os.path.exists(img_path):
                import base64
                with open(img_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                ext = os.path.splitext(pid)[1].lower() or ".jpg"
                mime = "image/png" if ext == ".png" else "image/jpeg"
                reference_urls.append(f"data:{mime};base64,{b64}")
                logger.info(f"  Ref image (data URI): {pid} ({len(b64)//1024}KB base64)")
            else:
                logger.warning(f"  Ref image not found: {img_path}")

    logger.info(f"Creating Seedance ad video task for ad {ad.id}, ref images: {len(reference_urls)}")

    # 检查 API key 是否已配置
    if not os.environ.get("SEEDANCE_API_KEY"):
        ad.status = "video_failed"
        ad.error_message = "SEEDANCE_API_KEY 未配置，无法生成视频"
        db.commit()
        logger.error(f"Ad {ad.id} failed: SEEDANCE_API_KEY not set")
        return

    video_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "uploads", "comic_videos",
    )
    os.makedirs(video_dir, exist_ok=True)
    output_path = os.path.join(
        video_dir, f"ad_{ad.id}_{datetime.utcnow():%Y%m%d_%H%M%S}.mp4"
    )

    # 单段生成：将所有场景写入一个 prompt，r2v 模型自动压缩场景
    SEGMENT_DURATION = 15  # 目标视频时长 ~15 秒

    # 从剧本中提取豆包视觉分析的商品描述，嵌入 Seedance prompt 强化参考
    image_desc_snippet = ""
    if isinstance(script_data, dict):
        raw_desc = script_data.get("image_description", "")
        if raw_desc:
            image_desc_snippet = raw_desc[:500]

    ref_instruction = (
        "CRITICAL: The generated video MUST strictly match the reference images. "
        "The product's appearance, color, shape, texture, material, and all visible details "
        "in the video must be identical to the uploaded reference photos. "
        "Do NOT alter or reimagine the product — reproduce it exactly as shown. "
    )

    style_prefix = (
        ref_instruction +
        "Cinematic product showcase video, professional model, multi-angle "
        "shoot, natural lighting, high quality, 4K, fashion photography style. "
    ) if visual_style == "realistic" else (
        ref_instruction +
        "2D anime fashion showcase, smooth animation, vibrant colors. "
    )

    if image_desc_snippet:
        style_prefix += f"Product appearance: {image_desc_snippet}. "

    scene_descs = []
    for s in scenes:
        angle = s.get("camera_angle", "")
        action = s.get("action", "")
        focus = s.get("product_focus", "")
        parts = [p for p in [angle, action, focus] if p]
        scene_descs.append(f"Scene {s.get('scene', '?')}: " + ", ".join(parts))
    combined_prompt = (style_prefix + ". ".join(scene_descs))[:2000]

    logger.info(
        f"Ad {ad.id}: generating single segment {SEGMENT_DURATION}s "
        f"with {len(scenes)} scenes, prompt={combined_prompt[:80]}..."
    )

    try:
        task = seedance_client.create_video_task(
            prompt=combined_prompt,
            duration=SEGMENT_DURATION,
            resolution=resolution,
            ratio="9:16",
            reference_images=reference_urls if reference_urls else None,
        )
        result = seedance_client.wait_for_completion(task["task_id"])
        if not result.get("video_url"):
            raise SeedanceError("Video generation returned no video_url")
        seedance_client.download_video(result["video_url"], output_path)

    except SeedanceError as e:
        ad.status = "video_failed"
        ad.error_message = str(e)
        db.commit()
        logger.error(f"Seedance video generation failed for ad {ad.id}: {e}")
        return

    # 后期处理：TTS 配音 + 字幕（仅剧情模式有对白）
    processed_path = output_path
    if script_data and isinstance(script_data, dict):
        showcase_style = script_data.get("showcase_style", "story")
        if showcase_style != "visual":
            try:
                from app.services.video_postprocessor import postprocess_video
                processed = postprocess_video(output_path, script_data)
                if processed != output_path:
                    processed_path = processed
                    logger.info(f"Post-processed ad video for ad {ad.id}: {processed_path}")
            except Exception as e:
                logger.exception(f"Ad post-processing failed: {e}")

    ad.video_path = processed_path
    ad.status = "video_done"
    db.commit()
    logger.info(f"Ad video done: id={ad.id}, path={processed_path}")


# ---- 查询 ----

@router.get("/list", response_model=List[ProductAdScriptResponse])
def list_product_ads(
    status: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    q = db.query(ProductAd).order_by(ProductAd.created_at.desc())
    if status:
        q = q.filter(ProductAd.status == status)
    return q.offset(skip).limit(limit).all()


@router.get("/{ad_id}", response_model=ProductAdScriptResponse)
def get_product_ad(ad_id: int, db: Session = Depends(get_db)):
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货剧本不存在")
    return ad


@router.post("/{ad_id}/review")
def review_product_ad(ad_id: int, db: Session = Depends(get_db)):
    """评审带货剧本质量和可行性."""
    from app.services.script_writer import review_script as do_review

    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货剧本不存在")

    script_content = json.loads(ad.script_content) if isinstance(ad.script_content, str) else ad.script_content
    result = do_review(script_content)
    return result


@router.delete("/{ad_id}")
def delete_product_ad(ad_id: int, db: Session = Depends(get_db)):
    """删除带货剧本."""
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货剧本不存在")
    db.delete(ad)
    db.commit()
    return {"message": "已删除", "ad_id": ad_id}
