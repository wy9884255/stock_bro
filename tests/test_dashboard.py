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
            cls_dir = root / "cls"
            web_dir = root / "web"
            eastmoney_dir.mkdir()
            cls_dir.mkdir()
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
            (cls_dir / "20260511_limit_up_analysis.json").write_text(
                json.dumps(
                    {
                        "title": "CLS limit-up analysis",
                        "url": "https://www.cls.cn/detail/example",
                        "summary": "CLS summary",
                        "classification_images": [
                            {"url": "https://image.cls.cn/example_1000x2000.jpg", "width": 1000, "height": 2000}
                        ],
                        "theme_stocks": [
                            {
                                "code": "600001",
                                "name": "Example",
                                "theme": "Robot+AI",
                                "reason": "reason",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            data_path = build_dashboard(date(2026, 5, 11), eastmoney_dir, cls_dir, web_dir)
            payload = json.loads(data_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["summary"]["failed"], 1)
        self.assertEqual(payload["summary"]["with_theme"], 1)
        self.assertEqual(payload["summary"]["cls_theme_records"], 1)
        self.assertEqual(payload["summary"]["cls_images"], 1)
        self.assertEqual(payload["cls_analysis"]["title"], "CLS limit-up analysis")
        stock = payload["stocks"][0]
        self.assertEqual(stock["name"], "Example")
        self.assertEqual(stock["themes"], ["Robot", "AI"])
        self.assertEqual(stock["reason_info"], "reason")
        self.assertTrue((data_path.parent / "dashboard.html").exists() or Path("web/dashboard.html").exists())

    def test_dashboard_index_excludes_empty_days(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eastmoney_dir = root / "limit_up"
            cls_dir = root / "cls"
            web_dir = root / "web"
            eastmoney_dir.mkdir()
            cls_dir.mkdir()
            (eastmoney_dir / "20260509.jsonl").write_text("", encoding="utf-8")

            build_dashboard(date(2026, 5, 9), eastmoney_dir, cls_dir, web_dir)
            index = json.loads((web_dir / "dashboard_index.json").read_text(encoding="utf-8"))

        self.assertEqual(index["dates"], [])

    def test_build_dashboard_reads_cls_theme_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eastmoney_dir = root / "limit_up"
            cls_dir = root / "cls"
            web_dir = root / "web"
            eastmoney_dir.mkdir()
            cls_dir.mkdir()
            (eastmoney_dir / "20260512.jsonl").write_text(
                json.dumps({"code": "002081", "name": "金 螳 螂", "failed_limit_up_times": 0}) + "\n",
                encoding="utf-8",
            )
            (cls_dir / "20260512_limit_up_analysis.json").write_text(
                json.dumps({"title": "5月12日涨停分析", "theme_stocks": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            (cls_dir / "20260512_theme_stocks.json").write_text(
                json.dumps(
                    {
                        "source": "CLS classification image",
                        "theme_stocks": [
                            {
                                "code": "002081",
                                "name": "金 螳 螂",
                                "theme": "芯片产业链",
                                "reason": "商业航天+洁净室+苏州",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            data_path = build_dashboard(date(2026, 5, 12), eastmoney_dir, cls_dir, web_dir)
            payload = json.loads(data_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["summary"]["with_theme"], 1)
        self.assertEqual(payload["themes"], [{"name": "芯片产业链", "count": 1, "failed_count": 0}])
        self.assertEqual(payload["stocks"][0]["themes"], ["芯片产业链"])
        self.assertEqual(payload["stocks"][0]["reason_info"], "商业航天+洁净室+苏州")

    def test_build_dashboard_reads_finance_anchor_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eastmoney_dir = root / "limit_up"
            cls_dir = root / "cls"
            web_dir = root / "web"
            eastmoney_dir.mkdir()
            cls_dir.mkdir()
            (eastmoney_dir / "20260512.jsonl").write_text(
                json.dumps({"code": "300308", "name": "Example", "failed_limit_up_times": 0}) + "\n",
                encoding="utf-8",
            )
            (cls_dir / "20260512_finance_anchors.json").write_text(
                json.dumps(
                    {
                        "source": "https://www.cls.cn/finance",
                        "api": "https://www.cls.cn/v3/transaction/anchor",
                        "trade_date": "2026-05-12",
                        "anchors": [{"symbol_name": "CPO"}],
                        "segments": [
                            {
                                "start": "09:30",
                                "end": "10:00",
                                "themes": [
                                    {
                                        "time": "09:31:50",
                                        "direction": "up",
                                        "name": "CPO",
                                        "code": "cls81935",
                                        "article_id": 2368610,
                                    }
                                ],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            data_path = build_dashboard(date(2026, 5, 12), eastmoney_dir, cls_dir, web_dir)
            payload = json.loads(data_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["finance_anchors"]["anchor_count"], 1)
        self.assertEqual(payload["finance_anchors"]["segments"][0]["themes"][0]["name"], "CPO")


if __name__ == "__main__":
    unittest.main()
