import uuid

import pytest
from starlette.responses import Response

from app.v1 import directory_router
from app.v1 import user_import_jobs


class DummyBackgroundTasks:
    def add_task(self, *_args, **_kwargs):
        return None


def _import_call_kwargs():
    return {
        "background_tasks": DummyBackgroundTasks(),  # type: ignore[arg-type]
        "response": Response(),
    }


@pytest.mark.asyncio
async def test_create_user_with_profile_happy_path(monkeypatch):
    calls = {"n": 0, "profile_code": None, "auth_provider": None, "can_login": None}

    async def fake_fetch_one(_db, sql, params):
        if "RETURNING id" in sql and "INSERT INTO people" in sql:
            calls["auth_provider"] = params.get("auth_provider")
            calls["can_login"] = params.get("can_login")
            return {"id": "p1"}
        if "INSERT INTO profiles" in sql:
            calls["profile_code"] = params.get("code")
            return {"id": "pr1"}
        if "FROM vw_profiles" in sql:
            return {"id": "pr1", "role": "student", "person_id": "p1", "school_id": None, "code": "RA123"}
        return {"ok": True}

    async def fake_execute(_db, _sql, _params):
        calls["n"] += 1

    monkeypatch.setattr(directory_router, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(directory_router, "execute", fake_execute)

    class DummyDB:
        async def commit(self):
            return None

    body = directory_router.UserCreateBody(
        full_name="A",
        email="a@a.com",
        role="student",
        code="RA123",
        create_firebase_user=False,
    )
    out = await directory_router._create_user_with_profile(DummyDB(), body=body)
    assert out["id"] == "pr1"
    assert calls["n"] == 0
    assert calls["profile_code"] == "RA123"
    assert calls["auth_provider"] == "database"
    assert calls["can_login"] is False


@pytest.mark.asyncio
async def test_users_import_collects_errors(monkeypatch):
    async def fake_create(_db, body):
        if body.email == "bad@example.com":
            raise RuntimeError("boom")
        return {"id": str(uuid.uuid4()), "email": body.email}

    monkeypatch.setattr(directory_router, "_create_user_with_profile", fake_create)
    async def fake_execute(_db, _sql, _params):
        return None

    async def fake_fetch_one(_db, _sql, _params):
        return None

    monkeypatch.setattr(directory_router, "execute", fake_execute)
    monkeypatch.setattr(directory_router, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(user_import_jobs, "fetch_one", fake_fetch_one)
    async def fake_ensure(_db):
        return None

    monkeypatch.setattr(directory_router, "ensure_import_jobs_table", fake_ensure)
    ctx = directory_router.AuthContext(  # type: ignore[attr-defined]
        session_id=uuid.uuid4(),
        person_id=uuid.uuid4(),
        active_profile_id=uuid.uuid4(),
        role="admin",
        school_id=None,
    )
    users = [
        directory_router.UserCreateBody(full_name="a", email="ok@example.com", role="teacher", create_firebase_user=False),
        directory_router.UserCreateBody(full_name="b", email="bad@example.com", role="teacher", create_firebase_user=False),
    ]
    class DummyDB:
        async def commit(self):
            return None

        async def rollback(self):
            return None

    payload = directory_router.ImportUsersRequest(users=users, continue_on_error=True)
    out = await directory_router.import_users_v1(
        payload=payload,
        ctx=ctx,
        db=DummyDB(),  # type: ignore[arg-type]
        **_import_call_kwargs(),
    )
    assert len(out["created"]) == 1
    assert len(out["errors"]) == 1


@pytest.mark.asyncio
async def test_dict_csv_row_to_user_create_respects_default_firebase_flag():
    row = {
        "full_name": "Aluno",
        "email": "aluno@example.com",
        "role": "STUDENT",
        "school_id": str(uuid.uuid4()),
    }
    body = directory_router._dict_csv_row_to_user_create(row, default_create_firebase_user=False)
    assert body.create_firebase_user is False

    row["create_firebase_user"] = "true"
    body_override = directory_router._dict_csv_row_to_user_create(
        row,
        default_create_firebase_user=False,
    )
    assert body_override.create_firebase_user is True


@pytest.mark.asyncio
async def test_users_import_accepts_csv_rows(monkeypatch):
    async def fake_create(_db, body):
        return {"id": str(uuid.uuid4()), "email": body.email}

    monkeypatch.setattr(directory_router, "_create_user_with_profile", fake_create)

    async def fake_link(*_a, **_k):
        return None

    monkeypatch.setattr(directory_router, "_link_import_profile_to_classroom", fake_link)

    async def fake_execute(_db, _sql, _params):
        return None

    async def fake_fetch_one(_db, _sql, _params):
        if "FROM app_import_jobs" in _sql or "app_import_jobs" in _sql:
            return None
        if "people WHERE lower(email)" in _sql:
            return None
        return None

    monkeypatch.setattr(directory_router, "execute", fake_execute)
    monkeypatch.setattr(directory_router, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(user_import_jobs, "fetch_one", fake_fetch_one)
    async def fake_ensure(_db):
        return None

    monkeypatch.setattr(directory_router, "ensure_import_jobs_table", fake_ensure)
    ctx = directory_router.AuthContext(  # type: ignore[attr-defined]
        session_id=uuid.uuid4(),
        person_id=uuid.uuid4(),
        active_profile_id=uuid.uuid4(),
        role="platform_admin",
        school_id=None,
    )

    class DummyDB:
        async def commit(self):
            return None

        async def rollback(self):
            return None

    sid = str(uuid.uuid4())
    cid = str(uuid.uuid4())
    payload = directory_router.ImportUsersRequest(
        rows=[
            {
                "full_name": "Aluno CSV",
                "email": "csv.student@example.com",
                "role": "STUDENT",
                "school_id": sid,
                "classroom_id": cid,
            }
        ],
        continue_on_error=True,
    )
    out = await directory_router.import_users_v1(
        payload=payload,
        ctx=ctx,
        db=DummyDB(),  # type: ignore[arg-type]
        **_import_call_kwargs(),
    )
    assert out["ok"] is True
    assert out["summary"]["received"] == 1
    assert len(out["created"]) == 1
    assert out["created"][0].get("classroom_linked") is True


@pytest.mark.asyncio
async def test_resolve_or_create_firebase_user_links_existing(monkeypatch):
    class FakeUser:
        uid = "firebase-123"
        display_name = "Old Name"

    def fake_get_user_by_email(email):
        assert email == "a@a.com"
        return FakeUser()

    def fake_update_user(uid, **kwargs):
        assert uid == "firebase-123"
        assert kwargs["display_name"] == "New Name"

    monkeypatch.setattr(directory_router, "ensure_firebase_initialized", lambda: None)
    monkeypatch.setattr(directory_router.firebase_auth, "get_user_by_email", fake_get_user_by_email)
    monkeypatch.setattr(directory_router.firebase_auth, "update_user", fake_update_user)

    uid, mode = directory_router._resolve_or_create_firebase_user(
        email="a@a.com",
        full_name="New Name",
    )
    assert uid == "firebase-123"
    assert mode == "linked"


@pytest.mark.asyncio
async def test_sync_user_firebase_links_existing(monkeypatch):
    calls = {"persist": False}

    async def fake_fetch_one(_db, sql, params):
        if "FROM vw_profiles" in sql:
            return {
                "id": params["id"],
                "person_id": "p1",
                "email": "a@a.com",
                "full_name": "Aluno",
                "firebase_uid": None,
            }
        return None

    async def fake_execute(_db, _sql, _params):
        return None

    async def fake_persist(_db, *, person_id, firebase_uid):
        calls["persist"] = True
        assert person_id == "p1"
        assert firebase_uid == "firebase-123"

    monkeypatch.setattr(directory_router, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(directory_router, "execute", fake_execute)
    monkeypatch.setattr(directory_router, "_persist_person_firebase_link", fake_persist)
    monkeypatch.setattr(
        directory_router,
        "_resolve_or_create_firebase_user",
        lambda **_: ("firebase-123", "linked"),
    )

    class DummyDB:
        async def commit(self):
            return None

    ctx = directory_router.AuthContext(  # type: ignore[attr-defined]
        session_id=uuid.uuid4(),
        person_id=uuid.uuid4(),
        active_profile_id=uuid.uuid4(),
        role="platform_admin",
        school_id=None,
    )
    out = await directory_router.sync_user_firebase_v1(
        user_id=uuid.uuid4(),
        body=directory_router.FirebaseSyncBody(),
        ctx=ctx,
        db=DummyDB(),  # type: ignore[arg-type]
    )
    assert out["mode"] == "linked"
    assert out["firebase_uid"] == "firebase-123"
    assert calls["persist"] is True


@pytest.mark.asyncio
async def test_sync_user_firebase_already_synced(monkeypatch):
    async def fake_fetch_one(_db, _sql, _params):
        return {
            "id": "pr1",
            "person_id": "p1",
            "email": "a@a.com",
            "full_name": "Aluno",
            "firebase_uid": "existing-uid",
        }

    monkeypatch.setattr(directory_router, "fetch_one", fake_fetch_one)

    class DummyDB:
        async def commit(self):
            return None

    ctx = directory_router.AuthContext(  # type: ignore[attr-defined]
        session_id=uuid.uuid4(),
        person_id=uuid.uuid4(),
        active_profile_id=uuid.uuid4(),
        role="platform_admin",
        school_id=None,
    )
    out = await directory_router.sync_user_firebase_v1(
        user_id=uuid.uuid4(),
        body=directory_router.FirebaseSyncBody(),
        ctx=ctx,
        db=DummyDB(),  # type: ignore[arg-type]
    )
    assert out["mode"] == "already_synced"
    assert out["firebase_uid"] == "existing-uid"
