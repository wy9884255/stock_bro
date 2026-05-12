from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_CALENDAR_PATH = Path("data/trade_calendar.json")


def fetch_a_share_trade_dates() -> list[date]:
    try:
        import akshare as ak  # type: ignore
    except ImportError as exc:
        raise RuntimeError("akshare is required to fetch the Sina trading calendar") from exc

    frame = ak.tool_trade_date_hist_sina()
    if "trade_date" not in frame:
        raise ValueError("Unexpected trading calendar shape: missing trade_date column")
    dates = [_to_date(value) for value in frame["trade_date"].tolist()]
    return sorted({item for item in dates if item is not None})


def write_trade_calendar(trade_dates: list[date], path: Path = DEFAULT_CALENDAR_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "akshare.tool_trade_date_hist_sina",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "trade_dates": [item.strftime("%Y-%m-%d") for item in sorted(set(trade_dates))],
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return path


def read_trade_calendar(path: Path = DEFAULT_CALENDAR_PATH) -> set[date]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    values = payload.get("trade_dates", [])
    if not isinstance(values, list):
        return set()
    return {parsed for value in values if (parsed := _to_date(value))}


def is_trade_date(value: date, trade_dates: set[date] | None = None) -> bool:
    if trade_dates:
        return value in trade_dates
    return value.weekday() < 5


def trading_dates_between(start: date, end: date, trade_dates: set[date] | None = None) -> list[date]:
    days = (end - start).days
    candidates = [start + timedelta(days=offset) for offset in range(days + 1)]
    return [candidate for candidate in candidates if is_trade_date(candidate, trade_dates)]


def _to_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if value in (None, "", "-"):
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None
