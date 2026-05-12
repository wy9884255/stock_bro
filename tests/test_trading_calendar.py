from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_bro.trading_calendar import is_trade_date, read_trade_calendar, trading_dates_between, write_trade_calendar


class TradingCalendarTests(unittest.TestCase):
    def test_write_and_read_trade_calendar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "calendar.json"
            write_trade_calendar([date(2026, 5, 6), date(2026, 5, 7)], path)
            trade_dates = read_trade_calendar(path)

        self.assertEqual(trade_dates, {date(2026, 5, 6), date(2026, 5, 7)})

    def test_trading_dates_between_uses_calendar_when_available(self) -> None:
        trade_dates = {date(2026, 5, 6), date(2026, 5, 8)}

        self.assertEqual(
            trading_dates_between(date(2026, 5, 5), date(2026, 5, 9), trade_dates),
            [date(2026, 5, 6), date(2026, 5, 8)],
        )

    def test_is_trade_date_falls_back_to_weekday(self) -> None:
        self.assertTrue(is_trade_date(date(2026, 5, 8), set()))
        self.assertFalse(is_trade_date(date(2026, 5, 9), set()))


if __name__ == "__main__":
    unittest.main()
