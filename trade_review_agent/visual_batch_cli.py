from __future__ import annotations

import argparse
from pathlib import Path

from .visual_report import build_all_reports


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate visual reports for all trade rounds in a brokerage statement")
    parser.add_argument("trades", help="成交记录文件")
    parser.add_argument("-o", "--output-dir", default="outputs/visual_reports", help="输出目录")
    parser.add_argument("--cache-db", default="work/real_trade_review_cache.sqlite", help="SQLite 行情缓存路径")
    parser.add_argument("--benchmark", default="sh000300", help="基准指数")
    args = parser.parse_args()

    results = build_all_reports(
        trades_path=args.trades,
        output_dir=Path(args.output_dir),
        cache_db=args.cache_db,
        benchmark_symbol=args.benchmark,
    )
    print(f"Wrote {len(results)} visual reports")
    print(Path(args.output_dir) / "index.html")


if __name__ == "__main__":
    main()
