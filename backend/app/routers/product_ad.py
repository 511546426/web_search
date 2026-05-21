"""商品带货视频 API — 步骤化制作流程.

流程：
  上传素材 → [商标合成预览 → 确认] → 生成带货剧本 → [确认剧本] → 生成视频
  每步支持确认/重试，用户可以在进入下一步前预览结果。
"""
import json
import os
import logging
import random
import threading
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from fastapi import Depends

from app.database import get_db
from app.models import ProductAd
from app.schemas import (
    ProductInfoRequest, ProductAdScriptResponse,
    CompositePreviewResponse, CompositePreviewItem,
    CompositeConfirmRequest, ScriptRetryRequest,
    ConfirmVariantRequest,
)

logger = logging.getLogger("product_ad")

router = APIRouter(prefix="/api/comic/product-ad", tags=["product_ad"])

PRODUCT_PHOTO_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads",
    "product_photos",
)
os.makedirs(PRODUCT_PHOTO_DIR, exist_ok=True)

PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")


# ==============================================================
# 随机化创意参数池（避免剧本同质化）
# ==============================================================

LOCATION_POOL = [
    "精品买手店二层阳光房，白色木窗框，窗外可见绿植，浅木色地板，米色亚麻沙发，龟背竹点缀",
    "简约 loft 办公室，整面落地窗引入午后柔光，灰色微水泥墙面，金属线条吊灯，深色木质地板，办公桌上有笔记本电脑和咖啡杯",
    "街角咖啡馆户外座位区，藤编椅子配大理石小圆桌，午后柔光透过浅色遮阳伞，地面铺着碎石子",
    "高层写字楼大堂休息区，大理石地面，现代风格沙发组，落地玻璃幕墙外可见城市景观，午后的自然光从幕墙洒入",
    "现代风格客厅，浅灰色布艺沙发，白色墙面配抽象装饰画，木地板上有几何图案地毯，落地窗引入柔和的自然光",
    "高端酒店行政走廊休息区，暖色壁灯，地毯，皮沙发，窗外可见城市天际线",
    "城市商业步行街，两旁有绿植和现代店铺橱窗，地面铺浅色石材，午后阳光透过行道树形成斑驳光影",
    "社区公园长椅旁，草坪修整整齐，远处有儿童游乐设施，柔和自然光，氛围轻松日常",
    "商务区露天咖啡座，简约白桌椅，灰色遮阳篷，周围是现代写字楼，背景有行人来往，光线明亮通透",
    "精品酒店大堂休息区，大理石前台，现代艺术吊灯，组合沙发区，落地窗引入自然光，空间开阔明亮",
    "城市滨河步道，木制栏杆，河面波光粼粼，远处可见城市建筑轮廓，傍晚柔光氛围恬静",
    "家居买手店展示区，北欧风木质置物架，暖光吊灯，绿植点缀，生活气息浓厚",
]

LIGHTING_POOL = [
    ("柔和漫射自然光，从左上方 45° 入射，干净通透，无明显阴影", "natural_diffuse"),
    ("暖金色侧光，从窗或门一侧斜射，勾勒出产品轮廓的戏剧性光边", "golden_side"),
    ("柔光箱质感正面光，光线均匀包裹主体，适合突出面料细节和色彩还原", "softbox_front"),
    ("逆光+正面补光，主体边缘有发光轮廓，正面细节依然清晰", "backlight_fill"),
    ("顶部天窗自然光，光线从正上方洒落，形成柔和的顶光层次", "top_skylight"),
    ("黄昏暖光+室内暖灯混合，色调偏暖，有生活氛围和故事感", "golden_hour_mix"),
]

CAMERA_STYLE_POOL = [
    ("快节奏动态开场：第一镜直接是产品动态特写（如面料飘动/模特大步走/快速转身），跳切切换场景，运镜以快摇+跟随为主",
     "fast_dynamic"),
    ("慢推电影感：每镜以缓慢推近或拉远为主，固定镜头间用 dissolve 式衔接，强调氛围和质感",
     "slow_cinematic"),
    ("动静交替节奏：固定镜头展示产品整体 → 快速环绕展示细节 → 固定镜头定帧收尾，张弛交替",
     "dynamic_static_mix"),
    ("手持纪实感：镜头微晃，跟随模特自然走动，像朋友随手拍的生活记录，弱化刻意摆拍感",
     "handheld_documentary"),
    ("升格慢动作点缀：正常速度展示穿戴效果 → 1-2 个关键镜头用慢动作（面料飘起/转身瞬间），强调高级感",
     "slowmo_accent"),
]

OPENING_HOOK_POOL = [
    ("产品动态冲击：第一帧就是产品材质的动态瞬间——拉扯面料回弹/按压凹陷恢复/揉搓后抚平，让用户先看到产品最impressive的特性",
     "product_impact"),
    ("细节揭示：开场即产品核心卖点的区域特写（胸部面料纹理/肩部版型线条/袖口轮廓），0.3秒内快速拉远揭示全貌",
     "detail_reveal"),
    ("对比反差：两个不同状态的产品并置或快速切换（揉皱vs平整/暗光vs光照/正面vs侧面），用对比本身制造视觉冲击",
     "contrast_hook"),
    ("面料质感特写：开场即大范围面料动态——拉伸回弹/飘动垂坠/自然褶皱恢复，触感可视化",
     "fabric_texture"),
    ("逆光轮廓冲击：模特侧身/3/4角度，逆光勾勒产品轮廓线条，第一帧用光影剪影吸引视线，0.3秒内转为正常曝光展示产品",
     "silhouette_reveal"),
]


def _pick_random() -> dict:
    """每次调用随机组合一组创意参数，保证每次生成的剧本有不同的视觉风格."""
    location = random.choice(LOCATION_POOL)
    lighting, _ = random.choice(LIGHTING_POOL)
    camera_style, _ = random.choice(CAMERA_STYLE_POOL)
    hook, _ = random.choice(OPENING_HOOK_POOL)
    return {
        "location": location,
        "lighting": lighting,
        "camera_style": camera_style,
        "opening_hook": hook,
    }


