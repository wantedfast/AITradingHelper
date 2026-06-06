from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class Trade:
    code: str
    name: str
    trade_date: date
    side: str
    price: float
    quantity: float
    amount: float
    fee: float = 0.0
    buy_reason: str = ""
    sell_reason: str = ""

    @property
    def signed_quantity(self) -> float:
        return self.quantity if self.side == "buy" else -self.quantity

    @property
    def reason(self) -> str:
        if self.side == "buy":
            return self.buy_reason
        return self.sell_reason


@dataclass(frozen=True)
class ReviewConfig:
    benchmark_symbol: str = "sh000300"
    lookahead_days: tuple[int, ...] = (1, 3, 5, 10)
    cache_db: str = "trade_review_cache.sqlite"
    adjust: str = "qfq"
    offline: bool = False
    openai_api_key: Optional[str] = None
