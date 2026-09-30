"""履约节点日期计算测试

运行：./venv/bin/python -m unittest tests.test_compliance_dates -v
"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.services.compliance_dates import (  # noqa: E402
    add_months,
    compute_due_date,
    days_left,
    expand_recurring,
    parse_date,
    period_start,
)


class TestParseDate(unittest.TestCase):
    def test_iso(self):
        self.assertEqual(parse_date("自2026-10-01起"), date(2026, 10, 1))

    def test_slash(self):
        self.assertEqual(parse_date("2026/10/1"), date(2026, 10, 1))

    def test_chinese(self):
        self.assertEqual(parse_date("2026年10月1日"), date(2026, 10, 1))

    def test_dots(self):
        self.assertEqual(parse_date("签署于2026.9.28"), date(2026, 9, 28))

    def test_none_and_invalid(self):
        self.assertIsNone(parse_date(""))
        self.assertIsNone(parse_date(None))
        self.assertIsNone(parse_date("2026-13-40"))  # 非法日期兜底

    def test_period_structure(self):
        # 自X起至Y止 —— 两个日期都能各自抓到
        text = "租赁期限：自2026-10-01起至2028-09-30止，共计24个月。"
        self.assertEqual(parse_date(text), date(2026, 10, 1))


class TestAddMonths(unittest.TestCase):
    def test_month_end_clamp(self):
        # 1.31 + 1 月 → 2.28（2026 非闰年）
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))

    def test_month_end_clamp_leap(self):
        # 1.31 + 1 月 → 2.29（2028 闰年）
        self.assertEqual(add_months(date(2028, 1, 31), 1), date(2028, 2, 29))

    def test_zero(self):
        self.assertEqual(add_months(date(2026, 5, 15), 0), date(2026, 5, 15))

    def test_years(self):
        # "终止后2年" → +24 个月，而不是 730 天
        self.assertEqual(add_months(date(2028, 9, 30), 24), date(2030, 9, 30))

    def test_negative(self):
        self.assertEqual(add_months(date(2026, 3, 31), -1), date(2026, 2, 28))


class TestPeriodStart(unittest.TestCase):
    def test_quarterly_from_base(self):
        base = date(2026, 10, 1)
        self.assertEqual(period_start(base, 0, "quarterly"), date(2026, 10, 1))
        self.assertEqual(period_start(base, 1, "quarterly"), date(2027, 1, 1))
        self.assertEqual(period_start(base, 3, "quarterly"), date(2027, 7, 1))

    def test_monthly(self):
        base = date(2026, 1, 31)
        self.assertEqual(period_start(base, 1, "monthly"), date(2026, 2, 28))

    def test_unknown_period_raises(self):
        with self.assertRaises(ValueError):
            period_start(date(2026, 1, 1), 0, "weekly")


class TestExpandRecurring(unittest.TestCase):
    def test_sample_quarterly_rent(self):
        # 样本合同：季度租金，每期开始前 7 日内支付
        out = expand_recurring(date(2026, 10, 1), "quarterly", -7, 4)
        self.assertEqual(
            [d for _, d in out],
            [
                date(2026, 9, 24),
                date(2026, 12, 25),
                date(2027, 3, 25),
                date(2027, 6, 24),
            ],
        )
        self.assertEqual([i for i, _ in out], [0, 1, 2, 3])

    def test_until_truncates(self):
        # 租期到 2027-03-30 → 第 3 期（2027-07-01 起）超出租期被截断
        out = expand_recurring(date(2026, 10, 1), "quarterly", -7, 4, until=date(2027, 3, 30))
        self.assertEqual(len(out), 2)

    def test_yearly(self):
        out = expand_recurring(date(2026, 5, 1), "yearly", 0, 3)
        self.assertEqual([d for _, d in out], [date(2026, 5, 1), date(2027, 5, 1), date(2028, 5, 1)])


class TestComputeDueDate(unittest.TestCase):
    def test_sign_plus_days(self):
        # 签署后 3 日内付押金：2026-09-28 + 3d
        self.assertEqual(compute_due_date(date(2026, 9, 28), 0, 3), date(2026, 10, 1))

    def test_end_plus_months_and_days(self):
        # 终止后 2 年内保密：2028-09-30 + 24 月
        self.assertEqual(compute_due_date(date(2028, 9, 30), 24, 0), date(2030, 9, 30))
        # 租赁期满后 7 日内退押金
        self.assertEqual(compute_due_date(date(2028, 9, 30), 0, 7), date(2028, 10, 7))


class TestDaysLeft(unittest.TestCase):
    def test_today_and_tomorrow(self):
        today = date(2026, 9, 30)
        self.assertEqual(days_left(today, today), 0)
        self.assertEqual(days_left(date(2026, 10, 1), today), 1)

    def test_overdue_negative(self):
        self.assertEqual(days_left(date(2026, 9, 24), date(2026, 9, 30)), -6)

    def test_none(self):
        self.assertIsNone(days_left(None))


if __name__ == "__main__":
    unittest.main()
