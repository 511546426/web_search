"""AI 小说生成 API — 世界观 → 大纲 → 逐章生成."""
import json
import logging
import threading
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Novel, NovelChapter

logger = logging.getLogger("novels")

router = APIRouter(prefix="/api/comic/novels", tags=["novels"])


# ---- 创建与列表 ----

@router.post("", status_code=201)
def create_novel(body: dict, db: Session = Depends(get_db)):
    """创建新小说项目."""
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="请填写小说标题")

    novel = Novel(
        title=title,
        genre=body.get("genre", ""),
        theme=body.get("theme", ""),
        total_chapters=body.get("total_chapters", 30),
        status="draft",
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)
    logger.info(f"Novel created: id={novel.id}, title={novel.title}")
    return {
        "id": novel.id,
        "title": novel.title,
        "genre": novel.genre,
        "theme": novel.theme,
        "total_chapters": novel.total_chapters,
        "status": novel.status,
        "created_at": novel.created_at.isoformat(),
    }


@router.get("")
def list_novels(
    status: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """小说列表."""
    q = db.query(Novel).order_by(Novel.created_at.desc())
    if status:
        q = q.filter(Novel.status == status)

    novels = q.offset(skip).limit(limit).all()
    result = []
    for n in novels:
        # 统计已完成章节数
        done_chapters = (
            db.query(NovelChapter)
            .filter(NovelChapter.novel_id == n.id, NovelChapter.status == "done")
            .count()
        )
        result.append({
            "id": n.id,
            "title": n.title,
            "genre": n.genre,
            "theme": n.theme,
            "total_chapters": n.total_chapters,
            "done_chapters": done_chapters,
            "status": n.status,
            "has_outline": bool(n.outline),
            "has_world": bool(n.world_setting),
            "created_at": n.created_at.isoformat(),
            "updated_at": n.updated_at.isoformat() if n.updated_at else None,
        })
    return result


@router.get("/{novel_id}")
def get_novel(novel_id: int, db: Session = Depends(get_db)):
    """小说详情."""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail="小说不存在")

    done_chapters = (
        db.query(NovelChapter)
        .filter(NovelChapter.novel_id == novel.id, NovelChapter.status == "done")
        .count()
    )

    return {
        "id": novel.id,
        "title": novel.title,
        "genre": novel.genre,
        "theme": novel.theme,
        "total_chapters": novel.total_chapters,
        "done_chapters": done_chapters,
        "status": novel.status,
        "outline": json.loads(novel.outline) if novel.outline else None,
        "world_setting": json.loads(novel.world_setting) if novel.world_setting else None,
        "character_profiles": json.loads(novel.character_profiles) if novel.character_profiles else None,
        "world_state": json.loads(novel.world_state) if novel.world_state else None,
        "error_message": novel.error_message,
        "created_at": novel.created_at.isoformat(),
        "updated_at": novel.updated_at.isoformat() if novel.updated_at else None,
    }


@router.delete("/{novel_id}")
def delete_novel(novel_id: int, db: Session = Depends(get_db)):
    """删除小说及其所有章节."""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail="小说不存在")
    db.query(NovelChapter).filter(NovelChapter.novel_id == novel_id).delete()
    db.delete(novel)
    db.commit()
    return {"message": "已删除", "novel_id": novel_id}


# ---- 世界观生成 ----

@router.post("/{novel_id}/generate-world")
def generate_world(novel_id: int, db: Session = Depends(get_db)):
    """生成世界观和角色设定（一次性）。"""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail="小说不存在")

    from app.services.novel_writer import generate_world as _generate_world
    from json import JSONDecodeError

    def _run():
        _db = next(get_db())
        try:
            n = _db.query(Novel).filter(Novel.id == novel_id).first()
            if not n:
                return
            # 重试最多 2 次
            last_error = None
            for attempt in range(2):
                try:
                    result = _generate_world(
                        topic=f"{n.title} {n.theme or ''}",
                        genre=n.genre or "",
                        total_chapters=n.total_chapters,
                    )
                    last_error = None
                    break
                except (JSONDecodeError, Exception) as e:
                    last_error = str(e)
                    logger.warning(f"World gen attempt {attempt+1} failed: {e}")
                    continue
            if last_error:
                raise Exception(last_error)
            n.error_message = None  # 清除历史错误
            n.world_setting = json.dumps(result, ensure_ascii=False)
            if result.get("characters"):
                n.character_profiles = json.dumps(result["characters"], ensure_ascii=False)
            _db.commit()
            logger.info(f"World generated for novel {novel_id}")
        except Exception as e:
            logger.exception(f"World generation failed for novel {novel_id}: {e}")
            try:
                n = _db.query(Novel).filter(Novel.id == novel_id).first()
                if n:
                    n.status = "draft"
                    n.error_message = str(e)[:500]
                    _db.commit()
            except Exception:
                pass
        finally:
            _db.close()

    threading.Thread(target=_run, daemon=True).start()
    return {"message": "世界观生成已触发，请稍后刷新查看"}


