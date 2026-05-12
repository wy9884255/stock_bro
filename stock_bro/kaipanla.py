from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


KAIPANLA_HQ_API_URL = "https://apphq.longhuvip.com/w1/api/index.php"
KAIPANLA_HISTORY_API_URL = "https://apphis.longhuvip.com/w1/api/index.php"
KAIPANLA_LHB_API_URL = "https://applhb.longhuvip.com/w1/api/index.php"
KAIPANLA_SERVERLESS_API_URL = "https://service-q4mj86xx-1252010818.sh.tencentapigw.com"
KAIPANLA_USER_AGENT = "lhb/5.11.1 (com.kaipanla.www; build:0; iOS 14.6.0) Alamofire/5.11.1"


@dataclass(frozen=True)
class KaipanlaMarketSentiment:
    trade_date: str | None
    limit_up_count: int | None
    decline_count: int | None
    strength: int | None
    high_limit_up_count: int | None
    tip: str | None
    raw: dict[str, Any]
    collected_at: str


@dataclass(frozen=True)
class KaipanlaSharpWithdrawalStock:
    trade_date: str | None
    code: str
    name: str
    current_price: float | None
    withdrawal_percent: float | None
    change_percent: float | None
    raw: list[Any]
    collected_at: str


@dataclass(frozen=True)
class KaipanlaDailyLimitPerformance:
    trade_date: str
    rows: list[Any]
    raw: dict[str, Any]
    collected_at: str


@dataclass(frozen=True)
class KaipanlaBlockLimitUp:
    trade_date: str
    blocks: list[dict[str, Any]]
    stocks: list[dict[str, Any]]
    raw: dict[str, Any]
    collected_at: str


@dataclass(frozen=True)
class KaipanlaDragonTigerStock:
    code: str
    name: str
    increase_amount: str | None
    net_buy_amount: float | None
    join_num: int | None
    buy_icons: list[str]
    sell_icons: list[str]
    concepts: list[str]
    limit_up_days: Any
    raw: dict[str, Any]
    collected_at: str


def fetch_market_sentiment(timeout: float = 15.0) -> KaipanlaMarketSentiment:
    payload = fetch_kaipanla_payload(
        KAIPANLA_HQ_API_URL,
        {"a": "ChangeStatistics", "apiv": "w28", "c": "HomeDingPan"},
        timeout=timeout,
    )
    collected_at = _now_utc()
    info = payload.get("info")
    row = info[0] if isinstance(info, list) and info and isinstance(info[0], dict) else {}
    return KaipanlaMarketSentiment(
        trade_date=_empty_to_none(row.get("Day")),
        limit_up_count=_to_int(row.get("ztjs")),
        decline_count=_to_int(row.get("df_num")),
        strength=_to_int(row.get("strong")),
        high_limit_up_count=_to_int(row.get("lbgd")),
        tip=_empty_to_none(payload.get("tip")),
        raw=payload,
        collected_at=collected_at,
    )


def fetch_sharp_withdrawal_stocks(limit: int = 20, timeout: float = 15.0) -> list[KaipanlaSharpWithdrawalStock]:
    payload = fetch_kaipanla_payload(
        KAIPANLA_HQ_API_URL,
        {
            "Index": 0,
            "Order": 0,
            "PhoneOSNew": 2,
            "Type": 0,
            "VerSion": "5.11.0.1",
            "a": "SharpWithdrawalList",
            "apiv": "w33",
            "c": "HomeDingPan",
            "st": limit,
        },
        timeout=timeout,
    )
    trade_date = _empty_to_none(payload.get("date"))
    collected_at = _now_utc()
    rows = payload.get("info")
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise ValueError(f"Unexpected Kaipanla response shape: info is {type(rows).__name__}")
    return [_parse_sharp_withdrawal_row(row, trade_date, collected_at) for row in rows]


def fetch_daily_limit_performance(
    trade_date: date,
    limit: int = 1000,
    timeout: float = 15.0,
) -> KaipanlaDailyLimitPerformance:
    payload = fetch_kaipanla_payload(
        KAIPANLA_HISTORY_API_URL,
        {
            "Day": trade_date.strftime("%Y-%m-%d"),
            "Index": 0,
            "Order": 0,
            "PhoneOSNew": 2,
            "PidType": 1,
            "Type": 4,
            "VerSion": "5.16.0.5",
            "a": "DailyLimitPerformance",
            "apiv": "w38",
            "c": "HisHomeDingPan",
            "st": limit,
        },
        timeout=timeout,
    )
    info = payload.get("info")
    rows = info[0] if isinstance(info, list) and info and isinstance(info[0], list) else []
    return KaipanlaDailyLimitPerformance(
        trade_date=trade_date.strftime("%Y-%m-%d"),
        rows=rows,
        raw=payload,
        collected_at=_now_utc(),
    )


