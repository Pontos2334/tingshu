import logging
import time
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import init_db, async_session
from app.routers import tts, voices, audio, playlists, settings, tts_tasks, ai_generate
from app.config import settings as app_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("tingshu")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("听书 TTS 工具启动中...")
    await init_db()
    logger.info("数据库初始化完成")
    await _reset_running_tasks()
    await _init_default_templates()
    yield
    logger.info("听书 TTS 工具关闭")


async def _reset_running_tasks():
    """启动时将 running 状态的任务重置为 pending"""
    from sqlalchemy import update
    from app.db_models import SynthesisTask
    async with async_session() as db:
        result = await db.execute(
            update(SynthesisTask)
            .where(SynthesisTask.status == "running")
            .values(status="pending")
        )
        if result.rowcount > 0:
            await db.commit()
            logger.info(f"已重置 {result.rowcount} 个运行中任务为 pending")


async def _init_default_templates():
    """初始化默认提示词模板（幂等，通过 slug 唯一约束保证）"""
    from sqlalchemy import select
    from app.db_models import PromptTemplate
    async with async_session() as db:
        result = await db.execute(select(PromptTemplate).limit(1))
        if result.scalar_one_or_none():
            return

        defaults = [
            PromptTemplate(
                slug="audiobook-story",
                name="有声书故事",
                description="根据主题生成适合朗读的有声书故事",
                system_prompt="你是一位专业的有声书内容创作者。请创作适合朗读的故事内容，语言流畅自然，段落分明，富有感染力。输出纯文本，不要使用 Markdown 格式。",
                user_prompt_template="请以\"{topic}\"为主题，创作一篇约2000字的有声书故事。",
                is_default=True,
            ),
            PromptTemplate(
                slug="knowledge-popular",
                name="知识科普",
                description="生成知识科普类听书内容",
                system_prompt="你是一位科普作家。请用通俗易懂、生动有趣的语言解释科学知识，适合朗读和聆听。输出纯文本。",
                user_prompt_template="请围绕\"{topic}\"这个主题，写一篇约1500字的科普文章，适合录制成有声内容。",
            ),
            PromptTemplate(
                slug="history-story",
                name="历史故事",
                description="生成历史题材的听书内容",
                system_prompt="你是一位历史故事讲述者。请用引人入胜的方式讲述历史事件和人物故事，语言生动，适合朗读。输出纯文本。",
                user_prompt_template="请以\"{topic}\"为主题，讲述一段历史故事，约2000字。",
            ),
        ]
        db.add_all(defaults)
        await db.commit()
        logger.info("已初始化默认提示词模板")


app = FastAPI(title="听书 - TTS 工具", version="1.0.0", lifespan=lifespan)

# CORS - 仅允许本地开发和配置的来源
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"未处理的异常: {request.method} {request.url} - {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试"},
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    if request.url.path.startswith("/api/"):
        logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({duration:.3f}s)")
    return response


WRITE_METHODS = {"POST", "PUT", "DELETE"}
PROTECTED_PREFIXES = ["/api/settings", "/api/playlists", "/api/voices", "/api/audio", "/api/tts", "/api/ai"]


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method in WRITE_METHODS:
        for prefix in PROTECTED_PREFIXES:
            if request.url.path.startswith(prefix):
                if not app_settings.admin_token:
                    break
                token = request.headers.get("X-Admin-Token")
                if token != app_settings.admin_token:
                    return JSONResponse(status_code=401, content={"detail": "认证令牌无效"})
                break
    return await call_next(request)


app.include_router(tts.router, prefix="/api/tts", tags=["TTS"])
app.include_router(tts_tasks.router, prefix="/api/tts", tags=["TTS Tasks"])
app.include_router(voices.router, prefix="/api/voices", tags=["音色"])
app.include_router(audio.router, prefix="/api/audio", tags=["音频"])
app.include_router(playlists.router, prefix="/api/playlists", tags=["播放列表"])
app.include_router(settings.router, prefix="/api/settings", tags=["设置"])
app.include_router(ai_generate.router, prefix="/api/ai", tags=["AI 生成"])


@app.get("/")
async def root():
    return {"message": "听书 TTS 工具 API"}


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "tingshu-tts"}