# ---- 大纲生成 ----

@router.post("/{novel_id}/generate-outline")
def generate_outline(novel_id: int, db: Session = Depends(get_db)):
    """生成完整分章大纲（一次性）。"""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail="小说不存在")
    if not novel.world_setting:
        raise HTTPException(status_code=400, detail="请先生成世界观")

    from app.services.novel_writer import generate_outline as _generate_outline
    from json import JSONDecodeError

    def _run():
        _db = next(get_db())
        try:
            n = _db.query(Novel).filter(Novel.id == novel_id).first()
            if not n:
                return
            world = json.loads(n.world_setting) if n.world_setting else {}
            characters = json.loads(n.character_profiles) if n.character_profiles else []
            last_error = None
            for attempt in range(2):
                try:
                    result = _generate_outline(world, characters, n.total_chapters)
                    last_error = None
                    break
                except (JSONDecodeError, Exception) as e:
                    last_error = str(e)
                    logger.warning(f"Outline gen attempt {attempt+1} failed: {e}")
                    continue
            if last_error:
                raise Exception(last_error)
            n.error_message = None
            n.outline = json.dumps(result, ensure_ascii=False)
            _db.commit()
            logger.info(f"Outline generated for novel {novel_id}")
        except Exception as e:
            logger.exception(f"Outline generation failed for novel {novel_id}: {e}")
            try:
                n = _db.query(Novel).filter(Novel.id == novel_id).first()
                if n:
                    n.error_message = str(e)[:500]
                    _db.commit()
            except Exception:
                pass
        finally:
            _db.close()

    threading.Thread(target=_run, daemon=True).start()
    return {"message": "大纲生成已触发，请稍后刷新查看"}


# ---- 单章生成 ----

