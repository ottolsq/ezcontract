"""法衡 AI · 企业多智能体工作台 — API 入口（Demo）"""
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.llm.client import chat_text
from app.routers import auth, draft, review

app = FastAPI(title="法衡 AI 企业多智能体工作台 API (Demo)", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    # 公网部署时把 allowedOrigins 替换为前端域名（如 "https://fa.example.com"）。
    # 反代同源（推荐：Nginx /api/* → 127.0.0.1:58069）则可直接关闭 CORS。
    # 当前保留本地 dev origin 以便本机调试。
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:58068",
        "http://127.0.0.1:58068",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 业务路由全部走 token 校验；登录接口本身无需校验
app.include_router(auth.router)
app.include_router(review.router, dependencies=[Depends(auth.require_auth)])
app.include_router(draft.router, dependencies=[Depends(auth.require_auth)])

# 部署形态：单容器由 uvicorn 同时 serve 前端 build 产物
# （本地 dev 形态：web_dist/ 不存在，StaticFiles 不挂载，行为不变）
WEB_DIST = Path(__file__).resolve().parent.parent / "web_dist"
if WEB_DIST.is_dir():
    # 必须在所有 /api 路由 include 之后挂载，避免拦截 API 请求
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")


@app.get("/api/health")
async def health():
    """探活：含一次 LLM 网关连通性检查"""
    llm_status = "ok"
    llm_error = None
    try:
        reply = await chat_text(
            [{"role": "user", "content": "回复：OK"}], temperature=0, max_tokens=500
        )
        if not reply.strip():
            llm_status, llm_error = "empty", "LLM 返回为空"
    except Exception as e:  # noqa: BLE001
        llm_status, llm_error = "error", str(e)[:200]
    return {
        "status": "ok",
        "llm": llm_status,
        "llm_model": settings.LLM_MODEL,
        "llm_error": llm_error,
    }
