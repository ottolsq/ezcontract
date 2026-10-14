"""语音转文字（ASR）客户端：上传浏览器录音 → 转写为文本

浏览器 MediaRecorder 产出 webm/opus（Chrome/Edge）、ogg/opus（Firefox）、
mp4/aac（Safari），统一 multipart 上传到 SiliconFlow 的
OpenAI 兼容 /audio/transcriptions 接口（SenseVoiceSmall，中文效果好）。

选型说明：浏览器原生 SpeechRecognition 依赖 Google 在线识别服务，
大陆网络下 Chrome 必然报 network 错误，故录音走后端转写。
"""
from __future__ import annotations

import io
import os

import httpx
from fastapi import HTTPException

from app.config import settings

# 浏览器常见录音容器 → 后缀（SiliconFlow 按后缀/内容识别音频格式）
_MIME_EXT_MAP = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
}

_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=60.0, pool=10.0)


def guess_ext(mime: str, filename: str | None = None) -> str:
    """从文件名或 MIME 猜音频后缀，供服务端识别格式。"""
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[1].lower()
        if ext.isalnum():
            return ext
    base = (mime or "").split(";")[0].strip().lower()
    return _MIME_EXT_MAP.get(base, "webm")


async def transcribe(data: bytes, mime: str = "", filename: str | None = None) -> str:
    """把录音二进制转写为文本；未配置 ASR_API_KEY 时给出明确指引。"""
    if not settings.ASR_API_KEY:
        raise HTTPException(
            503,
            "语音识别服务未配置：请在项目根目录 .env 中设置 ASR_API_KEY"
            "（SiliconFlow API Key，https://siliconflow.cn 注册获取），重启后端后生效",
        )
    if not data:
        raise HTTPException(400, "录音内容为空")

    ext = guess_ext(mime, filename)
    files = {"file": (f"voice.{ext}", io.BytesIO(data), mime or "application/octet-stream")}
    data_fields = {"model": settings.ASR_MODEL}

    url = settings.ASR_BASE_URL.rstrip("/") + "/audio/transcriptions"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.ASR_API_KEY}"},
                files=files,
                data=data_fields,
            )
        except httpx.HTTPError as e:
            raise HTTPException(502, f"语音识别服务连接失败：{e}") from None

    if resp.status_code != 200:
        detail = ""
        try:
            detail = resp.json().get("message") or resp.json().get("error", "")
        except Exception:  # noqa: BLE001
            detail = resp.text[:200]
        raise HTTPException(
            502,
            f"语音识别服务返回错误（{resp.status_code}）：{detail or '请稍后重试'}",
        )

    # OpenAI 兼容返回 {"text": "..."}；SenseVoiceSmall 不返回多语言标记
    try:
        text = (resp.json().get("text") or "").strip()
    except Exception:  # noqa: BLE001
        raise HTTPException(502, "语音识别服务返回格式异常") from None
    return text
