"""HTTP로 띄운 서버 (main_http와 같은 설정)."""

import sqlite3

import pytest
from starlette.testclient import TestClient

from cholog_mcp import http_app
from cholog_mcp.config import ALLOWED_HOSTS_ENV, DB_PATH_ENV
from pipeline.schema import create_schema

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def client(base_url: str = "http://localhost:8080") -> TestClient:
    return TestClient(http_app(), base_url=base_url)


def rpc(method: str, params: dict | None = None) -> dict:
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}


@pytest.fixture
def db_file(tmp_path, monkeypatch):
    path = tmp_path / "cholog.db"
    conn = sqlite3.connect(path)
    create_schema(conn)
    conn.execute("INSERT INTO missions VALUES ('java-racingcar', 'owner/repo', '미션', '2026-03-03T09:00:00+09:00')")
    conn.commit()
    conn.close()
    monkeypatch.setenv(DB_PATH_ENV, str(path))
    return path


def test_연결_절차_없이_바로_도구_목록을_받는다():
    with client() as c:
        response = c.post("/mcp", headers=HEADERS, json=rpc("tools/list"))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    (tool,) = response.json()["result"]["tools"]
    assert tool["name"] == "get_repeated_feedback"


def test_도구를_부르면_결과를_JSON_한_덩어리로_돌려준다(db_file):
    arguments = {"mission": "java-racingcar", "since": "2026-01-01"}

    with client() as c:
        response = c.post("/mcp", headers=HEADERS, json=rpc("tools/call", {"name": "get_repeated_feedback", "arguments": arguments}))

    assert response.status_code == 200
    assert "2026-03-03T09:00:00+09:00" in response.text


def test_옛_방식의_연결_요청도_받고_세션을_만들지_않는다():
    params = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}

    with client() as c:
        response = c.post("/mcp", headers=HEADERS, json=rpc("initialize", params))

    assert response.status_code == 200
    assert "mcp-session-id" not in response.headers


def test_Origin이_붙은_브라우저_요청은_거절한다():
    with client() as c:
        response = c.post("/mcp", headers={**HEADERS, "Origin": "https://evil.example"}, json=rpc("tools/list"))

    assert response.status_code == 403


def test_허용하지_않은_Host로_온_요청은_거절한다():
    with client(base_url="http://evil.example") as c:
        response = c.post("/mcp", headers=HEADERS, json=rpc("tools/list"))

    assert response.status_code == 421


def test_환경_변수로_허용할_Host를_바꾼다(monkeypatch):
    monkeypatch.setenv(ALLOWED_HOSTS_ENV, "abc.lambda-url.ap-northeast-2.on.aws, other.example")

    with client(base_url="https://abc.lambda-url.ap-northeast-2.on.aws") as c:
        allowed = c.post("/mcp", headers=HEADERS, json=rpc("tools/list"))
    with client() as c:
        local = c.post("/mcp", headers=HEADERS, json=rpc("tools/list"))

    assert allowed.status_code == 200
    assert local.status_code == 421


def test_POST가_아닌_요청은_스트림을_열지_않고_거절한다():
    with client() as c:
        response = c.get("/mcp", headers={"Accept": "text/event-stream"})

    assert response.status_code == 405
    assert response.headers["allow"] == "POST"
