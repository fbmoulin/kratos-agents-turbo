from __future__ import annotations

import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DATASET_ROOT = ROOT / "datasets" / "criminal_advocacy_stage2"
MANIFEST_PATH = DATASET_ROOT / "manifest.json"

RUNTIME_TASK_TYPE_BY_PIECE_TYPE = {
    "resposta_a_acusacao": "decisao",
    "revogacao_prisao_preventiva": "despacho",
    "habeas_corpus": "decisao",
    "alegacoes_finais": "decisao",
}


@dataclass(frozen=True)
class CriminalAdvocacyCase:
    case_id: str
    title: str
    target_piece_type: str
    raw_case_text: str
    raw_case_context: str | None
    expected_strategic_direction: str
    notes: dict[str, list[str]]
    canonical_advocacy_pipeline: dict[str, Any]
    runtime_task_type: str
    path: Path


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def iter_cases() -> list[CriminalAdvocacyCase]:
    manifest = load_manifest()
    cases: list[CriminalAdvocacyCase] = []
    for entry in manifest["cases"]:
        path = DATASET_ROOT / entry["path"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        piece_type = payload["target_piece_type"]
        cases.append(
            CriminalAdvocacyCase(
                case_id=payload["case_id"],
                title=payload["title"],
                target_piece_type=piece_type,
                raw_case_text=payload["raw_case_text"],
                raw_case_context=payload.get("raw_case_context"),
                expected_strategic_direction=payload["expected_strategic_direction"],
                notes=payload["notes"],
                canonical_advocacy_pipeline=payload["canonical_advocacy_pipeline"],
                runtime_task_type=RUNTIME_TASK_TYPE_BY_PIECE_TYPE[piece_type],
                path=path,
            )
        )
    return cases


def build_runtime_message(case: CriminalAdvocacyCase) -> str:
    priorities = "; ".join(case.notes["tactical_priorities"])
    risks = "; ".join(case.notes["risks"])
    proof_gaps = "; ".join(case.notes["proof_gaps"])
    return (
        f"Elabore minuta de defesa criminal do tipo {case.target_piece_type}. "
        f"Direção estratégica esperada: {case.expected_strategic_direction} "
        f"Prioridades táticas: {priorities}. "
        f"Riscos relevantes: {risks}. "
        f"Lacunas probatórias: {proof_gaps}."
    )


def build_case_document_text(case: CriminalAdvocacyCase) -> str:
    parts = [
        f"CASO: {case.title}",
        f"TIPO DE PECA ALVO: {case.target_piece_type}",
        "TEXTO BRUTO DO CASO:",
        case.raw_case_text,
    ]
    if case.raw_case_context:
        parts.extend(["CONTEXTO ADICIONAL:", case.raw_case_context])
    return "\n\n".join(parts)


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_simple_pdf_bytes(text: str) -> bytes:
    lines = [line for line in text.splitlines() if line.strip()] or [" "]
    content_lines = ["BT", "/F1 12 Tf", "72 780 Td", "14 TL"]
    first_line = True
    for line in lines:
        escaped = _escape_pdf_text(line)
        if first_line:
            content_lines.append(f"({escaped}) Tj")
            first_line = False
        else:
            content_lines.append(f"T* ({escaped}) Tj")
    content_lines.append("ET")
    content = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n",
        (
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        ),
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        (
            f"5 0 obj\n<< /Length {len(content)} >>\nstream\n".encode("latin-1")
            + content
            + b"\nendstream\nendobj\n"
        ),
    ]

    buffer = BytesIO()
    buffer.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(buffer.tell())
        buffer.write(obj)
    xref_start = buffer.tell()
    buffer.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    buffer.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.write(f"{offset:010d} 00000 n \n".encode("latin-1"))
    buffer.write(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF"
        ).encode("latin-1")
    )
    return buffer.getvalue()


def build_case_pdf_bytes(case: CriminalAdvocacyCase) -> bytes:
    return build_simple_pdf_bytes(build_case_document_text(case))
