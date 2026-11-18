"""MCP 서버 등록·DB 연결·실제 stdio 호출 (docs/tool-spec.md 8-4)."""

import json
import os
import sqlite3
from pathlib import Path

import anyio
import pytest
from mcp.client import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server.mcpserver.exceptions import ToolError

from cholog_mcp.config import DB_PATH_ENV
from cholog_mcp.db import open_db
from cholog_mcp.server import create_server
from pipeline.schema import create_schema


def call(arguments: dict):
    return anyio.run(create_server().call_tool, "get_repeated_feedback", arguments)


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


def test_도구_목록에_설명과_입력_스키마가_보인다():
    tool = next(t for t in anyio.run(create_server().list_tools) if t.name == "get_repeated_feedback")

    assert tool.name == "get_repeated_feedback"
    assert tool.title == "반복 지적된 리뷰 주제"
    assert "이럴 때 쓴다" in tool.description
    assert "분모는 리뷰어 코멘트가 달린 PR 수" in tool.description
    assert "overall_pr_ratio" in tool.description
    for phrase in ["[PR #번호 · 리뷰 내용 요약](url)", "댓글 ID만", "URL을 추측", "원문 URL: 전체 URL", "일반 텍스트"]:
        assert phrase in tool.description
    assert tool.input_schema["required"] == ["mission"]
    assert set(tool.input_schema["properties"]) == {"mission", "authors", "since", "max_topics", "examples_per_topic"}


def test_환경_변수로_받은_경로의_데이터를_읽는다(db_file):
    result = call({"mission": "java-racingcar", "since": "2026-01-01"})

    assert '"data_as_of": "2026-03-03T09:00:00+09:00"' in str(result)


def test_데이터_파일이_없으면_이유를_알려준다(tmp_path, monkeypatch):
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "missing.db"))

    with pytest.raises(ToolError, match="데이터 파일이 없다"):
        call({"mission": "java-racingcar"})


def test_미션의_데이터가_없으면_이유를_알려준다(db_file):
    sqlite3.connect(db_file).execute("DELETE FROM missions").connection.commit()

    with pytest.raises(ToolError, match="데이터가 없는 미션"):
        call({"mission": "java-racingcar"})


def test_지원하지_않는_미션은_받지_않는다(db_file):
    with pytest.raises(ToolError, match="java-racingcar"):
        call({"mission": "java-lotto"})


def call_context(arguments):
    return anyio.run(create_server().call_tool, "get_review_context", arguments)


def test_리뷰_문맥_도구의_설명과_스키마():
    tools = {t.name: t for t in anyio.run(create_server().list_tools)}
    tool = tools["get_review_context"]
    assert set(tool.input_schema["required"]) == {"mission", "authors"}
    assert set(tool.input_schema["properties"]) == {"mission", "authors", "since", "cursor"}
    assert tool.input_schema["properties"]["authors"]["minItems"] == 1
    assert tool.input_schema["properties"]["authors"]["maxItems"] == 100
    for phrase in ["선택 이유", "장단점", "후속 답", "해결", "조건", "빈도", "현재도", "합의", "오타", "스타일", "억지", "해석", "근거 링크", "시작할 질문", "실행 지시", "cursor", "data_as_of"]:
        assert phrase in tool.description
    for phrase in ["[PR #번호 · 리뷰 내용 요약](url)", "댓글 ID만", "URL을 추측", "원문 URL: 전체 URL", "일반 텍스트"]:
        assert phrase in tool.description


def test_새_도구가_설정한_DB의_원문을_돌려준다(context_db_file):
    result = call_context({"mission": "java-racingcar", "authors": ["learner-01"], "since": "2026-03-01"})
    assert "왜 이 선택이 나을까요?" in str(result)


@pytest.mark.parametrize("extra", [
    {"authors": []}, {"authors": [" "]}, {"authors": None},
    {"since": "2026-99-99"}, {"since": "2026-03-01T00:00:00Z"}, {"since": 0},
    {"mission": "unsupported"}, {"cursor": "bad"},
])
def test_새_도구의_입력_오류(context_db_file, extra):
    with pytest.raises(ToolError):
        call_context({"mission": "java-racingcar", "authors": ["learner-01"]} | extra)


