"""法衡 AI · 企业多智能体工作台 — API 入口（Demo）"""
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.llm.client import chat_text
from app.routers import auth, draft, review

app = FastAPI(title="法衡 AI 企业多智能体工作台 API (Demo)", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 业务路由全部走 token 校验；登录接口本身无需校验
app.include_router(auth.router)
app.include_router(review.router, dependencies=[Depends(auth.require_auth)])
app.include_router(draft.router, dependencies=[Depends(auth.require_auth)])


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
