"""Cadernos de plataforma (school_id opcional)."""

from uuid import uuid4

import pytest

from app.v1 import assessments_router as router


def _ctx_admin():
    from app.core.deps import AuthContext

    return AuthContext(
        session_id=uuid4(),
        person_id=uuid4(),
        active_profile_id=uuid4(),
        role="platform_admin",
        school_id=None,
    )


@pytest.mark.asyncio
async def test_assessment_covers_classroom_when_primary_school_null(monkeypatch):
    assessment_id = uuid4()
    classroom_school_id = uuid4()

    async def fake_fetch_one(_db, sql, params):
        if "FROM assessment_school" in sql:
            return {"ok": 1}
        return None

    monkeypatch.setattr(router, "fetch_one", fake_fetch_one)

    ok = await router._assessment_covers_classroom_school(
        object(),
        assessment_id=assessment_id,
        assessment_primary_school_id=None,
        classroom_school_id=classroom_school_id,
    )
    assert ok is True


@pytest.mark.asyncio
async def test_create_platform_assessment_without_school(monkeypatch):
    created_id = uuid4()

    async def fake_scope(_db, _ctx):
        return {"is_admin_like": True, "effective_school_ids": None}

    async def fake_fetch_one(_db, sql, params):
        if "INSERT INTO assessments" in sql:
            return {
                "id": str(created_id),
                "school_id": None,
                "title": params["title"],
            }
        return None

    async def fake_commit():
        return None

    monkeypatch.setattr(router, "get_effective_school_scope", fake_scope)
    monkeypatch.setattr(router, "fetch_one", fake_fetch_one)

    class FakeDb:
        async def commit(self):
            await fake_commit()

    body = router.AssessmentCreate(
        title="Caderno plataforma",
        created_by=uuid4(),
    )
    row = await router.create_assessment_v1(body, _ctx_admin(), FakeDb())  # type: ignore[arg-type]
    assert row["school_id"] is None
    assert row["title"] == "Caderno plataforma"


@pytest.mark.asyncio
async def test_add_assessment_question_items_idempotent(monkeypatch):
    assessment_id = uuid4()
    question_id = uuid4()
    calls: list[str] = []

    async def fake_get_assessment(*_args, **_kwargs):
        return {"id": str(assessment_id), "title": "Caderno"}

    async def fake_fetch_one(_db, sql, params):
        if "MAX(order_index)" in sql:
            return {"max_order": 2}
        if "FROM questions_assessments" in sql and "question_id" in sql:
            if params.get("qid") == str(question_id):
                return None
            return None
        if "FROM question_item" in sql:
            return {"id": str(question_id)}
        if "INSERT INTO questions_assessments" in sql:
            calls.append("insert")
            return {"id": str(uuid4())}
        return None

    async def fake_commit():
        return None

    monkeypatch.setattr(router, "get_assessment_v1", fake_get_assessment)
    monkeypatch.setattr(router, "fetch_one", fake_fetch_one)

    class FakeDb:
        async def commit(self):
            await fake_commit()

    body = router.AssessmentQuestionItemsAdd(question_ids=[question_id])
    result = await router.add_assessment_question_items_v1(
        assessment_id,
        body,
        _ctx_admin(),
        FakeDb(),  # type: ignore[arg-type]
    )
    assert result["added_count"] == 1
    assert str(question_id) in result["added"]
    assert calls == ["insert"]


@pytest.mark.asyncio
async def test_reorder_assessment_question_items(monkeypatch):
    assessment_id = uuid4()
    q1 = uuid4()
    q2 = uuid4()
    updates: list[tuple[int, str]] = []

    async def fake_get_assessment(*_args, **_kwargs):
        return {"id": str(assessment_id)}

    async def fake_fetch_all(_db, sql, params):
        if "question_id::text" in sql:
            return [{"question_id": str(q1)}, {"question_id": str(q2)}]
        return []

    async def fake_execute(_db, sql, params):
        if "UPDATE questions_assessments" in sql:
            updates.append((params["ord"], params["qid"]))
        return None

    async def fake_commit():
        return None

    monkeypatch.setattr(router, "get_assessment_v1", fake_get_assessment)
    monkeypatch.setattr(router, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(router, "execute", fake_execute)

    class FakeDb:
        async def commit(self):
            await fake_commit()

    body = router.AssessmentQuestionItemsOrder(question_ids=[q2, q1])
    result = await router.reorder_assessment_question_items_v1(
        assessment_id,
        body,
        _ctx_admin(),
        FakeDb(),  # type: ignore[arg-type]
    )
    assert result["ok"] is True
    assert updates == [(1, str(q2)), (2, str(q1))]
