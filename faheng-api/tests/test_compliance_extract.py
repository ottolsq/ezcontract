"""履约候选预筛选测试（手造 Clause 夹具，不依赖 gitignore 的 exmple/）

运行：./venv/bin/python -m unittest tests.test_compliance_extract -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.parser.docx_parser import ParagraphInfo  # noqa: E402
from app.parser.clause_splitter import split_clauses  # noqa: E402
from app.schemas.review import Clause, SubItem  # noqa: E402
from app.services.compliance_extract import (  # noqa: E402
    assign_line_to_subitem,
    collect_meta_lines,
    iter_clause_lines,
    prefilter_candidates,
)


def _make_paragraphs() -> list[ParagraphInfo]:
    """构造一个小型租赁合同：1 个条款（4.1 租金 / 4.2 押金），段落带 \\n 多行。"""
    return [
        ParagraphInfo(text="出租方（甲方）：张三", html="<p>出租方（甲方）：张三</p>"),
        ParagraphInfo(
            text="第4条 租金、押金及支付方式",
            html="<p>第4条 租金、押金及支付方式</p>",
        ),
        ParagraphInfo(text="4.1 租金", html="<p>4.1 租金</p>"),
        ParagraphInfo(
            text=(
                "（1）月租金为人民币4200元。\n"
                "（2）租金支付周期为每季度，乙方应于每个支付周期开始前7日内向甲方支付当期租金。"
            ),
            html="<p>…</p>",
        ),
        ParagraphInfo(text="4.2 押金", html="<p>4.2 押金</p>"),
        ParagraphInfo(
            text="（1）乙方应于本合同签署后3日内向甲方支付押金人民币8400元。",
            html="<p>…</p>",
        ),
        ParagraphInfo(
            text="4.3 水电费由乙方承担，据实结算。",
            html="<p>…</p>",
        ),
        ParagraphInfo(text="签署日期：2026-09-28", html="<p>…</p>"),
    ]


def _make_clauses(paragraphs: list[ParagraphInfo]) -> tuple[list[Clause], list, list]:
    return split_clauses(paragraphs)


class TestIterClauseLines(unittest.TestCase):
    def test_lines_with_paragraph_index(self):
        paragraphs = _make_paragraphs()
        clauses, _, _ = _make_clauses(paragraphs)
        self.assertEqual(len(clauses), 1)
        lines = iter_clause_lines(clauses[0], paragraphs)
        # 段1: 第4条标题；段2: 4.1；段3: 两行；段4: 4.2；段5: 一行；段6: 4.3
        self.assertEqual(len(lines), 7)
        self.assertEqual(lines[0], (1, 0, "第4条 租金、押金及支付方式"))
        self.assertEqual(lines[2], (3, 0, "（1）月租金为人民币4200元。"))
        self.assertEqual(lines[3], (3, 1, "（2）租金支付周期为每季度，乙方应于每个支付周期开始前7日内向甲方支付当期租金。"))


class TestAssignLineToSubitem(unittest.TestCase):
    def test_multiline_paragraph_belongs_to_subitem(self):
        paragraphs = _make_paragraphs()
        clauses, _, _ = _make_clauses(paragraphs)
        clause = clauses[0]
        subs = {s.internal_no: s for s in clause.subitems}
        self.assertIn("4.1(2)", subs)
        # 段3 行1 = （2）租金支付周期 → 归属 4.1(2)
        sub = assign_line_to_subitem(clause, 3, 1)
        self.assertIsNotNone(sub)
        self.assertEqual(sub.internal_no, "4.1(2)")

    def test_root_line_no_subitem(self):
        paragraphs = _make_paragraphs()
        clauses, _, _ = _make_clauses(paragraphs)
        # 段1 第4条标题行 → 无子项
        self.assertIsNone(assign_line_to_subitem(clauses[0], 1, 0))


class TestPrefilterCandidates(unittest.TestCase):
    def test_rent_and_deposit_candidates(self):
        paragraphs = _make_paragraphs()
        clauses, preamble, tail = _make_clauses(paragraphs)
        cands = prefilter_candidates(clauses, paragraphs)
        refs = [c.ref for c in cands]
        # 周期租金 + 签署后3日押金 必须命中
        self.assertIn("C01#4.1(2)", refs)
        self.assertIn("C01#4.2(1)", refs)
        # 4.3「据实结算」含"结算"关键词 → 命中（宁多勿漏，由 LLM 再筛）
        self.assertIn("C01#4.3", refs)

    def test_display_ref_keeps_original_style(self):
        paragraphs = _make_paragraphs()
        clauses, _, _ = _make_clauses(paragraphs)
        cands = prefilter_candidates(clauses, paragraphs)
        by_ref = {c.ref: c for c in cands}
        self.assertEqual(by_ref["C01#4.1(2)"].display_ref, "第4条 4.1（2）")

    def test_no_payment_only_false_positive(self):
        # "支付方式为银行转账"无时间关键词 → 不应命中
        paragraphs = [
            ParagraphInfo(text="第5条 支付", html=""),
            ParagraphInfo(text="（1）支付方式为银行转账。", html=""),
        ]
        clauses, _, _ = _make_clauses(paragraphs)
        # fallback 拆分下也验证不产出候选
        cands = prefilter_candidates(clauses, paragraphs)
        self.assertEqual(len(cands), 0)

    def test_max_candidates_cap(self):
        paragraphs = [
            ParagraphInfo(text=f"第{i}条 期限{i}", html="")
            for i in range(1, 40)
        ]
        clauses, _, _ = _make_clauses(paragraphs)
        cands = prefilter_candidates(clauses, paragraphs)
        self.assertLessEqual(len(cands), 24)


class TestCollectMetaLines(unittest.TestCase):
    def test_signature_date_from_tail(self):
        paragraphs = _make_paragraphs()
        _, _, tail = _make_clauses(paragraphs)
        meta = collect_meta_lines([], tail)
        # 签署区在 tail 中（split_clauses 把签署日期识别为签署区）
        joined = "".join(meta)
        self.assertIn("2026-09-28", joined)


if __name__ == "__main__":
    unittest.main()
