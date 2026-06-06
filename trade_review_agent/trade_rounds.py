from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .schema import Trade


@dataclass(frozen=True)
class TradeRound:
    code: str
    name: str
    round_id: int
    trades: tuple[Trade, ...]

    @property
    def start_date(self) -> date:
        return min(trade.trade_date for trade in self.trades)

    @property
    def end_date(self) -> date:
        return max(trade.trade_date for trade in self.trades)

    @property
    def is_closed(self) -> bool:
        return self.buy_qty > 0 and self.sell_qty >= self.buy_qty

    @property
    def buy_qty(self) -> float:
        return sum(trade.quantity for trade in self.trades if trade.side == "buy")

    @property
    def sell_qty(self) -> float:
        return sum(trade.quantity for trade in self.trades if trade.side == "sell")


def split_trade_rounds(trades: list[Trade]) -> list[TradeRound]:
    by_code: dict[str, list[Trade]] = {}
    for trade in trades:
        by_code.setdefault(trade.code, []).append(trade)

    rounds: list[TradeRound] = []
    for code, items in sorted(by_code.items()):
        ordered = sorted(items, key=lambda item: (item.trade_date, 0 if item.side == "buy" else 1, item.price))
        current: list[Trade] = []
        position = 0.0
        round_id = 1
        for trade in ordered:
            if not current and trade.side == "sell":
                rounds.append(TradeRound(code=code, name=trade.name, round_id=round_id, trades=(trade,)))
                round_id += 1
                continue
            current.append(trade)
            position += trade.quantity if trade.side == "buy" else -trade.quantity
            if current and position <= 0 and any(item.side == "buy" for item in current):
                rounds.append(TradeRound(code=code, name=current[0].name, round_id=round_id, trades=tuple(current)))
                current = []
                position = 0.0
                round_id += 1
        if current:
            rounds.append(TradeRound(code=code, name=current[0].name, round_id=round_id, trades=tuple(current)))
    return rounds
