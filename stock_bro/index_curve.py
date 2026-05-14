from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


EASTMONEY_TRENDS_URL = "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
TENCENT_MINUTE_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"
SHANGHAI_INDEX_SECID = "1.000001"


@dataclass(frozen=True)
class IndexCurvePoint:
    time: str
    value: float
    price: float
    average_price: float | None
    volume: float | None
    amount: float | None


@dataclass(frozen=True)
class IndexCurve:
    code: str
    name: str
    trade_date: str
    source: str
    points: list[IndexCurvePoint]
    collected_at: str


def fetch_shanghai_index_curve(
    trade_date: date,
    timeout: float = 15.0,
) -> IndexCurve:
    try:
        payload = fetch_eastmoney_index_trends_payload(timeout=timeout)
        curve = parse_eastmoney_index_trends(payload)
    except RuntimeError:
        payload = fetch_tencent_index_minute_payload(timeout=timeout)
        curve = parse_tencent_index_minute(payload, trade_date)
    if curve.trade_date != trade_date.strftime("%Y-%m-%d"):
        return IndexCurve(
            code=curve.code,
            name=curve.name,
            trade_date=curve.trade_date,
            source=curve.source,
            points=[],
            collected_at=curve.collected_at,
        )
    return curve


def fetch_tencent_index_minute_payload(timeout: float = 15.0) -> dict[str, Any]:
    query = urlencode({"code": "sh000001"})
    request = Request(
        f"{TENCENT_MINUTE_URL}?{query}",
        headers={
            "User-Agent": "Mozilla/5.0 stock-bro/0.1",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://gu.qq.com/sh000001/gp",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected Tencent minute response shape: root is {type(payload).__name__}")
    return payload


def fetch_eastmoney_index_trends_payload(timeout: float = 15.0) -> dict[str, Any]:
    query = urlencode(
        {
            "secid": SHANGHAI_INDEX_SECID,
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "iscr": 0,
            "iscca": 0,
            "ndays": 1,
            "_": int(datetime.now().timestamp() * 1000),
        }
    )
    request = Request(
        f"{EASTMONEY_TRENDS_URL}?{query}",
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
            raise RuntimeError(f"Eastmoney index trends request failed with HTTP {exc.code}") from exc
        except (TimeoutError, URLError, RemoteDisconnected) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1 + attempt)
                continue
    else:
        raise RuntimeError(f"Eastmoney index trends request failed: {last_error}") from last_error

    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected Eastmoney index trends response shape: root is {type(payload).__name__}")
    return payload


def parse_eastmoney_index_trends(payload: dict[str, Any]) -> IndexCurve:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Unexpected Eastmoney index trends response shape: missing data")
    rows = data.get("trends")
    if not isinstance(rows, list):
        raise ValueError("Unexpected Eastmoney index trends response shape: missing data.trends")

    points = [point for row in rows if (point := _parse_trends_row(row))]
    trade_date = points[0].time[:10] if points else str(data.get("trade_date") or "")
    normalized_points = [
        IndexCurvePoint(
            time=_normalize_time(point.time),
            value=point.value,
            price=point.price,
            average_price=point.average_price,
            volume=point.volume,
            amount=point.amount,
        )
        for point in points
    ]
    return IndexCurve(
        code=str(data.get("code") or "000001"),
        name=str(data.get("name") or "上证指数"),
        trade_date=trade_date,
        source=EASTMONEY_TRENDS_URL,
        points=normalized_points,
        collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def parse_tencent_index_minute(payload: dict[str, Any], trade_date: date) -> IndexCurve:
    rows = (
        payload.get("data", {})
        .get("sh000001", {})
        .get("data", {})
        .get("data", [])
    )
    if not isinstance(rows, list):
        raise ValueError("Unexpected Tencent minute response shape: missing data.sh000001.data.data")
    points: list[IndexCurvePoint] = []
    for row in rows:
        point = _parse_tencent_minute_row(row)
        if point:
            points.append(point)
    return IndexCurve(
        code="000001",
        name="上证指数",
        trade_date=trade_date.strftime("%Y-%m-%d"),
        source=TENCENT_MINUTE_URL,
        points=points,
        collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def write_index_curve_to_cls_finance_anchors(curve: IndexCurve, path: Path) -> Path:
    payload: dict[str, Any] = {}
    if path.exists():
        with path.open("r", encoding="utf-8-sig") as file:
            loaded = json.load(file)
        if isinstance(loaded, dict):
            payload = loaded
    payload.setdefault("anchors", [])
    payload.setdefault("segments", [])
    payload["index_curve"] = [asdict(point) for point in curve.points]
    payload["index_curve_meta"] = {
        "code": curve.code,
        "name": curve.name,
        "trade_date": curve.trade_date,
        "source": curve.source,
        "collected_at": curve.collected_at,
        "point_count": len(curve.points),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return path


def _parse_trends_row(row: Any) -> IndexCurvePoint | None:
    if not isinstance(row, str):
        return None
    parts = row.split(",")
    if len(parts) < 3:
        return None
    timestamp = parts[0]
    price = _to_float(parts[1])
    if price is None:
        return None
    return IndexCurvePoint(
        time=timestamp,
        value=price,
        price=price,
        average_price=_to_float(parts[2]),
        volume=_to_float(parts[3]) if len(parts) > 3 else None,
        amount=_to_float(parts[4]) if len(parts) > 4 else None,
    )


def _parse_tencent_minute_row(row: Any) -> IndexCurvePoint | None:
    if not isinstance(row, str):
        return None
    parts = row.split()
    if len(parts) < 2:
        return None
    raw_time = parts[0]
    price = _to_float(parts[1])
    if len(raw_time) != 4 or price is None:
        return None
    return IndexCurvePoint(
        time=f"{raw_time[:2]}:{raw_time[2:]}:00",
        value=price,
        price=price,
        average_price=None,
        volume=_to_float(parts[2]) if len(parts) > 2 else None,
        amount=_to_float(parts[3]) if len(parts) > 3 else None,
    )


def _to_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_time(value: str) -> str:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).strftime("%H:%M:%S")
        except ValueError:
            pass
    return value