def _get_category_strategy(category: str) -> str:
    """按商品品类返回差异化的展示策略提示."""
    c = (category or "").lower()
    if any(kw in c for kw in ["服装", "穿搭", "t恤", "套装", "polo", "衬衫", "裤", "裙", "外套", "卫衣", "毛衣", "夹克"]):
        return """【品类策略：服装/穿搭】
- 展示顺序：整体版型 → 动态垂坠 → 面料质感 → 细节工艺 → 搭配效果
- 关键时刻：面料回弹瞬间、抗皱恢复、动态垂坠的飘动感、领口贴合度
- 卖点分配参考：版型轮廓 → 面料回弹/抗皱 → 缝线/纽扣工艺 → 上身穿搭效果
- 模特动作必须以「展示卖点」为目的：如拉扯面料展示回弹、揉搓袖口展示抗皱、转身展示背部剪裁
- 注意：禁止为了动作而动作，每个动作必须对应一个 product_focus"""

    if any(kw in c for kw in ["美妆", "护肤", "化妆", "口红", "粉底", "精华", "面霜", "眼影"]):
        return """【品类策略：美妆/护肤】
- 展示顺序：产品外观 → 质地特写（推开/涂抹/吸收）→ 使用效果 → 光泽/妆感对比
- 关键时刻：产品挤出的瞬间、在皮肤上推开的质地变化、使用前后的光泽对比
- 必展示：产品包装质感、质地（流动性/细腻度）、上脸/上手后的效果
- 避免：只拍瓶子不展示质地的「静物摄影」"""

    if any(kw in c for kw in ["食品", "零食", "饮品", "饮料", "咖啡", "茶", "酒", "糕点", "面包"]):
        return """【品类策略：食品/饮品】
- 展示顺序：产品外观 → 动态质感（蒸汽/流动/倾倒/切开）→ 食用/饮用瞬间 → 满足感
- 关键时刻：倾倒时液体流动、切开时内部结构、咬下时的质感
- 必展示：色泽饱和度、动态质感（蒸汽/气泡/拉丝/酥脆）、食用场景
- 避免：全程静态摆放——必须包含动态的食用/制作过程"""

    if any(kw in c for kw in ["数码", "3c", "电子", "手机", "耳机", "手表", "音箱", "电脑", "相机"]):
        return """【品类策略：数码/3C】
- 展示顺序：整体设计 → 接口/按键细节 → 手持比例 → 使用场景 → 质感特写
- 关键时刻：屏幕点亮瞬间、设备翻转时的金属反光、手部操作交互
- 必展示：产品厚度/重量感（手持展示）、接口设计、材质对比（金属/玻璃/皮革）
- 避免：纯产品旋转——必须包含手持使用场景"""

    if any(kw in c for kw in ["配饰", "包", "首饰", "项链", "手链", "戒指", "耳环", "帽子", "墨镜", "围巾"]):
        return """【品类策略：配饰】
- 展示顺序：整体搭配 → 微距细节 → 佩戴动态 → 光线下的质感变化
- 关键时刻：佩戴瞬间、光线在金属/宝石表面移动时的折射
- 必展示：细节工艺（镶嵌/缝线/打磨）、与服装的搭配效果、不同角度下的光泽
- 避免：远距离平面展示——配饰需要大量微距特写"""

    # 通用策略
    return """【品类策略：通用展示】
- 展示顺序：产品外观 → 细节特写 → 使用/穿戴效果 → 场景融入
- 核心原则：前 3 秒必须有视觉冲击，每镜必须有明确的产品信息输出
- 避免：连续使用相同景别/角度，避免全程无动态的静物展示"""


# ==============================================================
# 随机化参数定义结束
# ==============================================================


def _photo_url(filename: str) -> str:
    if PUBLIC_URL:
        return f"{PUBLIC_URL}/uploads/product_photos/{filename}"
    return f"/uploads/product_photos/{filename}"


# ==============================================================
# 图片/视频上传（保持不变）
# ==============================================================

@router.post("/upload-photos")
def upload_photos(files: List[UploadFile] = File(...)):
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


@router.post("/upload-video")
def upload_product_video(file: UploadFile = File(...)):
    import subprocess
    import tempfile
    suffix = os.path.splitext(file.filename or ".mp4")[1] or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name
    try:
        dur_result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", tmp_path],
            capture_output=True, text=True, timeout=30,
        )
        duration = float(dur_result.stdout.strip())
        if duration <= 0:
            raise HTTPException(status_code=400, detail="无法获取视频时长")
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
        if not extracted:
            raise HTTPException(status_code=500, detail="视频抽帧失败")
        return {"photo_ids": extracted, "count": len(extracted), "source_video": file.filename}
    finally:
        os.unlink(tmp_path)


# ==============================================================
# 创建草稿（步骤 0：先创建 ad 记录，后续步骤在此基础上进行）
# ==============================================================

@router.post("/create-draft", status_code=201)
def create_draft(body: ProductInfoRequest, db: Session = Depends(get_db)):
    """创建商品带货草稿，返回 ad_id，后续步骤基于此 ad_id 进行。"""
    ad = ProductAd(
        title=body.name or "商品带货视频",
        product_info=json.dumps(body.model_dump(), ensure_ascii=False),
        photo_ids=json.dumps(body.photo_ids, ensure_ascii=False),
        script_content="{}",
        genre="带货",
        status="draft",
        tags="带货",
        composite_confirmed=len(body.photo_ids or []) == 0,  # 无照片则跳过合成步骤
    )
    db.add(ad)
    db.commit()
    db.refresh(ad)
    logger.info(f"Draft created: id={ad.id}, title={ad.title}")
    return {"ad_id": ad.id, "message": "草稿已创建"}


# ==============================================================
# 商标合成预览（步骤 1）
# ==============================================================

@router.post("/{ad_id}/preview-composite", response_model=CompositePreviewResponse)
def preview_composite(ad_id: int, db: Session = Depends(get_db)):
    """检测服装照片是否需要合成商标，返回合成预览结果。"""
    from app.services.doubao_vision_client import analyze_product_images
    from app.services.compositor import composite_logo_to_garment

    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="草稿不存在")

    photo_ids = json.loads(ad.photo_ids) if isinstance(ad.photo_ids, str) else (ad.photo_ids or [])
    if not photo_ids:
        raise HTTPException(status_code=400, detail="请先上传商品照片")

    # 区分服装照片和商标照片（简单启发：至少有一张图名含 logo/label/商标/标 视为商标图）
    logo_photo_id = None
    garment_ids = []
    for pid in photo_ids:
        lower = pid.lower()
        if any(kw in lower for kw in ["logo", "label", "商标", "标", "tag"]):
            logo_photo_id = pid
        else:
            garment_ids.append(pid)

    # 如果没有明显标识的商标图，无法合成
    if not logo_photo_id:
        return CompositePreviewResponse(
            ad_id=ad_id,
            items=[CompositePreviewItem(
                photo_id=pid,
                photo_url=_photo_url(pid),
                garment_type="",
                position=None,
                logo_visible=False,
                confirmed=False,
            ) for pid in garment_ids],
        )

    logo_path = os.path.join(PRODUCT_PHOTO_DIR, logo_photo_id)
    if not os.path.exists(logo_path):
        raise HTTPException(status_code=400, detail="商标照片文件不存在")

    # 尝试用豆包视觉分析服装照片，推断服装类型和推荐落标位置
    garment_paths = [os.path.join(PRODUCT_PHOTO_DIR, pid) for pid in garment_ids if os.path.exists(os.path.join(PRODUCT_PHOTO_DIR, pid))]

    # 默认位置映射
    garment_info = []
    for pid in garment_ids:
        path = os.path.join(PRODUCT_PHOTO_DIR, pid)
        if not os.path.exists(path):
            continue
        garment_info.append({"photo_id": pid, "path": path, "position": "左胸前", "garment_type": ""})

    # 如果有豆包 vision，尝试分析每件服装的类型和推荐位置
    if garment_paths:
        try:
            product_info = json.loads(ad.product_info) if isinstance(ad.product_info, str) else {}
            analysis_text = analyze_product_images(
                image_paths=garment_paths + [logo_path],
                product_name=product_info.get("name", ""),
                product_category=product_info.get("category", ""),
            )
            # 从分析文本中尝试提取服装类型和位置信息
            logger.info(f"Composite preview analysis done, text length: {len(analysis_text)}")
        except Exception as e:
            logger.warning(f"Vision analysis for composite failed: {e}")

    # 执行合成
    items = []
    for gi in garment_info:
        out = composite_logo_to_garment(
            garment_path=gi["path"],
            logo_path=logo_path,
            position=gi["position"],
            output_dir=PRODUCT_PHOTO_DIR,
        )
        photo_id = os.path.basename(out) if out else gi["photo_id"]
        items.append(CompositePreviewItem(
            photo_id=photo_id,
            photo_url=_photo_url(photo_id),
            garment_type=gi["garment_type"],
            position=gi["position"],
            logo_visible=True,
            confirmed=False,
        ))

    return CompositePreviewResponse(ad_id=ad_id, items=items)