@router.post("/{novel_id}/generate-chapter/{chapter_num}")
def generate_chapter(novel_id: int, chapter_num: int, db: Session = Depends(get_db)):
    """评审 → 生成单章 → 入库（同步等待，返回结果）。"""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail="小说不存在")
    if not novel.outline:
        raise HTTPException(status_code=400, detail="请先生成大纲")

    from app.services.novel_writer import (
        auto_review_chapter_loop,
        update_world_state,
        collect_recent_chapters,
    )

    outline = json.loads(novel.outline) if isinstance(novel.outline, str) else (novel.outline or {})
    chapters_list = outline.get("chapters", [])
    chapter_info = next((c for c in chapters_list if c.get("number") == chapter_num), {})
    if not chapter_info:
        # 用编号生成默认信息
        chapter_info = {"number": chapter_num, "title": f"第{chapter_num}章", "summary": ""}

    prev_world_state = json.loads(novel.world_state) if novel.world_state else None
    recent_chapters = collect_recent_chapters(db, novel_id, chapter_num)
    character_profiles = json.loads(novel.character_profiles) if novel.character_profiles else []

    novel_data = {
        "world_setting": json.loads(novel.world_setting) if novel.world_setting else {},
        "character_profiles": character_profiles,
        "outline": outline,
    }

    try:
        text, review = auto_review_chapter_loop(
            novel_data, chapter_num, chapter_info, recent_chapters, prev_world_state
        )
    except Exception as e:
        logger.exception(f"Chapter generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"章节生成失败: {e}")

    # 更新世界状态
    new_world_state = update_world_state(prev_world_state, text, character_profiles)
    novel.world_state = json.dumps(new_world_state, ensure_ascii=False)

    # 入库
    existing = (
        db.query(NovelChapter)
        .filter(NovelChapter.novel_id == novel_id, NovelChapter.chapter_number == chapter_num)
        .first()
    )
    if existing:
        existing.content = text
        existing.title = chapter_info.get("title", f"第{chapter_num}章")
        existing.word_count = len(text)
        existing.status = "done"
        existing.review_score = review.get("overall_score")
        existing.review_attempts = review.get("attempts", 1)
    else:
        ch = NovelChapter(
            novel_id=novel_id,
            chapter_number=chapter_num,
            title=chapter_info.get("title", f"第{chapter_num}章"),
            content=text,
            word_count=len(text),
            status="done",
            review_score=review.get("overall_score"),
            review_attempts=1,
        )
        db.add(ch)

    # 更新小说状态
    db.flush()  # 确保新入库章节能被 count 看到
    total_done = (
        db.query(NovelChapter)
        .filter(NovelChapter.novel_id == novel_id, NovelChapter.status == "done")
        .count()
    )
    if total_done >= novel.total_chapters:
        novel.status = "completed"
    elif novel.status == "draft":
        novel.status = "publishing"

    db.commit()

    return {
        "chapter_number": chapter_num,
        "title": chapter_info.get("title", f"第{chapter_num}章"),
        "word_count": len(text),
        "review_score": review.get("overall_score"),
        "verdict": review.get("verdict"),
        "status": "done",
    }


# ---- 批量生成全部章节 ----

@router.post("/{novel_id}/generate-all")
def generate_all_chapters(novel_id: int, db: Session = Depends(get_db)):
    """后台线程逐章生成全部剩余章节."""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail="小说不存在")
    if not novel.outline:
        raise HTTPException(status_code=400, detail="请先生成大纲")

    def _run():
        from app.database import SessionLocal
        from app.services.novel_writer import (
            auto_review_chapter_loop,
            update_world_state,
            collect_recent_chapters,
        )

        _db = SessionLocal()
        try:
            n = _db.query(Novel).filter(Novel.id == novel_id).first()
            if not n:
                return

            outline = json.loads(n.outline) if isinstance(n.outline, str) else (n.outline or {})
            chapters_list = outline.get("chapters", [])
            character_profiles = json.loads(n.character_profiles) if n.character_profiles else []
            novel_data = {
                "world_setting": json.loads(n.world_setting) if n.world_setting else {},
                "character_profiles": character_profiles,
                "outline": outline,
            }

            # 找出已生成的和未生成的
            existing = {
                c.chapter_number
                for c in _db.query(NovelChapter)
                .filter(NovelChapter.novel_id == novel_id, NovelChapter.status == "done")
                .all()
            }

            for chapter_info in chapters_list:
                num = chapter_info.get("number")
                if num in existing:
                    continue
                if num > n.total_chapters:
                    break

                logger.info(f"Generating chapter {num}/{n.total_chapters}...")

                prev_world_state = json.loads(n.world_state) if n.world_state else None
                recent = collect_recent_chapters(_db, novel_id, num)

                text, review = auto_review_chapter_loop(
                    novel_data, num, chapter_info, recent, prev_world_state
                )

                new_world_state = update_world_state(prev_world_state, text, character_profiles)
                n.world_state = json.dumps(new_world_state, ensure_ascii=False)

                ch = NovelChapter(
                    novel_id=novel_id,
                    chapter_number=num,
                    title=chapter_info.get("title", f"第{num}章"),
                    content=text,
                    word_count=len(text),
                    status="done",
                    review_score=review.get("overall_score"),
                    review_attempts=1,
                )
                _db.add(ch)
                _db.commit()

                logger.info(f"Chapter {num} done, score={review.get('overall_score')}")

            n.status = "completed"
            _db.commit()
            logger.info(f"Novel {novel_id} all chapters generated!")

        except Exception as e:
            logger.exception(f"Batch generation failed for novel {novel_id}: {e}")
        finally:
            _db.close()

    threading.Thread(target=_run, daemon=True).start()
    return {"message": "全部章节生成已触发，将在后台逐章生成"}


# ---- 章节查询 ----

@router.get("/{novel_id}/chapters")
def list_chapters(novel_id: int, db: Session = Depends(get_db)):
    """章节列表."""
    chapters = (
        db.query(NovelChapter)
        .filter(NovelChapter.novel_id == novel_id)
        .order_by(NovelChapter.chapter_number.asc())
        .all()
    )
    return [
        {
            "id": c.id,
            "chapter_number": c.chapter_number,
            "title": c.title,
            "word_count": c.word_count,
            "status": c.status,
            "review_score": c.review_score,
            "created_at": c.created_at.isoformat(),
            "preview": (c.content or "")[:200],
        }
        for c in chapters
    ]


@router.get("/{novel_id}/chapters/{chapter_number}")
def get_chapter(novel_id: int, chapter_number: int, db: Session = Depends(get_db)):
    """获取单章完整内容."""
    chapter = (
        db.query(NovelChapter)
        .filter(
            NovelChapter.novel_id == novel_id,
            NovelChapter.chapter_number == chapter_number,
        )
        .first()
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    return {
        "id": chapter.id,
        "chapter_number": chapter.chapter_number,
        "title": chapter.title,
        "content": chapter.content or "",
        "word_count": chapter.word_count,
        "status": chapter.status,
        "review_score": chapter.review_score,
        "created_at": chapter.created_at.isoformat(),
    }
