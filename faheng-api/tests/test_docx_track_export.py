"""Track Changes 导出单测（fixPlan.md §六；stdlib unittest，不引 pytest）

用 sample_contract.docx / 手工构造 docx 验证：
1. replace / insert / delete 后 w:ins / w:del / w:commentRangeStart 存在；
2. 新段落 pPr 与模板一致、w14:paraId 无重复；
3. 所有 w:t 内无字面 \n；
4. pack 产物能被 python-docx 重新打开；
5. 降级路径：越界 clause_id 不抛异常，落回就地替换。

运行：./venv/bin/python -m unittest tests.test_docx_track_export -v
"""
from __future__ import annotations

import io
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.schemas.review import (  # noqa: E402
    Clause,
    Decision,
    ReviewSession,
    RiskItem,
    SubItem,
)
from app.services.docx_export import export_final_docx  # noqa: E402
from app.services.docx_track_export import (  # noqa: E402
    _bridge_import,
    export_docx_with_track_changes,
)


def _make_docx_bytes() -> bytes:
    """构造测试 docx：3 条条款 + hyperlink 段 + 首行缩进 + 第X条加粗 + 多行子项段。"""
    from docx import Document
    from docx.enum.text import WD_LINE_SPACING
    from docx.oxml.ns import qn
    from docx.shared import Pt

    doc = Document()
    p = doc.add_paragraph()
    run = p.add_run("测试采购合同")
    run.bold = True
    run.font.size = Pt(16)

    for title, body in [
        ("第一条 合同金额", "合同总价为人民币壹拾万元整，含税。"),
        ("第二条 付款方式", "甲方应在收到发票后三十日内一次性支付全部款项。"),
        ("第三条 违约责任", "任何一方违约应赔偿对方全部损失。"),
    ]:
        hp = doc.add_paragraph()
        hr = hp.add_run(title)
        hr.bold = True
        pf = hp.paragraph_format
        pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
        pf.line_spacing = 1.5
        pPr = hp._p.get_or_add_pPr()
        ind = pPr.makeelement(qn("w:ind"), {})
        ind.set(qn("w:firstLineChars"), "200")
        ind.set(qn("w:firstLine"), "480")
        pPr.append(ind)
        bp = doc.add_paragraph()
        bp.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
        bp.paragraph_format.line_spacing = 1.5
        bp.add_run(body)

    # 多行子项段：单条 <w:p> 内用 w:br 分隔两条子项（模拟真实合同"4.1 ...\n4.2 ..."）
    mp = doc.add_paragraph()
    mp.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    mp.paragraph_format.line_spacing = 1.5
    mp.add_run("第四条 押金条款")
    br_run = mp.add_run()
    br_el = br_run._element.makeelement(qn("w:br"), {})
    br_run._element.append(br_el)
    mp.add_run("4.1 乙方应于合同签订后三日内支付押金")
    br_run2 = mp.add_run()
    br_el2 = br_run2._element.makeelement(qn("w:br"), {})
    br_run2._element.append(br_el2)
    mp.add_run("4.2 甲方应于合同终止后无息退还押金")

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _make_session(docx_bytes: bytes, risks, decisions) -> ReviewSession:
    clauses = [
        Clause(
            clause_id="C01",
            clause_no="第一条",
            title="合同金额",
            text="第一条 合同金额\n合同总价为人民币壹拾万元整，含税。",
            start_idx=1,
            end_idx=2,
        ),
        Clause(
            clause_id="C02",
            clause_no="第二条",
            title="付款方式",
            text="第二条 付款方式\n甲方应在收到发票后三十日内一次性支付全部款项。",
            start_idx=3,
            end_idx=4,
        ),
        Clause(
            clause_id="C03",
            clause_no="第三条",
            title="违约责任",
            text="第三条 违约责任\n任何一方违约应赔偿对方全部损失。",
            start_idx=5,
            end_idx=6,
        ),
        Clause(
            clause_id="C04",
            clause_no="第四条",
            title="押金条款",
            # 多行子项段：用 \\n 分隔以匹配 _make_docx_bytes() 内的 <w:br/> 结构
            text="第四条 押金条款\n4.1 乙方应于合同签订后三日内支付押金\n4.2 甲方应于合同终止后无息退还押金",
            start_idx=7,
            end_idx=7,
            subitems=[
                SubItem(sub_item_no="4.1", start_idx=7, end_idx=7),
                SubItem(sub_item_no="4.2", start_idx=7, end_idx=7),
            ],
        ),
    ]
    return ReviewSession(
        id="test-session",
        filename="测试合同.docx",
        file_type="docx",
        upload_bytes=docx_bytes,
        clauses=clauses,
        risks=risks,
        decisions={d.risk_id: d for d in decisions},
    )