@router.post("/{ad_id}/retry-composite", response_model=CompositePreviewResponse)
def retry_composite(
    ad_id: int,
    body: dict = None,
    db: Session = Depends(get_db),
):
    """重新合成商标，可指定新的落标位置。"""
    from app.services.compositor import composite_logo_to_garment

    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="草稿不存在")

    positions = (body or {}).get("positions", {})
    photo_ids = json.loads(ad.photo_ids) if isinstance(ad.photo_ids, str) else (ad.photo_ids or [])

    # 找商标图
    logo_photo_id = None
    garment_ids = []
    for pid in photo_ids:
        lower = pid.lower()
        if any(kw in lower for kw in ["logo", "label", "商标", "标", "tag"]):
            logo_photo_id = pid
        else:
            garment_ids.append(pid)

    if not logo_photo_id:
        raise HTTPException(status_code=400, detail="未找到商标照片")

    logo_path = os.path.join(PRODUCT_PHOTO_DIR, logo_photo_id)
    ad.composite_retry_count = (ad.composite_retry_count or 0) + 1
    db.commit()

    items = []
    for pid in garment_ids:
        pos = positions.get(pid, "左胸前")
        garment_path = os.path.join(PRODUCT_PHOTO_DIR, pid)
        if not os.path.exists(garment_path):
            continue
        out = composite_logo_to_garment(
            garment_path=garment_path,
            logo_path=logo_path,
            position=pos,
            output_dir=PRODUCT_PHOTO_DIR,
        )
        photo_id = os.path.basename(out) if out else pid
        items.append(CompositePreviewItem(
            photo_id=photo_id,
            photo_url=_photo_url(photo_id),
            garment_type="",
            position=pos,
            logo_visible=True,
            confirmed=False,
        ))

    return CompositePreviewResponse(ad_id=ad_id, items=items)


@router.post("/{ad_id}/confirm-composite")
def confirm_composite(ad_id: int, body: CompositeConfirmRequest, db: Session = Depends(get_db)):
    """确认商标合成结果。"""
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="草稿不存在")
    ad.composite_confirmed = True
    ad.composite_photo_ids = json.dumps(body.photo_ids, ensure_ascii=False)
    db.commit()
    logger.info(f"Composite confirmed for ad {ad_id}: {len(body.photo_ids)} photos")
    return {"message": "合成已确认", "ad_id": ad_id}


# ==============================================================
# 生成带货剧本（步骤 2）
# ==============================================================

def _generate_ad_script(product: ProductInfoRequest, user_feedback: str = "",
                         image_description: str = None,
                         creative_params: dict = None) -> dict:
    """生成带货剧本（可接受用户补充要求）。

    Args:
        image_description: 预先计算的图片分析结果（多版本生成时共享），为 None 时自动计算
        creative_params: 指定创意参数（视觉展示模式下覆盖随机选择）
    """
    from app.services.deepseek_client import chat_json
    from app.services.doubao_vision_client import analyze_product_images

    # 图片分析（支持共享）
    if image_description is None:
        image_paths = []
        for pid in product.photo_ids:
            if not pid:
                continue
            img_path = os.path.join(PRODUCT_PHOTO_DIR, pid)
            if os.path.exists(img_path):
                image_paths.append(img_path)
        image_description = ""
        if image_paths:
            try:
                image_description = analyze_product_images(
                    image_paths=image_paths,
                    product_name=product.name,
                    product_category=product.category,
                )
                logger.info(f"Doubao vision analysis done, desc length: {len(image_description)}")
            except Exception as e:
                logger.exception(f"Doubao vision analysis failed: {e}")
                image_description = f"（图片分析失败: {e}，请根据商品信息生成剧本）"
    else:
        image_paths = [os.path.join(PRODUCT_PHOTO_DIR, pid) for pid in product.photo_ids if pid and os.path.exists(os.path.join(PRODUCT_PHOTO_DIR, pid))]
        if not image_paths:
            image_paths = []

    visual_style_text = "真人实景拍摄，真人出镜或产品实拍展示" if product.visual_style == "realistic" else "动漫风格，二维动画展示产品"
    style_note = "写实、真实产品展示" if product.visual_style == "realistic" else "二次元动漫风格"

    creative_params = creative_params or None
    if product.showcase_style == "visual":
        if creative_params is None:
            creative_params = _pick_random()
        logger.info(f"Creative params: location={creative_params['location'][:40]}..., "
                    f"lighting={creative_params['lighting'][:30]}..., "
                    f"camera={creative_params['camera_style'][:30]}..., "
                    f"hook={creative_params['opening_hook'][:30]}...")
        system = _build_visual_system_prompt(product, style_note, creative_params)
    else:
        system = _build_story_system_prompt(product, style_note)

    image_section = ""
    if image_description:
        image_section = f"""
===== 商品图片视觉分析（由 AI 视觉模型识别）=====

{image_description}

===== 视觉分析结束 =====
"""

    user_feedback_section = ""
    if user_feedback:
        user_feedback_section = f"""
===== 用户补充要求 =====

{user_feedback}

===== 补充要求结束 =====
"""

    prompt = f"""{image_section}{user_feedback_section}Based on the above visual analysis of {len(image_paths)} product photos, create a short e-commerce video script.

IMPORTANT: The visual analysis above describes EXACTLY what the product looks like in the uploaded photos.
- Product appearance (color, shape, material, details): strictly follow the analysis, do NOT invent features.
- Scene backgrounds: do NOT copy the photo's plain studio background. Use ONE unified real-world location for the whole video.

Product info:
- Name: {product.name}
- Category: {product.category}
- Description: {product.description}
- Selling points: {product.selling_points}
- Target audience: {product.target_audience}
- Showcase mode: {'Visual showcase (no dialogue)' if product.showcase_style == 'visual' else 'Story-driven drama'}

CRITICAL RULES:
1. **PRODUCT FIRST**: The product must be clearly visible in every scene. Lighting and setting must serve product clarity — the product's true colors, texture, and details must be accurately shown. Do NOT sacrifice visibility for atmosphere.
2. Product features (product_focus) must reference actual features from the visual analysis.
3. ALL scenes in ONE unified real-world location — a place where people would naturally use/wear this product (e.g. office, coffee shop, living room, city street, park). NOT stage-like settings (art gallery, rooftop, beach boardwalk, photo studio). NEVER use plain/solid color backgrounds.
4. **LOGO**: If the product has a visible brand logo/trademark, let it appear naturally on the product during regular shots. Do NOT dedicate a close-up just for the logo — avoid obvious label-pushing shots.
5. **SCENE COHERENCE**: Adjacent scenes must flow naturally — action/movement/pose continuity, consistent gaze direction, coherent camera movement direction.
6. Total video duration: ~15 seconds.
7. **AI EXECUTABILITY**: All visual descriptions must be achievable by an AI video model. ONLY macro-level actions (walking, turning, standing, sitting, raising arms). NEVER describe finger-level micro-actions (flipping collar, turning button, picking thread, rubbing with fingers). Banned camera angles: inside collar, inside hem, inside pocket — AI cannot render these. Each scene = ONE continuous shot; no multi-cut within a scene.
8. **SHOT DISTRIBUTION**: ONLY scene 1 may be a close-up. Scenes 2-7 MUST be medium or full-body shots. At least 2 full-body shots required. The final scene must NOT be a close-up.

Style hint (LOW PRIORITY — lightly influence the shoot atmosphere only; the product visual analysis above is the primary creative driver, the setting must serve the product, not the style): {product.style_preference or 'None'}

Return ONLY the JSON."""
    result = chat_json(prompt, system=system, temperature=0.7, max_tokens=4096)
    result["visual_style"] = product.visual_style
    result["showcase_style"] = product.showcase_style
    result["image_description"] = image_description
    return result


