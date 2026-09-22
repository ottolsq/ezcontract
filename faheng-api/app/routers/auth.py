"""认证路由（Demo：单账号 + 进程内存 token 白名单）

设计取舍：
- 不引入 bcrypt/jwt 依赖；Demo 明文账号密码已在 .env 中配置；
- token 用随机 hex + 内存白名单 + TTL 过期，重启后端 token 自动失效；
- 业务路由（review/draft）通过 Depends(require_auth) 拦截。
"""
from __future__ import annotations

import secrets
import time

from fastapi import Depends, Header, HTTPException

from app.config import settings
from app.schemas.auth import LoginIn, LoginOut

# token -> (username, expires_at)
AUTH_TOKENS: dict[str, tuple[str, float]] = {}


def _new_token(username: str) -> str:
    """生成新 token 并写入白名单；同时清理过期项"""
    now = time.time()
    expires = now + settings.AUTH_TOKEN_TTL
    token = secrets.token_hex(16)
    AUTH_TOKENS[token] = (username, expires)
    # 顺手清理过期 token，避免内存只增不减
    for k, (_, exp) in list(AUTH_TOKENS.items()):
        if exp < now:
            AUTH_TOKENS.pop(k, None)
    return token


async def require_auth(authorization: str | None = Header(default=None)) -> str:
    """FastAPI 依赖：校验 Authorization: Bearer <token>，返回用户名"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    token = authorization[7:].strip()
    item = AUTH_TOKENS.get(token)
    if item is None:
        raise HTTPException(status_code=401, detail="登录凭证无效")
    username, expires = item
    if expires < time.time():
        AUTH_TOKENS.pop(token, None)
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return username


def login_router_factory():
    """工厂：路由放在模块顶层即可，但保持与项目其他 router 一致风格"""
    from fastapi import APIRouter

    router = APIRouter(prefix="/api/auth", tags=["auth"])

    @router.post("/login", response_model=LoginOut)
    async def login(body: LoginIn):
        if body.username != settings.DEMO_USERNAME or body.password != settings.DEMO_PASSWORD:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        token = _new_token(body.username)
        return LoginOut(access_token=token, username=body.username)

    @router.post("/logout")
    async def logout(authorization: str | None = Header(default=None)):
        """前端退出时调用，清掉对应 token；找不到也返回 ok（幂等）"""
        if authorization and authorization.lower().startswith("bearer "):
            AUTH_TOKENS.pop(authorization[7:].strip(), None)
        return {"ok": True}

    @router.get("/me")
    async def me(username: str = Depends(require_auth)):
        return {"username": username}

    return router


router = login_router_factory()
