from __future__ import annotations

from pathlib import Path

import pandas as pd

from .ai_trade_parser import parse_trade_file_to_frame, parse_trade_image_to_frame, parse_trade_text_to_frame


def screenshot_to_trade_csv(image_paths: list[str | Path] | str | Path, output_csv: str | Path) -> Path:
    """Compatibility wrapper: screenshots are parsed by OpenAI vision only."""
    if isinstance(image_paths, (str, Path)):
        image_paths = [image_paths]

    frames = [parse_trade_image_to_frame(path) for path in image_paths]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        raise ValueError("OpenAI vision did not find any recognizable trade facts")
    return _write_frame(pd.concat(frames, ignore_index=True), output_csv)


def screenshot_to_trade_frame(image_path: str | Path) -> pd.DataFrame:
    """Compatibility wrapper: keep old function name, use OpenAI vision only."""
    return parse_trade_image_to_frame(image_path)


def trade_file_to_trade_csv(input_path: list[str | Path] | str | Path, output_csv: str | Path) -> Path:
    """Parse image/Excel/CSV/TXT through OpenAI into trade facts."""
    if isinstance(input_path, (str, Path)):
        input_paths = [input_path]
    else:
        input_paths = list(input_path)

    frames = [parse_trade_file_to_frame(path) for path in input_paths]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        raise ValueError("OpenAI did not find any recognizable trade facts")
    return _write_frame(pd.concat(frames, ignore_index=True), output_csv)


def trade_text_to_trade_csv(text: str, output_csv: str | Path) -> Path:
    return _write_frame(parse_trade_text_to_frame(text), output_csv)


def _write_frame(frame: pd.DataFrame, output_csv: str | Path) -> Path:
    if frame.empty:
        raise ValueError("OpenAI did not find any recognizable trade facts")

    result = frame.drop_duplicates(subset=["trade_date", "trade_time", "code", "side", "quantity", "price"])
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_csv, index=False, encoding="utf-8-sig")
    return output_csv
