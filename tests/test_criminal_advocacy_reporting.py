from __future__ import annotations

from src.evaluation.criminal_advocacy_reporting import render_markdown_report


def test_criminal_advocacy_reporting_renders_summary_and_weakest_cases() -> None:
    report = {
        "dataset_id": "criminal-advocacy-stage2-v1",
        "evaluated_cases": 2,
        "piece_types": ["habeas_corpus", "resposta_a_acusacao"],
        "summary": {
            "completed_cases": 2,
            "completion_rate": 1.0,
            "classification_match_rate": 0.5,
            "piece_type_hint_rate": 0.5,
            "average_overall_score": 0.412,
            "average_strategy_coverage": 0.2,
            "average_tactical_coverage": 0.3,
            "average_proof_gap_coverage": 0.1,
            "average_risk_coverage": 0.15,
            "by_piece_type": {
                "habeas_corpus": {
                    "cases": 1,
                    "completion_rate": 1.0,
                    "average_overall_score": 0.33,
                },
                "resposta_a_acusacao": {
                    "cases": 1,
                    "completion_rate": 1.0,
                    "average_overall_score": 0.494,
                },
            },
        },
        "cases": [
            {
                "case_id": "hc_001",
                "target_piece_type": "habeas_corpus",
                "status": "completed",
                "classification": "Cível",
                "scores": {
                    "overall_score": 0.33,
                    "completed": True,
                    "classification_match": False,
                    "expected_runtime_classification": "Penal",
                    "piece_type_hint_present": False,
                    "strategy_coverage": {"score": 0.0, "missing": ["liminar", "fundamentacao"]},
                    "tactical_priorities_coverage": {"score": 0.25, "missing": ["urgencia"]},
                    "proof_gaps_coverage": {"score": 0.0, "missing": ["concreta"]},
                    "risks_coverage": {"score": 0.0, "missing": ["supressao"]},
                    "missing_required_events": ["TASK_COMPLETED"],
                },
            },
            {
                "case_id": "raa_001",
                "target_piece_type": "resposta_a_acusacao",
                "status": "completed",
                "classification": "Penal",
                "scores": {
                    "overall_score": 0.494,
                    "completed": True,
                    "classification_match": True,
                    "expected_runtime_classification": "Penal",
                    "piece_type_hint_present": True,
                    "strategy_coverage": {"score": 0.4, "missing": ["corroboração"]},
                    "tactical_priorities_coverage": {"score": 0.35, "missing": ["alibi"]},
                    "proof_gaps_coverage": {"score": 0.2, "missing": ["imagens"]},
                    "risks_coverage": {"score": 0.3, "missing": ["juizo"]},
                    "missing_required_events": [],
                },
            },
        ],
    }

    markdown = render_markdown_report(report)

    assert "# Criminal Advocacy Evaluation Report" in markdown
    assert "## Summary" in markdown
    assert "## Recommended Actions" in markdown
    assert "## Weakest Cases" in markdown
    assert "`hc_001`" in markdown
    assert "Review document classification prompts" in markdown
