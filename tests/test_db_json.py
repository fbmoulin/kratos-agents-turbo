from __future__ import annotations

import json
import uuid

from src import db


def test_db_json_serializes_uuid_values():
    payload = {"batch_id": uuid.uuid4(), "task_id": uuid.uuid4()}
    adapter = db._json(payload)
    serialized = adapter.dumps(payload)

    decoded = json.loads(serialized)
    assert decoded["batch_id"] == str(payload["batch_id"])
    assert decoded["task_id"] == str(payload["task_id"])
