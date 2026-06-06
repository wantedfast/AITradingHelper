from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path


def main() -> None:
    cache = Path("work/trade_review_cache.sqlite")
    cache.parent.mkdir(exist_ok=True)
    with sqlite3.connect(cache) as conn:
        for table in ("stock_daily", "index_daily"):
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    symbol TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    open REAL,
                    close REAL,
                    high REAL,
                    low REAL,
                    volume REAL,
                    amount REAL,
                    pct_chg REAL,
                    turnover REAL,
                    PRIMARY KEY (symbol, trade_date)
                )
                """
            )

        start = date(2024, 3, 12)
        stock_close = 10.0
        index_close = 3500.0
        for offset in range(45):
            day = start + timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            stock_close *= 1.006 if day < date(2024, 4, 8) else 0.997
            index_close *= 1.001
            volume = 900000 + offset * 10000
            if day == date(2024, 4, 1):
                volume *= 2.2

            conn.execute(
                """
                INSERT OR REPLACE INTO stock_daily
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "000001",
                    day.isoformat(),
                    stock_close * 0.99,
                    stock_close,
                    stock_close * 1.02,
                    stock_close * 0.98,
                    volume,
                    volume * stock_close,
                    0.6,
                    1.2,
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO index_daily
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "sh000300",
                    day.isoformat(),
                    index_close * 0.997,
                    index_close,
                    index_close * 1.004,
                    index_close * 0.996,
                    100000000,
                    200000000000.0,
                    0.1,
                    None,
                ),
            )
    print(f"Seeded {cache}")


if __name__ == "__main__":
    main()
