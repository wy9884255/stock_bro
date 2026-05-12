from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_bro import kaipanla
from stock_bro.cli import _date_range
from stock_bro.kaipanla import (
    fetch_block_limit_up_by_date,
    fetch_daily_limit_performance,
    fetch_dragon_tiger_stocks,
    fetch_market_sentiment,
    fetch_sharp_withdrawal_stocks,
    write_json,
)


class KaipanlaTests(unittest.TestCase):
    def test_fetch_market_sentiment_normalizes_fields(self) -> None:
        original = kaipanla.fetch_kaipanla_payload
        kaipanla.fetch_kaipanla_payload = lambda base_url, params, timeout=15.0: {
            "info": [{"ztjs": "57", "Day": "2026-05-12", "df_num": "4", "strong": "48", "lbgd": "5"}],
            "tip": "risk tip",
            "errcode": "0",
        }
        try:
            sentiment = fetch_market_sentiment()
        finally:
            kaipanla.fetch_kaipanla_payload = original

        self.assertEqual(sentiment.trade_date, "2026-05-12")
        self.assertEqual(sentiment.limit_up_count, 57)
        self.assertEqual(sentiment.decline_count, 4)
        self.assertEqual(sentiment.strength, 48)
        self.assertEqual(sentiment.high_limit_up_count, 5)
        self.assertEqual(sentiment.tip, "risk tip")

    def test_fetch_sharp_withdrawal_stocks_normalizes_rows(self) -> None:
        original = kaipanla.fetch_kaipanla_payload
        kaipanla.fetch_kaipanla_payload = lambda base_url, params, timeout=15.0: {
            "info": [["002030", "DaAn", 1, "hot money", 6.88, -11.6816, -5.75]],
            "num": 1,
            "date": "2026-05-12",
            "errcode": "0",
        }
        try:
            stocks = fetch_sharp_withdrawal_stocks(limit=20)
        finally:
            kaipanla.fetch_kaipanla_payload = original

        self.assertEqual(len(stocks), 1)
        self.assertEqual(stocks[0].trade_date, "2026-05-12")
        self.assertEqual(stocks[0].code, "002030")
        self.assertEqual(stocks[0].name, "DaAn")
        self.assertEqual(stocks[0].current_price, 6.88)
        self.assertEqual(stocks[0].withdrawal_percent, -11.6816)
        self.assertEqual(stocks[0].change_percent, -5.75)

    def test_fetch_daily_limit_performance_preserves_rows(self) -> None:
        original = kaipanla.fetch_kaipanla_payload
        kaipanla.fetch_kaipanla_payload = lambda base_url, params, timeout=15.0: {
            "info": [[["000409", "Yunding", 0]], {"meta": "value"}],
            "errcode": "0",
        }
        try:
            performance = fetch_daily_limit_performance(date(2024, 11, 29))
        finally:
            kaipanla.fetch_kaipanla_payload = original

        self.assertEqual(performance.trade_date, "2024-11-29")
        self.assertEqual(performance.rows, [["000409", "Yunding", 0]])
        self.assertEqual(performance.raw["errcode"], "0")

    def test_fetch_block_limit_up_by_date_flattens_unique_stocks(self) -> None:
        original = kaipanla.fetch_kaipanla_payload
        kaipanla.fetch_kaipanla_payload = lambda base_url, params, method="GET", timeout=15.0: {
            "success": True,
            "data": {
                "data": [
                    {"name": "Robot", "stock_list": [{"code": "600001", "name": "Common"}]},
                    {"name": "AI", "stock_list": [{"code": "600001", "name": "Common"}, {"code": "600002", "name": "Only"}]},
                ]
            },
        }
        try:
            block_limit_up = fetch_block_limit_up_by_date(date(2026, 5, 11))
        finally:
            kaipanla.fetch_kaipanla_payload = original

        self.assertEqual(block_limit_up.trade_date, "2026-05-11")
        self.assertEqual(len(block_limit_up.blocks), 2)
        self.assertEqual([stock["code"] for stock in block_limit_up.stocks], ["600001", "600002"])
        self.assertEqual(block_limit_up.stocks[0]["block_names"], ["Robot", "AI"])

    def test_fetch_dragon_tiger_stocks_normalizes_auxiliary_maps(self) -> None:
        original = kaipanla.fetch_kaipanla_payload
        kaipanla.fetch_kaipanla_payload = lambda base_url, params, method="GET", timeout=15.0: {
            "list": [{"ID": "002081", "Name": "GoldMantis", "IncreaseAmount": "10.07%", "BuyIn": "-30549217", "JoinNum": 2}],
            "BIcon": {"002081": ["Buyer"]},
            "SIcon": {"002081": ["Seller"]},
            "fkgn": {"002081": {"1": "Chip", "2": "AI"}},
            "lb": {"002081": "2"},
        }
        try:
            stocks = fetch_dragon_tiger_stocks(limit=500)
        finally:
            kaipanla.fetch_kaipanla_payload = original

        self.assertEqual(len(stocks), 1)
        self.assertEqual(stocks[0].code, "002081")
        self.assertEqual(stocks[0].net_buy_amount, -30549217.0)
        self.assertEqual(stocks[0].buy_icons, ["Buyer"])
        self.assertEqual(stocks[0].sell_icons, ["Seller"])
        self.assertEqual(stocks[0].concepts, ["Chip", "AI"])
        self.assertEqual(stocks[0].limit_up_days, "2")

    def test_write_json_serializes_dataclasses(self) -> None:
        original = kaipanla.fetch_kaipanla_payload
        kaipanla.fetch_kaipanla_payload = lambda base_url, params, timeout=15.0: {
            "info": [{"ztjs": "57", "Day": "2026-05-12"}],
            "errcode": "0",
        }
        try:
            sentiment = fetch_market_sentiment()
        finally:
            kaipanla.fetch_kaipanla_payload = original

        with tempfile.TemporaryDirectory() as tmp:
            path = write_json(sentiment, Path(tmp), "sentiment", date(2026, 5, 12))
            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(path.name, "20260512_sentiment.json")
        self.assertEqual(data["trade_date"], "2026-05-12")
        self.assertEqual(data["limit_up_count"], 57)

    def test_date_range_is_inclusive(self) -> None:
        self.assertEqual(
            _date_range(date(2026, 4, 30), date(2026, 5, 2)),
            [date(2026, 4, 30), date(2026, 5, 1), date(2026, 5, 2)],
        )


if __name__ == "__main__":
    unittest.main()
