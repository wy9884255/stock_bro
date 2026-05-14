from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stock_bro.quotes import parse_eastmoney_kline, read_jsonl, write_jsonl


class QuotesTests(unittest.TestCase):
    def test_parse_eastmoney_kline_calculates_returns_from_previous_close(self) -> None:
        quote = parse_eastmoney_kline(
            "600001",
            "2026-05-12,10.50,11.00,11.20,10.20,1000,10000,10.00,10.00,1.00,5.00",
            name="Example",
            collected_at="2026-05-12T08:00:00+00:00",
        )

        self.assertEqual(quote.trade_date, "2026-05-12")
        self.assertEqual(quote.previous_close, 10.0)
        self.assertAlmostEqual(quote.open_return_percent or 0, 5.0)
        self.assertAlmostEqual(quote.high_return_percent or 0, 12.0)
        self.assertAlmostEqual(quote.close_return_percent or 0, 10.0)

    def test_write_and_read_jsonl_indexes_by_code(self) -> None:
        quote = parse_eastmoney_kline("600001", "2026-05-12,10,11,12,9,1,1,1,10,1,1")
        with tempfile.TemporaryDirectory() as tmp:
            path = write_jsonl([quote], Path(tmp), quote_date("2026-05-12"))
            rows = read_jsonl(path)

        self.assertAlmostEqual(rows["600001"]["close_return_percent"], 10.0)


def quote_date(value: str):
    from datetime import datetime

    return datetime.strptime(value, "%Y-%m-%d").date()


if __name__ == "__main__":
    unittest.main()