def fetch_block_limit_up_by_date(trade_date: date, timeout: float = 15.0) -> KaipanlaBlockLimitUp:
    payload = fetch_kaipanla_payload(
        f"{KAIPANLA_SERVERLESS_API_URL}/getStockBlockUpByDate",
        {"date": trade_date.strftime("%Y%m%d")},
        timeout=timeout,
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected Kaipanla block response shape: data is {type(data).__name__}")
    blocks = data.get("data", [])
    if not isinstance(blocks, list):
        raise ValueError(f"Unexpected Kaipanla block response shape: data.data is {type(blocks).__name__}")

    stocks_by_code: dict[str, dict[str, Any]] = {}
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_name = block.get("name")
        for stock in block.get("stock_list", []) or []:
            if not isinstance(stock, dict):
                continue
            code = str(stock.get("code") or "")
            if not code:
                continue
            normalized = dict(stock)
            normalized.setdefault("block_names", [])
            normalized["block_names"] = list(normalized["block_names"])
            if block_name and block_name not in normalized["block_names"]:
                normalized["block_names"].append(block_name)
            if code in stocks_by_code:
                existing_blocks = stocks_by_code[code].setdefault("block_names", [])
                for name in normalized["block_names"]:
                    if name not in existing_blocks:
                        existing_blocks.append(name)
            else:
                stocks_by_code[code] = normalized

    return KaipanlaBlockLimitUp(
        trade_date=trade_date.strftime("%Y-%m-%d"),
        blocks=blocks,
        stocks=sorted(stocks_by_code.values(), key=lambda item: str(item.get("code") or "")),
        raw=payload,
        collected_at=_now_utc(),
    )


def fetch_dragon_tiger_stocks(limit: int = 500, timeout: float = 15.0) -> list[KaipanlaDragonTigerStock]:
    payload = fetch_kaipanla_payload(
        KAIPANLA_LHB_API_URL,
        {
            "st": limit,
            "Index": 0,
            "c": "LongHuBang",
            "PhoneOSNew": 1,
            "a": "GetStockList",
            "DeviceID": "0f6ac4ae-370d-3091-a618-1d9dbb2ecce0",
            "apiv": "w31",
            "Type": 2,
            "UserID": 0,
            "Token": 0,
            "Time": 0,
        },
        method="POST",
        timeout=timeout,
    )
    rows = payload.get("list")
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise ValueError(f"Unexpected Kaipanla dragon tiger response shape: list is {type(rows).__name__}")
    collected_at = _now_utc()
    return [_parse_dragon_tiger_row(row, payload, collected_at) for row in rows if isinstance(row, dict)]


def fetch_kaipanla_payload(
    base_url: str,
    params: dict[str, Any],
    method: str = "GET",
    timeout: float = 15.0,
) -> dict[str, Any]:
    method = method.upper()
    data = None
    url = base_url
    if method == "GET":
        url = f"{base_url}?{urlencode(params)}"
    elif method == "POST":
        data = urlencode(params).encode("utf-8")
    else:
        raise ValueError(f"Unsupported HTTP method: {method}")

    request = Request(
        url,
        data=data,
        headers={
            "User-Agent": KAIPANLA_USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"Kaipanla request failed with HTTP {exc.code}") from exc
    except (TimeoutError, URLError) as exc:
        raise RuntimeError(f"Kaipanla request failed: {exc}") from exc

    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected Kaipanla response shape: root is {type(payload).__name__}")
    return payload


def write_json(data: Any, out_dir: Path, dataset: str, trade_date: date | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = trade_date.strftime("%Y%m%d") if trade_date else date.today().strftime("%Y%m%d")
    output = out_dir / f"{suffix}_{dataset}.json"
    with output.open("w", encoding="utf-8") as file:
        json.dump(_to_jsonable(data), file, ensure_ascii=False, indent=2)
        file.write("\n")
    return output


def _parse_sharp_withdrawal_row(
    row: Any,
    trade_date: str | None,
    collected_at: str,
) -> KaipanlaSharpWithdrawalStock:
    if not isinstance(row, list):
        raise ValueError(f"Unexpected Kaipanla sharp withdrawal row type: {type(row).__name__}")
    return KaipanlaSharpWithdrawalStock(
        trade_date=trade_date,
        code=str(_list_get(row, 0) or ""),
        name=str(_list_get(row, 1) or ""),
        current_price=_to_float(_list_get(row, 4)),
        withdrawal_percent=_to_float(_list_get(row, 5)),
        change_percent=_to_float(_list_get(row, 6)),
        raw=row,
        collected_at=collected_at,
    )


def _parse_dragon_tiger_row(
    row: dict[str, Any],
    payload: dict[str, Any],
    collected_at: str,
) -> KaipanlaDragonTigerStock:
    code = str(row.get("ID") or "")
    concepts = payload.get("fkgn", {}).get(code, {})
    if isinstance(concepts, dict):
        concept_values = [str(value) for value in concepts.values()]
    else:
        concept_values = []
    return KaipanlaDragonTigerStock(
        code=code,
        name=str(row.get("Name") or ""),
        increase_amount=_empty_to_none(row.get("IncreaseAmount")),
        net_buy_amount=_to_float(row.get("BuyIn")),
        join_num=_to_int(row.get("JoinNum")),
        buy_icons=[str(item) for item in payload.get("BIcon", {}).get(code, [])],
        sell_icons=[str(item) for item in payload.get("SIcon", {}).get(code, [])],
        concepts=concept_values,
        limit_up_days=payload.get("lb", {}).get(code),
        raw=row,
        collected_at=collected_at,
    )


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value


def _list_get(values: list[Any], index: int) -> Any:
    return values[index] if index < len(values) else None


def _to_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
