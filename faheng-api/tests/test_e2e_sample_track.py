"""sample_contract.docx 端到端回归（不依赖 LLM，手造决策）

验证：真实合同 → 采纳（replace / insert_after / delete / modified 混合）→
Track Changes 导出 → XML 断言 + python-docx 能打开。

运行：./venv/bin/python -m unittest tests.test_e2e_sample_track -v
"""
from __future__ import annotations

import io
import sys
import unittest
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.parser.clause_splitter import split_clauses  # noqa: E402
from app.parser.docx_parser import extract_docx_paragraphs  # noqa: E402
from app.schemas.review import Decision, ReviewSession, RiskItem  # noqa: E402
from app.services.docx_export import export_final_docx  # noqa: E402


def _load_session() -> ReviewSession:
    paras = extract_docx_paragraphs(BASE_DIR / "sample_contract.docx")
    result = split_clauses(paras)
    if isinstance(result, tuple):
        clauses = result[0]
    else:
        clauses = result
    risks = [
        RiskItem(
            risk_id="R1",
            clause_id="C03",
            title="故障举证责任倒置",
            level="high",
            issue="无法证明代码引起的故障均视为甲方环境原因",
            impact="乙方免責空间过大",
            suggestion="3.2 凡无法明确证明由软件代码直接引起的故障，由双方共同委托第三方鉴定确定责任归属。",
            sub_item_no="3.2",
            operation="replace",
        ),
        RiskItem(
            risk_id="R2",
            clause_id="C05",
            title="单方调取数据",
            level="medium",
            issue="乙方无需确认即可调取业务数据",
            impact="数据泄露风险",
            suggestion="",
            sub_item_no="5.1",
            operation="delete",
        ),
        RiskItem(
            risk_id="R3",
            clause_id="C09",
            title="缺保密条款",
            level="high",
            issue="全文无保密义务约定",
            impact="商业信息无保护",
            suggestion="第十一条 保密义务\n11.1 双方对本合同内容及履行中知悉的对方商业秘密负有保密义务。\n11.2 保密期限为本合同终止后两年。",
            operation="insert_after",
            anchor_clause_id="C09",
        ),
    ]
    decisions = [
        Decision(risk_id="R1", type="accepted"),
        Decision(risk_id="R2", type="accepted"),
        Decision(
            risk_id="R3",
            type="modified",
            text="第十一条 保密义务\n11.1 双方对本合同内容及履行中知悉的对方商业秘密负有保密义务，保密期限为终止后三年。",
        ),
    ]
    return ReviewSession(
        id="e2e",
        filename="sample_contract.docx",
        file_type="docx",
        upload_bytes=(BASE_DIR / "sample_contract.docx").read_bytes(),
        clauses=clauses,
        risks=risks,
        decisions={d.risk_id: d for d in decisions},
    )


class TestE2ESampleTrack(unittest.TestCase):
    def test_sample_contract_full_flow(self):
        session = _load_session()
        buf = export_final_docx(session, track_changes=True)

        xml = zipfile.ZipFile(buf).read("word/document.xml").decode("utf-8")
        names = set(zipfile.ZipFile(buf).namelist())

        # 修订痕迹
        self.assertIn("<w:ins", xml)
        self.assertIn("<w:del", xml)
        # replace 生效（新文本在 w:ins 内）
        self.assertIn("第三方鉴定", xml)
        # delete 生效（原文进 w:delText）
        self.assertIn("w:delText", xml)
        # modified 决策采用用户编辑文本（三年）
        self.assertIn("三年", xml)
        # insert_after 新条款
        self.assertIn("第十一条 保密义务", xml)
        # 用户要求：直接在文档里改，不挂批注气泡
        self.assertNotIn("w:commentRangeStart", xml)
        self.assertNotIn("w:commentReference", xml)
        self.assertNotIn("word/comments.xml", names)
        # settings 带 trackRevisions（Word 打开后继续留痕）
        settings = zipfile.ZipFile(buf).read("word/settings.xml").decode("utf-8")
        self.assertIn("trackRevisions", settings)
        # python-docx 冒烟
        from docx import Document

        doc = Document(buf)
        self.assertTrue(len(doc.paragraphs) > 50)


if __name__ == "__main__":
    unittest.main()
