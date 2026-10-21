# cholog-mcp 에이전트 규칙

초록스터디 리드가 AI에게 질문하면, 미션별 PR·리뷰 기록을 근거로 답해주는 MCP 서버다.
이 파일이 프로젝트 규칙의 원본이다. `CLAUDE.md`는 이 파일을 가리키기만 한다.

## 확정값

- Python 3.13, 패키지 관리는 `uv` (`uv sync`, `uv add`, `uv run`). `pip`를 직접 쓰지 않는다.
- MCP SDK는 `mcp` 2.2.0. v2에서 `FastMCP`가 `mcp.server.MCPServer`로 이름이 바뀌었다. 옛 이름으로 쓰지 않는다.
- 응답과 문서는 한국어, 코드·명령어·식별자는 영어.

## 폴더

| 경로 | 내용 |
|---|---|
| `docs/` | 도구 명세(`tool-spec.md`), 결정과 이유(`decisions.md`), 기록(`records/`) |
| `src/cholog_mcp/` | MCP 서버 |
| `pipeline/` | PR·리뷰 데이터 수집과 SQLite 적재 |
| `data/` | 수집한 원본과 SQLite 파일. git에 올리지 않는다 |
| `tests/` | 테스트 |
| `scripts/` | 손으로 돌려 보는 확인용 스크립트 |

## 작업 순서

명세가 기준이다. 도구를 만들거나 고칠 때 이 순서를 지킨다.

1. `docs/tool-spec.md`에 입력, 출력, 규칙, 검증 기준을 먼저 쓴다.
2. 검증 기준을 테스트로 옮긴다 (`tests/`). 실제 데이터는 저장소에 없으므로 테스트는 직접 만든 작은 데이터를 쓴다.
3. 테스트가 통과하도록 구현한다 (`uv run pytest`).
4. 구현하다가 명세와 달라지면 명세를 먼저 고친다.

## 코드 구조

| 파일 | 역할 |
|---|---|
| `src/cholog_mcp/feedback.py` | 도구 로직. DB 연결을 받아 결과를 만든다. MCP를 모른다 |
| `src/cholog_mcp/server.py` | 도구를 MCP 서버에 등록한다. 입력 스키마와 도구 설명을 정한다 |
| `src/cholog_mcp/__init__.py` | 서버를 띄운다 (지금은 stdio) |
| `src/cholog_mcp/missions.py` | 지원하는 미션 목록 |
| `pipeline/topics.py` | 키워드 분류에 쓰는 주제 사전 |
| `pipeline/tagger.py` | 리뷰에 주제를 붙여 `comment_topics`에 쓴다 |

도구는 `comment_topics` 테이블만 읽는다. 분류 방법을 바꿀 때 도구 코드를 고치지 않는다.

## 문서

| 문서 | 성격 |
|---|---|
| `docs/tool-spec.md` | 명세. 코드와 늘 같아야 한다. 바뀌면 이 문서를 먼저 고친다 |
| `docs/decisions.md` | 결정과 이유. 결정이 바뀌면 고치고 날짜를 적는다 |
| `docs/records/` | 기록. 작성한 날의 내용 그대로 두고 갱신하지 않는다. 새 기록은 `날짜-주제.md`로 더한다 |

## 설계 원칙

배포 방식(로컬 stdio, 웹 HTTP)이 아직 정해지지 않았다. 실행 방식만 바꾸면 되도록 아래를 지킨다.

- 도구 로직을 실행 방식과 분리한다. 도구 함수는 stdio인지 HTTP인지 몰라야 한다.
- 데이터는 파일 하나에 두고, 경로는 설정으로 받는다. 코드에 경로를 박아 넣지 않는다.
- 핵심 기능은 Tool로만 만든다. AI 앱마다 Resource와 Prompt를 보여주는 방식이 달라서다.
- 도구의 설명(docstring)은 모델과 사용자가 읽는 설명서다. 언제 쓰는지, 무엇을 돌려주는지 적는다.
- 파라미터는 `Literal` 등으로 받을 수 있는 값을 좁힌다.
- 답은 숫자(집계)와 원문(인용)을 함께 돌려준다. 근거가 된 PR을 확인할 수 있어야 한다.

## git

- `main`에 직접 푸시하지 않는다. 브랜치를 만들고 PR로 올린다.
- 브랜치 이름: `종류/주제` (예: `feat/web-deploy`, `docs/tool-spec`).
- PR은 스쿼시 머지한다. 머지 커밋 없이 선형 히스토리를 유지한다.
- PR은 CI(`test` 체크: `uv sync --locked` 후 `uv run pytest`)를 통과해야 머지할 수 있다. 실패하면 로컬에서 `uv run pytest`로 재현한다.
- 커밋 메시지: `종류: 한국어 요약`. 종류는 `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
- 커밋은 사용자가 요청할 때만 한다.

## 올리면 안 되는 것

공개 저장소다.

- 수집한 데이터 (`data/` 아래의 원본 JSON, SQLite 파일)
- 토큰과 환경 설정 (`.env`). GitHub 토큰은 환경 변수로 받는다.
- 실제 사람의 GitHub ID와 이름. 문서와 테스트에는 PR 번호만 남기고, 스터디원과 리뷰어는 `learner-01`, `reviewer-id`처럼 가린다.
- 리뷰 원문을 모아 옮긴 문서. 인용은 필요한 만큼만 하고 원문은 PR 링크로 가리킨다.
