"""AI 智能题库与刷题平台 — FastAPI 主入口。"""
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .database import init_db
from .routers import auth, banks, questions, importer, practice, ai, stats

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


class NoCacheHTMLMiddleware(BaseHTTPMiddleware):
    """前端静态资源与页面一律 no-cache（协商缓存），避免旧 JS 被浏览器长期缓存。"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.startswith("/static") or not path.startswith("/api"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

app = FastAPI(
    title=settings.APP_NAME,
    description="AI 智能题库与在线刷题系统",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(NoCacheHTMLMiddleware)

app.include_router(auth.router)
app.include_router(banks.router)
app.include_router(questions.router)
app.include_router(importer.router)
app.include_router(practice.router)
app.include_router(ai.router)
app.include_router(stats.router)


@app.on_event("startup")
def on_startup():
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    init_db()


@app.get("/api/health")
def health():
    return {"ok": True, "app": settings.APP_NAME, "version": "1.0.0"}


# 静态前端
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets") \
        if (STATIC_DIR / "assets").exists() else None
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "API 服务运行中。前端文件未找到，请确认 backend/static/index.html 存在。"}


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """SPA 路由回退：非 /api 路径返回前端。"""
    from fastapi import HTTPException
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    raise HTTPException(status_code=404, detail="Not Found")
