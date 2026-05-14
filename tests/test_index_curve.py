from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stock_bro.index_curve import (
    parse_eastmoney_index_trends,
    parse_tencent_index_minute,
    write_index_curve_to_cls_finance_anchors,
)


class IndexCurveTests(unittest.TestCase):
    def test_parse_eastmoney_index_trends_extracts_intraday_points(self) -> None:
        curve = parse_eastmoney_index_trends(
            {
                "data": {
                    "code": "000001",
                    "name": "上证指数",
                    "trends": [
                        "2026-05-13 09:30,3880.12,3880.00,100,200",
                        "2026-05-13 09:31,3881.50,3880.80,120,240",
                    ],
                }
            }
        )

        self.assertEqual(curve.trade_date, "2026-05-13")
        self.assertEqual(curve.points[0].time, "09:30:00")
        self.assertEqual(curve.points[0].value, 3880.12)
        self.assertEqual(curve.points[1].average_price, 3880.8)

    def test_write_index_curve_to_cls_finance_anchors_preserves_existing_payload(self) -> None:
        curve = parse_eastmoney_index_trends(
            {
                "data": {
                    "code": "000001",
                    "name": "上证指数",
                    "trends": ["2026-05-13 09:30,3880.12,3880.00,100,200"],
                }
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "20260513_finance_anchors.json"
            path.write_text(json.dumps({"anchors": [], "segments": []}), encoding="utf-8")
            write_index_curve_to_cls_finance_anchors(curve, path)
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["anchors"], [])
        self.assertEqual(payload["segments"], [])
        self.assertEqual(payload["index_curve"][0]["time"], "09:30:00")
        self.assertEqual(payload["index_curve_meta"]["point_count"], 1)

    def test_parse_tencent_index_minute_extracts_points(self) -> None:
        curve = parse_tencent_index_minute(
            {
                "data": {
                    "sh000001": {
                        "data": {
                            "data": [
                                "0930 4256.16 7680656 14743175569.80",
                                "0931 4255.29 23869095 47423367142.60",
                            ]
                        }
                    }
                }
            },
            quote_date("2026-05-14"),
        )

        self.assertEqual(curve.trade_date, "2026-05-14")
        self.assertEqual(curve.points[0].time, "09:30:00")
        self.assertEqual(curve.points[0].value, 4256.16)
        self.assertEqual(curve.points[1].amount, 47423367142.60)

def quote_date(value: str):
    from datetime import datetime

    return datetime.strptime(value, "%Y-%m-%d").date()


if __name__ == "__main__":
    unittest.main()
