"""履约模块编排：上传入库 → 后台提取 → 物化节点 → CRUD → 通知惰性检查

DB 函数全部为同步函数（短命连接），路由层用 asyncio.to_thread 包装。
"""
from __future__ import annotations

import asyncio
import io
import json
import re
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings
from app.llm.client import LLMFormatError, chat_json
from app.llm.prompts import build_compliance_prompt
from app.parser.clause_splitter import split_clauses
from app.parser.docx_parser import extract_docx_paragraphs
from app.schemas.compliance import ComplianceLLMOut, ComplianceNodeLLM
from app.services.compliance_dates import (
    DATE_RE,
    compute_due_date,
    days_left,
    expand_recurring,
    parse_date,
)
from app.services.compliance_db import conn_ctx, row_to_dict
from app.services.compliance_extract import (
    CandidateUnit,
    prefilter_candidates,
    collect_meta_lines,
)

MAX_FILE_SIZE = 20 * 1024 * 1024

# 后台任务引用（防止被 GC）；stage 进度（cid → 文案）
_TASKS: set[asyncio.Task] = set()
PROGRESS: dict[str, str] = {}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# ── 上传 ──


async def save_upload(file: UploadFile) -> dict:
    """解析 docx、切条款、预筛候选 → 入库 pending。返回上传摘要。"""
    filename = file.filename or "contract.docx"
    if Path(filename).suffix.lower() != ".docx":
        raise HTTPException(400, "履约模块目前仅支持 .docx 文件")
    content = await file.read()
    if not content:
        raise HTTPException(400, "文件为空")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "文件超过 20MB 限制")
    if not content[:4] == b"PK\x03\x04":
        raise HTTPException(400, "不是有效的 docx 文件")

    def _parse():
        paragraphs = extract_docx_paragraphs(io.BytesIO(content))
        return split_clauses(paragraphs) + (paragraphs,)

    try:
        clauses, preamble, tail, paragraphs = await asyncio.to_thread(_parse)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"文件解析失败：{e}")

    if not clauses:
        raise HTTPException(400, "未能在文档中识别出任何条款内容")

    candidates = prefilter_candidates(clauses, paragraphs)
    meta_lines = collect_meta_lines(preamble, tail)

    contract_id = _new_id()
    with conn_ctx() as conn:
        conn.execute(
            "INSERT INTO contracts (id, filename, status, clause_count, "
            "candidate_count, candidates_json, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                contract_id,
                filename,
                "pending",
                len(clauses),
                len(candidates),
                json.dumps(
                    {
                        "candidates": [c.__dict__ for c in candidates],
                        "meta_lines": meta_lines,
                    },
                    ensure_ascii=False,
                ),
                _now(),
            ),
        )
    return {
        "contract_id": contract_id,
        "filename": filename,
        "clause_count": len(clauses),
        "candidate_count": len(candidates),
    }


# ── 后台提取 ──


