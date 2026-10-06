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
uv run pytest
```

## 데이터 준비

데이터는 저장소에 없다. 미션마다 아래 순서로 만든다. `fetch`는 [GitHub CLI](https://cli.github.com/)로 로그인(`gh auth login`)한 상태여야 한다.

```bash
uv run python -m pipeline fetch java-racingcar    # GitHub에서 PR과 리뷰를 받는다 (data/raw/)
uv run python -m pipeline load java-racingcar     # SQLite에 넣는다 (data/cholog.db)
uv run python -m pipeline tag java-racingcar      # 리뷰에 주제를 붙인다
uv run python -m pipeline verify java-racingcar   # 기준값과 비교한다
```

SQLite 파일의 위치는 환경 변수 `CHOLOG_DB_PATH`로 바꿀 수 있다.
