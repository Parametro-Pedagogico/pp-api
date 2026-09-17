import uuid

import pytest

from app.v1 import exam_report_router
from app.core.deps import AuthContext


def _ctx(role: str = "platform_admin") -> AuthContext:
    return AuthContext(
        session_id=uuid.uuid4(),
        person_id=uuid.uuid4(),
        active_profile_id=uuid.uuid4(),
        role=role,
        school_id=None,
    )


@pytest.mark.asyncio
async def test_admin_dashboard_cockpit_platform_admin(monkeypatch):
    ay = uuid.uuid4()

    async def fake_resolve(_db, _ay):
        return ay

    async def fake_school_ids(_db, _ctx, _school_id):
        return None

    async def fake_fetch_one(_db, sql, params=None):
        if "FROM question_item" in sql:
            return {"n": 42}
        if "assessment_response_import_batch" in sql and "FILTER" in sql:
            return {"failed": 2, "pending": 3}
        if "assessment_schedules" in sql and "COUNT" in sql:
            return {"n": 5}
        return {}

    async def fake_fetch_all(_db, sql, params=None):
        if "assessment_response_import_batch" in sql and "import_failed" in sql:
            return [
                {
                    "id": uuid.uuid4(),
                    "original_filename": "lote.csv",
                    "status": "import_failed",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        if "assessment_response_import_batch" in sql:
            return []
        if "assessment_schedules" in sql:
            return [
                {
                    "id": uuid.uuid4(),
                    "start_time": "2026-01-02T10:00:00+00:00",
                    "end_time": "2026-01-02T12:00:00+00:00",
                    "macro_assessment_id": uuid.uuid4(),
                    "assessment_title": "Caderno 1",
                    "classroom_name": "9A",
                }
            ]
        return []

    monkeypatch.setattr(exam_report_router, "resolve_academic_year_id", fake_resolve)
    monkeypatch.setattr(exam_report_router, "resolve_admin_dashboard_school_ids", fake_school_ids)
    monkeypatch.setattr(exam_report_router, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(exam_report_router, "fetch_all", fake_fetch_all)

    out = await exam_report_router.admin_dashboard_cockpit_v1(
        ctx=_ctx("platform_admin"),
        db=object(),  # type: ignore[arg-type]
        academic_year_id=None,
        school_id=None,
    )
    assert out["question_bank_total"] == 42
    assert out["imports_failed"] == 2
    assert out["imports_pending"] == 3
    assert out["upcoming_schedules"] == 5
    assert len(out["import_exceptions"]) == 1
    assert len(out["schedule_exceptions"]) == 1