def _generate_ad_script_variants(product: ProductInfoRequest, num_variants: int,
                                  user_feedback: str = "", image_description: str = None) -> list:
    """并行生成多个剧本变体，共享一次图片分析。

    每个变体使用不同的随机创意参数（视觉展示模式下），
    独立经过 auto-review 评审。
    """
    # 首次调用时计算图片分析，后续共享
    from app.services.deepseek_client import chat_json
    from app.services.doubao_vision_client import analyze_product_images

    if image_description is None:
        image_paths = []
        for pid in product.photo_ids:
            if not pid:
                continue
            img_path = os.path.join(PRODUCT_PHOTO_DIR, pid)
            if os.path.exists(img_path):
                image_paths.append(img_path)
        image_description = ""
        if image_paths:
            try:
                image_description = analyze_product_images(
                    image_paths=image_paths,
                    product_name=product.name,
                    product_category=product.category,
                )
                logger.info(f"Doubao vision analysis (shared) done, desc length: {len(image_description)}")
            except Exception as e:
                logger.exception(f"Doubao vision analysis failed: {e}")
                image_description = f"（图片分析失败: {e}，请根据商品信息生成剧本）"

    # 为每个变体分配一个"变体描述"：展示风格/创意参数的简短标识
    variant_labels = []
    for i in range(num_variants):
        label = f"方案{i+1}"
        if product.showcase_style == "visual":
            cp = _pick_random()
            label += f" · {cp['opening_hook'][:12]}..."
        if product.style_preference:
            short = product.style_preference.split("：")[0] if "：" in product.style_preference else product.style_preference[:8]
            label += f" · {short}"
        variant_labels.append(label)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _gen_one(idx):
        from app.services.script_writer import auto_review_loop, auto_review_loop_visual
        cp = _pick_random() if product.showcase_style == "visual" else None
        script = _generate_ad_script(
            product, user_feedback=user_feedback,
            image_description=image_description,
            creative_params=cp,
        )
        # 独立评审
        try:
            showcase = script.get("showcase_style", "story")
            if showcase == "visual":
                loop_result = auto_review_loop_visual(script)
            else:
                loop_result = auto_review_loop(script)
            script = loop_result["script"]
            script["_review"] = loop_result["review"]
            script["_review_score"] = loop_result["review"].get("overall_score")
        except Exception:
            logger.exception(f"Variant {idx} auto review failed")
            script["_review"] = None
            script["_review_score"] = None
        # 镜头硬约束代码级校验（兜底：prompt 约束不可靠）
        try:
            violations = _validate_shot_constraints(script)
            if violations:
                logger.warning(f"Variant {idx} has {len(violations)} constraint violations: {[v['detail'][:40] for v in violations]}")
                script = _fix_constraint_violations(script, violations)
                # 再跑一次评审更新分数
                if showcase == "visual":
                    from app.services.script_writer import review_visual_script
                    script["_review"] = review_visual_script(script)
                else:
                    from app.services.script_writer import review_script
                    script["_review"] = review_script(script)
                script["_review_score"] = script["_review"].get("overall_score")
                # 再校验一次，仅记日志不反复修
                remaining = _validate_shot_constraints(script)
                if remaining:
                    logger.warning(f"Variant {idx} still has {len(remaining)} violations after fix")
        except Exception:
            logger.exception(f"Variant {idx} constraint validation failed")
        script["_variant_label"] = variant_labels[idx]
        script["_variant_index"] = idx
        return script

    with ThreadPoolExecutor(max_workers=min(num_variants, 3)) as ex:
        futures = [ex.submit(_gen_one, i) for i in range(num_variants)]
        variants = []
        for f in as_completed(futures):
            variants.append(f.result())
    # 按 index 排序保持顺序
    variants.sort(key=lambda v: v.get("_variant_index", 0))
    logger.info(f"Generated {len(variants)} script variants")
    return variants, variant_labels


# ==============================================================
# 镜头约束后处理校验（代码级兜底，不依赖 LLM 自觉遵守）
# ==============================================================

_CLOSEUP_KEYWORDS = ["特写"]
_BANNED_ANGLE_KEYWORDS = ["内侧", "内侧视角", "领口内", "下摆内", "口袋内"]
_MICRO_ACTION_KEYWORDS = ["翻开", "翻起", "捏住", "捻", "指尖", "手指划过", "揉搓", "轻抚", "从喉结", "划过锁骨", "手指轻"]
_MULTI_CUT_KEYWORDS = ["跳切", "三连切", "快速切换", "交替切", "连续切换"]


def _validate_shot_constraints(script: dict) -> list:
    """检查剧本的镜头分布硬约束，返回违规列表."""
    violations = []
    scenes = script.get("scenes", [])
    if not scenes:
        return violations

    # 1. 特写数量：最多 1 个且仅限第 1 镜
    closeup_scenes = []
    for s in scenes:
        angle = s.get("camera_angle", "") or ""
        if any(kw in angle for kw in _CLOSEUP_KEYWORDS):
            closeup_scenes.append(s["scene"])

    if len(closeup_scenes) > 1:
        violations.append({
            "severity": "error",
            "detail": f"全片有 {len(closeup_scenes)} 个特写（场景 {closeup_scenes}），最多允许 1 个特写且仅限第 1 镜"
        })
    if len(closeup_scenes) == 1 and closeup_scenes[0] != 1:
        violations.append({
            "severity": "error",
            "detail": f"唯一的特写在场景 {closeup_scenes[0]}，不在第 1 镜"
        })

    # 2. 全景数量：至少 2 个
    full_count = sum(1 for s in scenes if "全景" in (s.get("camera_angle", "") or ""))
    if full_count < 2:
        violations.append({
            "severity": "error",
            "detail": f"全片只有 {full_count} 个全景，至少需要 2 个全景"
        })

    # 3. 禁止的内侧/微观视角（同时检查 camera_angle 和 action）
    for s in scenes:
        angle = s.get("camera_angle", "") or ""
        action = s.get("action", "") or ""
        for kw in _BANNED_ANGLE_KEYWORDS:
            if kw in angle or kw in action:
                violations.append({
                    "severity": "error",
                    "detail": f"场景 {s['scene']} 包含禁止词「{kw}」: {action[:60] or angle[:60]}"
                })

    # 4. 禁止的手指级微观动作
    for s in scenes:
        action = s.get("action", "") or ""
        for kw in _MICRO_ACTION_KEYWORDS:
            if kw in action:
                violations.append({
                    "severity": "error",
                    "detail": f"场景 {s['scene']} action 包含禁止微观动作「{kw}」: {action[:80]}"
                })

    # 5. 禁止的多镜头拼接
    for s in scenes:
        text = (s.get("action", "") or "") + (s.get("camera_angle", "") or "")
        for kw in _MULTI_CUT_KEYWORDS:
            if kw in text:
                violations.append({
                    "severity": "error",
                    "detail": f"场景 {s['scene']} 包含禁止的多镜头拼接「{kw}」"
                })
                break

    return violations


