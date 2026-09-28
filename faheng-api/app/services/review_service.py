"""审查流水线：上传解析 → 后台分批审查 → 后处理 → 算分 → 决策 → 导出编排"""
from __future__ import annotations

import asyncio
import io
import re
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


# 子项编号正则（与 clause_splitter 一致）
_SUBITEM_PREFIX_RE = re.compile(r"(?<!\d)(\d+\.\d+(?:\.\d+)?)")


# 关键词 → 12 类合同目录 key（与 skill_refs._TYPE_INDEX 对齐）
_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "01-sale": ("买卖", "采购", "购销", "sale", "purchase"),
    "02-lease": ("租赁", "lease", "rent", "rental"),
    "03-service": ("服务", "委托", "承揽", "外包", "service", "outsource", "consult"),
    "05-guarantee": ("担保", "保证", "guarantee", "surety"),
    "06-lending-gift": ("借款", "贷款", "借贷", "赠与", "loan", "lend"),
    "07-internet": ("互联网", "平台", "在线", "saas", "app", "网站", "internet"),
    "09-employment": ("劳动合同", "用工", "雇佣", "employment", "labor"),
    "10-real-estate": ("房地产", "房产", "real-estate", "property"),
    "11-construction": ("工程", "施工", "建设", "construction", "build"),
    "12-corporate-investment": ("投资", "股权", "增资", "investment", "equity"),
}


