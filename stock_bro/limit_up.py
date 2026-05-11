from __future__ import annotations

import csv
import json
import sqlite3
import time
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


EASTMONEY_LIMIT_UP_URL = "https://push2ex.eastmoney.com/getTopicZTPool"


@dataclass(frozen=True)
class LimitUpStock:
    trade_date: str
    code: str
    name: str
    latest_price: float | None
    change_percent: float | None
    turnover_amount: float | None
    limit_up_amount: float | None
    first_limit_up_time: str | None
    last_limit_up_time: str | None
    consecutive_limit_up_days: int | None
    failed_limit_up_times: int | None
    limit_up_session: str
    industry: str | None
    raw: dict[str, Any]
    collected_at: str


CSV_FIELDS = [
    "trade_date",
    "code",
    "name",
    "latest_price",
    "change_percent",
    "turnover_amount",
    "limit_up_amount",
    "first_limit_up_time",
    "last_limit_up_time",
    "consecutive_limit_up_days",
    "failed_limit_up_times",
    "limit_up_session",
    "industry",
    "raw",
    "collected_at",
]


def parse_trade_date(value: str) -> date:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("trade date must be in YYYY-MM-DD or YYYYMMDD format")


def collect_limit_up_stocks(
    trade_date: date,
    timeout: float = 15.0,
    include_st: bool = False,
) -> list[LimitUpStock]:
    payload = fetch_eastmoney_limit_up_payload(trade_date, timeout=timeout)
    data = payload.get("data")
    if data is None:
        return []
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected Eastmoney response shape: data is {type(data).__name__}")
    rows = data.get("pool")
    if rows is None:
        raise ValueError(f"Unexpected Eastmoney response shape: missing data.pool")
    if not isinstance(rows, list):
        raise ValueError(f"Unexpected Eastmoney response shape: data.pool is {type(rows).__name__}")

    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    records = [parse_eastmoney_limit_up_row(row, trade_date, collected_at) for row in rows]
    if include_st:
        return records
    return [record for record in records if not is_st_stock(record.name)]


def fetch_eastmoney_limit_up_payload(trade_date: date, timeout: float = 15.0) -> dict[str, Any]:
    query = urlencode(
        {
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "dpt": "wz.ztzt",
            "Pageindex": 0,
            "pagesize": 10000,
            "sort": "fbt:asc",
            "date": trade_date.strftime("%Y%m%d"),
            "_": int(datetime.now().timestamp() * 1000),
        }
    )
    url = f"{EASTMONEY_LIMIT_UP_URL}?{query}"
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 stock-bro/0.1",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://quote.eastmoney.com/ztb/detail",
        },
    )

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
            return json.loads(_strip_jsonp(body))
        except HTTPError as exc:
            raise RuntimeError(f"Eastmoney request failed with HTTP {exc.code}") from exc
        except (TimeoutError, URLError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1 + attempt)
                continue

    raise RuntimeError(f"Eastmoney request failed: {last_error}") from last_error


def parse_eastmoney_limit_up_row(row: dict[str, Any], trade_date: date, collected_at: str) -> LimitUpStock:
    if not isinstance(row, dict):
        raise ValueError(f"Unexpected Eastmoney row type: {type(row).__name__}")

    first_limit_up_time = _format_hhmmss(row.get("fbt"))
    failed_limit_up_times = _to_int(row.get("zbc"))
    return LimitUpStock(
        trade_date=trade_date.strftime("%Y-%m-%d"),
        code=str(row.get("c") or ""),
        name=str(row.get("n") or ""),
        latest_price=_to_eastmoney_price(row.get("p")),
        change_percent=_to_float(row.get("zdp")),
        turnover_amount=_to_float(row.get("amount")),
        limit_up_amount=_to_float(row.get("fund")),
        first_limit_up_time=first_limit_up_time,
        last_limit_up_time=_format_hhmmss(row.get("lbt")),
        consecutive_limit_up_days=_to_int(row.get("lbc")),
        failed_limit_up_times=failed_limit_up_times,
        limit_up_session=classify_limit_up_session(first_limit_up_time, failed_limit_up_times),
        industry=_empty_to_none(row.get("hybk")),
        raw=row,
        collected_at=collected_at,
    )


