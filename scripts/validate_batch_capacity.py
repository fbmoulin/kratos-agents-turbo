"""Run end-to-end batch capacity validation against the local API."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from urllib import request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core import (  # noqa: E402
    CapacityScenario,
    build_status_counts,
    build_task_duration_stats,
    default_scenarios,
    parse_scenario,
)

PDF_TEMPLATE = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
72 100 Td
(Kratos capacity validation) Tj
ET
endstream
endobj
trailer
<< /Root 1 0 R >>
%%EOF
"""


def _json_request(
    method: str,
    url: str,
    *,
    data: bytes | None = None,
    content_type: str | None = None,
    timeout: int = 60,
) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    req = request.Request(url, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _encode_multipart(
    *,
    fields: list[tuple[str, str]],
    files: list[tuple[str, str, bytes, str]],
) -> tuple[bytes, str]:
    boundary = f"kratos-{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for key, value in fields:
        parts.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    for field_name, file_name, file_bytes, content_type in files:
        parts.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{field_name}"; '
                    f'filename="{file_name}"\r\n'
                ).encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                file_bytes,
                b"\r\n",
            ]
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _submit_batch(api_base_url: str, scenario: CapacityScenario) -> dict[str, object]:
    files = []
    for index in range(1, scenario.count + 1):
        files.append(
            (
                "files",
                f"{scenario.task_type}-{index:03d}.pdf",
                PDF_TEMPLATE,
                "application/pdf",
            )
        )
    fields = [
        ("message", scenario.message),
        ("task_type", scenario.task_type),
        ("idempotency_key", f"capacity-{scenario.task_type}-{uuid.uuid4().hex}"),
    ]
    body, content_type = _encode_multipart(fields=fields, files=files)
    return _json_request(
        "POST",
        f"{api_base_url}/batches",
        data=body,
        content_type=content_type,
    )


def _get_batch(api_base_url: str, batch_id: str) -> dict[str, object]:
    return _json_request("GET", f"{api_base_url}/batches/{batch_id}")


def _get_task(api_base_url: str, task_id: str) -> dict[str, object]:
    return _json_request("GET", f"{api_base_url}/tasks/{task_id}")


def _poll_batch(
    api_base_url: str,
    batch_id: str,
    *,
    poll_interval_seconds: float,
    timeout_seconds: int,
) -> tuple[dict[str, object], float]:
    started = time.perf_counter()
    while True:
        batch = _get_batch(api_base_url, batch_id)
        status = str(batch["status"])
        if status in {"completed", "failed", "cancelled"}:
            return batch, time.perf_counter() - started
        if (time.perf_counter() - started) > timeout_seconds:
            raise TimeoutError(f"Batch '{batch_id}' did not finish within {timeout_seconds}s")
        time.sleep(poll_interval_seconds)


def run_scenario(
    api_base_url: str,
    scenario: CapacityScenario,
    *,
    poll_interval_seconds: float,
    timeout_seconds: int,
) -> dict[str, object]:
    submitted = _submit_batch(api_base_url, scenario)
    batch_id = str(submitted["batch_id"])
    final_batch, batch_elapsed = _poll_batch(
        api_base_url,
        batch_id,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
    )
    task_ids = [str(task["id"]) for task in final_batch.get("tasks", [])]
    task_details = [_get_task(api_base_url, task_id) for task_id in task_ids]
    duration_stats = build_task_duration_stats(task_details)
    status_counts = build_status_counts(task_details)
    throughput = 0.0
    if batch_elapsed > 0:
        throughput = round(len(task_ids) / batch_elapsed, 3)
    return {
        "task_type": scenario.task_type,
        "requested_count": scenario.count,
        "batch_id": batch_id,
        "queue": submitted.get("queue"),
        "batch_status": final_batch["status"],
        "status_counts": status_counts,
        "batch_elapsed_seconds": round(batch_elapsed, 3),
        "throughput_docs_per_second": throughput,
        "task_duration_seconds": duration_stats,
        "task_ids": task_ids,
        "meets_target": (
            final_batch["status"] == "completed"
            and status_counts["completed"] == scenario.count
            and status_counts["failed"] == 0
            and status_counts["cancelled"] == 0
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-base-url",
        default="http://127.0.0.1:8000",
        help="Base URL for the Kratos API",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        help=(
            "Scenario in the format '<task_type>=<count>'. "
            "Defaults to despacho=50 and decisao=20."
        ),
    )
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--output", help="Optional path to write the JSON report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scenarios = (
        [parse_scenario(spec) for spec in args.scenario]
        if args.scenario
        else default_scenarios()
    )
    report = {
        "api_base_url": args.api_base_url.rstrip("/"),
        "scenarios": [
            run_scenario(
                args.api_base_url.rstrip("/"),
                scenario,
                poll_interval_seconds=args.poll_interval_seconds,
                timeout_seconds=args.timeout_seconds,
            )
            for scenario in scenarios
        ],
    }
    report["all_targets_met"] = all(
        bool(scenario_result["meets_target"]) for scenario_result in report["scenarios"]
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["all_targets_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
