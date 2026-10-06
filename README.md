# cholog-mcp

초록스터디 리드가 AI에게 질문하면, 미션별 PR·리뷰 기록을 근거로 답해주는 MCP 서버.

## 상태

토대 개발 중 (미션 1개 + 도구 1개).

## 구조

| 경로 | 내용 |
|---|---|
| `docs/` | 도구 명세, 개발 안내 |
| `src/cholog_mcp/` | MCP 서버. 도구 로직과 실행 방식(stdio, HTTP)을 분리한다 |
| `pipeline/` | PR·리뷰 데이터 수집과 SQLite 적재 |
| `data/` | 수집한 원본과 SQLite 파일 (git에 올리지 않는다) |
| `tests/` | 테스트 |

## 개발 환경

- Python 3.13, [uv](https://docs.astral.sh/uv/)

```bash
uv sync
```
