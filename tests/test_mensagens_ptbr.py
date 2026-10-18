"""Mensagens de erro da API em português, com `type` estável para o frontend."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_sem_login_retorna_mensagem_em_portugues():
    r = client.get("/v1/me")
    assert r.status_code == 401
    erro = r.json()["error"]
    assert erro["type"] == "http_error"
    assert erro["message"] == "Você precisa entrar para continuar."


def test_token_invalido_pede_novo_login():
    r = client.get("/v1/me", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Sessão inválida. Entre novamente."


def test_validacao_lista_campos_em_portugues():
    r = client.post("/v1/auth/select-profile", json={})
    assert r.status_code == 422
    erro = r.json()["error"]
    assert erro["type"] == "validation_error"
    assert erro["message"].startswith("Alguns dados estão incompletos ou inválidos.")
    assert "profile_id" in erro["fields"]
