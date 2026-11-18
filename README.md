# cholog-mcp

초록스터디 리드가 AI에게 질문하면, 미션별 PR·리뷰 기록을 근거로 답해주는 MCP 서버.

## 상태

토대 개발 중 (미션 1개 + 도구 2개).

- `get_repeated_feedback`: 반복 지적 주제의 집계와 대표 리뷰.
- `get_review_context`: 선택한 스터디원의 리뷰·작성자 답글 원문과 실제 답글 관계. 에이전트가 근거를 읽고 함께 이야기할 주제를 제안한다.

## 구조

| 경로 | 내용 |
|---|---|
| `docs/` | [도구 명세](docs/tool-spec.md), [결정과 이유](docs/decisions.md), [기록](docs/records/README.md) |
| `src/cholog_mcp/` | MCP 서버. 도구 로직과 실행 방식(stdio, HTTP)을 분리한다 |
| `pipeline/` | PR·리뷰 데이터 수집과 SQLite 적재 |
| `data/` | 수집한 원본과 SQLite 파일 (git에 올리지 않는다) |
| `tests/` | 테스트 |
| `scripts/` | 손으로 돌려 보는 확인용 스크립트 |
| `infra/` | AWS Lambda 배포 (Terraform). [배포 순서](infra/README.md) |

## 개발 환경

- Python 3.13, [uv](https://docs.astral.sh/uv/)

```bash
uv sync
uv run pytest
```

## 데이터 준비

아래는 로컬 개발자와 배포 파이프라인의 데이터 준비 절차다. 배포된 HTTP 서비스 사용자는 DB를 생성하거나 경로를 교체하지 않고 MCP 서버에 연결해 도구를 사용한다.

데이터는 저장소에 없다. 미션마다 아래 순서로 만든다. `fetch`는 [GitHub CLI](https://cli.github.com/)로 로그인(`gh auth login`)한 상태여야 한다.

```bash
uv run python -m pipeline fetch java-racingcar    # GitHub에서 PR과 리뷰를 받는다 (data/raw/)
uv run python -m pipeline load java-racingcar     # SQLite에 넣는다 (data/cholog.db)
uv run python -m pipeline tag java-racingcar      # 리뷰에 주제를 붙인다
uv run python -m pipeline verify java-racingcar   # 기준값과 비교한다
uv run python -m pipeline check java-racingcar    # 기본 점검 (배포 전에 자동으로 돈다)
```

SQLite 파일의 위치는 환경 변수 `CHOLOG_DB_PATH`로 바꿀 수 있다. 각 명령이 하는 일은 [docs/tool-spec.md](docs/tool-spec.md)의 5번 파이프라인에 있다.

HTTP 배포는 수집 → 최신 스키마로 새 DB 생성·적재 → 분류 → 검증 후 코드와 DB를 같은 이미지에 포함한다. 직전 DB는 비교 검증에만 쓰고 새 DB의 입력으로 재사용하지 않는다. 원본과 분류 방식으로 배포마다 DB를 재생성하는 구조이므로 기존 DB 스키마를 변환하는 migrate는 지원하지 않는다. [결정과 재검토 조건](docs/decisions.md)을 따른다.

구 스키마를 사용하는 로컬 개발자는 별도 새 경로를 `CHOLOG_DB_PATH`로 지정해 `load` → `tag` → `check`를 실행한 뒤 서버의 DB 경로를 교체한다. 보관한 원본 JSON에 답글 부모 정보가 있으면 재적재로 보완하고, 원본에도 정보가 없거나 수집 완전성을 확인할 수 없으면 `fetch`부터 다시 실행한다. [새 DB 생성과 배포 방식](docs/tool-spec.md#새-db-생성과-http-배포)을 따른다. 서버는 DB를 읽기만 하며 시작할 때 자동으로 수집·적재하거나 스키마를 바꾸지 않는다.

## 서버 실행

데이터를 준비한 뒤, 서버가 뜨고 도구가 불리는지 확인한다.

실제 수집 원본 없이 임시 합성 DB로 두 도구를 호출하는 최소 확인 절차와 검증 범위는 [최종 검증 기록](docs/records/2026-11-18-review-context-validation.md)에 있다.

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

배포(Lambda)에 쓰는 이미지다. 배포할 코드의 최신 스키마로 새로 생성하고 분류·검증한 데이터(`data/cholog.db`)를 같은 이미지에 넣는다. 직전 DB는 별도 경로에서 비교 검증에만 사용한다. 현재 배포 워크플로는 이미지 빌드까지 수행하며 실제 AWS 자동 배포 연결은 후속 작업이다.

```bash
docker build --platform linux/arm64 -t cholog-mcp:local .
docker run --rm --read-only -p 8080:8080 cholog-mcp:local     # http://localhost:8080/mcp
```

`--read-only`는 Lambda처럼 파일 시스템에 쓸 수 없게 막는다. 이미지 안의 [Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter)는 Lambda 이벤트를 HTTP 요청으로 바꿔 서버에 넘기고, Lambda 밖에서는 아무 일도 하지 않는다.

도구의 입력과 출력은 [docs/tool-spec.md](docs/tool-spec.md)에 있다.