def _fix_constraint_violations(script: dict, violations: list) -> dict:
    """违反硬约束时，迭代修正直到全部合规（最多 3 轮）."""
    from app.services.script_writer import revise_visual_script

    current = dict(script)
    for attempt in range(3):
        detail_str = "\n".join(f"- {v['detail']}" for v in violations)
        fix_review = {
            "overall_score": 5.0,
            "summary": f"第 {attempt+1} 轮修复：以下镜头分布违规必须全部修复，否则剧本不可用",
            "weaknesses": [v["detail"] for v in violations],
            "suggestions": [
                "将多余的 close-up 改为 medium shot 或 full shot，只保留第 1 镜为 close-up",
                "确保至少 2 个全景镜头（模特全身从头到脚完整出镜）",
                "删除所有内侧视角和微观动作描述，改为宏观动作",
                "每镜保持一个连续镜头，删除所有多镜头拼接",
            ],
            "ready_for_video": False,
            "dimensions": {
                "shot_distribution": {"score": 3, "note": detail_str[:200]}
            }
        }
        current = revise_visual_script(current, fix_review)
        # 重新验证
        remaining = _validate_shot_constraints(current)
        if not remaining:
            logger.info(f"Constraint fix全部合规 (attempt {attempt+1})")
            return current
        violations = remaining
        logger.warning(f"Constraint fix第 {attempt+1} 轮后仍有 {len(remaining)} 条违规，继续修正")
    # 3 轮后仍有违规，记录日志但接受结果
    logger.warning(f"Constraint fix 3 轮后仍有 {len(violations)} 条违规未修复")
    return current


def _build_dimension_feedback_prompt(improve_dimensions: list, current_dimension_scores: dict = None) -> str:
    """将用户勾选的改进维度转换为结构化提示词片段."""
    if not improve_dimensions:
        return ""
    dim_prompts = {
        "hook_strength": "开场吸引力：请重构第一镜，使其在 0.5 秒内抓住注意力——动态入场/细节冲击/光影反差/对比转身四选一",
        "info_density": "信息密度：每镜必须传递至少 2 个产品信息点（外观+质感、版型+垂坠、细节+工艺等组合）",
        "product_persuasion": "产品说服力：卖点通过画面本身传递而非文字，让用户看完产生「想要」的冲动",
        "visual_diversity": "视觉多样性：景别/角度/运镜必须有明显交替，打破模板感，远中近特交替使用",
        "scene_flow": "场景衔接：相邻镜头动作/视线/运镜方向必须自然衔接，避免跳跃感",
        "ai_executability": "AI 可执行性：所有视觉描述具体到 Seedance 可直接理解，避免抽象概念",
        "story_completeness": "故事完整性：起承转合完整，前 3 秒有钩子，全程有推动力",
        "character_depth": "角色深度：角色有辨识度和记忆点，台词有个性",
        "scene_logic": "场景逻辑：场景衔接自然，情绪递进合理，因果关系清晰",
        "visual_feasibility": "视觉可行性：所有描述必须 AI 可生成，具体可执行",
        "dialogue_quality": "对白质量：口语化自然，有个性有记忆点",
        "pacing": "节奏把控：快慢得当，全程不拖沓",
    }
    result = "\n===== 用户指定的改进维度 =====\n"
    for dim in improve_dimensions:
        prompt_text = dim_prompts.get(dim, f"改进维度: {dim}")
        score_text = ""
        if current_dimension_scores and dim in current_dimension_scores:
            s = current_dimension_scores[dim]
            if isinstance(s, dict):
                s = s.get("score", "?")
            score_text = f"（当前评分: {s}）"
        result += f"- **{prompt_text}** {score_text}\n"
    result += "\n请优先针对以上维度进行优化，每条 criticized 点必须在修改中体现。\n=====\n"
    return result


def _build_visual_system_prompt(product, style_note, creative_params=None):
    if creative_params is None:
        creative_params = _pick_random()

    location = creative_params["location"]
    lighting = creative_params["lighting"]
    camera_style = creative_params["camera_style"]
    opening_hook = creative_params["opening_hook"]
    category_strategy = _get_category_strategy(product.category)

    return f"""你是一名抖音电商短视频创意导演，擅长在 15 秒内用纯视觉语言让用户产生购买欲望。你的视频完播率和转化率在团队里排名第一。

## 🎬 本次拍摄创意方向（每次随机组合，避免同质化）

**指定场景（必须使用）**：{location}
**指定光线风格（必须遵循）**：{lighting}
**指定运镜风格（必须遵循）**：{camera_style}
**指定开场方式（必须遵循）**：{opening_hook}

{category_strategy}

## ⚠️ 铁律 — 场景服务于产品使用场景，不是风景片
- 指定的拍摄场景是产品**使用场景**的载体，不是"找个好看的背景走秀"
- 场景的氛围/光线/布局必须让用户想象自己**在使用这个产品时的状态**
- 例如衬衫：办公室场景凸显版型正式 → 休闲场景凸显百搭 → 居家场景凸显舒适
- **如果指定的背景是纯风景（天台/海边/画廊），请主动赋予它一个产品使用场景的理由**（如"在天台参加朋友聚会时穿的衬衫"）

## 场景叙事框架（每镜必须有明确的"卖点任务"）
15 秒内完成「吸引 → 信任 → 欲望 → 行动」的心理旅程。
每个场景只能承担 1 个核心任务，禁止重复：

| 场景 | 任务 | 说明 |
|------|------|------|
| **第 1 镜** | **钩子 — 第一帧抓人** | 不是"模特开始走路"！必须是产品本身的视觉冲击——面料回弹/版型对比/质感特写/动态瞬间。0.5 秒内让用户舍不得划走 |
| **第 2~3 镜** | **信任 — 证明品质** | 具体卖点验证：抗皱测试/透气感/缝线细节/面料拉伸。用户看完觉得"做工不错" |
| **第 4~5 镜** | **欲望 — 上身效果** | 完整版型展示，动态垂坠感，整体穿搭效果。让用户想象"我穿上也是这样" |
| **第 6~7 镜** | **场景共鸣或收尾** | 穿着场景融入（商务/约会/日常），或 CTA。让用户觉得"我需要一件这样的" |

注意：如果只有 5 镜，合并第 6~7 镜的任务到第 4~5 镜中。

## 卖点差异化 — 相邻场景禁止重复展示同一卖点
- 每个场景的 product_focus 必须是**不同**的卖点维度
- 反例：场景 1 讲面料纹理 → 场景 2 还讲面料纹理 ❌
- 正例：场景 1 讲版型轮廓 → 场景 2 讲面料回弹 → 场景 3 讲缝线工艺 ✓
- 最后一个场景的 product_focus 必须概括整体上身效果（不重复具体细节卖点）

## 第一镜要求（完播率生死线）
- **禁止**：模特从远处走来、模特侧身站立、背影开场、空镜头
- **必须**：第一帧就是产品的高信息量画面——面料动态特写/版型对比/产品回弹/细节冲击
- 开场方式 '{opening_hook}' 必须被实现，但不能牺牲产品信息的传达

## 景别分布硬约束（极其重要，优先级高于所有其他要求）
- **🚫 全片最多只有第 1 镜可以是特写/微距**，第 2~7 镜全部必须是中景或全景。最后收尾镜禁止特写。
- **✅ 至少 2 个场景必须是全景**（模特全身从头到脚完整出镜），至少 2 个场景必须是中景（膝盖以上）。
- 景别递进逻辑：特写(第1镜钩子) → 中景(2~3信任) → 全景(4~5欲望) → 中景(6~7收尾)
- **违反此规则的剧本将被直接淘汰**。
- 每个场景 = 一个连续镜头，禁止在同一场景内写"三连切""跳切""快速切换"等多镜头拼接。

## AI 可执行性 — 所有描述必须在 AI 视频模型能力范围内
- **禁止**：手指级微操（翻开领口、翻转纽扣、翻开下摆、手指从喉结划到锁骨、指尖捏住某物、揉搓面料、手指划过某处）
- **禁止**：身体特殊视角（领口内侧、下摆内侧、口袋内部），AI 视频模型无法生成这些视角
- **允许**：宏观动作（自然站立、行走、转身、抬手、坐下、整理袖口、手插兜）
- **特写的定义**：特写以大部位为载体（胸部面料纹理、袖口区域褶皱、肩部缝线），不能是手指/纽扣级别
- 每个镜头的 action 必须直接服务于该镜的 product_focus

## 镜头多样性格要求（在中景/全景范围内实现）
- 角度必须有变化（均在中景/全景内）：正面/侧面/背面/3-4 角度/低角度/高角度至少使用 4 种
- 运镜必须有节奏：固定/推近/环绕/跟随/升降至少使用 3 种，按照上述指定运镜风格的节奏来分配
- 每镜的 camera_angle 必须写出角度+运镜（如"3/4 侧面，缓慢推近"）。注意：不用写景别，因为大多已是中景/全景。

## 镜头连贯性
- 相邻场景动作/视线/运镜方向衔接自然
- 最后一镜必须是倒数第二镜动作的自然延伸

## 模特出镜要求
- 每个镜头中模特必须完整、清晰出镜，产品始终穿在模特身上
- 特写必须以模特身体为载体（如特写左胸刺绣时需同时包含身体轮廓）
- 严禁空衣架、悬浮衣物、平铺展示

## 肖像权规避
- 模特面部描述用通用特征词汇，严禁使用明星/艺人姓名
- 面部特征保持中性、通用，不具有可识别的个人特征

## 场景背景
- 必须使用上述指定场景，所有场景在同一实景环境内的不同区域
- 禁止纯色背景/摄影棚/白墙/红砖墙/水泥墙

## LOGO 要求
- 商品上如有品牌商标/图案，在拍摄中自然出现即可，不需要专门大特写

输出 JSON 结构：
{{
  "title": "...", "product": "...", "genre": "带货/穿搭展示", "theme": "...",
  "showcase_style": "visual", "visual_style": "{product.visual_style}",
  "setting": "上述指定场景的详细描述",
  "scenes": [{{"scene": 1, "camera_angle": "...", "action": "...", "product_focus": "...", "duration_seconds": 2}}],
  "duration_estimate": 15, "tags": [], "background_music": "..."
}}"""


