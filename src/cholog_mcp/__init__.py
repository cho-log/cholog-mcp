"""초록스터디 미션의 PR·리뷰 기록을 근거로 답하는 MCP 서버."""

from cholog_mcp.server import create_server


def main() -> None:
    """로컬 실행. AI 앱이 이 프로세스를 띄워 표준 입출력으로 대화한다."""
    create_server().run(transport="stdio")
