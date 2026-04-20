from __future__ import annotations

from src.evaluation.criminal_advocacy_thresholds import evaluate_report_against_thresholds


def test_criminal_advocacy_thresholds_detect_failures() -> None:
    report = {
        "dataset_id": "criminal-advocacy-stage2-v1",
        "piece_types": ["resposta_a_acusacao"],
        "summary": {
            "completion_rate": 0.5,
            "classification_match_rate": 0.5,
            "piece_type_hint_rate": 0.5,
            "average_overall_score": 0.4,
            "average_strategy_coverage": 0.2,
            "average_tactical_coverage": 0.2,
            "average_proof_gap_coverage": 0.1,
            "average_risk_coverage": 0.1,
            "by_piece_type": {
                "resposta_a_acusacao": {
                    "completion_rate": 0.5,
                    "average_overall_score": 0.4,
                }
            },
        },
    }
    thresholds = {
        "dataset_id": "criminal-advocacy-stage2-v1",
        "required_piece_types": [
            "resposta_a_acusacao",
            "revogacao_prisao_preventiva",
        ],
        "summary_minimums": {
            "completion_rate": 1.0,
            "average_overall_score": 0.75,
        },
        "per_piece_type_minimums": {
            "resposta_a_acusacao": {
                "completion_rate": 1.0,
            },
            "revogacao_prisao_preventiva": {
                "average_overall_score": 0.75,
            },
        },
    }

    result = evaluate_report_against_thresholds(report, thresholds)

    assert result["passed"] is False
    assert result["failure_count"] >= 3
    assert any("missing required piece types" in item for item in result["failures"])
    assert any("summary metric 'completion_rate'" in item for item in result["failures"])


def test_criminal_advocacy_thresholds_pass_with_matching_report() -> None:
    report = {
        "dataset_id": "criminal-advocacy-stage2-v1",
        "piece_types": [
            "resposta_a_acusacao",
            "revogacao_prisao_preventiva",
        ],
        "summary": {
            "completion_rate": 1.0,
            "classification_match_rate": 1.0,
            "piece_type_hint_rate": 1.0,
            "average_overall_score": 0.9,
            "average_strategy_coverage": 0.85,
            "average_tactical_coverage": 0.83,
            "average_proof_gap_coverage": 0.81,
            "average_risk_coverage": 0.8,
            "by_piece_type": {
                "resposta_a_acusacao": {
                    "completion_rate": 1.0,
                    "average_overall_score": 0.9,
                },
                "revogacao_prisao_preventiva": {
                    "completion_rate": 1.0,
                    "average_overall_score": 0.88,
                },
            },
        },
    }
    thresholds = {
        "dataset_id": "criminal-advocacy-stage2-v1",
        "required_piece_types": [
            "resposta_a_acusacao",
            "revogacao_prisao_preventiva",
        ],
        "summary_minimums": {
            "completion_rate": 1.0,
            "average_overall_score": 0.75,
        },
        "per_piece_type_minimums": {
            "resposta_a_acusacao": {
                "completion_rate": 1.0,
            },
            "revogacao_prisao_preventiva": {
                "average_overall_score": 0.75,
            },
        },
    }

    result = evaluate_report_against_thresholds(report, thresholds)

    assert result["passed"] is True
    assert result["failure_count"] == 0
