from __future__ import annotations

import argparse
from pathlib import Path

from trade_review_agent.ocr.ocr_trades import screenshot_to_trade_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Use OpenAI vision to extract trade facts from screenshots.")
    parser.add_argument("images", nargs="+", help="Screenshot image paths")
    parser.add_argument("-o", "--output", default="outputs/ai_trades.csv", help="Internal CSV output path")
    args = parser.parse_args()

    output = screenshot_to_trade_csv([Path(path) for path in args.images], Path(args.output))
    print(output)


if __name__ == "__main__":
    main()
