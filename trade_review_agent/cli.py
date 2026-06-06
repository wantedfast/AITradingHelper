from __future__ import annotations

import argparse
from pathlib import Path

from .io import read_trade_file
from .report import write_markdown_report
from .review import review_trades
from .schema import ReviewConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="A-share trade review agent MVP")
    parser.add_argument("trades", help="成交记录 CSV 或 Excel 文件")
    parser.add_argument("-o", "--output", default="outputs/review_report.md", help="输出 Markdown 报告路径")
    parser.add_argument("--cache-db", default="work/trade_review_cache.sqlite", help="SQLite 行情缓存路径")
    parser.add_argument("--benchmark", default="sh000300", help="基准指数，默认沪深300 sh000300")
    parser.add_argument("--adjust", default="qfq", choices=["", "qfq", "hfq"], help="复权方式")
    parser.add_argument("--offline", action="store_true", help="只使用本地 SQLite 缓存，不调用 AKShare")
    args = parser.parse_args()

    trades = read_trade_file(args.trades)
    config = ReviewConfig(
        benchmark_symbol=args.benchmark,
        cache_db=args.cache_db,
        adjust=args.adjust,
        offline=args.offline,
    )
    reviews = review_trades(trades, config)
    output = write_markdown_report(reviews, Path(args.output))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