def test_새_도구는_authors_생략을_거절한다(context_db_file):
    with pytest.raises(ToolError, match="authors"):
        call_context({"mission": "java-racingcar"})


def test_새_도구의_DB_부재와_손상을_알린다(tmp_path, monkeypatch):
    path = tmp_path / "missing.db"
    monkeypatch.setenv(DB_PATH_ENV, str(path))
    with pytest.raises(ToolError, match="데이터 파일이 없다"):
        call_context({"mission": "java-racingcar", "authors": ["learner-01"]})
    assert not path.exists()
    path.write_text("not sqlite")
    with pytest.raises(ToolError, match="DB"):
        call_context({"mission": "java-racingcar", "authors": ["learner-01"]})


def test_새_도구의_구_스키마_오류(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE comments (id INTEGER PRIMARY KEY)")
    monkeypatch.setenv(DB_PATH_ENV, str(path))
    before = path.read_bytes()
    with pytest.raises(ToolError, match="최신 스키마로 새 DB"):
        call_context({"mission": "java-racingcar", "authors": ["learner-01"]})
    assert path.read_bytes() == before


def test_새_도구는_미션_부재와_테이블_부재를_설명한다(db_file):
    arguments = {"mission": "java-racingcar", "authors": ["learner-01"]}
    with sqlite3.connect(db_file) as conn:
        conn.execute("DELETE FROM missions")
    with pytest.raises(ToolError, match="데이터가 없는 미션"):
        call_context(arguments)
    with sqlite3.connect(db_file) as conn:
        conn.execute("DROP TABLE missions")
    with pytest.raises(ToolError, match="DB"):
        call_context(arguments)


def test_서버_DB_연결은_여전히_읽기_전용이다(context_db_file):
    with open_db() as conn:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM comments")


def test_새_열만_추가한_중간_스키마를_조회하지_않는다(tmp_path, monkeypatch):
    from pipeline.schema import SCHEMA

    path = tmp_path / "intermediate.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA.replace("github_id    INTEGER NOT NULL", "github_id    INTEGER"))
        conn.execute("INSERT INTO missions VALUES ('java-racingcar','owner/repo','미션',NULL)")
    monkeypatch.setenv(DB_PATH_ENV, str(path))
    with pytest.raises(ToolError, match="최신 스키마로 새 DB"):
        call_context({"mission": "java-racingcar", "authors": ["learner-01"]})


@pytest.mark.parametrize("filename", ["review #1.db", "review?mode=rw.db", "review%231.db"])
def test_특수문자_DB_경로에서_지정한_파일만_읽기_전용으로_연다(context_db_file, monkeypatch, filename):
    path = context_db_file.with_name(filename)
    context_db_file.rename(path)
    monkeypatch.setenv("CHOLOG_DB_PATH", str(path))
    before = set(path.parent.iterdir())

    with open_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pull_requests").fetchone() == (4,)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM comments")

    assert set(path.parent.iterdir()) == before


def test_실제_stdio_프로세스에서_두_도구를_호출한다(context_db_file):
    async def run():
        # 이미 설치된 실행 파일을 직접 실행한다. uv의 네트워크 접근도 필요 없다.
        executable = Path(__file__).resolve().parents[1] / ".venv/bin/cholog-mcp"
        params = StdioServerParameters(command=str(executable), env=dict(os.environ))
        with anyio.fail_after(15):
            async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
                await session.initialize()
                tools = {t.name: t for t in (await session.list_tools()).tools}
                assert {"get_review_context", "get_repeated_feedback"} <= tools.keys()
                for name in ("get_review_context", "get_repeated_feedback"):
                    assert "[PR #번호 · 리뷰 내용 요약](url)" in tools[name].description
                    assert "원문 URL: 전체 URL" in tools[name].description
                result = await session.call_tool("get_review_context", {"mission": "java-racingcar", "authors": ["learner-01"]})
                assert not result.is_error
                data = json.loads(result.content[0].text)
                assert data["scope"]["pr_numbers"] == [1, 3]
                assert "왜 이 선택이 나을까요?" in result.content[0].text
                old = await session.call_tool("get_repeated_feedback", {"mission": "java-racingcar"})
                assert not old.is_error
                assert json.loads(old.content[0].text)["scope"]["pr_count"] == 4

    anyio.run(run)
