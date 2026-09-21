"""LLM 客户端：OpenAI 兼容网关封装 + 结构化 JSON 输出（清洗/重试/截断抢救）

经验继承自 Docspect 的 riskDetectionService：三段式 JSON 处理
1. clean: 去 ```json 围栏 → 定位首个 { / [ → json.loads
2. fix: 去尾逗号再试
3. salvage: 截断时取最后完整对象补齐括号，逐元素校验丢弃残缺项
"""
from __future__ import annotations

import json
import re
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.config import settings

T = TypeVar("T", bound=BaseModel)

MAX_ATTEMPTS = 3  # 1 次原始 + 2 次重试

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            timeout=180.0,
        )
    return _client


class LLMFormatError(Exception):
    """LLM 输出经多次尝试仍无法解析为目标 schema"""


def _clean(raw: str) -> str:
    """去掉 markdown 围栏与前导杂文"""
    if not raw:
        return ""
    s = raw.replace("```json", "").replace("```", "").strip()
    m = re.search(r"[\[{]", s)
    if m and m.start() > 0:
        s = s[m.start() :]
    return s.strip()


def _try_loads(s: str):
    """json.loads + 尾逗号修复"""
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        fixed = re.sub(r",\s*([\]}])", r"\1", s)
        return json.loads(fixed)
    except (json.JSONDecodeError, ValueError):
        return None


def _salvage_array(cleaned: str) -> list | None:
    """截断抢救：从残缺 JSON 中救回完整的数组元素。

    仅适用于顶层为 {..., "risks": [ {...}, {...}(截断) } 之类的结构。
    做法：找最后一个完整闭合的元素边界，截到最后一个 } 后补 ]}。
    """
    try:
        last_brace = cleaned.rfind("}")
        if last_brace == -1:
            return None
        salvaged = cleaned[: last_brace + 1]
        # 定位数组起点（"risks":[ 或顶层 [）
        arr_start = salvaged.find("[")
        if arr_start == -1:
            return None
        head = salvaged[:arr_start]  # 可能是 {"risks":
        # 尝试补齐成合法 JSON
        if head.lstrip().startswith("{"):
            # 对象包裹：{"risks":[...}  → 补 ]}
            attempt = head + salvaged[arr_start:] + "]}"
            data = _try_loads(attempt)
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        return v
                return None
        # 顶层数组：[...} → 补 ]
        attempt = salvaged[arr_start:] + "]"
        data = _try_loads(attempt)
        return data if isinstance(data, list) else None
    except Exception:
        return None


async def chat_text(
    messages: list[dict],
    temperature: float = 0.0,
    max_tokens: int = 4000,
    strip_emoji: bool = True,
) -> str:
    """原始文本对话（health 探活等场景）。

    部分国产模型会在正文里夹 emoji/零宽字符，Windows GBK 控制台打印
    或后续 JSON 解析都会出问题，默认剥离。
    """
    resp = await get_client().chat.completions.create(
        model=settings.LLM_MODEL,
        messages=messages,  # type: ignore[arg-type]
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = resp.choices[0].message.content or ""
    if strip_emoji:
        text = "".join(ch for ch in text if ord(ch) >= 32 and not (0x1F000 <= ord(ch) <= 0x1FAFF))
    return text.strip()


async def chat_json(
    messages: list[dict],
    schema: type[T],
    temperature: float = 0.0,
    max_tokens: int = 3000,
    salvage: bool = True,
) -> T:
    """调用 LLM 并解析为 pydantic schema。

    - 失败自动重试（把上次错误原因附进重试消息）
    - salvage=True 且 schema 含名为 risks 的 list 字段时启用截断抢救
    """
    current_messages = list(messages)
    last_error = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        resp = await get_client().chat.completions.create(
            model=settings.LLM_MODEL,
            messages=current_messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = resp.choices[0]
        content = choice.message.content or ""
        finish_reason = getattr(choice, "finish_reason", None)

        # 剥离 emoji / 控制字符（GBK 控制台与 JSON 解析都怕它们）
        content = "".join(
            ch for ch in content if ord(ch) >= 32 and not (0x1F000 <= ord(ch) <= 0x1FAFF)
        ).strip()

        cleaned = _clean(content)
        data = _try_loads(cleaned)

        if data is not None:
            try:
                return schema.model_validate(data)
            except ValidationError as e:
                last_error = f"JSON 结构不符合要求：{e.errors()[:3]}"
        else:
            # 解析失败：截断场景尝试抢救
            if salvage and finish_reason == "length":
                items = _salvage_array(cleaned)
                if items:
                    try:
                        return schema.model_validate({"risks": items})
                    except ValidationError:
                        pass
                    # 抢救出的元素逐个过滤
                    if schema.__name__ == "ReviewLLMOut":
                        from app.schemas.review import RiskItem

                        valid = []
                        for it in items:
                            if isinstance(it, dict):
                                try:
                                    valid.append(RiskItem.model_validate(it))
                                except ValidationError:
                                    continue
                        if valid:
                            from app.schemas.review import ReviewLLMOut

                            return ReviewLLMOut(risks=valid)  # type: ignore[return-value]
            last_error = (
                f"输出不是合法 JSON（finish_reason={finish_reason}）"
                f"，前 100 字符：{cleaned[:100]}"
            )

        # 准备重试
        if attempt < MAX_ATTEMPTS:
            current_messages = list(messages) + [
                {"role": "assistant", "content": content[:2000]},
                {
                    "role": "user",
                    "content": (
                        f"你上一次的输出无法使用，错误原因：{last_error}。\n"
                        "请严格重新输出，只输出合法的 JSON，"
                        "不要任何解释、markdown 围栏或其他文本，"
                        "并确保所有括号引号完整闭合。"
                    ),
                },
            ]

    raise LLMFormatError(f"LLM 输出解析失败（已尝试 {MAX_ATTEMPTS} 次）：{last_error}")
