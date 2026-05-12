from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_bro.compare import compare_limit_up_archives, format_comparison


class CompareLimitUpTests(unittest.TestCase):
    def test_compare_limit_up_archives_by_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eastmoney_dir = root / "eastmoney"
            kaipanla_dir = root / "kaipanla"
            eastmoney_dir.mkdir()
            kaipanla_dir.mkdir()

            (eastmoney_dir / "20260511.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"code": "600001", "name": "CommonA"}),
                        json.dumps({"code": "600002", "name": "EastOnly"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (kaipanla_dir / "20260511_daily_limit_performance.json").write_text(
                json.dumps(
                    {
                        "trade_date": "2026-05-11",
                        "rows": [
                            ["600001", "CommonB"],
                            ["600003", "KaiOnly"],
                        ],
                    }
                ),
                encoding="utf-8",
            )

            comparison = compare_limit_up_archives(date(2026, 5, 11), eastmoney_dir, kaipanla_dir)

        self.assertEqual(comparison.kaipanla_source, "daily-limit-performance")
        self.assertEqual(comparison.common_codes, ["600001"])
        self.assertEqual(comparison.eastmoney_only_codes, ["600002"])
        self.assertEqual(comparison.kaipanla_only_codes, ["600003"])
        report = format_comparison(comparison)
        self.assertIn("Eastmoney: 2", report)
        self.assertIn("Kaipanla (daily-limit-performance): 2", report)
        self.assertIn("600002 EastOnly", report)
        self.assertIn("600003 KaiOnly", report)

    def test_compare_prefers_block_limit_up_archive_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eastmoney_dir = root / "eastmoney"
            kaipanla_dir = root / "kaipanla"
            eastmoney_dir.mkdir()
            kaipanla_dir.mkdir()

            (eastmoney_dir / "20260511.jsonl").write_text(
                json.dumps({"code": "600001", "name": "Common"}) + "\n",
                encoding="utf-8",
            )
            (kaipanla_dir / "20260511_daily_limit_performance.json").write_text(
                json.dumps({"rows": []}),
                encoding="utf-8",
            )
            (kaipanla_dir / "20260511_block_limit_up.json").write_text(
                json.dumps({"stocks": [{"code": "600001", "name": "CommonBlock"}]}),
                encoding="utf-8",
            )

            comparison = compare_limit_up_archives(date(2026, 5, 11), eastmoney_dir, kaipanla_dir)

        self.assertEqual(comparison.kaipanla_source, "block-limit-up")
        self.assertEqual(comparison.common_codes, ["600001"])


if __name__ == "__main__":
    unittest.main()
