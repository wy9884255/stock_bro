from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from .trading_calendar import read_trade_calendar


def build_dashboard(
    trade_date: date,
    eastmoney_dir: Path = Path("data/limit_up"),
    kaipanla_dir: Path = Path("data/kaipanla"),
    web_dir: Path = Path("web"),
) -> Path:
    records = _read_eastmoney_records(eastmoney_dir / f"{trade_date:%Y%m%d}.jsonl")
    block_map = _read_block_limit_up(kaipanla_dir / f"{trade_date:%Y%m%d}_block_limit_up.json")
    dragon_tiger_map = _read_latest_dragon_tiger(kaipanla_dir)

    stocks = [
        _merge_stock(record, block_map.get(record["code"], {}), dragon_tiger_map.get(record["code"]))
        for record in records
    ]
    stocks.sort(key=lambda item: (item["last_limit_up_time"] or "99:99:99", item["code"]))

    payload = {
        "trade_date": trade_date.strftime("%Y-%m-%d"),
        "generated_at": _latest_generated_at(stocks),
        "summary": _build_summary(stocks, block_map, dragon_tiger_map),
        "themes": _build_themes(stocks),
        "stocks": stocks,
    }

    web_dir.mkdir(parents=True, exist_ok=True)
    dated_data_path = web_dir / f"dashboard_data_{trade_date:%Y%m%d}.json"
    with dated_data_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    data_path = web_dir / "dashboard_data.json"
    shutil.copyfile(dated_data_path, data_path)
    _write_dashboard_index(web_dir)
    _copy_dashboard_html(web_dir)
    return dated_data_path


def _read_eastmoney_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                row = json.loads(line)
                code = str(row.get("code") or "")
                if code:
                    row["code"] = code
                    row["name"] = str(row.get("name") or "")
                    records.append(row)
    return records


