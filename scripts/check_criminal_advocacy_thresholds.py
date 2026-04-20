from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.criminal_advocacy_thresholds import (
    evaluate_report_against_thresholds,
    load_thresholds,
)


DEFAULT_THRESHOLDS_PATH = (
    ROOT / "datasets" / "criminal_advocacy_stage2" / "thresholds.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a criminal advocacy evaluation report against dataset thresholds."
    )
    parser.add_argument("input", type=Path, help="Path to the JSON evaluation report.")
    parser.add_argument(
        "--thresholds",
        type=Path,
        default=DEFAULT_THRESHOLDS_PATH,
        help="Path to the threshold definition JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the JSON threshold result.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = json.loads(args.input.read_text(encoding="utf-8"))
    thresholds = load_thresholds(args.thresholds)
    result = evaluate_report_against_thresholds(report, thresholds)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(payload)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
