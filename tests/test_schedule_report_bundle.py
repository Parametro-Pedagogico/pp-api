"""Schedule report bundle: enrolled students without assessment results."""

import uuid

import pytest

from app.v1 import report_bundle


@pytest.mark.asyncio
async def test_schedule_report_includes_students_without_results(monkeypatch):
    schedule_id = uuid.uuid4()
    academic_year_id = uuid.uuid4()
    classroom_id = uuid.uuid4()
    assessment_id = uuid.uuid4()
    student_with_result = uuid.uuid4()
    student_without_result = uuid.uuid4()
    result_id = uuid.uuid4()

    async def fake_fetch_one(_db, sql, _params):
        if "FROM assessment_attendance_list" in sql and "SELECT 1" in sql:
            return None
        if "FROM assessment_schedules" in sql:
            return {
                "id": str(schedule_id),
                "classroom_id": str(classroom_id),
                "assessment_id": str(assessment_id),
                "assessment_title": "Prova 1",
                "assessment_type": "regular",
                "assessment_description": None,
                "classroom_name": "Turma A",
                "classroom_code": "TA",
                "school_name": "Escola X",
            }
        return None

    fetch_all_calls: list[tuple[str, dict]] = []

    async def fake_fetch_all(_db, sql, params):
        fetch_all_calls.append((sql, params))
        if "classroom_students" in sql:
            return [
                {
                    "result_id": result_id,
                    "student_id": student_with_result,
                    "schedule_id": str(schedule_id),
                    "assessment_id": str(assessment_id),
                    "classroom_id": str(classroom_id),
                    "started_at": "2026-01-01T10:00:00",
                    "submitted_at": "2026-01-01T11:00:00",
                    "score": 8.5,
                    "feedback": None,
                    "status": "submitted",
                    "student_full_name": "Aluno Com Resultado",
                    "student_email": "com@example.com",
                },
                {
                    "result_id": None,
                    "student_id": student_without_result,
                    "schedule_id": None,
                    "assessment_id": None,
                    "classroom_id": None,
                    "started_at": None,
                    "submitted_at": None,
                    "score": None,
                    "feedback": None,
                    "status": "pending",
                    "student_full_name": "Aluno Sem Resultado",
                    "student_email": "sem@example.com",
                },
            ]
        return []

    monkeypatch.setattr(report_bundle, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(report_bundle, "fetch_all", fake_fetch_all)

    out = await report_bundle.assessment_schedule_report_bundle(
        db=object(),  # type: ignore[arg-type]
        schedule_id=schedule_id,
        academic_year_id=academic_year_id,
    )

    assert len(fetch_all_calls) == 1
    _sql, params = fetch_all_calls[0]
    assert "classroom_students" in _sql
    assert "LEFT JOIN assessment_results" in _sql
    assert params["sid"] == str(schedule_id)
    assert params["aid"] == str(assessment_id)
    assert params["cid"] == str(classroom_id)

    assert out["statistics"]["total_students"] == 2
    assert out["statistics"]["completed_count"] == 1
    assert out["statistics"]["student_scope"] == "enrollment"
    assert len(out["results"]) == 2

    pending = next(r for r in out["results"] if r["student_id"] == student_without_result)
    assert pending["id"] == student_without_result
    assert pending["status"] == "pending"
    assert pending["score"] is None
    assert pending["profiles"]["full_name"] == "Aluno Sem Resultado"
    assert pending["profiles"]["email"] == "sem@example.com"

    done = next(r for r in out["results"] if r["student_id"] == student_with_result)
    assert done["id"] == result_id
    assert done["status"] == "submitted"
    assert done["score"] == 8.5


@pytest.mark.asyncio
async def test_schedule_report_uses_attendance_when_list_exists(monkeypatch):
    schedule_id = uuid.uuid4()
    academic_year_id = uuid.uuid4()
    classroom_id = uuid.uuid4()
    assessment_id = uuid.uuid4()
    student_present = uuid.uuid4()

    async def fake_fetch_one(_db, sql, _params):
        if "FROM assessment_attendance_list" in sql and "SELECT 1" in sql:
            return {"ok": 1}
        if "FROM assessment_schedules" in sql:
            return {
                "id": str(schedule_id),
                "classroom_id": str(classroom_id),
                "assessment_id": str(assessment_id),
                "assessment_title": "Prova 1",
                "assessment_type": "regular",
                "assessment_description": None,
                "classroom_name": "Turma A",
                "classroom_code": "TA",
                "school_name": "Escola X",
            }
        return None

    fetch_all_calls: list[tuple[str, dict]] = []

    async def fake_fetch_all(_db, sql, params):
        fetch_all_calls.append((sql, params))
        if "FROM assessment_attendance_list aal" in sql:
            return [
                {
                    "result_id": None,
                    "student_id": student_present,
                    "schedule_id": None,
                    "assessment_id": None,
                    "classroom_id": None,
                    "started_at": None,
                    "submitted_at": None,
                    "score": None,
                    "feedback": None,
                    "status": "pending",
                    "student_full_name": "Presente",
                    "student_email": "presente@example.com",
                }
            ]
        return []

    monkeypatch.setattr(report_bundle, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(report_bundle, "fetch_all", fake_fetch_all)

    out = await report_bundle.assessment_schedule_report_bundle(
        db=object(),  # type: ignore[arg-type]
        schedule_id=schedule_id,
        academic_year_id=academic_year_id,
    )

    assert len(fetch_all_calls) == 1
    _sql, _params = fetch_all_calls[0]
    assert "assessment_attendance_list" in _sql
    assert "status IS DISTINCT FROM 'out'" in _sql
    assert out["statistics"]["student_scope"] == "attendance"
    assert out["statistics"]["total_students"] == 1
    assert out["results"][0]["student_id"] == student_present
