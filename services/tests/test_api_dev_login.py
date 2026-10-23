"""Developer login: dev tokens next to Cognito only when RF_DEV_LOGIN is on (local)."""

import pytest
from conftest import EMP


@pytest.fixture
def cognito_mode(monkeypatch):
    from receiptflow_common import aws

    monkeypatch.setenv("RF_AUTH_MODE", "cognito")
    monkeypatch.setenv("RF_COGNITO_POOL_ID", "ap-northeast-2_test")
    monkeypatch.setenv("RF_COGNITO_CLIENT_ID", "test")
    aws.reset()
    return monkeypatch


def test_off_by_default(api, cognito_mode):
    assert api.get("/api/me", headers=EMP).status_code == 401
    assert api.get("/api/dev/profiles").status_code == 404


def test_on_locally(api, cognito_mode):
    from receiptflow_common import aws

    cognito_mode.setenv("RF_DEV_LOGIN", "true")
    aws.reset()
    profiles = api.get("/api/dev/profiles").json()["items"]
    assert len(profiles) == 10
    assert sorted({p["role"] for p in profiles}) == ["admin", "employee", "reviewer"]
    me = api.get("/api/me", headers=EMP).json()
    assert me["name"] == "김민준" and me["employee_no"] == "SAL2026901"
    assert api.get("/api/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