def start_extract(contract_id: str) -> str:
    """幂等启动后台提取任务。返回当前状态。"""
    with conn_ctx() as conn:
        row = conn.execute(
            "SELECT status FROM contracts WHERE id=?", (contract_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, "合同不存在")
    status = row["status"]
    if status in ("processing", "completed"):
        return status
    with conn_ctx() as conn:
        conn.execute(
            "UPDATE contracts SET status='processing', error=NULL WHERE id=?",
            (contract_id,),
        )
    PROGRESS[contract_id] = "正在提取履约节点"
    task = asyncio.get_running_loop().create_task(run_extraction(contract_id))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return "processing"


async def run_extraction(contract_id: str) -> None:
    """后台任务：读候选 → LLM 提取 → 物化 → 更新状态。"""
    try:
        PROGRESS[contract_id] = "正在读取候选条款"
        with conn_ctx() as conn:
            row = conn.execute(
                "SELECT candidates_json, filename FROM contracts WHERE id=?",
                (contract_id,),
            ).fetchone()
        if row is None:
            return
        payload = json.loads(row["candidates_json"])
        candidates = [CandidateUnit(**c) for c in payload.get("candidates", [])]
        meta_lines = payload.get("meta_lines", [])
        filename = row["filename"]

        llm_out: ComplianceLLMOut | None = None
        fallback_reason = ""
        if candidates:
            PROGRESS[contract_id] = "AI 正在识别履约节点"
            candidates_text = "\n".join(
                f"[{c.ref}] {c.display_ref} {c.text}" for c in candidates
            )
            meta_text = "\n".join(meta_lines) if meta_lines else "（无）"
            try:
                llm_out = await chat_json(
                    build_compliance_prompt(candidates_text, meta_text),
                    schema=ComplianceLLMOut,
                    temperature=settings.COMPLIANCE_TEMPERATURE,
                    max_tokens=settings.COMPLIANCE_MAX_TOKENS,
                    salvage=False,
                )
            except LLMFormatError as e:
                fallback_reason = f"AI 提取失败（{str(e)[:80]}），已转为人工确认模式"
        else:
            fallback_reason = "未筛选出含时间信息的条款"

        PROGRESS[contract_id] = "正在计算截止日期"
        _materialize(contract_id, filename, candidates, meta_lines, llm_out, fallback_reason)

        with conn_ctx() as conn:
            conn.execute(
                "UPDATE contracts SET status='completed', extracted_at=?, error=NULL WHERE id=?",
                (_now(), contract_id),
            )
        PROGRESS[contract_id] = "提取完成"
    except Exception as e:  # noqa: BLE001 — 后台任务兜底
        with conn_ctx() as conn:
            conn.execute(
                "UPDATE contracts SET status='failed', error=? WHERE id=?",
                (str(e)[:300], contract_id),
            )
        PROGRESS[contract_id] = "提取失败"


# ── 元信息兜底 + 物化 ──

_SIGN_DATE_RE = re.compile(r"签署日期[:：]?\s*" + DATE_RE.pattern)
_PERIOD_RE = re.compile(
    r"自?\s*" + DATE_RE.pattern + r"\s*[起之]?\s*[至到]\s*" + DATE_RE.pattern
)


def _meta_with_fallback(
    llm_meta, meta_lines: list[str], candidates: list[CandidateUnit]
) -> dict[str, date | None]:
    """meta 以 LLM 为首选，代码正则兜底。返回 {sign/start/end: date|None}。"""
    def _to_date(s: str) -> date | None:
        d = parse_date(s)
        return d if d else None

    sign = _to_date(getattr(llm_meta, "sign_date", ""))
    start = _to_date(getattr(llm_meta, "contract_start", ""))
    end = _to_date(getattr(llm_meta, "contract_end", ""))

    if sign is None:
        for line in meta_lines:
            m = _SIGN_DATE_RE.search(line)
            if m:
                sign = _to_date(f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
                break

    if start is None or end is None:
        # 从候选行里找「自X起至Y止」结构（如 2.2 租赁期限）
        for c in candidates:
            m = _PERIOD_RE.search(c.text)
            if m:
                try:
                    s = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    e = date(int(m.group(4)), int(m.group(5)), int(m.group(6)))
                    if start is None:
                        start = s
                    if end is None:
                        end = e
                    break
                except ValueError:
                    continue
    return {"sign": sign, "start": start, "end": end}


def _node_rows(
    node: ComplianceNodeLLM,
    cand: CandidateUnit,
    meta: dict,
) -> list[dict]:
    """单个 LLM 节点 → 一或多行 milestone 行数据（周期义务展开多期）。"""
    base = {
        "node_type": node.node_type,
        "title": node.title[:24] or "履约节点",
        "description": node.description[:200],
        "clause_ref": cand.display_ref,
        "clause_text": cand.text,
        "recurring": node.recurring,
        "offset_days": node.offset_days,
        "needs_review": 0,
        "due_date": None,
    }

    if node.needs_review:
        base["needs_review"] = 1
        return [base]

    if node.recurring != "none":
        start = meta["start"]
        if start is None:
            base["needs_review"] = 1
            return [base]
        group = _new_id()
        rows = []
        for idx, due in expand_recurring(
            start,
            node.recurring,
            node.offset_days,
            settings.COMPLIANCE_EXPAND_COUNT,
            until=meta["end"],
        ):
            rows.append(
                {
                    **base,
                    "recurring_group": group,
                    "instance_index": idx,
                    "due_date": due.isoformat(),
                }
            )
        return rows or [{**base, "needs_review": 1}]

    if node.anchor == "absolute":
        due = parse_date(node.anchor_date)
        if due is None:
            base["needs_review"] = 1
        else:
            base["due_date"] = due.isoformat()
        return [base]

    anchor = meta.get(
        {
            "sign_date": "sign",
            "contract_start": "start",
            "contract_end": "end",
        }.get(node.anchor, "sign")
    )
    if anchor is None:
        base["needs_review"] = 1
        return [base]
    due = compute_due_date(anchor, node.offset_months, node.offset_days)
    base["due_date"] = due.isoformat()
    return [base]


def _materialize(
    contract_id: str,
    filename: str,
    candidates: list[CandidateUnit],
    meta_lines: list[str],
    llm_out: ComplianceLLMOut | None,
    fallback_reason: str,
) -> int:
    """把 LLM 输出（或回退候选）写成 milestone 行。返回写入行数。"""
    meta = _meta_with_fallback(
        llm_out.meta if llm_out else None, meta_lines, candidates
    )

    rows: list[dict] = []
    if llm_out and llm_out.nodes:
        cand_by_ref = {c.ref: c for c in candidates}
        seen_refs: set[str] = set()
        for node in llm_out.nodes:
            if node.ref in seen_refs:
                continue
            cand = cand_by_ref.get(node.ref)
            if cand is None:  # 防幻觉：ref 不在候选集
                continue
            seen_refs.add(node.ref)
            rows.extend(_node_rows(node, cand, meta))
    else:
        # LLM 失败回退：全部候选转人工确认节点
        for cand in candidates:
            rows.append(
                {
                    "node_type": "other",
                    "title": cand.text[:24],
                    "description": "",
                    "clause_ref": cand.display_ref,
                    "clause_text": cand.text,
                    "recurring": "none",
                    "offset_days": 0,
                    "needs_review": 1,
                    "due_date": None,
                }
            )

    now = _now()
    with conn_ctx() as conn:
        conn.execute("DELETE FROM milestones WHERE contract_id=?", (contract_id,))
        for r in rows:
            conn.execute(
                "INSERT INTO milestones (id, contract_id, recurring_group, "
                "instance_index, node_type, title, description, clause_ref, "
                "clause_text, due_date, status, needs_review, due_date_edited, "
                "recurring, offset_days, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?, 'pending', ?, 0, ?, ?, ?)",
                (
                    _new_id(),
                    contract_id,
                    r.get("recurring_group", ""),
                    r.get("instance_index", 0),
                    r.get("node_type", "other"),
                    r.get("title", ""),
                    r.get("description", ""),
                    r.get("clause_ref", ""),
                    r.get("clause_text", ""),
                    r.get("due_date"),
                    r.get("needs_review", 0),
                    r.get("recurring", "none"),
                    r.get("offset_days", 0),
                    now,
                ),
            )
        conn.execute(
            "UPDATE contracts SET sign_date=?, start_date=?, end_date=? WHERE id=?",
            (
                meta["sign"].isoformat() if meta["sign"] else None,
                meta["start"].isoformat() if meta["start"] else None,
                meta["end"].isoformat() if meta["end"] else None,
                contract_id,
            ),
        )
    # 失败回退原因存到 contracts.error（前端 detail 提示可重试）
    if fallback_reason:
        with conn_ctx() as conn:
            conn.execute(
                "UPDATE contracts SET error=? WHERE id=?", (fallback_reason, contract_id)
            )
    return len(rows)


# ── 查询 ──


def get_contract_status(contract_id: str) -> dict:
    with conn_ctx() as conn:
        row = conn.execute(
            "SELECT status, error FROM contracts WHERE id=?", (contract_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "合同不存在")
        count = conn.execute(
            "SELECT COUNT(*) FROM milestones WHERE contract_id=?", (contract_id,)
        ).fetchone()[0]
    return {
        "status": row["status"],
        "stage": PROGRESS.get(contract_id, ""),
        "error": row["error"],
        "milestone_count": count,
    }


def list_contracts() -> list[dict]:
    with conn_ctx() as conn:
        rows = conn.execute(
            "SELECT c.*, "
            "(SELECT COUNT(*) FROM milestones m WHERE m.contract_id=c.id) AS total, "
            "(SELECT COUNT(*) FROM milestones m WHERE m.contract_id=c.id AND m.status='pending') AS pending, "
            "(SELECT COUNT(*) FROM milestones m WHERE m.contract_id=c.id AND m.status='pending' "
            " AND m.due_date IS NOT NULL AND m.due_date <= date('now','+7 day')) AS due_soon7, "
            "(SELECT COUNT(*) FROM milestones m WHERE m.contract_id=c.id AND m.status='pending' "
            " AND m.due_date IS NOT NULL AND m.due_date < date('now')) AS overdue, "
            "(SELECT COUNT(*) FROM milestones m WHERE m.contract_id=c.id AND m.status='done') AS done "
            "FROM contracts c ORDER BY c.created_at DESC"
        ).fetchall()
    return [row_to_dict(r) for r in rows]


def get_contract_detail(contract_id: str) -> dict:
    with conn_ctx() as conn:
        row = conn.execute(
            "SELECT * FROM contracts WHERE id=?", (contract_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "合同不存在")
        contract = row_to_dict(row)
        contract.pop("candidates_json", None)
        ms = conn.execute(
            "SELECT * FROM milestones WHERE contract_id=? "
            "ORDER BY due_date IS NULL, due_date, instance_index",
            (contract_id,),
        ).fetchall()
    today = date.today()
    milestones = []
    for m in ms:
        m = row_to_dict(m)
        m["days_left"] = days_left(parse_date(m["due_date"]), today)
        milestones.append(m)
    return {"contract": contract, "milestones": milestones}


# ── 节点操作 ──


def set_milestone_status(milestone_id: str, status: str) -> dict:
    with conn_ctx() as conn:
        row = conn.execute(
            "SELECT * FROM milestones WHERE id=?", (milestone_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "履约节点不存在")
        m = row_to_dict(row)
        now = _now()
        conn.execute(
            "UPDATE milestones SET status=?, done_at=? WHERE id=?",
            (status, now if status == "done" else None, milestone_id),
        )
        next_created = False
        # 周期组：完成/跳过组内最大 instance_index → 惰性追加下一期
        if (
            status in ("done", "skipped")
            and m["recurring_group"]
            and m["recurring"] != "none"
        ):
            max_idx = conn.execute(
                "SELECT MAX(instance_index) FROM milestones WHERE recurring_group=?",
                (m["recurring_group"],),
            ).fetchone()[0]
            group_count = conn.execute(
                "SELECT COUNT(*) FROM milestones WHERE recurring_group=?",
                (m["recurring_group"],),
            ).fetchone()[0]
            if (
                m["instance_index"] == max_idx
                and group_count < settings.COMPLIANCE_MAX_INSTANCES
            ):
                with conn_ctx() as conn2:
                    crow = conn2.execute(
                        "SELECT start_date, end_date FROM contracts WHERE id=?",
                        (m["contract_id"],),
                    ).fetchone()
                start = parse_date(crow["start_date"]) if crow else None
                end = parse_date(crow["end_date"]) if crow else None
                if start is not None:
                    from app.services.compliance_dates import period_start

                    next_idx = max_idx + 1
                    nstart = period_start(start, next_idx, m["recurring"])
                    if end is None or nstart <= end:
                        ndue = nstart + timedelta(days=m["offset_days"])
                        conn.execute(
                            "INSERT INTO milestones (id, contract_id, recurring_group, "
                            "instance_index, node_type, title, description, clause_ref, "
                            "clause_text, due_date, status, needs_review, due_date_edited, "
                            "recurring, offset_days, created_at) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?, 'pending', 0, 0, ?, ?, ?)",
                            (
                                _new_id(),
                                m["contract_id"],
                                m["recurring_group"],
                                next_idx,
                                m["node_type"],
                                m["title"],
                                m["description"],
                                m["clause_ref"],
                                m["clause_text"],
                                ndue.isoformat(),
                                m["recurring"],
                                m["offset_days"],
                                now,
                            ),
                        )
                        next_created = True
    return {"ok": True, "next_created": next_created}


def set_milestone_due_date(milestone_id: str, due_date: str) -> dict:
    d = parse_date(due_date) if due_date else None
    if due_date and d is None:
        raise HTTPException(400, "日期格式不合法，应为 YYYY-MM-DD")
    with conn_ctx() as conn:
        row = conn.execute(
            "SELECT id FROM milestones WHERE id=?", (milestone_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "履约节点不存在")
        conn.execute(
            "UPDATE milestones SET due_date=?, due_date_edited=1 WHERE id=?",
            (d.isoformat() if d else None, milestone_id),
        )
    return {"ok": True}


def delete_contract(contract_id: str) -> dict:
    with conn_ctx() as conn:
        row = conn.execute(
            "SELECT id FROM contracts WHERE id=?", (contract_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "合同不存在")
        # 显式级联（不依赖 PRAGMA foreign_keys）
        conn.execute(
            "DELETE FROM notifications WHERE contract_id=?", (contract_id,)
        )
        conn.execute(
            "DELETE FROM milestones WHERE contract_id=?", (contract_id,)
        )
        conn.execute("DELETE FROM contracts WHERE id=?", (contract_id,))
    PROGRESS.pop(contract_id, None)
    return {"ok": True}


# ── 通知（惰性检查）──


def check_notifications() -> None:
    """惰性检查：到期前一天的 pending 节点 → due_soon；已逾期 → overdue。

    `UNIQUE(milestone_id, kind)` + `INSERT OR IGNORE` 保证幂等（每节点每类仅一条）。
    """
    today = date.today()
    tomorrow = (today + timedelta(days=1)).isoformat()
    today_s = today.isoformat()
    now = _now()
    with conn_ctx() as conn:
        rows = conn.execute(
            "SELECT m.id, m.contract_id, m.title, m.due_date, c.filename "
            "FROM milestones m JOIN contracts c ON c.id = m.contract_id "
            "WHERE m.status='pending' AND m.due_date IS NOT NULL "
            "AND m.due_date <= ?",
            (tomorrow,),
        ).fetchall()
        for r in rows:
            if r["due_date"] == tomorrow:
                kind = "due_soon"
                title = f"履约提醒：{r['title']} 明天截止"
            elif r["due_date"] == today_s:
                kind = "due_soon"
                title = f"履约提醒：{r['title']} 今天截止"
            else:  # due_date < today
                overdue_days = (today - date.fromisoformat(r["due_date"])).days
                kind = "overdue"
                title = f"已逾期 {overdue_days} 天：{r['title']}"
            content = f"合同《{r['filename']}》 · {r['due_date']}"
            conn.execute(
                "INSERT OR IGNORE INTO notifications "
                "(milestone_id, contract_id, kind, title, content, due_date, is_read, created_at) "
                "VALUES (?,?,?,?,?,?, 0, ?)",
                (r["id"], r["contract_id"], kind, title, content, r["due_date"], now),
            )


def list_notifications() -> dict:
    """先跑惰性检查，再返回列表 + 未读数（≤50 条，新在前）。"""
    check_notifications()
    with conn_ctx() as conn:
        rows = conn.execute(
            "SELECT n.*, m.title AS milestone_title, m.clause_ref "
            "FROM notifications n LEFT JOIN milestones m ON m.id = n.milestone_id "
            "ORDER BY n.id DESC LIMIT 50"
        ).fetchall()
        unread = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE is_read=0"
        ).fetchone()[0]
    return {"items": [row_to_dict(r) for r in rows], "unread": unread}


def mark_notifications_read(ids: list[int] | None = None, mark_all: bool = False) -> dict:
    with conn_ctx() as conn:
        if mark_all:
            conn.execute("UPDATE notifications SET is_read=1 WHERE is_read=0")
        elif ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"UPDATE notifications SET is_read=1 WHERE id IN ({placeholders})",
                ids,
            )
        unread = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE is_read=0"
        ).fetchone()[0]
    return {"ok": True, "unread": unread}
