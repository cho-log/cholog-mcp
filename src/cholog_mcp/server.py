"""MCP 서버에 도구를 등록한다.

여기서는 입력 스키마와 도구 설명만 정하고, 실제 일은 도구 로직(feedback 등)에 맡긴다.
어떤 방식(stdio, HTTP)으로 띄울지는 이 모듈이 정하지 않는다.
"""

from datetime import date
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from cholog_mcp import feedback
from cholog_mcp.db import open_db
from cholog_mcp.missions import MissionId

INSTRUCTIONS = (
    "초록스터디 미션의 과거 PR과 코드 리뷰 기록을 근거로 답한다. "
    "숫자를 말할 때는 대표 리뷰의 GitHub 링크를 함께 보여주고, 데이터 기준 시각(data_as_of)을 밝힌다."
)


def create_server() -> MCPServer:
    server = MCPServer(name="cholog", instructions=INSTRUCTIONS)

    @server.tool(title="반복 지적된 리뷰 주제")
    def get_repeated_feedback(
        mission: Annotated[MissionId, Field(description="미션")],
        authors: Annotated[
            list[str] | None,
            Field(description="PR 작성자의 GitHub ID 목록. 주면 이 사람들의 PR만 본다. 없으면 미션 전체"),
        ] = None,
        since: Annotated[
            date | None,
            Field(description="이 날짜(YYYY-MM-DD) 이후에 만든 PR만 본다"),
        ] = None,
        max_topics: Annotated[int, Field(ge=1, le=20, description="돌려줄 주제 수")] = 8,
        examples_per_topic: Annotated[int, Field(ge=0, le=5, description="주제마다 붙일 대표 리뷰 수")] = 2,
    ) -> dict:
        """미션에서 리뷰어들이 반복해서 지적한 주제를 많은 순으로 돌려준다.
        주제마다 지적받은 PR 수와 대표 리뷰(GitHub 원문 링크 포함)가 붙는다.

        이럴 때 쓴다:
        - 미션이 끝난 뒤 스터디원들이 공통으로 받은 리뷰를 정리할 때 (authors에 스터디원 GitHub ID를 넣는다)
        - 미션을 시작하기 전에 과거 참가자들이 자주 지적받은 점을 알고 싶을 때 (authors를 비운다)

        숫자는 키워드로 센 값이라 실제보다 적다. 답할 때 대략적인 값임을 밝히고, 대표 리뷰의 링크를 함께 보여준다.

        돌려주는 값 읽는 법:
        - pr_count, pr_ratio: 이 주제를 지적받은 PR 수와 비율. 비율의 분모는 리뷰어 코멘트가 달린 PR 수(scope.reviewed_pr_count)다.
        - overall_pr_ratio: 같은 미션의 과거 참가자 전체에서 이 주제를 지적받은 PR 비율. authors를 줬을 때만 채워진다.
          pr_ratio가 이 값보다 크면 이 스터디가 유독 많이 지적받은 주제다.
        - subtopics: 주제 안의 세부 지적. 아직 일부 주제에만 있다.
        - examples: 대표 리뷰. author는 리뷰를 받은 PR 작성자, reviewer는 리뷰를 쓴 사람이다. excerpt는 앞부분만 자른 것이다.
        """
        try:
            with open_db() as conn:
                return feedback.get_repeated_feedback(conn, mission, authors, since, max_topics, examples_per_topic)
        except (FileNotFoundError, ValueError) as error:
            # 예상한 실패는 이유를 그대로 돌려준다. 그 밖의 예외는 SDK가 내용을 가리고 로그에만 남긴다.
            raise ToolError(str(error)) from error

    return server
