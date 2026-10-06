"""도구가 MCP 서버에 등록된 모습 (docs/tool-spec.md 7-4)."""

import sqlite3

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from cholog_mcp.config import DB_PATH_ENV
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
    (tool,) = anyio.run(create_server().list_tools)

    assert tool.name == "get_repeated_feedback"
    assert tool.title == "반복 지적된 리뷰 주제"
    assert "이럴 때 쓴다" in tool.description
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
