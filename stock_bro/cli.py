from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .cls import fetch_cls_limit_up_analysis, write_json as write_cls_json
from .compare import compare_limit_up_archives, format_comparison
from .dashboard import build_dashboard
from .kaipanla import (
    fetch_block_limit_up_by_date,
    fetch_daily_limit_performance,
    fetch_dragon_tiger_stocks,
    fetch_market_sentiment,
    fetch_sharp_withdrawal_stocks,
    write_json as write_kaipanla_json,
)
from .limit_up import (
    LimitUpStock,
    collect_limit_up_stocks,
    parse_trade_date,
    summarize_failed_limit_up_stocks,
    write_csv,
    write_jsonl,
    write_sqlite,
)
from .trading_calendar import (
    DEFAULT_CALENDAR_PATH,
    fetch_a_share_trade_dates,
    read_trade_calendar,
    trading_dates_between,
    write_trade_calendar,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stock-bro")
    subparsers = parser.add_subparsers(dest="command", required=True)

    limit_up = subparsers.add_parser("limit-up", help="Collect daily A-share limit-up stocks.")
    limit_up.add_argument("--date", dest="trade_date", help="Trade date in YYYY-MM-DD or YYYYMMDD format.")
    limit_up.add_argument("--out-dir", default="data/limit_up", help="Directory for CSV and JSONL files.")
    limit_up.add_argument("--sqlite", default="data/stock_bro.sqlite3", help="SQLite database path.")
    limit_up.add_argument("--no-csv", action="store_true", help="Do not write CSV output.")
    limit_up.add_argument("--no-jsonl", action="store_true", help="Do not write JSONL output.")
    limit_up.add_argument("--no-sqlite", action="store_true", help="Do not write SQLite output.")
    limit_up.add_argument("--include-st", action="store_true", help="Include ST and *ST stocks. Default excludes them.")
    limit_up.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds.")

    kaipanla = subparsers.add_parser("kaipanla", help="Collect public Kaipanla data.")
    kaipanla.add_argument(
        "--dataset",
        choices=(
            "sentiment",
            "sharp-withdrawal",
            "daily-limit-performance",
            "block-limit-up",
            "dragon-tiger",
            "all",
        ),
        default="all",
        help="Kaipanla dataset to collect.",
    )
    kaipanla.add_argument("--date", dest="trade_date", help="Trade date for date-based datasets.")
    kaipanla.add_argument(
        "--from-date",
        dest="from_date",
        help="Start date for daily-limit-performance and block-limit-up.",
    )
    kaipanla.add_argument(
        "--to-date",
        dest="to_date",
        help="End date for daily-limit-performance and block-limit-up.",
    )
    kaipanla.add_argument("--out-dir", default="data/kaipanla", help="Directory for JSON files.")
    kaipanla.add_argument("--limit", type=int, default=1000, help="Maximum rows for list datasets.")
    kaipanla.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds.")
    kaipanla.add_argument("--no-file", action="store_true", help="Do not write JSON output.")

    cls = subparsers.add_parser("cls", help="Collect CLS limit-up analysis article data.")
    cls.add_argument("--url", required=True, help="CLS article URL, for example https://www.cls.cn/detail/2368985.")
    cls.add_argument("--date", dest="trade_date", help="Trade date in YYYY-MM-DD or YYYYMMDD format.")
    cls.add_argument("--out-dir", default="data/cls", help="Directory for CLS JSON files.")
    cls.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds.")
    cls.add_argument("--no-file", action="store_true", help="Do not write JSON output.")

    compare = subparsers.add_parser("compare-limit-up", help="Compare Eastmoney and Kaipanla local archives.")
    compare.add_argument("--date", required=True, dest="trade_date", help="Trade date in YYYY-MM-DD or YYYYMMDD format.")
    compare.add_argument("--eastmoney-dir", default="data/limit_up", help="Directory with Eastmoney JSONL archives.")
    compare.add_argument("--kaipanla-dir", default="data/kaipanla", help="Directory with Kaipanla JSON archives.")
    compare.add_argument(
        "--kaipanla-source",
        choices=("auto", "block-limit-up", "daily-limit-performance"),
        default="auto",
        help="Kaipanla local archive source to compare.",
    )
    compare.add_argument("--max-items", type=int, default=50, help="Maximum stock names to print for each diff side.")

    dashboard = subparsers.add_parser("build-dashboard", help="Build a local HTML dashboard from archived data.")
    dashboard.add_argument("--date", required=True, dest="trade_date", help="Trade date in YYYY-MM-DD or YYYYMMDD format.")
    dashboard.add_argument("--eastmoney-dir", default="data/limit_up", help="Directory with Eastmoney JSONL archives.")
    dashboard.add_argument("--cls-dir", default="data/cls", help="Directory with CLS limit-up analysis JSON archives.")
    dashboard.add_argument("--web-dir", default="web", help="Output directory for dashboard files.")

    trade_calendar = subparsers.add_parser("trade-calendar", help="Fetch and cache A-share trading calendar.")
    trade_calendar.add_argument("--out", default=str(DEFAULT_CALENDAR_PATH), help="Output calendar JSON path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "limit-up":
        trade_date = parse_trade_date(args.trade_date) if args.trade_date else date.today()
        records = collect_limit_up_stocks(trade_date, timeout=args.timeout, include_st=args.include_st)

        out_dir = Path(args.out_dir)
        written: list[Path] = []
        if not args.no_csv:
            written.append(write_csv(records, out_dir, trade_date=trade_date))
        if not args.no_jsonl:
            written.append(write_jsonl(records, out_dir, trade_date=trade_date))
        if not args.no_sqlite:
            sqlite_path = Path(args.sqlite)
            write_sqlite(records, sqlite_path, trade_date=trade_date)
            written.append(sqlite_path)

        print(f"Collected {len(records)} limit-up stocks for {trade_date:%Y-%m-%d}.")
        _print_failed_limit_up_summary(records)
        for path in written:
            print(f"Wrote {path}")
        return 0

    if args.command == "kaipanla":
        trade_date = parse_trade_date(args.trade_date) if args.trade_date else date.today()
        from_date = parse_trade_date(args.from_date) if args.from_date else None
        to_date = parse_trade_date(args.to_date) if args.to_date else None
        if (from_date or to_date) and args.dataset not in ("daily-limit-performance", "block-limit-up", "all"):
            parser.error("--from-date and --to-date only apply to daily-limit-performance and block-limit-up")
        if from_date and to_date and from_date > to_date:
            parser.error("--from-date must be earlier than or equal to --to-date")

        out_dir = Path(args.out_dir)
        written: list[Path] = []
        cached_trade_dates = read_trade_calendar()

        if args.dataset in ("sentiment", "all"):
            sentiment = fetch_market_sentiment(timeout=args.timeout)
            print(
                "Kaipanla sentiment: "
                f"date={sentiment.trade_date}, limit_up={sentiment.limit_up_count}, "
                f"decline={sentiment.decline_count}, strength={sentiment.strength}"
            )
            if not args.no_file:
                written.append(write_kaipanla_json(sentiment, out_dir, "sentiment", trade_date))

        if args.dataset in ("sharp-withdrawal", "all"):
            stocks = fetch_sharp_withdrawal_stocks(limit=args.limit, timeout=args.timeout)
            print(f"Kaipanla sharp withdrawal stocks: {len(stocks)}")
            if stocks:
                print(f"  {_format_kaipanla_stock_list(stocks)}")
            if not args.no_file:
                written.append(write_kaipanla_json(stocks, out_dir, "sharp_withdrawal", trade_date))

        if args.dataset in ("daily-limit-performance", "all"):
            dates = _trading_date_range(from_date or trade_date, to_date or from_date or trade_date, cached_trade_dates)
            total_rows = 0
            for current_date in dates:
                performance = fetch_daily_limit_performance(current_date, limit=args.limit, timeout=args.timeout)
                total_rows += len(performance.rows)
                print(f"Kaipanla daily limit performance rows: {len(performance.rows)} for {current_date:%Y-%m-%d}")
                if performance.rows:
                    print(f"  {_format_kaipanla_raw_rows(performance.rows)}")
                if not args.no_file:
                    written.append(
                        write_kaipanla_json(performance, out_dir, "daily_limit_performance", current_date)
                    )
            if len(dates) > 1:
                print(f"Kaipanla daily limit performance total rows: {total_rows} from {dates[0]} to {dates[-1]}")

        if args.dataset in ("block-limit-up", "all"):
            dates = _trading_date_range(from_date or trade_date, to_date or from_date or trade_date, cached_trade_dates)
            total_stocks = 0
            for current_date in dates:
                block_limit_up = fetch_block_limit_up_by_date(current_date, timeout=args.timeout)
                total_stocks += len(block_limit_up.stocks)
                print(
                    "Kaipanla block limit-up: "
                    f"{len(block_limit_up.stocks)} stocks in {len(block_limit_up.blocks)} blocks "
                    f"for {current_date:%Y-%m-%d}"
                )
                if block_limit_up.stocks:
                    print(f"  {_format_kaipanla_dict_stocks(block_limit_up.stocks)}")
                if not args.no_file:
                    written.append(write_kaipanla_json(block_limit_up, out_dir, "block_limit_up", current_date))
            if len(dates) > 1:
                print(f"Kaipanla block limit-up total stocks: {total_stocks} from {dates[0]} to {dates[-1]}")

        if args.dataset in ("dragon-tiger", "all"):
            dragon_tiger = fetch_dragon_tiger_stocks(limit=args.limit, timeout=args.timeout)
            print(f"Kaipanla dragon tiger stocks: {len(dragon_tiger)}")
            if dragon_tiger:
                print(f"  {_format_kaipanla_stock_list(dragon_tiger)}")
            if not args.no_file:
                written.append(write_kaipanla_json(dragon_tiger, out_dir, "dragon_tiger", trade_date))

        for path in written:
            print(f"Wrote {path}")
        return 0

    if args.command == "cls":
        trade_date = parse_trade_date(args.trade_date) if args.trade_date else None
        analysis = fetch_cls_limit_up_analysis(args.url, trade_date=trade_date, timeout=args.timeout)
        print(f"CLS limit-up analysis: {analysis.title} ({analysis.trade_date})")
        print(f"Classification images: {len(analysis.classification_images)}")
        for image in analysis.classification_images:
            dimensions = f"{image.width}x{image.height}" if image.width and image.height else "unknown size"
            print(f"  {dimensions} {image.url}")
        if analysis.related_stocks:
            print(f"Related stocks: {_format_cls_stock_list(analysis.related_stocks)}")
        if not args.no_file:
            path = write_cls_json(analysis, Path(args.out_dir))
            print(f"Wrote {path}")
        return 0

    if args.command == "compare-limit-up":
        trade_date = parse_trade_date(args.trade_date)
        comparison = compare_limit_up_archives(
            trade_date,
            eastmoney_dir=Path(args.eastmoney_dir),
            kaipanla_dir=Path(args.kaipanla_dir),
            kaipanla_source=args.kaipanla_source,
        )
        print(format_comparison(comparison, max_items=args.max_items))
        return 0

    if args.command == "build-dashboard":
        trade_date = parse_trade_date(args.trade_date)
        data_path = build_dashboard(
            trade_date,
            eastmoney_dir=Path(args.eastmoney_dir),
            cls_dir=Path(args.cls_dir),
            web_dir=Path(args.web_dir),
        )
        print(f"Built dashboard data: {data_path}")
        print(f"Open dashboard: {data_path.parent / 'dashboard.html'}")
        return 0

    if args.command == "trade-calendar":
        trade_dates = fetch_a_share_trade_dates()
        path = write_trade_calendar(trade_dates, Path(args.out))
        print(f"Fetched {len(trade_dates)} A-share trading dates.")
        if trade_dates:
            print(f"Range: {trade_dates[0]} to {trade_dates[-1]}")
        print(f"Wrote {path}")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


def _print_failed_limit_up_summary(records: list[LimitUpStock]) -> None:
    summary = summarize_failed_limit_up_stocks(records)
    print(f"Failed limit-up stocks: {len(summary.failed_stocks)}")
    if not summary.failed_stocks:
        return
    print(f"  Closed above previous close: {len(summary.closed_above_previous_close)}")
    print(f"    {_format_stock_list(summary.closed_above_previous_close)}")
    print(f"  Closed at previous close: {len(summary.closed_at_previous_close)}")
    print(f"    {_format_stock_list(summary.closed_at_previous_close)}")
    print(f"  Closed below previous close: {len(summary.closed_below_previous_close)}")
    print(f"    {_format_stock_list(summary.closed_below_previous_close)}")
    if summary.unknown_close_relation:
        print(f"  Unknown close relation: {len(summary.unknown_close_relation)}")
        print(f"    {_format_stock_list(summary.unknown_close_relation)}")


def _format_stock_list(records: list[LimitUpStock]) -> str:
    if not records:
        return "-"
    return ", ".join(f"{record.code} {record.name}" for record in records)


def _format_kaipanla_stock_list(records: list[object]) -> str:
    return ", ".join(f"{record.code} {record.name}" for record in records[:20])


def _format_kaipanla_raw_rows(rows: list[Any], limit: int = 20) -> str:
    items = []
    for row in rows[:limit]:
        if isinstance(row, list) and len(row) >= 2:
            items.append(f"{row[0]} {row[1]}")
        else:
            items.append(str(row))
    return ", ".join(items)


def _format_kaipanla_dict_stocks(rows: list[dict[str, Any]], limit: int = 20) -> str:
    return ", ".join(f"{row.get('code')} {row.get('name')}" for row in rows[:limit])


def _format_cls_stock_list(records: list[object]) -> str:
    return ", ".join(
        f"{record.name} {record.change_percent or ''}".strip()
        for record in records[:20]
    )


def _date_range(start: date, end: date) -> list[date]:
    days = (end - start).days
    return [start + timedelta(days=offset) for offset in range(days + 1)]


def _trading_date_range(start: date, end: date, trade_dates: set[date]) -> list[date]:
    if trade_dates:
        return trading_dates_between(start, end, trade_dates)
    return _date_range(start, end)


if __name__ == "__main__":
    raise SystemExit(main())
