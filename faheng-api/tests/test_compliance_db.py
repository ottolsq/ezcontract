"""履约模块 DB / 物化 / 通知测试（tempfile 临时库，不碰真实 data/）

运行：./venv/bin/python -m unittest tests.test_compliance_db -v
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.schemas.compliance import ComplianceLLMOut  # noqa: E402
from app.services import compliance_service as svc  # noqa: E402
from app.services.compliance_db import get_conn, init_db, row_to_dict  # noqa: E402
from app.services.compliance_extract import CandidateUnit  # noqa: E402


class _TempDB(unittest.TestCase):
    """每个用例独立临时库，并通过 settings 注入"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "compliance.db"
        init_db(self.db_path)
        self._orig_path = svc.settings.COMPLIANCE_DB_PATH
        svc.settings.COMPLIANCE_DB_PATH = self.db_path  # type: ignore[misc]

    def tearDown(self):
        svc.settings.COMPLIANCE_DB_PATH = self._orig_path  # type: ignore[misc]
        self._tmp.cleanup()

    def _insert_contract(self, cid="c1", filename="t.docx", status="completed", **kw):
        with get_conn(self.db_path) as conn:
            conn.execute(
                "INSERT INTO contracts (id, filename, status, sign_date, start_date, "
                "end_date, clause_count, candidate_count, candidates_json, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    cid,
                    filename,
                    status,
                    kw.get("sign_date"),
                    kw.get("start_date"),
                    kw.get("end_date"),
                    1,
                    1,
                    "[]",
                    "2026-09-30T00:00:00",
                ),
            )

    def _insert_milestone(self, mid, cid="c1", **kw):
        defaults = {
            "recurring_group": "",
            "instance_index": 0,
            "node_type": "other",
            "title": "测试节点",
            "description": "",
            "clause_ref": "第1条",
            "clause_text": "",
            "due_date": None,
            "status": "pending",
            "needs_review": 0,
            "due_date_edited": 0,
            "recurring": "none",
            "offset_days": 0,
            "done_at": None,
            "created_at": "2026-09-30T00:00:00",
        }
        defaults.update(kw)
        with get_conn(self.db_path) as conn:
            conn.execute(
                "INSERT INTO milestones (id, contract_id, recurring_group, instance_index, "
                "node_type, title, description, clause_ref, clause_text, due_date, status, "
                "needs_review, due_date_edited, recurring, offset_days, done_at, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (mid, cid, *[defaults[k] for k in (
                    "recurring_group", "instance_index", "node_type", "title",
                    "description", "clause_ref", "clause_text", "due_date", "status",
                    "needs_review", "due_date_edited", "recurring", "offset_days",
                    "done_at", "created_at")]),
            )
        return defaults


