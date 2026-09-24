"""审查流水线：上传解析 → 后台分批审查 → 后处理 → 算分 → 决策 → 导出编排"""
from __future__ import annotations

import asyncio
import io
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings
from app.llm.client import LLMFormatError, chat_json
from app.llm.prompts import build_review_prompt
from app.parser.clause_splitter import split_clauses
from app.parser.docx_parser import extract_docx_paragraphs
from app.parser.pdf_parser import extract_pdf_lines
from app.schemas.review import Clause, Decision, ReviewLLMOut, ReviewSession, RiskItem
from app.services.docx_export import export_final_docx
from app.services.rules import get_rule_ids

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
ALLOWED_EXT = {".docx", ".pdf"}


def new_review_id() -> str:
    return uuid.uuid4().hex[:12]


async def save_upload(file: UploadFile) -> ReviewSession:
    """解析上传文件并切分条款（字节全程驻留内存，无状态化）"""
    filename = file.filename or "contract.docx"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, "仅支持 .docx / .pdf 文件")
    if not ext:
        ext = ".docx"

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "文件超过 20MB 限制")
    if not content:
        raise HTTPException(400, "文件为空")

    review_id = new_review_id()
    buf = io.BytesIO(content)

    try:
        if ext == ".docx":
            lines = extract_docx_paragraphs(buf)
        else:
            lines = extract_pdf_lines(buf)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"文件解析失败：{e}")

    clauses, preamble, tail = split_clauses(lines)
    if not clauses:
        raise HTTPException(400, "未能在文档中识别出任何条款内容")

    session = ReviewSession(
        id=review_id,
        filename=filename,
        file_type=ext.lstrip("."),
        clauses=clauses,
        preamble_text="\n".join(p.text for p in preamble),
        tail_text="\n".join(p.text for p in tail),
        preamble_lines=[p.text for p in preamble],
        tail_lines=[p.text for p in tail],
        preamble_html="".join(p.html for p in preamble),
        tail_html="".join(p.html for p in tail),
        upload_bytes=content,  # DOCX 就地替换导出仍需打开原件，留在 session 内存里
    )
    return session


def _make_batches(clauses: list[Clause]) -> list[list[Clause]]:
    """分批：每批 ≤ N 条且 ≤ M 字符"""
    batches: list[list[Clause]] = []
    current: list[Clause] = []
    current_chars = 0
    for c in clauses:
        n_chars = len(c.text)
        if current and (
            len(current) >= settings.BATCH_MAX_CLAUSES
            or current_chars + n_chars > settings.BATCH_MAX_CHARS
        ):
            batches.append(current)
            current, current_chars = [], 0
        current.append(c)
        current_chars += n_chars
    if current:
        batches.append(current)
    return batches


def _clauses_text(batch: list[Clause]) -> str:
    return "\n\n".join(f"{c.clause_id} {c.clause_no}{' ' + c.title if c.title else ''}\n{c.text}" for c in batch)


def _postprocess(
    raw_risks: list[RiskItem], clauses: list[Clause], salvaged: bool
) -> tuple[list[RiskItem], bool]:
    """代码侧确定性校验：过滤非法引用、去重、编号、子项编号归一"""
    clause_map = {c.clause_id: c for c in clauses}
    known_rules = get_rule_ids()

    # (clause_id -> {valid_subitem_no set}) —— 仅记录真实出现的 X.Y
    clause_subitems: dict[str, set[str]] = {
        c.clause_id: {s.sub_item_no for s in c.subitems} for c in clauses
    }

    def _normalize_subitem(raw: str | None, suggestion: str, clause_id: str) -> str:
        raw = (raw or "").strip()
        valid = clause_subitems.get(clause_id, set())
        if raw and raw in valid:
            return raw
        # 兜底：从 suggestion 文本开头抓 X.Y
        if suggestion:
            import re as _re

            m = _re.match(r"^\s*(\d+\.\d+(?:\.\d+)?)", suggestion)
            if m and m.group(1) in valid:
                return m.group(1)
        # 进一步兜底：LLM 给的 raw 编号格式合法 + 该 clause 至少有 1 个子项 → 信任 LLM
        if raw and valid and _re.match(r"^\d+\.\d+(?:\.\d+)?$", raw):
            return raw
        return ""

    seen: set[tuple[str, str]] = set()
    result: list[RiskItem] = []
    for r in raw_risks:
        clause = clause_map.get(r.clause_id)
        if clause is None:  # 引用不存在的条款 → 丢弃
            continue
        if not r.suggestion.strip():  # 无法采纳 → 丢弃
            continue
        key = (r.clause_id, r.title.strip())
        if key in seen:
            continue
        seen.add(key)
        r.matched_rules = [x for x in r.matched_rules if x in known_rules]
        r.risk_id = f"R{len(result) + 1:02d}"
        r.clause_no = clause.clause_no
        r.sub_item_no = _normalize_subitem(r.sub_item_no, r.suggestion, r.clause_id)
        result.append(r)
    return result, salvaged


async def run_review(session: ReviewSession) -> None:
    """后台审查任务：分批调 LLM → 后处理 → completed"""
    try:
        batches = _make_batches(session.clauses)
        all_risks: list[RiskItem] = []
        salvaged_any = False
        total = len(batches)

        for i, batch in enumerate(batches):
            session.stage = f"比对规则库，审查条款批次 {i + 1}/{total}（{batch[0].clause_no} 起）"
            session.progress = 10 + int(85 * i / max(total, 1))

            try:
                out = await chat_json(
                    build_review_prompt(_clauses_text(batch)),
                    schema=ReviewLLMOut,
                    temperature=settings.REVIEW_TEMPERATURE,
                    max_tokens=settings.REVIEW_MAX_TOKENS,
                )
                all_risks.extend(out.risks)
            except LLMFormatError as e:
                # 单批失败不终止整个审查
                session.stage = f"批次 {i + 1} 解析失败已跳过：{str(e)[:80]}"

        session.progress = 96
        risks, salvaged = _postprocess(all_risks, session.clauses, salvaged_any)
        session.risks = risks
        session.truncated_salvaged = salvaged
        # 风险分由前端根据"剩余未消除风险"派生，后端不再计算
        session.progress = 100
        session.stage = f"审查完成，共识别 {len(risks)} 项风险"
        session.status = "completed"
    except Exception as e:  # noqa: BLE001 — 后台任务兜底
        session.status = "failed"
        session.error = str(e)[:300]


def start_review_task(session: ReviewSession) -> None:
    session.status = "processing"
    session.progress = 5
    session.stage = "正在准备条款审查"
    # 立即调度后台任务（引用 session 对象，进度实时可见）
    asyncio.get_running_loop().create_task(run_review(session))


def apply_decisions(session: ReviewSession, decisions: list[Decision]) -> int:
    """全量幂等覆盖决策"""
    session.decisions = {d.risk_id: d for d in decisions}
    return len(session.decisions)


async def export_review_docx(session: ReviewSession) -> io.BytesIO:
    """导出决策回填后的最终合同 docx（内存 BytesIO，无落盘）"""
    if not session.decisions:
        raise HTTPException(400, "尚无任何决策记录，请先在风险清单中处理至少一项")
    buf = await asyncio.to_thread(export_final_docx, session)
    buf.seek(0)
    return buf
