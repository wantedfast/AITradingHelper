from __future__ import annotations

from pathlib import Path

from .review import TradeReview
from .schema import Trade


def write_markdown_report(reviews: list[TradeReview], output: str | Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# A股交易复盘报告", ""]
    lines.extend(_summary(reviews))
    lines.extend(_position_summary([review.trade for review in reviews]))
    for index, review in enumerate(reviews, start=1):
        trade = review.trade
        lines.extend(
            [
                "",
                f"## {index}. {trade.name or trade.code} {trade.code} {side_label(trade.side)}",
                "",
                f"- 成交日期：{trade.trade_date}",
                f"- 对齐交易日：{review.execution_date}",
                f"- 成交价格：{trade.price:.2f}",
                f"- 成交数量：{trade.quantity:.0f}",
                f"- 成交金额：{trade.amount:.2f}",
                f"- 当日收盘：{_fmt(review.execution_close)}",
                f"- 当日涨跌幅：{_pct(review.execution_pct_chg)}",
                f"- 当日量比(相对前5日)：{_ratio(review.volume_ratio_5d)}",
                f"- 10日最大上涨：{_pct(review.max_gain_10d)}",
                f"- 10日最大回撤：{_pct(review.max_drawdown_10d)}",
                "",
                "| 指标 | 1日 | 3日 | 5日 | 10日 |",
                "| --- | ---: | ---: | ---: | ---: |",
                f"| 个股收益 | {_days(review.returns)} |",
                f"| 沪深300收益 | {_days(review.benchmark_returns)} |",
                f"| 相对强弱 | {_days(review.relative_returns)} |",
                "",
                f"- 结论：{review.verdict}",
                f"- 问题：{review.problem}",
                f"- 改进：{review.improvement}",
            ]
        )
        if trade.reason:
            lines.append(f"- 原始理由：{trade.reason}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def _summary(reviews: list[TradeReview]) -> list[str]:
    buy_count = sum(1 for item in reviews if item.trade.side == "buy")
    sell_count = len(reviews) - buy_count
    data_missing = sum(1 for item in reviews if item.execution_close is None)
    return [
        f"- 复盘成交：{len(reviews)} 笔",
        f"- 买入：{buy_count} 笔",
        f"- 卖出：{sell_count} 笔",
        f"- 数据不足：{data_missing} 笔",
    ]


def _position_summary(trades: list[Trade]) -> list[str]:
    grouped: dict[tuple[str, str], dict[str, float]] = {}
    for trade in trades:
        key = (trade.code, trade.name)
        row = grouped.setdefault(
            key,
            {
                "buy_qty": 0.0,
                "sell_qty": 0.0,
                "buy_amount": 0.0,
                "sell_amount": 0.0,
                "cash_flow": 0.0,
                "fee": 0.0,
                "count": 0.0,
            },
        )
        row["count"] += 1
        row["fee"] += trade.fee
        row["cash_flow"] += trade.amount if trade.side == "sell" else -trade.amount
        if trade.side == "buy":
            row["buy_qty"] += trade.quantity
            row["buy_amount"] += trade.amount
        else:
            row["sell_qty"] += trade.quantity
            row["sell_amount"] += trade.amount

    lines = [
        "",
        "## 成交汇总",
        "",
        "| 代码 | 名称 | 笔数 | 买入数量 | 买入均价 | 卖出数量 | 卖出均价 | 期间净买入数量 | 期间现金流 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for (code, name), row in sorted(grouped.items()):
        net_qty = row["buy_qty"] - row["sell_qty"]
        buy_avg = row["buy_amount"] / row["buy_qty"] if row["buy_qty"] else None
        sell_avg = row["sell_amount"] / row["sell_qty"] if row["sell_qty"] else None
        lines.append(
            "| "
            + " | ".join(
                [
                    code,
                    name or "",
                    f"{int(row['count'])}",
                    f"{row['buy_qty']:.0f}",
                    _fmt(buy_avg),
                    f"{row['sell_qty']:.0f}",
                    _fmt(sell_avg),
                    f"{net_qty:.0f}",
                    f"{row['cash_flow']:.2f}",
                ]
            )
            + " |"
        )
    return lines


def side_label(side: str) -> str:
    return "买入" if side == "buy" else "卖出"


def _days(values: dict[int, float | None]) -> str:
    return " | ".join(_pct(values.get(day)) for day in (1, 3, 5, 10))


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}%"


def _ratio(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}x"
