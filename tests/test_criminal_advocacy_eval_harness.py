from __future__ import annotations

from io import BytesIO

import pdfplumber

from src.evaluation.criminal_advocacy_dataset import (
    build_case_pdf_bytes,
    build_runtime_message,
    iter_cases,
)


def test_criminal_advocacy_eval_harness_builds_runtime_projections() -> None:
    cases = iter_cases()

    assert len(cases) == 10
    assert {case.target_piece_type for case in cases} == {
        "resposta_a_acusacao",
        "revogacao_prisao_preventiva",
        "habeas_corpus",
        "alegacoes_finais",
    }
    assert {case.runtime_task_type for case in cases} == {"despacho", "decisao"}

    for case in cases:
        message = build_runtime_message(case)
        assert case.target_piece_type in message
        assert case.expected_strategic_direction in message


def test_criminal_advocacy_eval_harness_generates_extractable_pdf() -> None:
    case = iter_cases()[0]
    pdf_bytes = build_case_pdf_bytes(case)

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)

    assert case.title in text
    assert case.raw_case_text.split(".")[0] in text
