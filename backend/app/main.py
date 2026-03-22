"""
情侣记录站 · FastAPI 后端
对象打开网页即可看到你们的点点滴滴 💕
"""
import os
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.models import Anniversary
from app.routers import anniversaries, memories, notes, photos

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BACKEND_DIR, "uploads")
FRONTEND_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "frontend")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="情侣记录站",
    description="记录两个人的点点滴滴",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(memories.router)
app.include_router(anniversaries.router)
app.include_router(photos.router)
app.include_router(notes.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "message": "我们的小站运行中 💕"}


@app.get("/api/today-in-history")
def today_in_history():
    """今日·我们的历史：可后续按日期查 memories 表，这里先返回占位."""
    return {"message": "今天也是和你在一起的美好一天", "items": []}


@app.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    """我们在一起第 N 天：取最早的一个纪念日计算."""
    first = db.query(Anniversary).order_by(Anniversary.date.asc()).first()
    if not first:
        return {"days_together": None, "message": "还没有添加纪念日哦"}
    delta = date.today() - first.date
    return {"days_together": delta.days, "first_date": str(first.date), "name": first.name}


app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
# 前端静态资源（最后挂载，保证 /api、/uploads 优先）
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