def write_csv(records: list[LimitUpStock], out_dir: Path, trade_date: date | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{_records_date(records, trade_date)}.csv"
    with output.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            row = _serialize_record(record)
            writer.writerow(row)
    return output


def write_jsonl(records: list[LimitUpStock], out_dir: Path, trade_date: date | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{_records_date(records, trade_date)}.jsonl"
    with output.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(_serialize_record(record), ensure_ascii=False) + "\n")
    return output


def write_sqlite(records: list[LimitUpStock], db_path: Path, trade_date: date | None = None) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS limit_up_stocks (
                trade_date TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                latest_price REAL,
                change_percent REAL,
                turnover_amount REAL,
                limit_up_amount REAL,
                first_limit_up_time TEXT,
                last_limit_up_time TEXT,
                consecutive_limit_up_days INTEGER,
                failed_limit_up_times INTEGER,
                limit_up_session TEXT NOT NULL DEFAULT 'unknown',
                industry TEXT,
                raw TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                PRIMARY KEY (trade_date, code)
            )
            """
        )
        _ensure_sqlite_schema(connection)
        snapshot_date = _records_trade_date(records, trade_date)
        if snapshot_date:
            connection.execute("DELETE FROM limit_up_stocks WHERE trade_date = ?", (snapshot_date,))

        rows = [_serialize_record(record) for record in records]
        connection.executemany(
            """
            INSERT INTO limit_up_stocks (
                trade_date, code, name, latest_price, change_percent,
                turnover_amount, limit_up_amount, first_limit_up_time,
                last_limit_up_time, consecutive_limit_up_days,
                failed_limit_up_times, limit_up_session, industry, raw, collected_at
            )
            VALUES (
                :trade_date, :code, :name, :latest_price, :change_percent,
                :turnover_amount, :limit_up_amount, :first_limit_up_time,
                :last_limit_up_time, :consecutive_limit_up_days,
                :failed_limit_up_times, :limit_up_session, :industry, :raw, :collected_at
            )
            ON CONFLICT(trade_date, code) DO UPDATE SET
                name = excluded.name,
                latest_price = excluded.latest_price,
                change_percent = excluded.change_percent,
                turnover_amount = excluded.turnover_amount,
                limit_up_amount = excluded.limit_up_amount,
                first_limit_up_time = excluded.first_limit_up_time,
                last_limit_up_time = excluded.last_limit_up_time,
                consecutive_limit_up_days = excluded.consecutive_limit_up_days,
                failed_limit_up_times = excluded.failed_limit_up_times,
                limit_up_session = excluded.limit_up_session,
                industry = excluded.industry,
                raw = excluded.raw,
                collected_at = excluded.collected_at
            """,
            rows,
        )
        connection.commit()


def _ensure_sqlite_schema(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(limit_up_stocks)").fetchall()
    }
    if "limit_up_session" not in columns:
        connection.execute(
            "ALTER TABLE limit_up_stocks ADD COLUMN limit_up_session TEXT NOT NULL DEFAULT 'unknown'"
        )


def _serialize_record(record: LimitUpStock) -> dict[str, Any]:
    row = asdict(record)
    row["raw"] = json.dumps(record.raw, ensure_ascii=False, sort_keys=True)
    return row


def _records_date(records: list[LimitUpStock], fallback: date | None = None) -> str:
    if records:
        return records[0].trade_date.replace("-", "")
    if fallback:
        return fallback.strftime("%Y%m%d")
    return date.today().strftime("%Y%m%d")


def _records_trade_date(records: list[LimitUpStock], fallback: date | None = None) -> str | None:
    if records:
        return records[0].trade_date
    if fallback:
        return fallback.strftime("%Y-%m-%d")
    return None


def is_st_stock(name: str) -> bool:
    normalized = name.strip().upper()
    return normalized.startswith("ST") or normalized.startswith("*ST") or normalized.startswith("S*ST")


def classify_limit_up_session(first_limit_up_time: str | None, failed_limit_up_times: int | None) -> str:
    if not first_limit_up_time:
        return "unknown"
    if first_limit_up_time == "09:25:00" and (failed_limit_up_times or 0) == 0:
        return "opening_one_word"
    if first_limit_up_time <= "11:30:00":
        return "morning"
    if first_limit_up_time >= "13:00:00":
        return "afternoon"
    return "unknown"


def _strip_jsonp(value: str) -> str:
    value = value.strip()
    if value.startswith("{"):
        return value
    start = value.find("(")
    end = value.rfind(")")
    if start == -1 or end == -1 or end <= start:
        return value
    return value[start + 1 : end]


def _to_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_eastmoney_price(value: Any) -> float | None:
    price = _to_float(value)
    if price is None:
        return None
    if abs(price) >= 1000:
        return price / 1000
    return price


def _to_int(value: Any) -> int | None:
    if value in (None, "", "-"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _empty_to_none(value: Any) -> str | None:
    if value in (None, "", "-"):
        return None
    return str(value)


def _format_hhmmss(value: Any) -> str | None:
    if value in (None, "", "-", 0, "0"):
        return None
    digits = str(value).strip()
    if not digits.isdigit():
        return None
    digits = digits.zfill(6)
    return f"{digits[-6:-4]}:{digits[-4:-2]}:{digits[-2:]}"
