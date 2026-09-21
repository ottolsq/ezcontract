"""规则库加载：解析 rules/erp_rules.md，启动时缓存"""
from __future__ import annotations

import re
from functools import lru_cache

from pydantic import BaseModel

from app.config import settings


class Rule(BaseModel):
    rule_id: str
    title: str
    level: str  # high / medium
    trigger: str  # 触发条件
    suggestion: str  # 建议条款


_RULE_HEADER = re.compile(
    r"^###\s+([A-Z0-9\-]+)\s*\|\s*(.+?)\s*\|\s*(high|medium|low)\s*$"
)


def _parse_rules(text: str) -> list[Rule]:
    rules: list[Rule] = []
    current: dict | None = None
    for line in text.splitlines():
        line = line.strip()
        m = _RULE_HEADER.match(line)
        if m:
            if current:
                rules.append(Rule.model_validate(current))
            current = {
                "rule_id": m.group(1),
                "title": m.group(2),
                "level": m.group(3),
                "trigger": "",
                "suggestion": "",
            }
            continue
        if current is None:
            continue
        if line.startswith("- 触发条件：") or line.startswith("- 触发条件:"):
            current["trigger"] = line.split("：", 1)[-1].split(":", 1)[-1].strip()
        elif line.startswith("- 建议条款：") or line.startswith("- 建议条款:"):
            current["suggestion"] = line.split("：", 1)[-1].split(":", 1)[-1].strip()
    if current:
        rules.append(Rule.model_validate(current))
    return rules


@lru_cache(maxsize=1)
def _load() -> tuple[Rule, ...]:
    text = settings.RULES_PATH.read_text(encoding="utf-8")
    return tuple(_parse_rules(text))


def get_rules() -> list[Rule]:
    return list(_load())


def get_rule_ids() -> set[str]:
    return {r.rule_id for r in get_rules()}
