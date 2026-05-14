from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_bro.dashboard import LEADER_THEME_NAME, build_dashboard


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

    def test_build_dashboard_applies_failed_limit_up_grace_to_archives(self) -> None:
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
                        "code": "600002",
                        "name": "GraceStock",
                        "first_limit_up_time": "09:30:00",
                        "last_limit_up_time": "09:59:59",
                        "failed_limit_up_times": 2,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            data_path = build_dashboard(date(2026, 5, 11), eastmoney_dir, cls_dir, web_dir)
            payload = json.loads(data_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["summary"]["failed"], 0)
        self.assertEqual(payload["stocks"][0]["failed_limit_up_times"], 0)
        self.assertFalse(payload["stocks"][0]["is_failed_limit_up"])

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
                        "index_curve": [{"time": "09:30:00", "value": 0.0}, {"time": "10:00:00", "value": 0.5}],
                        "index_curve_meta": {"name": "上证指数", "point_count": 2},
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
        self.assertEqual(len(payload["finance_anchors"]["index_curve"]), 2)
        self.assertEqual(payload["finance_anchors"]["index_curve_meta"]["point_count"], 2)
        self.assertEqual(payload["finance_anchors"]["segments"][0]["themes"][0]["name"], "CPO")

    def test_build_dashboard_marks_finance_anchor_leaders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eastmoney_dir = root / "limit_up"
            cls_dir = root / "cls"
            web_dir = root / "web"
            eastmoney_dir.mkdir()
            cls_dir.mkdir()
            rows = [
                {
                    "code": "600001",
                    "name": "Early",
                    "first_limit_up_time": "09:31:00",
                    "last_limit_up_time": "09:31:00",
                    "failed_limit_up_times": 0,
                },
                {
                    "code": "600002",
                    "name": "Later",
                    "first_limit_up_time": "09:35:00",
                    "last_limit_up_time": "09:35:00",
                    "failed_limit_up_times": 0,
                },
                {
                    "code": "600003",
                    "name": "NextSegment",
                    "first_limit_up_time": "10:05:00",
                    "last_limit_up_time": "10:05:00",
                    "failed_limit_up_times": 0,
                },
            ]
            (eastmoney_dir / "20260512.jsonl").write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )
            (cls_dir / "20260512_theme_stocks.json").write_text(
                json.dumps(
                    {
                        "theme_stocks": [
                            {"code": "600001", "theme": "AI", "reason": "算力租赁"},
                            {"code": "600002", "theme": "AI", "reason": "算力租赁"},
                            {"code": "600003", "theme": "AI", "reason": "算力租赁"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (cls_dir / "20260512_finance_anchors.json").write_text(
                json.dumps(
                    {
                        "anchors": [{"symbol_name": "算力租赁"}],
                        "segments": [
                            {
                                "start": "09:30",
                                "end": "10:00",
                                "themes": [{"time": "09:32:00", "name": "算力租赁", "article_id": 1}],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            data_path = build_dashboard(date(2026, 5, 12), eastmoney_dir, cls_dir, web_dir)
            payload = json.loads(data_path.read_text(encoding="utf-8"))

        leaders = payload["finance_leaders"]
        self.assertEqual(len(leaders), 1)
        self.assertEqual(leaders[0]["code"], "600001")
        self.assertEqual(leaders[0]["anchor_theme"], "算力租赁")
        stocks = {stock["code"]: stock for stock in payload["stocks"]}
        self.assertIn("领涨龙头", stocks["600001"]["themes"])
        self.assertNotIn("领涨龙头", stocks["600002"]["themes"])
        self.assertEqual(payload["themes"][0]["name"], "领涨龙头")

    def test_build_dashboard_includes_previous_theme_next_day_returns(self) -> None:
        import stock_bro.dashboard as dashboard

        original_calendar = dashboard.read_trade_calendar
        dashboard.read_trade_calendar = lambda: {date(2026, 5, 11), date(2026, 5, 12)}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                eastmoney_dir = root / "limit_up"
                cls_dir = root / "cls"
                quotes_dir = root / "quotes"
                web_dir = root / "web"
                eastmoney_dir.mkdir()
                cls_dir.mkdir()
                quotes_dir.mkdir()
                (eastmoney_dir / "20260511.jsonl").write_text(
                    "\n".join(
                        [
                            json.dumps(
                                {
                                    "code": "600001",
                                    "name": "Alpha",
                                    "first_limit_up_time": "09:31:00",
                                    "failed_limit_up_times": 0,
                                }
                            ),
                            json.dumps(
                                {
                                    "code": "600002",
                                    "name": "Beta",
                                    "first_limit_up_time": "09:35:00",
                                    "failed_limit_up_times": 0,
                                }
                            ),
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (eastmoney_dir / "20260512.jsonl").write_text(
                    json.dumps({"code": "600003", "name": "Today", "failed_limit_up_times": 0}) + "\n",
                    encoding="utf-8",
                )
                (cls_dir / "20260511_theme_stocks.json").write_text(
                    json.dumps(
                        {
                            "theme_stocks": [
                                {"code": "600001", "theme": "AI"},
                                {"code": "600002", "theme": "AI"},
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                (cls_dir / "20260511_finance_anchors.json").write_text(
                    json.dumps(
                        {
                            "anchors": [{"symbol_name": "AI"}],
                            "segments": [
                                {
                                    "start": "09:30",
                                    "end": "10:00",
                                    "themes": [{"time": "09:32:00", "name": "AI", "article_id": 1}],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                (quotes_dir / "20260512.jsonl").write_text(
                    "\n".join(
                        [
                            json.dumps(
                                {
                                    "code": "600001",
                                    "open_return_percent": 1.0,
                                    "high_return_percent": 5.0,
                                    "close_return_percent": 2.0,
                                }
                            ),
                            json.dumps(
                                {
                                    "code": "600002",
                                    "open_return_percent": 3.0,
                                    "high_return_percent": 7.0,
                                    "close_return_percent": 4.0,
                                }
                            ),
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )

                data_path = build_dashboard(
                    date(2026, 5, 12),
                    eastmoney_dir=eastmoney_dir,
                    cls_dir=cls_dir,
                    web_dir=web_dir,
                    quotes_dir=quotes_dir,
                )
                payload = json.loads(data_path.read_text(encoding="utf-8"))
        finally:
            dashboard.read_trade_calendar = original_calendar

        returns = payload["next_day_returns"]
        self.assertEqual(returns["source_trade_date"], "2026-05-11")
        self.assertEqual(returns["return_trade_date"], "2026-05-12")
        self.assertEqual(returns["all"]["name"], LEADER_THEME_NAME)
        self.assertEqual(returns["all"]["stock_count"], 1)
        self.assertEqual(returns["all"]["priced_count"], 1)
        self.assertEqual(returns["all"]["open_return_percent"], 1.0)
        self.assertEqual(returns["all"]["high_return_percent"], 5.0)
        self.assertEqual(returns["all"]["close_return_percent"], 2.0)
        self.assertEqual(returns["themes"][0]["name"], "AI")
        self.assertEqual(returns["themes"][0]["stock_count"], 1)
        self.assertEqual(returns["stocks"][0]["code"], "600001")
        self.assertEqual(returns["stocks"][0]["name"], "Alpha")
        self.assertEqual(returns["stocks"][0]["themes"], ["AI"])
        self.assertEqual(returns["stocks"][0]["open_return_percent"], 1.0)


if __name__ == "__main__":
    unittest.main()
