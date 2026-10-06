"""서버를 stdio로 띄워 실제 MCP 클라이언트로 불러 본다 (docs/tool-spec.md 검증 기준 7-4).

    uv run python scripts/smoke.py                        미션 전체
    uv run python scripts/smoke.py id1 id2 id3            이 GitHub ID들의 PR만
"""

import json
import sys

import anyio
from mcp.client import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

PARAMS = StdioServerParameters(command="uv", args=["run", "cholog-mcp"])


async def main(authors: list[str]) -> None:
    async with stdio_client(PARAMS) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        for tool in (await session.list_tools()).tools:
            print(f"[도구] {tool.name} ({tool.title})")
            print(tool.description)
            print(json.dumps(tool.input_schema, ensure_ascii=False, indent=2))

        arguments: dict = {"mission": "java-racingcar"}
        if authors:
            arguments["authors"] = authors
        result = await session.call_tool("get_repeated_feedback", arguments)
        text = result.content[0].text
        print(f"\n[호출] {json.dumps(arguments, ensure_ascii=False)}")
        print(f"[응답 길이] {len(text)}자")
        print(json.dumps(json.loads(text), ensure_ascii=False, indent=2))


anyio.run(main, sys.argv[1:])
