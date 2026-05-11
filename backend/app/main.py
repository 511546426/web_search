"""漫剧视频自动化系统 · 剧本生成 + 视频生成"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import auth, comic_videos, coze_api, novels, product_ad

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BACKEND_DIR, "uploads")
FRONTEND_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "frontend")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="漫剧视频系统",
    description="自动抓取热点 → 生成剧本 → 生成视频",
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

app.include_router(auth.router)
app.include_router(comic_videos.router)
app.include_router(coze_api.router)
app.include_router(product_ad.router)
app.include_router(novels.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "message": "漫剧视频系统运行中"}


app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
# 前端静态资源（最后挂载，保证 /api、/uploads 优先）
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
