from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path

from stock_bro.limit_up import (
    LimitUpStock,
    classify_limit_up_session,
    collect_limit_up_stocks,
    is_st_stock,
    parse_eastmoney_limit_up_row,
    parse_trade_date,
    summarize_failed_limit_up_stocks,
    write_csv,
    write_jsonl,
    write_sqlite,
)


class LimitUpTests(unittest.TestCase):
    def test_parse_trade_date_accepts_dash_and_compact_formats(self) -> None:
        self.assertEqual(parse_trade_date("2026-05-11"), date(2026, 5, 11))
        self.assertEqual(parse_trade_date("20260511"), date(2026, 5, 11))

    def test_parse_eastmoney_row_normalizes_fields(self) -> None:
        record = parse_eastmoney_limit_up_row(
            {
                "c": "600000",
                "n": "ExampleBank",
                "p": 10230,
                "zdp": 10.04,
                "amount": 123456789,
                "fund": 9876543,
                "fbt": 93015,
                "lbt": "145901",
                "lbc": 2,
                "zbc": 1,
                "hybk": "Bank",
            },
            date(2026, 5, 11),
            "2026-05-11T08:00:00+00:00",
        )

        self.assertEqual(record.trade_date, "2026-05-11")
        self.assertEqual(record.code, "600000")
        self.assertEqual(record.latest_price, 10.23)
        self.assertEqual(record.first_limit_up_time, "09:30:15")
        self.assertEqual(record.last_limit_up_time, "14:59:01")
        self.assertEqual(record.consecutive_limit_up_days, 2)
        self.assertEqual(record.failed_limit_up_times, 1)
        self.assertEqual(record.limit_up_session, "late_afternoon_after_1430")

        zero_time_record = parse_eastmoney_limit_up_row(
            {"c": "600001", "n": "ExampleStock", "fbt": 0, "lbt": "0"},
            date(2026, 5, 11),
            "2026-05-11T08:00:00+00:00",
        )
        self.assertIsNone(zero_time_record.first_limit_up_time)
        self.assertIsNone(zero_time_record.last_limit_up_time)

    def test_collect_returns_empty_list_when_payload_data_is_null(self) -> None:
        import stock_bro.limit_up as limit_up

        original = limit_up.fetch_eastmoney_limit_up_payload
        limit_up.fetch_eastmoney_limit_up_payload = lambda trade_date, timeout=15.0: {"data": None}
        try:
            self.assertEqual(collect_limit_up_stocks(date(2026, 5, 11)), [])
        finally:
            limit_up.fetch_eastmoney_limit_up_payload = original

    def test_collect_excludes_st_by_default(self) -> None:
        import stock_bro.limit_up as limit_up

        payload = {
            "data": {
                "pool": [
                    {"c": "600001", "n": "STExample"},
                    {"c": "600002", "n": "*STExample"},
                    {"c": "600003", "n": "NormalName"},
                ]
            }
        }
        original = limit_up.fetch_eastmoney_limit_up_payload
        limit_up.fetch_eastmoney_limit_up_payload = lambda trade_date, timeout=15.0: payload
        try:
            default_records = collect_limit_up_stocks(date(2026, 5, 11))
            all_records = collect_limit_up_stocks(date(2026, 5, 11), include_st=True)
        finally:
            limit_up.fetch_eastmoney_limit_up_payload = original

        self.assertEqual([record.code for record in default_records], ["600003"])
        self.assertEqual(len(all_records), 3)

    def test_is_st_stock_matches_st_prefixes(self) -> None:
        self.assertTrue(is_st_stock("STExample"))
        self.assertTrue(is_st_stock("*STExample"))
        self.assertTrue(is_st_stock("S*STExample"))
        self.assertFalse(is_st_stock("ExampleST"))

    def test_classify_limit_up_session(self) -> None:
        self.assertEqual(classify_limit_up_session("09:25:00", 0), "opening")
        self.assertEqual(classify_limit_up_session("09:25:00", 1), "opening")
        self.assertEqual(classify_limit_up_session("09:30:00", 0), "opening")
        self.assertEqual(classify_limit_up_session("09:30:01", 0), "morning_9_to_10")
        self.assertEqual(classify_limit_up_session("09:59:59", 0), "morning_9_to_10")
        self.assertEqual(classify_limit_up_session("10:00:00", 0), "morning_10_to_1130")
        self.assertEqual(classify_limit_up_session("11:30:00", 0), "morning_10_to_1130")
        self.assertEqual(classify_limit_up_session("12:10:00", 0), "afternoon_1130_to_1430")
        self.assertEqual(classify_limit_up_session("14:30:00", 0), "afternoon_1130_to_1430")
        self.assertEqual(classify_limit_up_session("14:30:01", 0), "late_afternoon_after_1430")
        self.assertEqual(classify_limit_up_session(None, 0), "unknown")

    def test_summarize_failed_limit_up_stocks_groups_by_close_relation(self) -> None:
        records = [
            self._record("600001", "Above", failed_limit_up_times=1, change_percent=3.2),
            self._record("600002", "At", failed_limit_up_times=2, change_percent=0.0),
            self._record("600003", "Below", failed_limit_up_times=1, change_percent=-1.1),
            self._record("600004", "Unknown", failed_limit_up_times=1, change_percent=None),
            self._record("600005", "NotFailed", failed_limit_up_times=0, change_percent=-2.0),
        ]

        summary = summarize_failed_limit_up_stocks(records)

        self.assertEqual([record.code for record in summary.failed_stocks], ["600001", "600002", "600003", "600004"])
        self.assertEqual([record.code for record in summary.closed_above_previous_close], ["600001"])
        self.assertEqual([record.code for record in summary.closed_at_previous_close], ["600002"])
        self.assertEqual([record.code for record in summary.closed_below_previous_close], ["600003"])
        self.assertEqual([record.code for record in summary.unknown_close_relation], ["600004"])

    def test_writes_csv_jsonl_and_sqlite(self) -> None:
        records = [
            LimitUpStock(
                trade_date="2026-05-11",
                code="600000",
                name="ExampleBank",
                latest_price=10.23,
                change_percent=10.04,
                turnover_amount=123456789.0,
                limit_up_amount=9876543.0,
                first_limit_up_time="09:30:15",
                last_limit_up_time="14:59:01",
                consecutive_limit_up_days=2,
                failed_limit_up_times=1,
                limit_up_session="morning_9_to_10",
                industry="Bank",
                raw={"c": "600000"},
                collected_at="2026-05-11T08:00:00+00:00",
            )
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = write_csv(records, root)
            jsonl_path = write_jsonl(records, root)
            db_path = root / "stock_bro.sqlite3"
            write_sqlite(records, db_path, trade_date=date(2026, 5, 11))

            self.assertTrue(csv_path.exists())
            self.assertIn("ExampleBank", csv_path.read_text(encoding="utf-8-sig"))

            json_line = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
            self.assertEqual(json_line["code"], "600000")
            self.assertEqual(json_line["limit_up_session"], "morning_9_to_10")

            with closing(sqlite3.connect(db_path)) as connection:
                row = connection.execute(
                    "SELECT code, name, limit_up_session FROM limit_up_stocks WHERE trade_date = ?",
                    ("2026-05-11",),
                ).fetchone()
            self.assertEqual(row, ("600000", "ExampleBank", "morning_9_to_10"))

    def _record(
        self,
        code: str,
        name: str,
        failed_limit_up_times: int | None,
        change_percent: float | None,
    ) -> LimitUpStock:
        return LimitUpStock(
            trade_date="2026-05-11",
            code=code,
            name=name,
            latest_price=None,
            change_percent=change_percent,
            turnover_amount=None,
            limit_up_amount=None,
            first_limit_up_time=None,
            last_limit_up_time=None,
            consecutive_limit_up_days=None,
            failed_limit_up_times=failed_limit_up_times,
            limit_up_session="unknown",
            industry=None,
            raw={},
            collected_at="2026-05-11T08:00:00+00:00",
        )


if __name__ == "__main__":
    unittest.main()
