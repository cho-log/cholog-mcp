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

### HTTP로 실행

원격에서 쓰도록 HTTP로 띄울 수도 있다. AI 앱은 `http://주소:포트/mcp`로 연결한다.

```bash
uv run cholog-mcp-http                                   # http://127.0.0.1:8080/mcp
claude mcp add --transport http cholog http://127.0.0.1:8080/mcp
```

| 환경 변수 | 기본값 | 내용 |
|---|---|---|
| `CHOLOG_HTTP_HOST` | `127.0.0.1` | 요청을 받을 주소. 배포할 땐 `0.0.0.0` |
| `CHOLOG_HTTP_PORT` | `8080` | 포트 |
| `CHOLOG_ALLOWED_HOSTS` | 로컬 주소 | 받을 Host 헤더 값, 쉼표로 구분. 배포할 땐 서버의 도메인을 넣는다 |

요청마다 독립(stateless)이고 응답은 JSON 한 덩어리다. Origin이 붙은 브라우저 요청과 POST가 아닌 요청은 거절한다.

### 컨테이너로 실행

배포(Lambda)에 쓰는 이미지다. 데이터(`data/cholog.db`)를 이미지에 넣으므로, 데이터를 먼저 준비해야 빌드된다.

```bash
docker build --platform linux/arm64 -t cholog-mcp:local .
docker run --rm --read-only -p 8080:8080 cholog-mcp:local     # http://localhost:8080/mcp
```

`--read-only`는 Lambda처럼 파일 시스템에 쓸 수 없게 막는다. 이미지 안의 [Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter)는 Lambda 이벤트를 HTTP 요청으로 바꿔 서버에 넘기고, Lambda 밖에서는 아무 일도 하지 않는다.

도구의 입력과 출력은 [docs/tool-spec.md](docs/tool-spec.md)에 있다.
