"""ezContract API 入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.llm.client import chat_text
from app.routers import draft, review

app = FastAPI(title="ezContract 智能合同 Demo API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(review.router)
app.include_router(draft.router)


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