class TestMaterialize(_TempDB):
    def _candidates(self):
        return [
            CandidateUnit(
                ref="C04#4.1(2)",
                display_ref="第4条 4.1（2）",
                text="（2）租金支付周期为每季度，乙方应于每个支付周期开始前7日内向甲方支付当期租金。",
            ),
            CandidateUnit(
                ref="C04#4.2(1)",
                display_ref="第4条 4.2（1）",
                text="（1）乙方应于本合同签署后3日内向甲方支付押金人民币8400元。",
            ),
        ]

    def test_llm_nodes_materialized(self):
        self._insert_contract()
        out = ComplianceLLMOut.model_validate(
            {
                "meta": {
                    "sign_date": "2026-09-28",
                    "contract_start": "2026-10-01",
                    "contract_end": "2028-09-30",
                },
                "nodes": [
                    {
                        "ref": "C04#4.1(2)",
                        "node_type": "payment",
                        "title": "支付季度租金",
                        "anchor": "contract_start",
                        "offset_days": -7,
                        "recurring": "quarterly",
                    },
                    {
                        "ref": "C04#4.2(1)",
                        "node_type": "deposit",
                        "title": "支付押金",
                        "anchor": "sign_date",
                        "offset_days": 3,
                    },
                    # 幻觉 ref：不在候选集 → 丢弃
                    {"ref": "C99#FAKE", "node_type": "other", "title": "幻觉"},
                    # 重复 ref → 去重
                    {
                        "ref": "C04#4.2(1)",
                        "node_type": "other",
                        "title": "重复节点",
                    },
                ],
            }
        )
        n = svc._materialize("c1", "t.docx", self._candidates(), [], out, "")
        self.assertEqual(n, 5)  # 4 期租金 + 1 押金

        with get_conn(self.db_path) as conn:
            rows = [
                row_to_dict(r)
                for r in conn.execute(
                    "SELECT * FROM milestones WHERE contract_id='c1' ORDER BY instance_index"
                )
            ]
        rents = [r for r in rows if r["recurring"] == "quarterly"]
        self.assertEqual(len(rents), 4)
        self.assertEqual(rents[0]["due_date"], "2026-09-24")
        self.assertEqual(rents[1]["due_date"], "2026-12-25")
        # 同组共享 recurring_group
        self.assertTrue(rents[0]["recurring_group"])
        self.assertEqual(rents[0]["recurring_group"], rents[3]["recurring_group"])
        deposit = [r for r in rows if r["node_type"] == "deposit"]
        self.assertEqual(deposit[0]["due_date"], "2026-10-01")

        # 合同 meta 已写回
        with get_conn(self.db_path) as conn:
            crow = row_to_dict(
                conn.execute("SELECT * FROM contracts WHERE id='c1'").fetchone()
            )
        self.assertEqual(crow["sign_date"], "2026-09-28")
        self.assertEqual(crow["start_date"], "2026-10-01")
        self.assertEqual(crow["end_date"], "2028-09-30")

    def test_meta_fallback_from_candidates(self):
        # LLM meta 全空 → 从候选行「自X起至Y止」+ meta_lines「签署日期」兜底
        self._insert_contract()
        cands = [
            CandidateUnit(
                ref="C02#2.2",
                display_ref="第2条 2.2",
                text="2.2 租赁期限：自2026-10-01起至2028-09-30止，共计24个月。",
            )
        ]
        out = ComplianceLLMOut.model_validate(
            {
                "meta": {},
                "nodes": [
                    {
                        "ref": "C02#2.2",
                        "node_type": "expiry",
                        "title": "租期届满",
                        "anchor": "absolute",
                        "anchor_date": "2028-09-30",
                    }
                ],
            }
        )
        svc._materialize("c1", "t.docx", cands, ["签署日期：2026-09-28"], out, "")
        with get_conn(self.db_path) as conn:
            crow = row_to_dict(
                conn.execute("SELECT * FROM contracts WHERE id='c1'").fetchone()
            )
        self.assertEqual(crow["sign_date"], "2026-09-28")
        self.assertEqual(crow["start_date"], "2026-10-01")
        self.assertEqual(crow["end_date"], "2028-09-30")

    def test_fallback_all_candidates_needs_review(self):
        self._insert_contract()
        cands = self._candidates()
        n = svc._materialize("c1", "t.docx", cands, [], None, "AI 提取失败，已转为人工确认模式")
        self.assertEqual(n, 2)
        with get_conn(self.db_path) as conn:
            rows = [
                row_to_dict(r)
                for r in conn.execute(
                    "SELECT * FROM milestones WHERE contract_id='c1'"
                )
            ]
        self.assertTrue(all(r["needs_review"] == 1 for r in rows))
        self.assertTrue(all(r["due_date"] is None for r in rows))
        with get_conn(self.db_path) as conn:
            crow = row_to_dict(
                conn.execute("SELECT * FROM contracts WHERE id='c1'").fetchone()
            )
        self.assertIn("人工确认", crow["error"])


