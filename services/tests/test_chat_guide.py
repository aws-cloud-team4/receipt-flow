"""Public guide chat on the landing page (chat_service.guide): docs search, masking, limits (mock model)."""

import json

import pytest
from chat_service import guide, guide_docs
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    guide._recent.clear()
    return TestClient(guide.app)


def _events(resp) -> list[tuple[str, dict]]:
    out = []
    for block in resp.text.strip().split("\n\n"):
        head, data = block.split("\n", 1)
        out.append((head.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def test_answers_from_the_docs_without_login(client):
    resp = client.post("/guide/ask", json={"question": "정확도는 얼마나 돼요?"})
    assert resp.status_code == 200
    events = _events(resp)
    assert events[0][0] == "delta" and events[-1][0] == "done"
    done = events[-1][1]
    assert any(s["file"] == "docs/model-eval.md" for s in done["sources"])
    assert "시험 모드" in done["text"]


def test_documents_are_masked():
    sections, _ = guide_docs.index()
    text = "\n".join(s.text for s in sections)
    assert sections and "[계정]" in text
    for secret in ("431777499129", "arn:aws:", "@dev.com", "user/junyoung"):
        assert secret not in text


def test_every_document_goes_with_every_question():
    docs, _ = guide._documents("전체 api 알려주세요")
    assert docs.count("=== 파일:") >= 12
    for part in (
        "=== 파일: docs/contract.md ===",
        "## HTTP API",
        "## DynamoDB",
        "=== 파일: deploy/README.md ===",
    ):
        assert part in docs
    assert "431777499129" not in docs and "arn:aws:" not in docs


def test_question_and_history_are_bounded(client):
    assert client.post("/guide/ask", json={"question": "  "}).status_code == 400
    assert client.post("/guide/ask", json={"question": "가" * 301}).status_code == 400
    history = [{"role": "user", "text": "a"}] * 7
    assert client.post("/guide/ask", json={"question": "안녕", "history": history}).status_code == 400


def test_per_minute_and_daily_limits(client, monkeypatch):
    monkeypatch.setattr(guide, "PER_MINUTE", 2)
    ip = {"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}
    assert client.post("/guide/ask", json={"question": "검수는?"}, headers=ip).status_code == 200
    assert client.post("/guide/ask", json={"question": "검수는?"}, headers=ip).status_code == 200
    third = client.post("/guide/ask", json={"question": "검수는?"}, headers=ip)
    assert third.status_code == 429 and third.json()["error"]["code"] == "too_many_questions"
    # another visitor is not affected; the shared daily cap stops everyone
    other = {"X-Forwarded-For": "198.51.100.9"}
    assert client.post("/guide/ask", json={"question": "검수는?"}, headers=other).status_code == 200
    monkeypatch.setattr(guide, "DAY_LIMIT", 3)
    capped = client.post("/guide/ask", json={"question": "검수는?"}, headers={"X-Forwarded-For": "192.0.2.1"})
    assert capped.status_code == 429 and capped.json()["error"]["code"] == "service_limit"