def _build_story_system_prompt(product, style_note):
    return f"""你是一名头部 MCN 创意总监，擅长制作"看了就想买"的电商短视频。
## 镜头连贯性（极其重要）
- 相邻场景之间必须有动作或视线连贯性，不能是割裂的独立镜头
- 每个场景的 action/narration 必须自然承接上一个场景的结尾，形成流畅的视觉叙事流
- 景别变化遵循递进逻辑：远→中→近→特→中→远，相邻景别跨度不超过两级
- 运镜方向在相邻场景间保持一致流向
- 模特/主体的姿态和视线在相邻场景间保持连贯
- **最后一镜衔接规则（极其重要）**：最后一镜的动作必须是倒数第二镜动作的自然延伸，严禁在最后一镜另起一个全新的动作或姿态。倒数第二镜的结尾必须已经启动了最后一镜的动作（如转身、迈步、抬手等），让两镜之间过渡毫无痕迹。倒数第二镜禁止以静态定格结束——必须包含一个微小的动态信号，为最后一镜做铺垫
- **运镜衔接规则**：相邻镜头的运镜方式不得突变。固定镜头后不能直接接运动镜头；若前一镜为固定，下一镜开头必须也是固定，随后再缓慢启动运动。同理，运动镜头的收尾速度应放缓，为下一镜留出衔接空间
## 模特出镜要求（极其重要）
- 每个镜头中模特必须完整、清晰出镜，严禁出现只有衣服/产品而没有模特的镜头
- 模特从头到尾穿着展示的商品，商品始终穿在模特身上
- 即使是特写镜头（如面料、图案细节），也必须以模特身体为载体——画面中必须同时包含模特的身体轮廓和穿着状态
- 严禁出现空衣架、悬浮衣物、平铺展示等无模特的画面
## 肖像权规避（法律合规要求）
- 模特的面部描述必须使用通用、匿名化的特征词汇，严禁使用任何真实明星、艺人、公众人物的姓名或外号
- 禁止在剧本中暗示模特与任何真实人物相似
- 模特整体气质为"专业商业广告模特"，面部特征保持中性、通用，不具有可识别的个人特征
## 黄金开场
痛点直击 / 结果展示 / 悬念提问 / 冲突引入
## 产品展示体系
场景 1-2：建立需求 → 场景 3-5：产品解决方案 → 场景 6-7：信任建立 → 场景 8：CTA
## 场景背景设计
- 禁止纯色背景/摄影棚/白墙
- 所有场景在同一实景环境中（禁止红砖墙/水泥墙）
- 优选室内或半室内柔光环境（精品买手店、艺术展厅、阳光房、loft公寓、咖啡馆、商场中庭、酒店大堂落地窗旁、屋顶花园黄昏光），避免强烈直射阳光或昏暗环境
- 同一环境内不同区域变化
## LOGO 要求
- 商品上有品牌商标/图案，仅用1个短特写（≤1.5秒）在第4或第5个场景自然展示即可
- 其余场景不需要刻意展示商标，让商标作为产品自然细节融入
## 对白
自然口语化，像朋友推荐
输出 JSON 结构：
{{
  "title": "...", "product": "...", "genre": "带货/评测/好物推荐", "theme": "...",
  "showcase_style": "story", "visual_style": "{product.visual_style}",
  "setting": "统一场景环境描述",
  "characters": [{{"name": "...", "role": "...", "description": "..."}}],
  "scenes": [{{"scene": 1, "location": "...", "narration": "...", "dialogues": [], "product_focus": "...", "shot_type": "中景", "duration_seconds": 2}}],
  "duration_estimate": 15, "tags": [], "cta": "行动号召"
}}"""


