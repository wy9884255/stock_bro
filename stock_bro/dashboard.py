from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from .limit_up import normalize_failed_limit_up_times
from .quotes import read_jsonl as read_quote_jsonl
from .trading_calendar import read_trade_calendar


LEADER_THEME_NAME = "领涨龙头"


def build_dashboard(
    trade_date: date,
    eastmoney_dir: Path = Path("data/limit_up"),
    cls_dir: Path = Path("data/cls"),
    web_dir: Path = Path("web"),
    quotes_dir: Path = Path("data/quotes"),
) -> Path:
    records = _read_eastmoney_records(eastmoney_dir / f"{trade_date:%Y%m%d}.jsonl")
    cls_analysis = _read_cls_analysis(cls_dir, trade_date)
    finance_anchors = _read_cls_finance_anchors(cls_dir / f"{trade_date:%Y%m%d}_finance_anchors.json")
    theme_map = _theme_map_from_cls(cls_analysis)

    stocks = [
        _merge_stock(record, theme_map.get(record["code"], {}))
        for record in records
    ]
    stocks.sort(key=lambda item: (item["last_limit_up_time"] or "99:99:99", item["code"]))
    finance_leaders = _mark_finance_leaders(stocks, finance_anchors)
    next_day_returns = _build_previous_theme_returns(
        trade_date,
        eastmoney_dir=eastmoney_dir,
        cls_dir=cls_dir,
        quotes_dir=quotes_dir,
    )

    payload = {
        "trade_date": trade_date.strftime("%Y-%m-%d"),
        "generated_at": _latest_generated_at(stocks),
        "summary": _build_summary(stocks, theme_map, cls_analysis),
        "cls_analysis": _dashboard_cls_payload(cls_analysis),
        "finance_anchors": finance_anchors,
        "finance_leaders": finance_leaders,
        "next_day_returns": next_day_returns,
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
                    row["failed_limit_up_times"] = normalize_failed_limit_up_times(
                        row.get("failed_limit_up_times"),
                        row.get("first_limit_up_time"),
                        row.get("last_limit_up_time"),
                    )
                    records.append(row)
    return records


def _read_cls_analysis(cls_dir: Path, trade_date: date) -> dict[str, Any]:
    cls_analysis = _read_cls_limit_up_analysis(cls_dir / f"{trade_date:%Y%m%d}_limit_up_analysis.json")
    _merge_cls_theme_stocks(cls_analysis, cls_dir / f"{trade_date:%Y%m%d}_theme_stocks.json")
    return cls_analysis


def _read_cls_limit_up_analysis(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        return {}
    return payload


def _merge_cls_theme_stocks(cls_analysis: dict[str, Any], path: Path) -> None:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if isinstance(payload, dict):
        rows = payload.get("theme_stocks", [])
    else:
        rows = payload
    if isinstance(rows, list):
        cls_analysis["theme_stocks"] = rows


def _read_cls_finance_anchors(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        return None
    anchors = payload.get("anchors")
    segments = payload.get("segments")
    if not isinstance(anchors, list) or not isinstance(segments, list):
        return None
    result = {
        "source": payload.get("source"),
        "api": payload.get("api"),
        "trade_date": payload.get("trade_date"),
        "anchor_count": len(anchors),
        "segments": segments,
    }
    index_curve = payload.get("index_curve") or payload.get("index_points")
    if isinstance(index_curve, list):
        result["index_curve"] = index_curve
    index_curve_meta = payload.get("index_curve_meta")
    if isinstance(index_curve_meta, dict):
        result["index_curve_meta"] = index_curve_meta
    return result


def _theme_map_from_cls(cls_analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = cls_analysis.get("theme_stocks", [])
    if not isinstance(rows, list):
        return {}

    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "")
        if not code:
            continue
        item = result.setdefault(code, {"themes": [], "reason_info": None})
        for theme in _extract_theme_names(row.get("theme") or row.get("themes") or []):
            if theme not in item["themes"]:
                item["themes"].append(theme)
        reason = _clean_text(row.get("reason") or row.get("analysis"))
        if reason and not item.get("reason_info"):
            item["reason_info"] = reason
    return result


def _merge_stock(eastmoney: dict[str, Any], cls_theme: dict[str, Any]) -> dict[str, Any]:
    themes = _clean_strings(cls_theme.get("themes", []))
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
        "themes": themes,
        "reason_type": ", ".join(themes) if themes else None,
        "reason_info": _clean_text(cls_theme.get("reason_info")),
        "collected_at": eastmoney.get("collected_at"),
    }


def _build_summary(
    stocks: list[dict[str, Any]],
    theme_map: dict[str, dict[str, Any]],
    cls_analysis: dict[str, Any],
) -> dict[str, Any]:
    times = [stock["last_limit_up_time"] for stock in stocks if stock["last_limit_up_time"]]
    return {
        "total": len(stocks),
        "failed": sum(1 for stock in stocks if stock["is_failed_limit_up"]),
        "with_theme": sum(1 for stock in stocks if stock["themes"]),
        "cls_theme_records": len(theme_map),
        "cls_images": len(cls_analysis.get("classification_images") or []),
        "earliest_limit_up": min(times) if times else None,
        "latest_limit_up": max(times) if times else None,
    }


def _dashboard_cls_payload(cls_analysis: dict[str, Any]) -> dict[str, Any] | None:
    if not cls_analysis:
        return None
    return {
        "title": cls_analysis.get("title"),
        "url": cls_analysis.get("url"),
        "published_at": cls_analysis.get("published_at"),
        "summary": cls_analysis.get("summary"),
        "classification_images": cls_analysis.get("classification_images") or [],
    }


def _build_themes(stocks: list[dict[str, Any]], min_count: int = 1) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    failed: dict[str, int] = {}
    for stock in stocks:
        for theme in stock["themes"]:
            counts[theme] = counts.get(theme, 0) + 1
            if stock["is_failed_limit_up"]:
                failed[theme] = failed.get(theme, 0) + 1
    return [
        {"name": name, "count": count, "failed_count": failed.get(name, 0)}
        for name, count in sorted(counts.items(), key=lambda item: (item[0] != LEADER_THEME_NAME, -item[1], item[0]))
        if count >= min_count
    ]


def _mark_finance_leaders(
    stocks: list[dict[str, Any]],
    finance_anchors: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not finance_anchors:
        return []
    segments = finance_anchors.get("segments")
    if not isinstance(segments, list):
        return []

    leaders: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        start = _time_to_minutes(segment.get("start"))
        end = _time_to_minutes(segment.get("end"))
        if start is None or end is None:
            continue
        for anchor in segment.get("themes") or []:
            if not isinstance(anchor, dict):
                continue
            anchor_name = _clean_text(anchor.get("name"))
            if not anchor_name:
                continue
            candidate = _finance_leader_candidate(stocks, anchor_name, start, end)
            if not candidate:
                continue

            if LEADER_THEME_NAME not in candidate["themes"]:
                candidate["themes"].append(LEADER_THEME_NAME)
            candidate.setdefault("leader_tags", [])
            leader_tag = {
                "theme": anchor_name,
                "time": anchor.get("time"),
                "segment": f"{segment.get('start')}-{segment.get('end')}",
                "article_id": anchor.get("article_id"),
            }
            if leader_tag not in candidate["leader_tags"]:
                candidate["leader_tags"].append(leader_tag)

            key = (candidate["code"], anchor_name, leader_tag["segment"])
            if key in seen:
                continue
            seen.add(key)
            leaders.append(
                {
                    "code": candidate["code"],
                    "name": candidate["name"],
                    "anchor_theme": anchor_name,
                    "anchor_time": anchor.get("time"),
                    "segment": leader_tag["segment"],
                    "first_limit_up_time": candidate.get("first_limit_up_time"),
                    "themes": [theme for theme in candidate["themes"] if theme != LEADER_THEME_NAME],
                    "reason_info": candidate.get("reason_info"),
                    "article_id": anchor.get("article_id"),
                }
            )
    return leaders


def _finance_leader_candidate(
    stocks: list[dict[str, Any]],
    anchor_name: str,
    start: int,
    end: int,
) -> dict[str, Any] | None:
    candidates = [
        stock
        for stock in stocks
        if _stock_in_time_segment(stock, start, end)
        and _stock_matches_anchor_theme(stock, anchor_name)
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda stock: (stock.get("first_limit_up_time") or "99:99:99", stock["code"]))[0]


def _stock_in_time_segment(stock: dict[str, Any], start: int, end: int) -> bool:
    current = _time_to_minutes(stock.get("first_limit_up_time"))
    if current is None:
        return False
    if end >= 15 * 60:
        return start <= current <= end
    return start <= current < end


def _stock_matches_anchor_theme(stock: dict[str, Any], anchor_name: str) -> bool:
    anchor = _normalize_match_text(anchor_name)
    if not anchor:
        return False
    values = [
        *(stock.get("themes") or []),
        stock.get("reason_type"),
        stock.get("reason_info"),
        stock.get("industry"),
    ]
    for value in values:
        text = _normalize_match_text(value)
        if not text:
            continue
        if anchor in text or text in anchor:
            return True
    return False


def _build_previous_theme_returns(
    trade_date: date,
    eastmoney_dir: Path,
    cls_dir: Path,
    quotes_dir: Path,
) -> dict[str, Any] | None:
    source_date = _previous_trade_date(trade_date)
    if source_date is None:
        return None

    source_records = _read_eastmoney_records(eastmoney_dir / f"{source_date:%Y%m%d}.jsonl")
    if not source_records:
        return None
    source_cls_analysis = _read_cls_analysis(cls_dir, source_date)
    source_theme_map = _theme_map_from_cls(source_cls_analysis)
    source_stocks = [
        _merge_stock(record, source_theme_map.get(record["code"], {}))
        for record in source_records
    ]
    source_finance_anchors = _read_cls_finance_anchors(cls_dir / f"{source_date:%Y%m%d}_finance_anchors.json")
    _mark_finance_leaders(source_stocks, source_finance_anchors)
    leader_stocks = [stock for stock in source_stocks if LEADER_THEME_NAME in stock["themes"]]
    if not leader_stocks:
        return None

    quotes = read_quote_jsonl(quotes_dir / f"{trade_date:%Y%m%d}.jsonl")
    if not quotes:
        return None

    all_stats = _return_stats(LEADER_THEME_NAME, leader_stocks, quotes)
    theme_groups: dict[str, list[dict[str, Any]]] = {}
    for stock in leader_stocks:
        for theme in stock["themes"]:
            if theme == LEADER_THEME_NAME:
                continue
            theme_groups.setdefault(theme, []).append(stock)

    themes = [
        _return_stats(name, stocks, quotes)
        for name, stocks in sorted(theme_groups.items(), key=lambda item: (-len(item[1]), item[0]))
    ]
    return {
        "source_trade_date": source_date.strftime("%Y-%m-%d"),
        "return_trade_date": trade_date.strftime("%Y-%m-%d"),
        "quote_count": len(quotes),
        "all": all_stats,
        "themes": themes,
        "stocks": _return_stock_rows(leader_stocks, quotes),
    }


def _previous_trade_date(trade_date: date) -> date | None:
    trade_dates = sorted(item for item in read_trade_calendar() if item < trade_date)
    if trade_dates:
        return trade_dates[-1]
    return None


def _return_stats(
    name: str,
    stocks: list[dict[str, Any]],
    quotes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    priced = [quotes[stock["code"]] for stock in stocks if stock["code"] in quotes]
    return {
        "name": name,
        "stock_count": len(stocks),
        "priced_count": len(priced),
        "open_return_percent": _average(row.get("open_return_percent") for row in priced),
        "high_return_percent": _average(row.get("high_return_percent") for row in priced),
        "close_return_percent": _average(row.get("close_return_percent") for row in priced),
    }


def _return_stock_rows(
    stocks: list[dict[str, Any]],
    quotes: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stock in sorted(stocks, key=lambda item: (item.get("first_limit_up_time") or "99:99:99", item["code"])):
        quote = quotes.get(stock["code"])
        if not quote:
            continue
        rows.append(
            {
                "code": stock["code"],
                "name": stock["name"],
                "themes": [theme for theme in stock["themes"] if theme != LEADER_THEME_NAME],
                "first_limit_up_time": stock.get("first_limit_up_time"),
                "open_return_percent": quote.get("open_return_percent"),
                "high_return_percent": quote.get("high_return_percent"),
                "close_return_percent": quote.get("close_return_percent"),
            }
        )
    return rows


def _average(values: Any) -> float | None:
    numbers = [float(value) for value in values if isinstance(value, (int, float))]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _time_to_minutes(value: Any) -> int | None:
    if not value:
        return None
    parts = str(value).split(":")
    if len(parts) < 2:
        return None
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        return None


def _normalize_match_text(value: Any) -> str:
    if value in (None, "", "-"):
        return ""
    return "".join(str(value).lower().split())


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
        normalized = value
        for separator in ("+", "，", "、", "/", "|"):
            normalized = normalized.replace(separator, "+")
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
