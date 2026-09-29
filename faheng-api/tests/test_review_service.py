"""review_service 后处理归一化测试：括号归一、sub_item_no 兜底。

运行：./venv/bin/python -m unittest tests.test_review_service -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.schemas.review import Clause, Decision, RiskItem, SubItem  # noqa: E402
from app.services.review_service import (  # noqa: E402
    _normalize_parens,
    _postprocess,
)


def _clauses() -> list[Clause]:
    return [
        Clause(
            clause_id="C07",
            clause_no="第七条",
            title="违约责任",
            text=(
                "第七条 违约责任\n"
                "7.1 甲方应依约履行\n"
                "（1）乙方可主张权利\n"
                "（2）违约金不超过实际损失\n"
                "7.2 乙方应承担违约责任\n"
                "（1）通知甲方并采取补救措施\n"
                "（2）赔偿守约方损失"
            ),
            start_idx=0,
            end_idx=1,
            subitems=[
                SubItem(sub_item_no="7.1", start_idx=0, end_idx=0),
                SubItem(sub_item_no="7.2", start_idx=0, end_idx=0),
            ],
        ),
    ]


class TestNormalizeParens(unittest.TestCase):
    def test_halfwidth_paren_to_fullwidth(self):
        # 半角 (1) → 全角 （１）；同时数字也被转为全角（与中文合同版式一致）
        self.assertEqual(
            _normalize_parens("(1) 押金抵扣条款；原条款 (3) 规定押金可全额抵扣。"),
            "（１） 押金抵扣条款；原条款 （３） 规定押金可全额抵扣。",
        )

    def test_no_paren_unchanged(self):
        self.assertEqual(
            _normalize_parens("合同总价为人民币壹拾万元整。"),
            "合同总价为人民币壹拾万元整。",
        )

    def test_empty_input(self):
        self.assertEqual(_normalize_parens(""), "")
        self.assertEqual(_normalize_parens(None), None)  # type: ignore[arg-type]

    def test_letters_unchanged(self):
        # 仅替换半角数字括号 (Z)；半角字母括号不受影响
        self.assertEqual(_normalize_parens("(a) 选择项"), "(a) 选择项")


class TestPostprocess(unittest.TestCase):
    def test_postprocess_normalizes_halfwidth_parens_in_suggestion(self):
        """replace：suggestion 中的 (1)/(2) → （１）/（２）（数字也全角）。"""
        risks = [
            RiskItem(
                risk_id="R1",
                clause_id="C07",
                title="违约金风险",
                level="high",
                issue="7.1(2) 违约金过高",
                impact="损失不可控",
                suggestion="7.1 (2) 违约金以实际损失为限",
                sub_item_no="7.1",
                operation="replace",
            )
        ]
        out, _ = _postprocess(risks, _clauses(), salvaged=False)
        self.assertEqual(len(out), 1)
        self.assertIn("（２）", out[0].suggestion)
        self.assertNotIn("(2)", out[0].suggestion)

    def test_postprocess_normalizes_parens_in_insert(self):
        """insert_after：suggestion 含 (1) → （１）。"""
        risks = [
            RiskItem(
                risk_id="R2",
                clause_id="C07",
                title="缺保密条款",
                level="medium",
                issue="无保密",
                impact="信息泄露",
                suggestion="7.3 保密条款\n(1) 双方对合同内容负有保密义务",
                sub_item_no="",
                operation="insert_after",
                anchor_clause_id="C07",
            )
        ]
        out, _ = _postprocess(risks, _clauses(), salvaged=False)
        self.assertEqual(len(out), 1)
        self.assertIn("（１）", out[0].suggestion)

    def test_postprocess_sub_item_no_from_issue_fallback(self):
        """replace：sub_item_no 为空时，从 issue 字段兜底提取。"""
        risks = [
            RiskItem(
                risk_id="R3",
                clause_id="C07",
                title="通知义务",
                level="medium",
                issue="7.2(1) 通知条款缺失补救措施",
                impact="违约损失扩大",
                suggestion="乙方应在违约发生后三日内通知甲方并采取补救措施",
                sub_item_no="",
                operation="replace",
            )
        ]
        out, _ = _postprocess(risks, _clauses(), salvaged=False)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].sub_item_no, "7.2")

    def test_postprocess_sub_item_no_keeps_llm_choice(self):
        """replace：sub_item_no 已指向真实子项 → 信任 LLM。"""
        risks = [
            RiskItem(
                risk_id="R4",
                clause_id="C07",
                title="违约金比例",
                level="high",
                issue="7.1(2) 违约金过高",
                impact="损失不可控",
                suggestion="7.1 （2） 违约金以实际损失为限",
                sub_item_no="7.1",
                operation="replace",
            )
        ]
        out, _ = _postprocess(risks, _clauses(), salvaged=False)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].sub_item_no, "7.1")

    def test_postprocess_sub_item_no_invalid_falls_back_empty(self):
        """replace：sub_item_no LLM 编造 + suggestion / issue 都没有 → 清空（触发 fallback）。"""
        risks = [
            RiskItem(
                risk_id="R5",
                clause_id="C07",
                title="其它",
                level="low",
                issue="条款整体风险",
                impact="无",
                suggestion="建议整体改写该条款正文。",
                sub_item_no="99.99",  # 编造的子项编号
                operation="replace",
            )
        ]
        out, _ = _postprocess(risks, _clauses(), salvaged=False)
        self.assertEqual(len(out), 1)
        # 编造的编号必须清空，避免下游按子项错位替换
        self.assertEqual(out[0].sub_item_no, "")


if __name__ == "__main__":
    unittest.main()