@router.post("/generate-script", status_code=201)
def generate_ad_script(body: ProductInfoRequest, db: Session = Depends(get_db)):
    """生成带货剧本（支持多版本对比）。

    如果 num_variants > 1，并行生成多个变体供用户对比选择（recommended: 3）。
    如果已存在同商品草稿（ad_id 可选），则更新而非新建。
    """
    if not body.name and not body.description:
        raise HTTPException(status_code=400, detail="请提供商品名称或描述")

    num_variants = max(1, min(body.num_variants or 1, 3))

    if num_variants > 1:
        # 多版本生成：并行生成 + 独立评审
        variants, labels = _generate_ad_script_variants(body, num_variants)
        script_data = variants[0]  # 默认选第一个
        review_data = script_data.get("_review") or {}
        review_score = review_data.get("overall_score")
        review_detail = json.dumps(review_data, ensure_ascii=False) if review_data else None
        # 序列化所有变体（去掉 _review 中的冗余大字段以节省空间）
        serializable_variants = []
        for v in variants:
            sv = {k: v for k, v in v.items() if not k.startswith("_")}
            sv["_review_score"] = v.get("_review_score")
            if v.get("_review"):
                sv["_review"] = v["_review"]
            sv["_variant_label"] = v.get("_variant_label")
            sv["_variant_index"] = v.get("_variant_index")
            serializable_variants.append(sv)
    else:
        # 单版本模式（原逻辑）
        from app.services.script_writer import auto_review_loop, auto_review_loop_visual
        script_data = _generate_ad_script(body)
        try:
            showcase = script_data.get("showcase_style", "story")
            if showcase == "visual":
                loop_result = auto_review_loop_visual(script_data)
            else:
                loop_result = auto_review_loop(script_data)
            script_data = loop_result["script"]
            review_score = loop_result["review"].get("overall_score")
            review_detail = json.dumps(loop_result["review"], ensure_ascii=False)
        except Exception:
            logger.exception("Auto review failed, using raw script")
            review_score = None
            review_detail = None
        serializable_variants = None

    # 检查是否有 ad_id 参数（复用已有草稿）
    ad_id = getattr(body, "ad_id", None)
    if ad_id:
        ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
        if ad:
            ad.title = script_data.get("title", body.name or "商品带货视频")
            ad.product_info = json.dumps(body.model_dump(), ensure_ascii=False)
            ad.photo_ids = json.dumps(body.photo_ids, ensure_ascii=False)
            ad.script_content = json.dumps(script_data, ensure_ascii=False)
            ad.script_variants = json.dumps(serializable_variants, ensure_ascii=False) if serializable_variants else None
            ad.genre = script_data.get("genre", "带货")
            ad.status = "draft"
            ad.tags = ",".join(script_data.get("tags", [])) if isinstance(script_data.get("tags"), list) else "带货"
            ad.script_confirmed = False
            ad.review_score = review_score
            ad.review_detail = review_detail
            db.commit()
            db.refresh(ad)
            logger.info(f"Ad script updated (existing): id={ad.id}, variants={num_variants}, score={review_score}")
            return ad

    ad = ProductAd(
        title=script_data.get("title", body.name or "商品带货视频"),
        product_info=json.dumps(body.model_dump(), ensure_ascii=False),
        photo_ids=json.dumps(body.photo_ids, ensure_ascii=False),
        script_content=json.dumps(script_data, ensure_ascii=False),
        script_variants=json.dumps(serializable_variants, ensure_ascii=False) if serializable_variants else None,
        genre=script_data.get("genre", "带货"),
        status="draft",
        tags=",".join(script_data.get("tags", [])) if isinstance(script_data.get("tags"), list) else "带货",
        review_score=review_score,
        review_detail=review_detail,
    )
    db.add(ad)
    db.commit()
    db.refresh(ad)
    logger.info(f"Ad script created: id={ad.id}, title={ad.title}, variants={num_variants}, score={review_score}")
    return ad


@router.post("/{ad_id}/retry-script")
def retry_ad_script(ad_id: int, body: ScriptRetryRequest = None, db: Session = Depends(get_db)):
    """根据用户反馈重新生成带货剧本（支持结构化维度反馈）。"""
    from app.services.deepseek_client import chat_json

    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货剧本不存在")

    req_body = body or ScriptRetryRequest(ad_id=ad_id)
    feedback = req_body.feedback or ""
    improve_dims = req_body.improve_dimensions or []

    # 构建结构化维度反馈
    structured_prompt = ""
    if improve_dims:
        # 读取当前剧本的评审数据，获取各维度当前分数
        current_dims = {}
        if ad.review_detail:
            try:
                rd = json.loads(ad.review_detail) if isinstance(ad.review_detail, str) else ad.review_detail
                current_dims = rd.get("dimensions", {})
            except Exception:
                pass
        structured_prompt = _build_dimension_feedback_prompt(improve_dims, current_dims)
        logger.info(f"Structured feedback for ad {ad_id}: dimensions={improve_dims}")

    # 合并反馈：结构化维度反馈在前，自由文本在后
    combined_feedback = structured_prompt
    if feedback:
        combined_feedback += f"\n===== 用户补充要求 =====\n\n{feedback}\n=====\n"
    ad.script_user_feedback = combined_feedback
    db.commit()

    # 重新调用 DeepSeek 生成
    product_info = json.loads(ad.product_info) if isinstance(ad.product_info, str) else {}
    photo_ids = json.loads(ad.photo_ids) if isinstance(ad.photo_ids, str) else []

    # 使用合成后的照片
    if ad.composite_confirmed and ad.composite_photo_ids:
        try:
            composite_ids = json.loads(ad.composite_photo_ids)
            photo_ids = composite_ids + [p for p in photo_ids if not any(kw in p.lower() for kw in ["logo", "label", "商标", "标", "tag"])]
        except Exception:
            pass

    req = ProductInfoRequest(
        name=product_info.get("name", ""),
        category=product_info.get("category", ""),
        description=product_info.get("description", ""),
        selling_points=product_info.get("selling_points", ""),
        target_audience=product_info.get("target_audience", ""),
        style_preference=product_info.get("style_preference", ""),
        photo_ids=photo_ids,
        visual_style=product_info.get("visual_style", "realistic"),
        showcase_style=product_info.get("showcase_style", "story"),
    )
    script_data = _generate_ad_script(req, user_feedback=combined_feedback)

    # 重新评审
    try:
        showcase = script_data.get("showcase_style", "story")
        if showcase == "visual":
            from app.services.script_writer import auto_review_loop_visual
            loop_result = auto_review_loop_visual(script_data)
        else:
            from app.services.script_writer import auto_review_loop
            loop_result = auto_review_loop(script_data)
        script_data = loop_result["script"]
        ad.review_score = loop_result["review"].get("overall_score")
        ad.review_detail = json.dumps(loop_result["review"], ensure_ascii=False)
    except Exception:
        logger.exception(f"Auto review failed for ad retry {ad_id}")

    # 镜头硬约束校验 + 修正
    try:
        violations = _validate_shot_constraints(script_data)
        if violations:
            logger.warning(f"Retry ad {ad_id}: {len(violations)} constraint violations, fixing")
            script_data = _fix_constraint_violations(script_data, violations)
            # 重新评审更新分数
            if script_data.get("showcase_style", "visual") == "visual":
                from app.services.script_writer import review_visual_script
                script_data["_review"] = review_visual_script(script_data)
            else:
                from app.services.script_writer import review_script
                script_data["_review"] = review_script(script_data)
            ad.review_score = script_data["_review"].get("overall_score")
            ad.review_detail = json.dumps(script_data["_review"], ensure_ascii=False)
    except Exception:
        logger.exception(f"Constraint validation failed for retry ad {ad_id}")

    ad.script_content = json.dumps(script_data, ensure_ascii=False)
    ad.script_confirmed = False
    db.commit()
    db.refresh(ad)
    logger.info(f"Ad script retry done: id={ad_id}, score={ad.review_score}")
    return ad


@router.post("/{ad_id}/confirm-script")
def confirm_ad_script(ad_id: int, db: Session = Depends(get_db)):
    """确认带货剧本。"""
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货剧本不存在")
    ad.script_confirmed = True
    db.commit()
    logger.info(f"Script confirmed for ad {ad_id}")
    return {"message": "剧本已确认", "ad_id": ad_id}


