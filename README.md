# cholog-mcp

초록스터디 리드가 AI에게 질문하면, 미션별 PR·리뷰 기록을 근거로 답해주는 MCP 서버.

## 상태

토대 개발 중 (미션 1개 + 도구 1개).

## 구조

| 경로 | 내용 |
|---|---|
| `docs/` | [도구 명세](docs/tool-spec.md), [결정과 이유](docs/decisions.md), [기록](docs/records/README.md) |
| `src/cholog_mcp/` | MCP 서버. 도구 로직과 실행 방식(stdio, HTTP)을 분리한다 |
| `pipeline/` | PR·리뷰 데이터 수집과 SQLite 적재 |
| `data/` | 수집한 원본과 SQLite 파일 (git에 올리지 않는다) |
| `tests/` | 테스트 |
| `scripts/` | 손으로 돌려 보는 확인용 스크립트 |

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

SQLite 파일의 위치는 환경 변수 `CHOLOG_DB_PATH`로 바꿀 수 있다. 각 명령이 하는 일은 [docs/tool-spec.md](docs/tool-spec.md)의 5번 파이프라인에 있다.

## 서버 실행

데이터를 준비한 뒤, 서버가 뜨고 도구가 불리는지 확인한다.

```bash
uv run python scripts/smoke.py                # 미션 전체
uv run python scripts/smoke.py id1 id2 id3    # 이 GitHub ID들의 PR만
```

Claude Code에 연결하려면 이 저장소의 절대 경로를 넣어 등록한다.

```bash
claude mcp add cholog -- uv run --directory /저장소/절대/경로 cholog-mcp
```

도구의 입력과 출력은 [docs/tool-spec.md](docs/tool-spec.md)에 있다.
