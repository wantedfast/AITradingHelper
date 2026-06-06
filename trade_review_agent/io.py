from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from .schema import Trade


COLUMN_ALIASES = {
    "code": ["code", "symbol", "stock_code", "证券代码", "股票代码", "代码"],
    "name": ["name", "stock_name", "证券名称", "股票名称", "名称"],
    "trade_date": ["trade_date", "date", "成交日期", "交易日期", "日期"],
    "side": ["side", "action", "direction", "买卖方向", "操作", "方向", "买卖"],
    "price": ["price", "成交价格", "成交价", "成交均价", "价格"],
    "quantity": ["quantity", "volume", "shares", "成交数量", "数量", "股数"],
    "amount": ["amount", "成交金额", "金额", "发生金额"],
    "fee": ["fee", "commission", "手续费", "佣金", "费用"],
    "buy_reason": ["buy_reason", "买入理由", "买入逻辑"],
    "sell_reason": ["sell_reason", "卖出理由", "卖出逻辑"],
}

BUY_WORDS = {"buy", "b", "买", "买入", "证券买入", "担保品买入"}
SELL_WORDS = {"sell", "s", "卖", "卖出", "证券卖出", "担保品卖出"}


def read_trade_file(path: str | Path) -> list[Trade]:
    path = Path(path)
    frame = _read_input_frame(path)

    frame = _rename_columns(frame)
    required = {"code", "trade_date", "side", "price", "quantity"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    if "name" not in frame.columns:
        frame["name"] = ""
    if "amount" not in frame.columns:
        frame["amount"] = frame["price"].astype(float) * frame["quantity"].astype(float)
    if "fee" not in frame.columns:
        frame["fee"] = 0.0
    for optional in ("buy_reason", "sell_reason"):
        if optional not in frame.columns:
            frame[optional] = ""

    trades: list[Trade] = []
    for row in frame.to_dict("records"):
        trades.append(
            Trade(
                code=normalize_code(row["code"]),
                name=str(row.get("name") or ""),
                trade_date=parse_trade_date(row["trade_date"]),
                side=normalize_side(row["side"]),
                price=float(row["price"]),
                quantity=float(row["quantity"]),
                amount=float(row.get("amount") or 0),
                fee=float(row.get("fee") or 0),
                buy_reason=str(row.get("buy_reason") or ""),
                sell_reason=str(row.get("sell_reason") or ""),
            )
        )
    return sorted(trades, key=lambda item: (item.trade_date, item.code, item.side))


def _read_input_frame(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    header = path.read_bytes()[:8]
    is_real_excel = header.startswith(b"\xd0\xcf\x11\xe0") or header.startswith(b"PK\x03\x04")
    if suffix in {".xlsx", ".xls"} and is_real_excel:
        return pd.read_excel(path)

    separators = ["\t", ","]
    encodings = ["utf-8-sig", "gbk", "gb18030"]
    last_error: Exception | None = None
    for encoding in encodings:
        for separator in separators:
            try:
                frame = pd.read_csv(path, sep=separator, encoding=encoding)
            except Exception as exc:
                last_error = exc
                continue
            if len(frame.columns) > 1:
                return frame
    if last_error:
        raise last_error
    raise ValueError(f"Could not read trade file: {path}")


def normalize_code(value: object) -> str:
    text = str(value).strip().upper()
    if text.endswith((".SH", ".SZ", ".BJ")):
        text = text.split(".")[0]
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        raise ValueError(f"Invalid stock code: {value!r}")
    return digits.zfill(6)[-6:]


def normalize_side(value: object) -> str:
    text = str(value).strip().lower()
    if text in BUY_WORDS or "买" in text:
        return "buy"
    if text in SELL_WORDS or "卖" in text:
        return "sell"
    raise ValueError(f"Unknown side/action: {value!r}")


def parse_trade_date(value: object):
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 8:
        return pd.to_datetime(digits, format="%Y%m%d").date()
    return pd.to_datetime(value).date()


def _rename_columns(frame: pd.DataFrame) -> pd.DataFrame:
    lookup = {str(col).strip(): col for col in frame.columns}
    rename: dict[object, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lookup:
                rename[lookup[alias]] = canonical
                break
    return frame.rename(columns=rename)


def trades_to_frame(trades: Iterable[Trade]) -> pd.DataFrame:
    return pd.DataFrame([trade.__dict__ for trade in trades])
