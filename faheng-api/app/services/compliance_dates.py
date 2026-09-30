"""履约节点日期计算（纯函数，只依赖 stdlib date，无时区概念）

设计要点：
- LLM 只负责抽出「锚点 + 偏移 + 周期」结构，具体日期一律由本模块确定性计算；
- `add_months` 做月末钳制（1.31 + 1 月 → 2.28/29）；
- 周期实例永远 `period_start(base, k)` 从基准重算，不做累积加法 → 无漂移；
- `days_left` 在服务端算好下发，避免客户端时区/日期差。
"""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

# 2026-10-01 / 2026/10/1 / 2026年10月1日 / 2026.10.1（允许任意 - / 年月. 分隔）
DATE_RE = re.compile(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})\s*日?")

# 「自X起至Y止 / 自X至Y」期限结构（用于合同起止日兜底提取）
PERIOD_RE = re.compile(
    r"自?\s*" + DATE_RE.pattern + r"\s*[起之]?\s*[至到]\s*" + DATE_RE.pattern
)

PERIOD_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}


def parse_date(s: str | None) -> date | None:
    """从字符串中提取第一个日期；无匹配返回 None。"""
    if not s:
        return None
    m = DATE_RE.search(s)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def add_months(d: date, months: int) -> date:
    """d + months 个月，月末钳制（2026-01-31 + 1 月 → 2026-02-28）。"""
    if months == 0:
        return d
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def period_start(base: date, index: int, period: str) -> date:
    """第 index 期（0 起）的期初日：monthly/quarterly/yearly 从 base 重算。"""
    months = PERIOD_MONTHS.get(period)
    if months is None:
        raise ValueError(f"未知周期类型: {period}")
    return add_months(base, months * index)


def compute_due_date(anchor: date, offset_months: int = 0, offset_days: int = 0) -> date:
    """截止日 = 锚点 + offset_months 个月 + offset_days 天（先月后天）。"""
    return add_months(anchor, offset_months) + timedelta(days=offset_days)


def expand_recurring(
    base: date,
    period: str,
    offset_days: int,
    count: int,
    until: date | None = None,
) -> list[tuple[int, date]]:
    """展开周期义务的前 count 期（期初 ≤ until 时截断），返回 [(instance_index, due)]。

    due = 期初日 + offset_days（如「每期开始前 7 日内」offset_days=-7）。
    """
    out: list[tuple[int, date]] = []
    for idx in range(count):
        start = period_start(base, idx, period)
        if until is not None and start > until:
            break
        out.append((idx, start + timedelta(days=offset_days)))
    return out


def days_left(due: date | None, today: date | None = None) -> int | None:
    """距离截止还剩几天：0=今天截止，负数=已逾期 N 天；due 为 None 返回 None。"""
    if due is None:
        return None
    today = today or date.today()
    return (due - today).days
