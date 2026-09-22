"""认证相关 pydantic 模型（Demo 登录）"""
from __future__ import annotations

from pydantic import BaseModel


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    """登录成功：返回 token + 用户名（前端用用户名展示）"""

    access_token: str
    token_type: str = "bearer"
    username: str
