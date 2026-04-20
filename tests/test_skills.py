from __future__ import annotations

from src.evaluation.criminal_advocacy_dataset import iter_cases
from src.skills import classify_document


def test_classify_document_detects_penal_stage2_case() -> None:
    case = next(
        item
        for item in iter_cases()
        if item.case_id == "rpp_002_trafico_mae_responsavel_pequena_quantidade"
    )

    assert classify_document(case.raw_case_text) == "Penal"


def test_classify_document_detects_health_keyword() -> None:
    text = "Pedido para fornecimento de medicamento e cobertura por plano de saúde."

    assert classify_document(text) == "Saúde"


def test_classify_document_defaults_to_civel() -> None:
    text = "Ação de cobrança fundada em inadimplemento contratual."

    assert classify_document(text) == "Cível"
