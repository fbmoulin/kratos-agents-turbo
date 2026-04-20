from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.criminal_advocacy_reporting import render_markdown_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a Markdown review report from a criminal advocacy evaluation JSON."
    )
    parser.add_argument("input", type=Path, help="Path to the JSON evaluation report.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the Markdown report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = json.loads(args.input.read_text(encoding="utf-8"))
    markdown = render_markdown_report(report)
    if args.output:
        args.output.write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
