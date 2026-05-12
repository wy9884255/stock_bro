from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_bro.dashboard import build_dashboard


class DashboardTests(unittest.TestCase):
    def test_build_dashboard_merges_archives_by_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eastmoney_dir = root / "limit_up"
            kaipanla_dir = root / "kaipanla"
            web_dir = root / "web"
            eastmoney_dir.mkdir()
            kaipanla_dir.mkdir()
            (eastmoney_dir / "20260511.jsonl").write_text(
                json.dumps(
                    {
                        "code": "600001",
                        "name": "Example",
                        "first_limit_up_time": "09:30:00",
                        "last_limit_up_time": "14:31:00",
                        "failed_limit_up_times": 2,
                        "consecutive_limit_up_days": 3,
                        "change_percent": 10.0,
                        "limit_up_session": "late_afternoon_after_1430",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (kaipanla_dir / "20260511_block_limit_up.json").write_text(
                json.dumps(
                    {
                        "stocks": [
                            {
                                "code": "600001",
                                "name": "IgnoredName",
                                "block_names": ["Robot"],
                                "reason_type": "Robot+AI",
                                "reason_info": "reason",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (kaipanla_dir / "20260512_dragon_tiger.json").write_text(
                json.dumps(
                    [
                        {
                            "code": "600001",
                            "name": "Example",
                            "net_buy_amount": 12345.0,
                            "buy_icons": ["Buyer"],
                            "sell_icons": [],
                            "concepts": ["AI"],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            data_path = build_dashboard(date(2026, 5, 11), eastmoney_dir, kaipanla_dir, web_dir)
            payload = json.loads(data_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["summary"]["failed"], 1)
        self.assertEqual(payload["summary"]["with_theme"], 1)
        self.assertEqual(payload["summary"]["with_dragon_tiger"], 1)
        stock = payload["stocks"][0]
        self.assertEqual(stock["name"], "Example")
        self.assertEqual(stock["themes"], ["Robot", "AI"])
        self.assertEqual(stock["dragon_tiger"]["net_buy_amount"], 12345.0)
        self.assertTrue((data_path.parent / "dashboard.html").exists() or Path("web/dashboard.html").exists())

    def test_dashboard_index_excludes_empty_days(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eastmoney_dir = root / "limit_up"
            kaipanla_dir = root / "kaipanla"
            web_dir = root / "web"
            eastmoney_dir.mkdir()
            kaipanla_dir.mkdir()
            (eastmoney_dir / "20260509.jsonl").write_text("", encoding="utf-8")

            build_dashboard(date(2026, 5, 9), eastmoney_dir, kaipanla_dir, web_dir)
            index = json.loads((web_dir / "dashboard_index.json").read_text(encoding="utf-8"))

        self.assertEqual(index["dates"], [])


if __name__ == "__main__":
    unittest.main()
