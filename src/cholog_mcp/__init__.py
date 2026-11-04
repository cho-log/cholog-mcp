"""초록스터디 미션의 PR·리뷰 기록을 근거로 답하는 MCP 서버."""

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from cholog_mcp import config
from cholog_mcp.server import create_server


def main() -> None:
    """로컬 실행. AI 앱이 이 프로세스를 띄워 표준 입출력으로 대화한다."""
    create_server().run(transport="stdio")


def http_app() -> ASGIApp:
    """HTTP 서버 앱. main_http와 테스트가 같은 앱을 쓴다.

    - stateless_http: 요청마다 독립이고 세션을 기억하지 않는다. 요청마다 다른 인스턴스가 받아도 된다.
    - json_response: 응답을 스트림(SSE) 대신 JSON 한 덩어리로 보낸다. 도구 결과가 한 번에 나와서다.
    - transport_security: 허용한 Host만 받고, Origin이 붙은 브라우저 요청은 거절한다.
      SDK는 host가 로컬 주소일 때만 이 검증을 자동으로 켜므로 직접 넘긴다.
    """
    app = create_server().streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=config.allowed_hosts()),
    )
    return _post_only(app)


def _post_only(app: ASGIApp) -> ASGIApp:
    """POST가 아닌 요청은 405로 거절한다.

    SDK는 옛 방식 클라이언트의 GET에 서버 알림용 스트림을 열고 끊지 않는다.
    이 서버는 알림을 보내지 않고, 배포 환경(Lambda)에서는 열린 요청이 실행 시간과 동시 실행 수를 붙잡는다.
    """

    async def wrapped(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] != "POST":
            await Response(status_code=405, headers={"Allow": "POST"})(scope, receive, send)
            return
        await app(scope, receive, send)

    return wrapped


def main_http() -> None:
    """원격 실행. 서버가 HTTP로 요청을 받고, AI 앱은 URL(/mcp)로 연결한다."""
    uvicorn.run(http_app(), host=config.http_host(), port=config.http_port())