def _read_block_limit_up(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    stocks = payload.get("stocks", [])
    if not isinstance(stocks, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for stock in stocks:
        if isinstance(stock, dict):
            code = str(stock.get("code") or "")
            if code:
                result[code] = stock
    return result


def _read_latest_dragon_tiger(kaipanla_dir: Path) -> dict[str, dict[str, Any]]:
    files = sorted(kaipanla_dir.glob("*_dragon_tiger.json"))
    if not files:
        return {}
    with files[-1].open("r", encoding="utf-8") as file:
        rows = json.load(file)
    if not isinstance(rows, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict):
            code = str(row.get("code") or "")
            if code:
                result[code] = row
    return result


def _merge_stock(
    eastmoney: dict[str, Any],
    block: dict[str, Any],
    dragon_tiger: dict[str, Any] | None,
) -> dict[str, Any]:
    block_names = _extract_theme_names(block.get("block_names", []))
    reason_type = _clean_text(block.get("reason_type"))
    if reason_type:
        block_names.extend(_extract_theme_names(reason_type))
    concepts = _clean_strings((dragon_tiger or {}).get("concepts", []))
    return {
        "code": eastmoney["code"],
        "name": eastmoney["name"],
        "latest_price": eastmoney.get("latest_price"),
        "change_percent": eastmoney.get("change_percent"),
        "first_limit_up_time": eastmoney.get("first_limit_up_time"),
        "last_limit_up_time": eastmoney.get("last_limit_up_time"),
        "consecutive_limit_up_days": eastmoney.get("consecutive_limit_up_days"),
        "failed_limit_up_times": eastmoney.get("failed_limit_up_times") or 0,
        "limit_up_session": eastmoney.get("limit_up_session") or "unknown",
        "industry": _clean_text(eastmoney.get("industry")),
        "is_failed_limit_up": (eastmoney.get("failed_limit_up_times") or 0) > 0,
        "themes": _dedupe(block_names),
        "reason_type": reason_type,
        "reason_info": _clean_text(block.get("reason_info")),
        "change_tag": _clean_text(block.get("change_tag")),
        "market_type": _clean_text(block.get("market_type")),
        "kaipanla_latest": block.get("latest"),
        "dragon_tiger": _merge_dragon_tiger(dragon_tiger, concepts),
        "collected_at": eastmoney.get("collected_at"),
    }


def _merge_dragon_tiger(row: dict[str, Any] | None, concepts: list[str]) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "increase_amount": _clean_text(row.get("increase_amount")),
        "net_buy_amount": row.get("net_buy_amount"),
        "join_num": row.get("join_num"),
        "buy_icons": _clean_strings(row.get("buy_icons", [])),
        "sell_icons": _clean_strings(row.get("sell_icons", [])),
        "concepts": concepts,
        "limit_up_days": row.get("limit_up_days"),
    }


def _build_summary(
    stocks: list[dict[str, Any]],
    block_map: dict[str, dict[str, Any]],
    dragon_tiger_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    times = [stock["last_limit_up_time"] for stock in stocks if stock["last_limit_up_time"]]
    return {
        "total": len(stocks),
        "failed": sum(1 for stock in stocks if stock["is_failed_limit_up"]),
        "with_theme": sum(1 for stock in stocks if stock["themes"]),
        "with_dragon_tiger": sum(1 for stock in stocks if stock["dragon_tiger"]),
        "kaipanla_theme_records": len(block_map),
        "dragon_tiger_records": len(dragon_tiger_map),
        "earliest_limit_up": min(times) if times else None,
        "latest_limit_up": max(times) if times else None,
    }


def _build_themes(stocks: list[dict[str, Any]], min_count: int = 5) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    failed: dict[str, int] = {}
    for stock in stocks:
        for theme in stock["themes"]:
            counts[theme] = counts.get(theme, 0) + 1
            if stock["is_failed_limit_up"]:
                failed[theme] = failed.get(theme, 0) + 1
    return [
        {"name": name, "count": count, "failed_count": failed.get(name, 0)}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        if count >= min_count
    ]


def _latest_generated_at(stocks: list[dict[str, Any]]) -> str | None:
    values = [stock.get("collected_at") for stock in stocks if stock.get("collected_at")]
    return max(values) if values else None


def _clean_text(value: Any) -> str | None:
    if value in (None, "", "-"):
        return None
    return str(value)


def _clean_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return _dedupe(str(value) for value in values if value not in (None, "", "-"))


def _extract_theme_names(values: Any) -> list[str]:
    if isinstance(values, str):
        raw_values = [values]
    elif isinstance(values, list):
        raw_values = [str(value) for value in values if value not in (None, "", "-")]
    else:
        return []

    result: list[str] = []
    for value in raw_values:
        normalized = value.replace("，", "+").replace("、", "+").replace("/", "+").replace("|", "+")
        for item in normalized.split("+"):
            item = item.strip()
            if item and item not in result:
                result.append(item)
    return result


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _write_dashboard_index(web_dir: Path) -> None:
    trade_dates = read_trade_calendar()
    dates = []
    for path in sorted(web_dir.glob("dashboard_data_*.json")):
        raw = path.stem.removeprefix("dashboard_data_")
        if len(raw) == 8 and raw.isdigit():
            current = date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))
            if trade_dates and current not in trade_dates:
                continue
            if _dashboard_total(path) <= 0:
                continue
            dates.append(
                {
                    "date": f"{raw[:4]}-{raw[4:6]}-{raw[6:]}",
                    "file": path.name,
                }
            )
    with (web_dir / "dashboard_index.json").open("w", encoding="utf-8") as file:
        json.dump({"dates": dates}, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _dashboard_total(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        return int(payload.get("summary", {}).get("total") or 0)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0


def _copy_dashboard_html(web_dir: Path) -> None:
    source = Path(__file__).resolve().parent.parent / "web" / "dashboard.html"
    target = web_dir / "dashboard.html"
    if source.exists() and source.resolve() != target.resolve():
        shutil.copyfile(source, target)