@router.post("/{ad_id}/confirm-variant")
def confirm_ad_variant(ad_id: int, body: ConfirmVariantRequest, db: Session = Depends(get_db)):
    """用户选择某个变体并确认（多版本对比模式）。"""
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货草稿不存在")

    variants_json = ad.script_variants
    if not variants_json:
        raise HTTPException(status_code=400, detail="草稿没有多版本数据，请直接使用确认剧本")

    variants = json.loads(variants_json) if isinstance(variants_json, str) else variants_json
    if not variants or body.variant_index < 0 or body.variant_index >= len(variants):
        raise HTTPException(status_code=400, detail=f"无效的变体索引: {body.variant_index}，可用范围: 0-{len(variants)-1}")

    chosen = variants[body.variant_index]
    chosen_review = chosen.get("_review") or {}

    ad.script_content = json.dumps(chosen, ensure_ascii=False)
    ad.review_score = chosen.get("_review_score") or chosen_review.get("overall_score")
    ad.review_detail = json.dumps(chosen_review, ensure_ascii=False)
    ad.script_confirmed = True
    ad.title = chosen.get("title", ad.title or "商品带货视频")
    db.commit()
    db.refresh(ad)

    logger.info(f"Variant {body.variant_index} confirmed for ad {ad_id}, score={ad.review_score}")
    return {
        "message": f"已选择方案{body.variant_index + 1}并确认剧本",
        "ad_id": ad_id,
        "variant_index": body.variant_index,
        "review_score": ad.review_score,
    }


# ==============================================================
# 生成视频（步骤 3）
# ==============================================================

@router.post("/{ad_id}/generate-video")
def generate_ad_video(ad_id: int, resolution: str = "720p", db: Session = Depends(get_db)):
    """生成带货视频（要求剧本已确认）。"""
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货剧本不存在")

    if ad.status == "video_done":
        return {"message": "视频已存在", "ad_id": ad_id, "video_path": ad.video_path}

    if not ad.script_confirmed:
        raise HTTPException(status_code=400, detail="请先确认剧本")

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
    """生成带货视频。剧本已在确认时完成评审，此处直接使用已存储的剧本。"""
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        return
    logger.info(f"Starting video generation for ad {ad_id} (script score={ad.review_score})")
    _do_generate_ad_video(db, ad, resolution)


def _do_generate_ad_video(db, ad: ProductAd, resolution: str = "720p", script_data_override: dict = None):
    from app.services.seedance_client import seedance_client, SeedanceError

    ad.status = "generating_video"
    db.commit()

    script_data = script_data_override or (json.loads(ad.script_content) if isinstance(ad.script_content, str) else ad.script_content)
    visual_style = script_data.get("visual_style", "realistic") if isinstance(script_data, dict) else "realistic"

    # 使用合成后的照片作为参考图（优先 composite_photo_ids）
    photo_ids = []
    if ad.composite_confirmed and ad.composite_photo_ids:
        try:
            photo_ids = json.loads(ad.composite_photo_ids)
        except Exception:
            pass
    if not photo_ids:
        photo_ids = json.loads(ad.photo_ids) if isinstance(ad.photo_ids, str) else (ad.photo_ids or [])

    raw_scenes = script_data.get("scenes") or script_data.get("script") or []
    scenes = raw_scenes if isinstance(raw_scenes, list) else []
    showcase_style = script_data.get("showcase_style", "story")

    reference_urls = []
    for pid in photo_ids:
        if not pid:
            continue
        if PUBLIC_URL:
            reference_urls.append(_photo_url(pid))
        else:
            img_path = os.path.join(PRODUCT_PHOTO_DIR, pid)
            if os.path.exists(img_path):
                import base64
                with open(img_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                ext = os.path.splitext(pid)[1].lower() or ".jpg"
                mime = "image/png" if ext == ".png" else "image/jpeg"
                reference_urls.append(f"data:{mime};base64,{b64}")
            else:
                logger.warning(f"  Ref image not found: {img_path}")

    logger.info(f"Creating Seedance ad video for ad {ad.id}, ref images: {len(reference_urls)}")

    if not os.environ.get("SEEDANCE_API_KEY"):
        ad.status = "video_failed"
        ad.error_message = "SEEDANCE_API_KEY 未配置"
        db.commit()
        return

    video_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "uploads", "comic_videos",
    )
    os.makedirs(video_dir, exist_ok=True)
    output_path = os.path.join(video_dir, f"ad_{ad.id}_{datetime.utcnow():%Y%m%d_%H%M%S}.mp4")

    SEGMENT_DURATION = 15

    # 紧凑 prompt（参考图已承载产品外观细节，文本聚焦运镜/动作/合规约束）
    constraint = (
        "带货短视频：模特身穿参考图商品，面部通用无明星特征，每镜模特必须出镜。"
    )
    if visual_style == "realistic":
        suffix = "真人实拍，自然柔光，时尚摄影质感。"
    else:
        suffix = "二维动漫风格，色彩鲜明，流畅动画。"

    # 场景 → 紧凑运镜序列（每镜取景别+首句动作，→ 连接形成流畅视觉流）
    flow_parts = []
    for s in scenes:
        angle = (s.get("camera_angle", "") or "").split("，")[0].strip()
        action = (s.get("action", "") or "").split("。")[0].strip()
        if len(action) > 60:
            action = action[:60]
        part = f"{angle}，{action}" if angle and action else (angle or action)
        flow_parts.append(part)
    flow_text = " → ".join(flow_parts)

    # 追加背景音乐要求（剧本生成的 background_music 描述了风格/节奏/氛围）
    bgm = ""
    if isinstance(script_data, dict) and script_data.get("background_music"):
        bgm_text = script_data["background_music"]
        bgm = f"背景音乐：{bgm_text[:80]}。"
    combined_prompt = f"{constraint}{flow_text}。{suffix}{bgm}"
    if len(combined_prompt) > 800:
        # 超长则先砍 bgm
        combined_prompt = f"{constraint}{flow_text}。{suffix}"
        if len(combined_prompt) > 800:
            # 再超长则逐镜缩短动作描述
            flow_parts = []
            for s in scenes:
                angle = (s.get("camera_angle", "") or "").split("，")[0].strip()[:20]
                action = (s.get("action", "") or "").split("。")[0].strip()[:30]
                part = f"{angle}，{action}" if angle and action else (angle or action)
                flow_parts.append(part)
            flow_text = " → ".join(flow_parts)
            combined_prompt = f"{constraint}{flow_text}。{suffix}"
            if len(combined_prompt) > 800:
                combined_prompt = combined_prompt[:800]

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
            raise SeedanceError("No video_url returned")
        seedance_client.download_video(result["video_url"], output_path)
    except SeedanceError as e:
        ad.status = "video_failed"
        ad.error_message = str(e)
        db.commit()
        logger.error(f"Seedance failed for ad {ad.id}: {e}")
        return

    processed_path = output_path
    if script_data and isinstance(script_data, dict):
        if script_data.get("showcase_style", "story") != "visual":
            try:
                from app.services.video_postprocessor import postprocess_video
                processed = postprocess_video(output_path, script_data)
                if processed != output_path:
                    processed_path = processed
            except Exception as e:
                logger.exception(f"Post-processing failed: {e}")

    ad.video_path = processed_path
    ad.status = "video_done"
    db.commit()
    logger.info(f"Ad video done: id={ad.id}")


# ==============================================================
# 查询 & 删除
# ==============================================================

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


@router.delete("/{ad_id}")
def delete_product_ad(ad_id: int, db: Session = Depends(get_db)):
    ad = db.query(ProductAd).filter(ProductAd.id == ad_id).first()
    if not ad:
        raise HTTPException(status_code=404, detail="带货剧本不存在")
    db.delete(ad)
    db.commit()
    return {"message": "已删除", "ad_id": ad_id}
