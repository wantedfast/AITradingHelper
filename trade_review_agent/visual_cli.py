from __future__ import annotations

import argparse
from pathlib import Path

from .visual_report import build_single_stock_html


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an interactive single-stock trade review page")
    parser.add_argument("trades", help="成交记录文件")
    parser.add_argument("--code", default="600584", help="股票代码")
    parser.add_argument("-o", "--output", default="outputs/charts/600584_changdian.html", help="输出 HTML 路径")
    parser.add_argument("--cache-db", default="work/real_trade_review_cache.sqlite", help="SQLite 行情缓存路径")
    parser.add_argument("--benchmark", default="sh000300", help="基准指数")
    parser.add_argument("--sector", default="512480", help="对比板块/ETF代码，默认半导体ETF")
    parser.add_argument("--trade-date", default=None, help="指定交易日期，如 2026-05-29；不填则使用第一轮闭合交易")
    args = parser.parse_args()

    output = build_single_stock_html(
        trades_path=args.trades,
        code=args.code,
        output=Path(args.output),
        cache_db=args.cache_db,
        benchmark_symbol=args.benchmark,
        sector_symbol=args.sector,
        trade_date=args.trade_date,
    )
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
