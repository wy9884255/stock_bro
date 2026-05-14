from __future__ import annotations

import json
import time
from http.client import RemoteDisconnected
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"


@dataclass(frozen=True)
class DailyQuote:
    trade_date: str
    code: str
    name: str | None
    open_price: float | None
    high_price: float | None
    close_price: float | None
    previous_close: float | None
    open_return_percent: float | None
    high_return_percent: float | None
    close_return_percent: float | None
    raw: dict[str, Any]
    collected_at: str


def collect_daily_quotes(
    stocks: list[dict[str, Any]],
    trade_date: date,
    timeout: float = 15.0,
) -> list[DailyQuote]:
    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    quotes: list[DailyQuote] = []
    for stock in stocks:
        code = str(stock.get("code") or "")
        if not code:
            continue
        try:
            quote = fetch_daily_quote(
                code,
                trade_date,
                name=str(stock.get("name") or ""),
                market=_extract_market(stock),
                timeout=timeout,
                collected_at=collected_at,
            )
        except RuntimeError:
            continue
        if quote:
            quotes.append(quote)
        time.sleep(0.05)
    return quotes


def fetch_daily_quote(
    code: str,
    trade_date: date,
    name: str | None = None,
    market: int | None = None,
    timeout: float = 15.0,
    collected_at: str | None = None,
) -> DailyQuote | None:
    payload = fetch_eastmoney_kline_payload(code, trade_date, market=market, timeout=timeout)
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    klines = data.get("klines")
    if not isinstance(klines, list) or not klines:
        return None
    return parse_eastmoney_kline(code, klines[0], payload, name=name, collected_at=collected_at)


def fetch_eastmoney_kline_payload(
    code: str,
    trade_date: date,
    market: int | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    secid = f"{_market_for_code(code, market)}.{code}"
    query = urlencode(
        {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": 101,
            "fqt": 0,
            "beg": trade_date.strftime("%Y%m%d"),
            "end": trade_date.strftime("%Y%m%d"),
            "_": int(datetime.now().timestamp() * 1000),
        }
    )
    request = Request(
        f"{EASTMONEY_KLINE_URL}?{query}",
        headers={
            "User-Agent": "Mozilla/5.0 stock-bro/0.1",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://quote.eastmoney.com/",
        },
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
            break
        except HTTPError as exc:
            raise RuntimeError(f"Eastmoney kline request failed with HTTP {exc.code}") from exc
        except (TimeoutError, URLError, RemoteDisconnected) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1 + attempt)
                continue
    else:
        raise RuntimeError(f"Eastmoney kline request failed: {last_error}") from last_error

    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected Eastmoney kline response shape: root is {type(payload).__name__}")
    return payload


def parse_eastmoney_kline(
    code: str,
    kline: Any,
    raw: dict[str, Any] | None = None,
    name: str | None = None,
    collected_at: str | None = None,
) -> DailyQuote:
    if not isinstance(kline, str):
        raise ValueError(f"Unexpected Eastmoney kline row type: {type(kline).__name__}")
    parts = kline.split(",")
    if len(parts) < 10:
        raise ValueError(f"Unexpected Eastmoney kline row shape: {kline}")

    trade_date = parts[0]
    open_price = _to_float(parts[1])
    close_price = _to_float(parts[2])
    high_price = _to_float(parts[3])
    change_amount = _to_float(parts[9])
    previous_close = None
    if close_price is not None and change_amount is not None:
        previous_close = close_price - change_amount

    return DailyQuote(
        trade_date=trade_date,
        code=code,
        name=name,
        open_price=open_price,
        high_price=high_price,
        close_price=close_price,
        previous_close=previous_close,
        open_return_percent=_return_percent(open_price, previous_close),
        high_return_percent=_return_percent(high_price, previous_close),
        close_return_percent=_return_percent(close_price, previous_close),
        raw=raw or {"kline": kline},
        collected_at=collected_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def write_jsonl(records: list[DailyQuote], out_dir: Path, trade_date: date) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{trade_date:%Y%m%d}.jsonl"
    with output.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    return output


def read_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            row = json.loads(line)
            if isinstance(row, dict) and row.get("code"):
                records[str(row["code"])] = row
    return records


def _extract_market(stock: dict[str, Any]) -> int | None:
    raw = stock.get("raw")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = None
    if isinstance(raw, dict):
        value = raw.get("m")
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _market_for_code(code: str, market: int | None = None) -> int:
    if market in (0, 1):
        return market
    if code.startswith(("5", "6", "9")):
        return 1
    return 0


def _return_percent(price: float | None, previous_close: float | None) -> float | None:
    if price is None or previous_close in (None, 0):
        return None
    return (price / previous_close - 1) * 100


def _to_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
