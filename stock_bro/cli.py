from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .limit_up import collect_limit_up_stocks, parse_trade_date, write_csv, write_jsonl, write_sqlite


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
        for path in written:
            print(f"Wrote {path}")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
