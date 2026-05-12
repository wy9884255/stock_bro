from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StockIdentity:
    code: str
    name: str


@dataclass(frozen=True)
class LimitUpComparison:
    trade_date: str
    kaipanla_source: str
    eastmoney: dict[str, StockIdentity]
    kaipanla: dict[str, StockIdentity]
    common_codes: list[str]
    eastmoney_only_codes: list[str]
    kaipanla_only_codes: list[str]


def compare_limit_up_archives(
    trade_date: date,
    eastmoney_dir: Path = Path("data/limit_up"),
    kaipanla_dir: Path = Path("data/kaipanla"),
    kaipanla_source: str = "auto",
) -> LimitUpComparison:
    eastmoney = read_eastmoney_limit_up_jsonl(eastmoney_dir / f"{trade_date:%Y%m%d}.jsonl")
    kaipanla, resolved_source = read_kaipanla_limit_up_archive(kaipanla_dir, trade_date, kaipanla_source)
    eastmoney_codes = set(eastmoney)
    kaipanla_codes = set(kaipanla)
    return LimitUpComparison(
        trade_date=trade_date.strftime("%Y-%m-%d"),
        kaipanla_source=resolved_source,
        eastmoney=eastmoney,
        kaipanla=kaipanla,
        common_codes=sorted(eastmoney_codes & kaipanla_codes),
        eastmoney_only_codes=sorted(eastmoney_codes - kaipanla_codes),
        kaipanla_only_codes=sorted(kaipanla_codes - eastmoney_codes),
    )


def read_kaipanla_limit_up_archive(
    archive_dir: Path,
    trade_date: date,
    source: str = "auto",
) -> tuple[dict[str, StockIdentity], str]:
    if source not in ("auto", "block-limit-up", "daily-limit-performance"):
        raise ValueError(f"Unsupported Kaipanla source: {source}")

    block_path = archive_dir / f"{trade_date:%Y%m%d}_block_limit_up.json"
    daily_path = archive_dir / f"{trade_date:%Y%m%d}_daily_limit_performance.json"
    if source in ("auto", "block-limit-up") and block_path.exists():
        return read_kaipanla_block_limit_up_json(block_path), "block-limit-up"
    if source == "block-limit-up":
        return {}, "block-limit-up"
    return read_kaipanla_daily_limit_performance_json(daily_path), "daily-limit-performance"


def read_eastmoney_limit_up_jsonl(path: Path) -> dict[str, StockIdentity]:
    records: dict[str, StockIdentity] = {}
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            row = json.loads(line)
            code = str(row.get("code") or "")
            if code:
                records[code] = StockIdentity(code=code, name=str(row.get("name") or ""))
    return records


def read_kaipanla_block_limit_up_json(path: Path) -> dict[str, StockIdentity]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    rows = payload.get("stocks", [])
    if not isinstance(rows, list):
        raise ValueError(f"Unexpected Kaipanla block archive shape: stocks is {type(rows).__name__}")

    records: dict[str, StockIdentity] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "")
        if code:
            records[code] = StockIdentity(code=code, name=str(row.get("name") or ""))
    return records


def read_kaipanla_daily_limit_performance_json(path: Path) -> dict[str, StockIdentity]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        raise ValueError(f"Unexpected Kaipanla archive shape: rows is {type(rows).__name__}")

    records: dict[str, StockIdentity] = {}
    for row in rows:
        identity = _parse_kaipanla_identity(row)
        if identity:
            records[identity.code] = identity
    return records


def format_comparison(comparison: LimitUpComparison, max_items: int = 50) -> str:
    lines = [
        f"Limit-up comparison for {comparison.trade_date}",
        f"  Eastmoney: {len(comparison.eastmoney)}",
        f"  Kaipanla ({comparison.kaipanla_source}): {len(comparison.kaipanla)}",
        f"  Common: {len(comparison.common_codes)}",
        f"  Eastmoney only: {len(comparison.eastmoney_only_codes)}",
        f"    {_format_identities(comparison.eastmoney, comparison.eastmoney_only_codes, max_items)}",
        f"  Kaipanla only: {len(comparison.kaipanla_only_codes)}",
        f"    {_format_identities(comparison.kaipanla, comparison.kaipanla_only_codes, max_items)}",
    ]
    return "\n".join(lines)


def _parse_kaipanla_identity(row: Any) -> StockIdentity | None:
    if not isinstance(row, list) or len(row) < 2:
        return None
    code = str(row[0] or "")
    if not code:
        return None
    return StockIdentity(code=code, name=str(row[1] or ""))


def _format_identities(records: dict[str, StockIdentity], codes: list[str], max_items: int) -> str:
    if not codes:
        return "-"
    visible_codes = codes[:max_items]
    items = [f"{code} {records[code].name}" for code in visible_codes]
    if len(codes) > max_items:
        items.append(f"... +{len(codes) - max_items} more")
    return ", ".join(items)