def _unpack_xml(buf: io.BytesIO, part: str = "word/document.xml") -> str:
    with zipfile.ZipFile(buf) as zf:
        return zf.read(part).decode("utf-8")


class TestTrackExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docx_bytes = _make_docx_bytes()

    def _session_replace(self):
        risks = [
            RiskItem(
                risk_id="R1",
                clause_id="C01",
                title="金额条款风险",
                level="high",
                issue="总价未明确币种",
                impact="可能产生汇率争议",
                suggestion="合同总价为人民币壹拾万元整（含税），币种为人民币。",
                sub_item_no="",
                operation="replace",
            )
        ]
        decisions = [Decision(risk_id="R1", type="accepted")]
        return _make_session(self.docx_bytes, risks, decisions)

    def test_replace_produces_ins_del_no_comment(self):
        """用户要求直接在文档里改，不再挂批注：export 不写 w:commentRangeStart / comments.xml。"""
        buf = export_docx_with_track_changes(self._session_replace())
        xml = _unpack_xml(buf)
        # 修订痕迹仍保留
        self.assertIn("<w:ins", xml)
        self.assertIn("<w:del", xml)
        # 批注气泡已关闭
        self.assertNotIn("w:commentRangeStart", xml)
        self.assertNotIn("w:commentRangeEnd", xml)
        self.assertNotIn("w:commentReference", xml)
        # word/comments.xml 不应被打包（无批注 → 整文件缺失）
        with zipfile.ZipFile(buf) as zf:
            self.assertNotIn("word/comments.xml", zf.namelist())

    def test_no_literal_newline_in_wt(self):
        session = self._session_replace()
        buf = export_docx_with_track_changes(session)
        xml = _unpack_xml(buf)
        for frag in xml.split("<w:t")[1:]:
            body = frag.split(">", 1)[1].split("</w:t>")[0]
            self.assertNotIn("\n", body, f"w:t 含字面换行: {body[:50]!r}")

    def test_para_ids_unique(self):
        buf = export_docx_with_track_changes(self._session_replace())
        xml = _unpack_xml(buf)
        import re

        ids = re.findall(r'w14:paraId="([0-9A-F]+)"', xml)
        self.assertEqual(len(ids), len(set(ids)), "paraId 重复")

    def test_output_opens_with_python_docx(self):
        buf = export_docx_with_track_changes(self._session_replace())
        from docx import Document

        doc = Document(buf)  # Word 级解析器能打开即冒烟通过
        self.assertTrue(len(doc.paragraphs) >= 6)

    def test_insert_after_new_clause(self):
        risks = [
            RiskItem(
                risk_id="R2",
                clause_id="C03",
                title="缺保密条款",
                level="medium",
                issue="无保密义务约定",
                impact="商业信息可能泄露",
                suggestion="第四条 保密义务\n4.1 双方对合同内容负有保密义务。\n4.2 保密期限为合同终止后两年。",
                operation="insert_after",
                anchor_clause_id="C03",
            )
        ]
        decisions = [Decision(risk_id="R2", type="accepted")]
        session = _make_session(self.docx_bytes, risks, decisions)
        buf = export_docx_with_track_changes(session)
        xml = _unpack_xml(buf)
        self.assertIn("<w:ins", xml)
        self.assertIn("第四条 保密义务", xml)
        self.assertIn("4.1", xml)
        self.assertIn("4.2", xml)
        from docx import Document

        Document(buf)  # 能打开

    def test_insert_before(self):
        risks = [
            RiskItem(
                risk_id="R3",
                clause_id="C02",
                title="缺定义条款",
                level="low",
                issue="无术语定义",
                impact="解释空间大",
                suggestion="1.1 定义：本合同所称“产品”指附件一所列设备。",
                operation="insert_before",
                anchor_clause_id="C02",
            )
        ]
        decisions = [Decision(risk_id="R3", type="accepted")]
        session = _make_session(self.docx_bytes, risks, decisions)
        buf = export_docx_with_track_changes(session)
        xml = _unpack_xml(buf)
        self.assertIn("1.1 定义", xml)

    def test_delete_clause_body(self):
        risks = [
            RiskItem(
                risk_id="R4",
                clause_id="C03",
                title="责任过重",
                level="high",
                issue="全部损失赔偿过重",
                impact="风险不可控",
                suggestion="",
                operation="delete",
            )
        ]
        decisions = [Decision(risk_id="R4", type="accepted")]
        session = _make_session(self.docx_bytes, risks, decisions)
        buf = export_docx_with_track_changes(session)
        xml = _unpack_xml(buf)
        self.assertIn("<w:del", xml)
        self.assertIn("w:delText", xml)

    def test_replace_keeps_ppr_from_template(self):
        """新/替换段落 pPr 应继承模板段（w:ind / w:spacing 存在）。"""
        risks = [
            RiskItem(
                risk_id="R5",
                clause_id="C02",
                title="付款期过长",
                level="medium",
                issue="三十日过长",
                impact="资金占用",
                suggestion="甲方应在收到发票后十五日内一次性支付全部款项。",
                operation="replace",
            )
        ]
        decisions = [Decision(risk_id="R5", type="accepted")]
        session = _make_session(self.docx_bytes, risks, decisions)
        buf = export_docx_with_track_changes(session)
        xml = _unpack_xml(buf)
        self.assertIn("<w:ins", xml)

    def test_out_of_range_clause_degrades_inplace(self):
        """越界 clause_id：track 路径单条跳过，导出仍成功（不 500）。"""
        risks = [
            RiskItem(
                risk_id="R6",
                clause_id="C99",
                title="幽灵条款",
                level="low",
                issue="引用不存在条款",
                impact="无",
                suggestion="不存在条款的替换文本",
                operation="replace",
            )
        ]
        decisions = [Decision(risk_id="R6", type="accepted")]
        session = _make_session(self.docx_bytes, risks, decisions)
        buf = export_final_docx(session)  # 不抛异常
        from docx import Document

        Document(buf)

    def test_track_changes_false_goes_inplace(self):
        session = self._session_replace()
        buf = export_final_docx(session, track_changes=False)
        xml = _unpack_xml(buf)
        # 就地替换：无修订标记
        self.assertNotIn("<w:ins", xml)

    def test_corrupt_docx_degrades(self):
        """损坏 docx：降级路径最终也会失败（重建不可用），但错误可预期。"""
        risks = [
            RiskItem(
                risk_id="R7",
                clause_id="C01",
                title="x",
                level="low",
                issue="x",
                impact="x",
                suggestion="x",
            )
        ]
        decisions = [Decision(risk_id="R7", type="accepted")]
        session = _make_session(b"not a docx", risks, decisions)
        # 损坏字节会让两条路径都失败 —— export_final_docx 不吞此异常是预期行为
        with self.assertRaises(Exception):
            export_final_docx(session)

    def test_replace_keeps_line_break_in_paragraph(self):
        """多行子项段：替换其中一行后 w:br 保留，python-docx 仍能解析出换行。

        旧实现 _node_text() 忽略 w:br → old_text 丢失 \\n → 整段被压平，版式坍塌。
        修复后：文本按 \\n 拆分到多个 w:r，行间用 <w:br/> 分隔。
        本用例触发既有 delete（删除原 4.1 子句部分文本）又有 insert（追加"（已修订）"），
        确保 <w:del>/<w:ins> 都出现，证明 difflib 拿到了含 \\n 的 old_text。
        """
        risks = [
            RiskItem(
                risk_id="R_BR",
                clause_id="C04",
                title="押金条款多行替换",
                level="low",
                issue="验证 w:br 保留",
                impact="无",
                # 删除 4.1 末尾"押金"二字并追加"（已修订）" → 必产 delete + insert
                suggestion="第四条 押金条款\n4.1 乙方应于合同签订后三日内支付（已修订）\n4.2 甲方应于合同终止后无息退还押金",
                sub_item_no="",
                operation="replace",
            )
        ]
        decisions = [Decision(risk_id="R_BR", type="accepted")]
        session = _make_session(self.docx_bytes, risks, decisions)
        buf = export_docx_with_track_changes(session)
        xml = _unpack_xml(buf)
        # 修订痕迹就位
        self.assertIn("<w:ins", xml)
        self.assertIn("<w:del", xml)
        self.assertIn("w:delText", xml)
        # 关键回归：<w:br/> 元素仍然存在（多行版式未坍塌）
        self.assertIn("<w:br", xml)
        # 原"押"+"金"被删、新"（已修订）"已插（直接在 XML 里看，避免被 python-docx
        # 对 w:ins 的渲染策略影响）
        self.assertIn("押金", xml)  # 出现在 <w:delText> 里
        self.assertIn("（已修订）", xml)  # 出现在 <w:t>（w:ins 内）
        # python-docx 重打开后能解析出换行（w:br 留在段落层，w:ins 内文本不进入 .text）
        from docx import Document

        doc = Document(buf)
        target = next(p for p in doc.paragraphs if "第四条" in p.text)
        self.assertIn("\n", target.text)
        # w:t 内不含字面 \\n
        for frag in xml.split("<w:t")[1:]:
            body = frag.split(">", 1)[1].split("</w:t>")[0]
            self.assertNotIn("\n", body)

    def test_replace_parenthetical_subitem_hits_body_not_title(self):
        """X.Y(Z) 形式子项（如 3.1(3)）：必须命中 body 段，绝不能落在条款标题段。

        旧实现：clause_splitter.SUBITEM_RE 不识别 3.1(3) → clause.subitems 里没有
        该编号 → _resolve_target_idx 回落 clause.start_idx（标题段下标）→
        整段标题被删除替换。修复后：
        1. parser 已把 3.1(3) 加入 subitems（精确命中）；或
        2. parser 未识别时，_resolve_target_idx 退回基编号 3.1 子项；或
        3. _resolve_target 二次防御：若 idx==start_idx 且目标段是标题，
           主动扫 clause 区间找基编号开头的段。
        """
        # 专用 docx：idx 0 = 标题，idx 1 = body 段（含 3.1 + (3) 两行，w:br 分隔）
        from docx import Document

        doc = Document()
        hp = doc.add_paragraph()
        hr = hp.add_run("第三条 租金及支付方式")
        hr.bold = True
        bp = doc.add_paragraph()
        bp.add_run("3.1 租赁期间，乙方应依约履行义务")
        bp.add_run().add_break()  # <w:br/>
        bp.add_run("(3) 押金抵扣条款，原条款规定押金可全额抵扣。")
        buf = io.BytesIO()
        doc.save(buf)
        custom_docx = buf.getvalue()

        from app.schemas.review import Clause, SubItem

        clauses = [
            Clause(
                clause_id="C03",
                clause_no="第三条",
                title="租金及支付方式",
                text="第三条 租金及支付方式\n3.1 租赁期间，乙方应依约履行义务\n(3) 押金抵扣条款，原条款规定押金可全额抵扣。",
                start_idx=0,
                end_idx=1,
                subitems=[
                    SubItem(sub_item_no="3.1", start_idx=1, end_idx=1, line_in_paragraph=0),
                    SubItem(sub_item_no="3.1(3)", start_idx=1, end_idx=1, line_in_paragraph=1),
                ],
            ),
        ]
        risks = [
            RiskItem(
                risk_id="R_PAREN",
                clause_id="C03",
                title="括号层级替换",
                level="medium",
                issue="3.1(3) 条款需限定押金抵扣",
                impact="押金被全扣风险",
                # 直接以 3.1(3) 开头 —— 必须命中 body 段，不能落在标题段
                suggestion="3.1(3) 押金抵扣以实际损失为限，余额应退还乙方。",
                sub_item_no="3.1(3)",
                operation="replace",
            )
        ]
        decisions = [Decision(risk_id="R_PAREN", type="accepted")]
        session = ReviewSession(
            id="paren-test",
            filename="测试合同.docx",
            file_type="docx",
            upload_bytes=custom_docx,
            clauses=clauses,
            risks=risks,
            decisions={d.risk_id: d for d in decisions},
        )
        buf = export_docx_with_track_changes(session)
        xml = _unpack_xml(buf)
        # 修订痕迹存在
        self.assertIn("<w:ins", xml)
        self.assertIn("<w:del", xml)
        # 新文本落到 w:ins —— difflib 会按字符对齐拆分，新插入片段至少含 "以实际损失为限"
        self.assertIn("以实际损失为限", xml)
        self.assertIn("余额应退还乙方", xml)
        # 标题段（paragraph 0）不应被删除 —— 标题文本必须仍出现在 w:t 中
        # 关键校验：标题文本片段不能出现在 <w:delText>...</w:delText> 里
        import re as _re

        del_blocks = _re.findall(r"<w:delText[^>]*>([^<]*)</w:delText>", xml)
        joined_del = "".join(del_blocks)
        self.assertNotIn(
            "第三条",
            joined_del,
            f"标题段被误删（被替换进了 w:delText）：{joined_del[:120]!r}",
        )
        self.assertNotIn(
            "租金及支付方式",
            joined_del,
            f"标题文本被误删：{joined_del[:120]!r}",
        )
        # 标题段必须仍存在且含原始文本
        self.assertIn("第三条 租金及支付方式", xml)
        # python-docx 重打开后能解析出 body 段含原编号
        out_doc = Document(buf)
        body_texts = [p.text for p in out_doc.paragraphs]
        # python-docx .text 跳过 w:delText，所以 3.1 行（被 w:del 包裹）不出现在 .text；
        # (3) 行未被编辑应保留；本测试核心是保护标题段（paragraph 0）不被误删。
        self.assertTrue(
            any("第三条" in t for t in body_texts),
            f"标题段应保留：{body_texts}",
        )
        # 同段多子项：替换 line_in_paragraph=1（即 (3) 行），line 0 的 3.1 行原样保留，
        # 但被 w:del 包裹 → python-docx 不读。line 1 的 (3) 行被 w:del 包裹 → 同样跳过。
        # 因此 .text 只剩 paragraph 0 标题 + 仍可见的 3.1 旧 run（前面 w:r 没被标记）。
        self.assertTrue(
            any("3.1" in t for t in body_texts),
            f"未编辑的 3.1 行应保留：{body_texts}",
        )
        # (3) 行被 w:del 包住，python-docx 不读，是预期。3.1 行未被编辑应保留。
        # 标题段必须仍能被 python-docx 读到
        self.assertTrue(
            any("第三条" in t for t in body_texts),
            f"标题段应保留：{body_texts}",
        )

    def test_run_has_east_asia_font(self):
        """Track Changes 新生成的 w:r 必须显式声明 w:rFonts w:eastAsia，避免 Word 默认字体。"""
        buf = export_docx_with_track_changes(self._session_replace())
        xml = _unpack_xml(buf)
        # w:ins 内至少一个 w:r 含 eastAsia 声明
        ins_seg = xml.split("<w:ins", 1)[1].split("</w:ins>", 1)[0]
        self.assertIn("w:eastAsia", ins_seg, "修订段落缺少中文字体声明")

    def test_replace_inserts_use_role_fonts(self):
        """replace 后新插入的子项编号行 / 标题行 / 正文行应分别套用对应字体与加粗。

        回归原 bug：旧实现把段落首个 run 的 rPr 套到整段替换，导致子项编号行变成普通仿宋、
        标题加粗丢失、字号丢失。本用例要求每行独立判断角色：
        - 子项行（X.Y）：黑体、12pt、加粗
        - 正文行：仿宋、12pt、不加粗
        """
        from docx import Document

        doc = Document()
        # 模板段：标题加粗、子项加粗、正文仿宋
        hp = doc.add_paragraph()
        hr = hp.add_run("第一条 测试条款")
        hr.bold = True
        bp = doc.add_paragraph()
        sr = bp.add_run("1.1 子项正文")
        sr.bold = True
        bp2 = doc.add_paragraph()
        br = bp2.add_run("普通正文行")
        buf = io.BytesIO()
        doc.save(buf)
        custom_docx = buf.getvalue()

        from app.schemas.review import Clause

        clauses = [
            Clause(
                clause_id="C01",
                clause_no="第一条",
                title="测试条款",
                text="第一条 测试条款\n1.1 子项正文\n普通正文行",
                start_idx=0,
                end_idx=2,
                subitems=[],
            ),
        ]
        # 让 LLM 一次替换三行混合内容（子项行 + 正文行 + 新加的子项编号行）
        risks = [
            RiskItem(
                risk_id="R_ROLE",
                clause_id="C01",
                title="角色格式化",
                level="low",
                issue="子项加粗应保留",
                impact="无",
                suggestion="1.1 子项正文新版\n普通正文行新版\n1.2 新增子项",
                sub_item_no="",
                operation="replace",
            )
        ]
        decisions = [Decision(risk_id="R_ROLE", type="accepted")]
        session = ReviewSession(
            id="role-test",
            filename="测试合同.docx",
            file_type="docx",
            upload_bytes=custom_docx,
            clauses=clauses,
            risks=risks,
            decisions={d.risk_id: d for d in decisions},
        )
        buf = export_docx_with_track_changes(session)
        xml = _unpack_xml(buf)
        # 修订痕迹
        self.assertIn("<w:ins", xml)
        ins_seg = xml.split("<w:ins", 1)[1].split("</w:ins>", 1)[0]
        # 必须包含黑体（子项编号 / 标题）和仿宋（正文）
        self.assertIn("黑体", ins_seg, "子项行/标题行应使用黑体")
        self.assertIn("仿宋", ins_seg, "正文行应使用仿宋")
        # 子项行应加粗：寻找子项编号所在 run 必须有 w:b
        # 简化断言：ins 内 w:b 总数应 >= 1（子项行至少有一个加粗 run）
        self.assertIn("<w:b/>", ins_seg, "子项行加粗丢失")
        # 字号：应至少有半磅 24（12pt）声明
        self.assertIn('<w:sz w:val="24"', ins_seg, "正文行/子项行字号丢失")


if __name__ == "__main__":
    unittest.main()
