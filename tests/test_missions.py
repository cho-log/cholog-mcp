from typing import get_args

from cholog_mcp.missions import MISSIONS, MissionId


def test_입력으로_받는_미션과_미션_목록이_같다():
    assert set(get_args(MissionId)) == set(MISSIONS)


def test_도구_입력_스키마에_계산기_미션이_보인다():
    import anyio

    from cholog_mcp.server import create_server

    tool = next(t for t in anyio.run(create_server().list_tools) if t.name == "get_repeated_feedback")

    assert "java-calculator" in tool.input_schema["properties"]["mission"]["enum"]
