from __future__ import annotations

import json
from pathlib import Path

DATASET_ROOT = (
    Path(__file__).resolve().parents[1] / "datasets" / "criminal_advocacy_stage2"
)
MANIFEST_PATH = DATASET_ROOT / "manifest.json"
REQUIRED_PIECE_TYPES = {
    "resposta_a_acusacao",
    "revogacao_prisao_preventiva",
    "habeas_corpus",
    "alegacoes_finais",
}
REQUIRED_NOTE_KEYS = {"risks", "proof_gaps", "tactical_priorities"}
REQUIRED_PIPELINE_KEYS = {"detector", "firac", "validator"}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_criminal_advocacy_dataset_manifest_and_cases_are_consistent() -> None:
    assert DATASET_ROOT.exists()
    manifest = load_json(MANIFEST_PATH)

    assert set(manifest["piece_types"]) == REQUIRED_PIECE_TYPES
    assert manifest["case_count"] == 10
    assert len(manifest["cases"]) == 10

    seen_ids: set[str] = set()
    seen_piece_types: set[str] = set()

    for entry in manifest["cases"]:
        case_path = DATASET_ROOT / entry["path"]
        assert case_path.exists(), entry["path"]

        payload = load_json(case_path)
        assert payload["case_id"] == entry["case_id"]
        assert payload["target_piece_type"] == entry["target_piece_type"]
        assert payload["case_id"] not in seen_ids
        seen_ids.add(payload["case_id"])
        seen_piece_types.add(payload["target_piece_type"])

        assert isinstance(payload["raw_case_text"], str) and payload["raw_case_text"].strip()
        if "raw_case_context" in payload:
            assert isinstance(payload["raw_case_context"], str)
            assert payload["raw_case_context"].strip()
        assert (
            isinstance(payload["expected_strategic_direction"], str)
            and payload["expected_strategic_direction"].strip()
        )

        notes = payload["notes"]
        assert set(notes) == REQUIRED_NOTE_KEYS
        for key in REQUIRED_NOTE_KEYS:
            assert isinstance(notes[key], list) and notes[key]
            assert all(isinstance(item, str) and item.strip() for item in notes[key])

        pipeline = payload["canonical_advocacy_pipeline"]
        assert set(pipeline) == REQUIRED_PIPELINE_KEYS
        assert (
            pipeline["detector"]["expected_piece_type"] == payload["target_piece_type"]
        )

        folder_name = case_path.parent.name
        assert folder_name == payload["target_piece_type"]

    assert seen_piece_types == REQUIRED_PIECE_TYPES
