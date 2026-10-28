"""Shape de replicação dos dados mestres (lógica pura, sem banco)."""

import uuid

import pytest

from app.events import master_data as md
from app.events import replication as repl
from app.events.master_data import CLASSROOM_FIELDS, SCHOOL_FIELDS, _shape


def test_school_shape_selects_fields_and_coerces_uuid():
    sid = uuid.uuid4()
    pid = uuid.uuid4()
    row = {
        "id": sid,
        "version": 3,
        "name": "Escola X",
        "code": "X1",
        "city": "C",
        "state": "ST",
        "parent": pid,
        "type": "school",
        "network_user_management_enabled": True,
        "created_at": "2026-10-23",  # fora do shape: não deve viajar
    }
    shaped = _shape(row, SCHOOL_FIELDS)
    assert shaped["id"] == str(sid)  # UUID vira str
    assert shaped["parent"] == str(pid)
    assert shaped["version"] == 3
    assert "created_at" not in shaped  # só os campos declarados


def test_classroom_shape_ignores_missing_fields():
    row = {"id": uuid.uuid4(), "version": 1, "name": "5A"}  # sem grade_id etc.
    shaped = _shape(row, CLASSROOM_FIELDS)
    assert set(shaped) == {"id", "version", "name"}
    assert isinstance(shaped["id"], str)


@pytest.mark.asyncio
async def test_tombstone_bumps_version_and_flags_deleted(monkeypatch):
    captured = {}

    async def fake_enqueue(db, topic, envelope):
        captured["topic"] = topic
        captured["env"] = envelope

    monkeypatch.setattr(repl, "enqueue", fake_enqueue)
    await md.replicate_deletion(
        db=None, collection="escolas", record_id="e1", last_version=5
    )

    env = captured["env"]
    assert env.event_type == "replicacao.escolas"
    assert env.idempotency_key == "escolas:e1:v6"  # última versão + 1
    assert env.data["deleted"] is True
    assert env.data["version"] == 6