class TestRecurringAppend(_TempDB):
    def test_complete_max_instance_appends_next(self):
        self._insert_contract(start_date="2026-10-01", end_date="2028-09-30")
        group = "g1"
        for idx, due in enumerate(
            ["2026-09-24", "2026-12-25", "2027-03-25", "2027-06-24"]
        ):
            self._insert_milestone(
                f"m{idx}",
                recurring_group=group,
                instance_index=idx,
                recurring="quarterly",
                offset_days=-7,
                due_date=due,
            )
        result = svc.set_milestone_status("m3", "done")
        self.assertTrue(result["next_created"])
        with get_conn(self.db_path) as conn:
            rows = [
                row_to_dict(r)
                for r in conn.execute(
                    "SELECT instance_index, due_date, status FROM milestones "
                    "WHERE recurring_group=? ORDER BY instance_index",
                    (group,),
                )
            ]
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[4]["instance_index"], 4)
        self.assertEqual(rows[4]["due_date"], "2027-09-24")
        self.assertEqual(rows[4]["status"], "pending")

    def test_complete_older_instance_no_append(self):
        self._insert_contract(start_date="2026-10-01", end_date="2028-09-30")
        for idx, due in enumerate(
            ["2026-09-24", "2026-12-25", "2027-03-25", "2027-06-24"]
        ):
            self._insert_milestone(
                f"m{idx}",
                recurring_group="g1",
                instance_index=idx,
                recurring="quarterly",
                offset_days=-7,
                due_date=due,
            )
        result = svc.set_milestone_status("m0", "done")
        self.assertFalse(result["next_created"])
        with get_conn(self.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM milestones WHERE recurring_group='g1'"
            ).fetchone()[0]
        self.assertEqual(count, 4)

    def test_append_respects_end_date(self):
        # 租期到 2027-06-30：第 4 期（2027-07-01 起）超出租期 → 不追加
        self._insert_contract(start_date="2026-10-01", end_date="2027-06-30")
        for idx, due in enumerate(
            ["2026-09-24", "2026-12-25", "2027-03-25"]
        ):
            self._insert_milestone(
                f"m{idx}",
                recurring_group="g1",
                instance_index=idx,
                recurring="quarterly",
                offset_days=-7,
                due_date=due,
            )
        result = svc.set_milestone_status("m2", "done")
        # nstart = 2027-07-01 > end 2027-06-30 → 不追加
        self.assertFalse(result["next_created"])


class TestNotifications(_TempDB):
    def test_due_soon_and_overdue_created_once(self):
        self._insert_contract()
        # 明天到期 / 已逾期 6 天 / 今天到期 / 待确认（无 due）
        self._insert_milestone("m1", due_date=str(date.today().toordinal() and (date.fromordinal(date.today().toordinal() + 1))))
        self._insert_milestone("m2", due_date="2026-09-24")
        self._insert_milestone("m3", due_date=str(date.today()))
        self._insert_milestone("m4", due_date=None, needs_review=1)

        result = svc.list_notifications()
        # today 是测试运行日；m2 的 2026-09-24 只有在 today > 2026-09-24 时才算逾期
        # （CI 环境日期不定 → 只断言结构性与幂等）
        first = {n["milestone_id"]: n["kind"] for n in result["items"]}
        self.assertIn("m1", first)
        self.assertEqual(first["m1"], "due_soon")
        self.assertNotIn("m4", first)  # 无 due 不产生通知

        # 幂等：跑两遍不重复
        again = svc.list_notifications()
        ids = [n["milestone_id"] + n["kind"] for n in again["items"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_mark_read(self):
        self._insert_contract()
        self._insert_milestone("m1", due_date=str(date.fromordinal(date.today().toordinal() + 1)))
        svc.list_notifications()
        result = svc.mark_notifications_read(mark_all=True)
        self.assertEqual(result["unread"], 0)

    def test_done_milestone_not_notified(self):
        self._insert_contract()
        self._insert_milestone(
            "m1", due_date=str(date.fromordinal(date.today().toordinal() + 1)), status="done"
        )
        result = svc.list_notifications()
        self.assertNotIn("m1", [n["milestone_id"] for n in result["items"]])


class TestDeleteCascade(_TempDB):
    def test_delete_removes_milestones_and_notifications(self):
        self._insert_contract()
        self._insert_milestone("m1", due_date="2026-09-24")
        svc.list_notifications()  # 产生通知（若当日已逾期）
        svc.delete_contract("c1")
        with get_conn(self.db_path) as conn:
            for table in ("milestones", "notifications", "contracts"):
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                self.assertEqual(count, 0, table)


class TestDueDateEdit(_TempDB):
    def test_edit_and_clear(self):
        self._insert_contract()
        self._insert_milestone("m1", needs_review=1)
        svc.set_milestone_due_date("m1", "2026-10-05")
        with get_conn(self.db_path) as conn:
            row = row_to_dict(
                conn.execute("SELECT * FROM milestones WHERE id='m1'").fetchone()
            )
        self.assertEqual(row["due_date"], "2026-10-05")
        self.assertEqual(row["due_date_edited"], 1)
        # 清空回待确认
        svc.set_milestone_due_date("m1", "")
        with get_conn(self.db_path) as conn:
            row = row_to_dict(
                conn.execute("SELECT * FROM milestones WHERE id='m1'").fetchone()
            )
        self.assertIsNone(row["due_date"])


if __name__ == "__main__":
    unittest.main()