def _infer_contract_type(session: ReviewSession) -> str | None:
    """从文件名 + 首条款前文本中粗略推断合同类型 key（如 '03-service'）。

    Plan A 的轻量增强：未命中时返回 None，回落到通用 skill 参考注入。
    """
    name = (session.filename or "").lower()
    head = (session.preamble_text or "")[:400]
    text = (name + " " + head).lower()
    for key, words in _TYPE_KEYWORDS.items():
        for w in words:
            if w.lower() in text:
                return key
    return None


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
    """代码侧确定性校验：过滤非法引用、去重、编号、子项编号归一、operation 校验"""
    clause_map = {c.clause_id: c for c in clauses}
    known_rules = get_rule_ids()

    # (clause_id -> {valid_subitem_no set}) —— 仅记录真实出现的 X.Y
    clause_subitems: dict[str, set[str]] = {
        c.clause_id: {s.sub_item_no for s in c.subitems} for c in clauses
    }

    # Pydantic 实例不能挂私有属性，因此用外部字典按 id 暂存子项位置信息
    autosplit_state: dict[int, list[tuple[int, str]]] = {}

    def _normalize_subitem(raw: str | None, suggestion: str, clause_id: str) -> str:
        raw = (raw or "").strip()
        valid = clause_subitems.get(clause_id, set())
        # 优先级 1：raw 已是合法子项编号 → 直接返回（信任 LLM）
        if raw and raw in valid:
            return raw
        # 优先级 2：suggestion 以 X.Y + 合法分隔符开头 → 抓这个编号
        if suggestion:
            m = _SUBITEM_PREFIX_RE.match(suggestion)
            if m and m.group(1) in valid and len(suggestion) > m.end() and re.match(r"[\s　:：、]", suggestion[m.end():m.end()+1]):
                return m.group(1)
            # 优先级 3：整段扫描找第一个合法 X.Y（处理 "押金条款：3.2 ..." 这种）
            for m in _SUBITEM_PREFIX_RE.finditer(suggestion):
                if m.group(1) in valid:
                    return m.group(1)
        # raw 不在 valid 中且无法从 suggestion 推导 → 返回空（强制按整条款处理，
        # 触发 autosplit 或 fallback）。避免误信任 LLM 的伪造编号。
        return ""

    def _validate(r: RiskItem) -> str | None:
        """返回 None 表示保留；返回 reason 表示丢弃原因（用于日志/调试）。"""
        op = r.operation
        # 1) clause_id 必须存在
        if r.clause_id not in clause_map:
            return "clause_id 不存在"
        # 2) operation 维度校验
        if op == "replace":
            # suggestion 必须有内容
            if not (r.suggestion or "").strip():
                return "replace 缺少 suggestion"
            valid = clause_subitems.get(r.clause_id, set())
            # 一次性扫描 suggestion 中所有真实子项编号出现位置
            found_iter = list(_SUBITEM_PREFIX_RE.finditer(r.suggestion))
            real_numbers = [m.group(1) for m in found_iter if m.group(1) in valid]
            unique_real = sorted(set(real_numbers))
            # sub_item_no 归一化（确保指向真实子项或空）
            normalized = _normalize_subitem(r.sub_item_no, r.suggestion, r.clause_id)
            r.sub_item_no = normalized
            # 情形 A：sub_item_no 非空（子项级 replace）：
            #   若 suggestion 含其它子项编号则降级为 autosplit；否则按子项精确替换。
            #   不强制要求 suggestion 以编号开头 —— LLM 写 "押金条款：3.2 ..." 时，sub_item_no 已锁定目标。
            if normalized:
                # suggestion 包含多个真实编号 → autosplit
                if len(unique_real) > 1:
                    autosplit_state[id(r)] = [
                        (m.start(), m.group(1)) for m in found_iter if m.group(1) in valid
                    ]
                    return "replace suggestion 包含其他子项编号，自动按子项拆分"
                # suggestion 以 normalized + 合法分隔符开头 → 严格通过
                first_match = _SUBITEM_PREFIX_RE.match(r.suggestion)
                if (
                    first_match
                    and first_match.group(1) == normalized
                    and first_match.end() < len(r.suggestion)
                    and re.match(r"[\s　:：、]", r.suggestion[first_match.end():first_match.end()+1])
                ):
                    return None
                # suggestion 不以编号开头但 sub_item_no 有效 → 信任 LLM，自动补编号前缀
                if r.sub_item_no == normalized and not first_match:
                    r.suggestion = f"{normalized} {r.suggestion.lstrip()}"
                    return None
                return "replace suggestion 编号与 sub_item_no 不一致"
            # 情形 B：sub_item_no 为空（整条款 replace）：若 suggestion 含多个真实子项编号，
            # 由代码侧按子项编号自动拆成 N 个 RiskItem，每个 sub_item_no 指向一个子项。
            if len(unique_real) > 1:
                autosplit_state[id(r)] = [
                    (m.start(), m.group(1)) for m in found_iter if m.group(1) in valid
                ]
                return "replace 整条款 suggestion 含多子项，自动按子项拆分"
            # 唯一编号时回填 sub_item_no，按子项精确替换
            if len(unique_real) == 1:
                r.sub_item_no = unique_real[0]
            return None
        if op in ("insert_after", "insert_before"):
            if not (r.suggestion or "").strip():
                return "insert_* 缺少 suggestion"
            if not r.anchor_clause_id or r.anchor_clause_id not in clause_map:
                return "insert_* anchor_clause_id 不存在"
            if r.anchor_sub_item_no:
                anchor_valid = clause_subitems.get(r.anchor_clause_id, set())
                if r.anchor_sub_item_no not in anchor_valid:
                    return "insert_* anchor_sub_item_no 不存在"
            # suggestion 必须以合法 X.Y 开头（新增子项）或第X条形式（新增整条款）
            # 这里只做轻量校验：必须有 X.Y 或 第X条 形式
            if not (_SUBITEM_PREFIX_RE.match(r.suggestion) or re.search(r"^第[一二三四五六七八九十百零〇\d]+条", r.suggestion.strip())):
                return "insert_* suggestion 缺少合法编号"
            # 新增整条款时，禁止 suggestion 携带超过 1 个真实子项编号（同 replace 规则）
            if not r.anchor_sub_item_no:
                anchor_valid = clause_subitems.get(r.anchor_clause_id, set())
                found_numbers = [
                    m.group(1)
                    for m in _SUBITEM_PREFIX_RE.finditer(r.suggestion)
                    if m.group(1) in anchor_valid
                ]
                unique_real = sorted(set(found_numbers))
                if len(unique_real) > 1:
                    return (
                        f"insert_* suggestion 携带 {len(unique_real)} 个真实子项编号 "
                        f"{unique_real}，建议拆成多个子项插入"
                    )
            return None
        if op == "delete":
            if r.sub_item_no:
                valid = clause_subitems.get(r.clause_id, set())
                if r.sub_item_no not in valid:
                    return "delete sub_item_no 不存在"
            return None
        return f"未知 operation: {op}"

    seen: set[tuple[str, str, str]] = set()
    result: list[RiskItem] = []
    for r in raw_risks:
        if r.clause_id not in clause_map:
            continue  # 引用不存在的条款 → 丢弃
        valid = clause_subitems.get(r.clause_id, set())
        if r.operation == "replace" and not (r.suggestion or "").strip():
            continue  # replace 缺少 suggestion → 丢弃
        if r.operation in ("insert_after", "insert_before") and not (r.suggestion or "").strip():
            continue
        reason = _validate(r)
        if reason:
            # 校验失败：默认保留 replace 子集（fallback 旧行为），丢弃 insert/delete 等高风险项
            if r.operation in ("insert_after", "insert_before", "delete"):
                continue
            # 例外：replace 整条款 suggestion 包含多个真实子项编号时，
            # 不再丢弃，而是按子项边界自动拆成多个 RiskItem，逐一精确替换。
            if "自动按子项拆分" in reason and r.operation == "replace":
                positions = autosplit_state.pop(id(r), None) or []
                if not positions:
                    continue
                # 重新按子项编号顺序拆 suggestion
                seen_per_no: set[str] = set()
                for idx, (start, no) in enumerate(positions):
                    # 同一编号出现多次 → 用第一次出现的子项段，避免重复风险
                    if no in seen_per_no:
                        continue
                    seen_per_no.add(no)
                    # 子项段起点：从 no 位置开始；终点：下一个出现在真实编号集合里的 X.Y 起点。
                    end = len(r.suggestion)
                    for jdx in range(idx + 1, len(positions)):
                        nxt_no = positions[jdx][1]
                        if nxt_no in valid:
                            end = positions[jdx][0]
                            break
                    raw_seg = r.suggestion[start:end].strip()
                    if not raw_seg:
                        continue
                    # 子项段以 no + 分隔符开头（满足 _normalize_subitem 的合法格式）
                    no_re = re.compile(r"^\s*" + re.escape(no) + r"[\s　:：、]")
                    if not no_re.match(raw_seg):
                        # 极端兜底：手动补编号前缀
                        raw_seg = f"{no} {raw_seg}"
                    # 去掉尾随可能混入的其他 X.Y 编号：从段尾向前截断到最后一个合法 no 的位置
                    trimmed = raw_seg
                    last_no_end = no_re.match(trimmed).end() if no_re.match(trimmed) else 0
                    extra = re.search(
                        r"(?<!\d)(\d+\.\d+(?:\.\d+)?)[\s　:：、]",
                        trimmed[last_no_end:],
                    )
                    if extra:
                        trimmed = trimmed[: last_no_end + extra.start()].rstrip()
                    child = RiskItem(
                        risk_id="",
                        clause_id=r.clause_id,
                        clause_no=r.clause_no,
                        title=r.title,
                        level=r.level,
                        matched_rules=list(r.matched_rules),
                        issue=r.issue,
                        impact=r.impact,
                        suggestion=trimmed,
                        sub_item_no=no,
                        operation="replace",
                        anchor_clause_id="",
                        anchor_sub_item_no="",
                    )
                    child_reason = _validate(child)
                    if child_reason:
                        # 子项段仍然不合法（极端情况），退回到兜底丢弃
                        continue
                    key = (
                        child.clause_id,
                        (child.sub_item_no or "").strip(),
                        child.operation,
                        child.title.strip(),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    child.matched_rules = [x for x in child.matched_rules if x in known_rules]
                    child.risk_id = f"R{len(result) + 1:02d}"
                    child.clause_no = clause_map[child.clause_id].clause_no
                    result.append(child)
                continue
            # replace 失败时仍保留，但子项编号清空（按整条款处理）
            r.sub_item_no = ""
        # 去重键：扩展为 (clause_id, sub_item_no, operation, title)
        key = (r.clause_id, (r.sub_item_no or "").strip(), r.operation, r.title.strip())
        if key in seen:
            continue
        seen.add(key)
        r.matched_rules = [x for x in r.matched_rules if x in known_rules]
        r.risk_id = f"R{len(result) + 1:02d}"
        r.clause_no = clause_map[r.clause_id].clause_no
        result.append(r)
    return result, salvaged


async def run_review(session: ReviewSession) -> None:
    """后台审查任务：分批调 LLM → 后处理 → completed"""
    try:
        batches = _make_batches(session.clauses)
        all_risks: list[RiskItem] = []
        salvaged_any = False
        total = len(batches)
        contract_type = _infer_contract_type(session)

        for i, batch in enumerate(batches):
            session.stage = f"比对规则库，审查条款批次 {i + 1}/{total}（{batch[0].clause_no} 起）"
            session.progress = 10 + int(85 * i / max(total, 1))

            try:
                out = await chat_json(
                    build_review_prompt(_clauses_text(batch), contract_type=contract_type),
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
