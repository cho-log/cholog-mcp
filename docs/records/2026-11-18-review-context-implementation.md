# get_review_context 구현과 검증 기록

- 날짜: 2026-11-18
- 대상: [이슈 #8](https://github.com/cho-log/cholog-mcp/issues/8). 확인 당시 댓글 없음.
- 기준: `origin/main`의 `d73a44f`. 시작 작업 트리는 깨끗했고 `main`에서 `feat/get-review-context`를 생성했다.
- 커밋·원격 push·PR 생성·운영 DB 변경·유료 API 호출은 하지 않았다. 학생 코드를 실행하지 않았다.

## 구현한 범위와 결정

서버는 선택한 작성자의 PR·리뷰어 댓글·작성자 질문·후속 답변을 원문과 실제 부모 관계로 제공한다. 사용자 에이전트가 선정 기준을 읽고 주제·선정 이유·근거 링크·시작 질문을 제안한다. 서버 내부 LLM과 AI 주제 분류는 구현하지 않았다.

1. 새 도구는 `comment_topics` 없이 조회한다. 기존 집계 도구의 분류 의존과 구분되도록 AGENTS.md를 명확히 했다. `feedback.py`·`db.py`·`tagger.py` 구현은 변경하지 않았다.
2. GitHub 종류별 ID 충돌을 허용하기 위해 `comments.id`는 내부 키로 유지하고 `github_id`에 원본 ID를 저장한다. `(mission_id, kind, github_id)`가 유일하다. `comment_topics.comment_id`는 계속 내부 키를 참조한다. 전환 시 기존 키를 보존한다. 재적재 시 원본 ID 순으로 내부 키를 부여해 기존 대표 리뷰의 동점 선정 순서를 유지한다.
3. `in_reply_to_id`는 nullable 원본 ID다. 같은 미션·PR의 review만 부모로 연결한다. 부모 누락은 상태로 표시하고, issue 대화는 시간순으로만 제공한다. NULL 부모는 최상위와 미수집을 구분할 수 없다.
4. PR 번호, 대화 첫 댓글 시각, 댓글 시각·원본 ID 순으로 정렬한다. 작은 대화를 온전히 유지하고 큰 대화만 댓글 경계에서 분할한다. 페이지 기준은 50댓글·본문과 diff 24,000자·20개 대화 조각 또는 빈 PR이다. 단일 초과 댓글은 원문을 보존하고 표시한다. 이는 합성 자료로 검증한 초기값이다.
5. 커서는 범위와 자료 해시·버전·페이지 위치를 검증한다. 읽기 트랜잭션으로 한 응답의 스냅샷을 고정하며 대상 자료가 바뀌면 이어 읽기를 거절한다. 내부 키와 태그는 커서 자료 해시에서 제외한다.

## 변경 파일

- 규칙·안내: `AGENTS.md`, `README.md`
- 명세·결정·기록: `docs/tool-spec.md`, `docs/decisions.md`, 이 기록
- 조회·등록: `src/cholog_mcp/review_context.py`, `src/cholog_mcp/server.py`
- DB·적재·명령: `pipeline/schema.py`, `pipeline/load.py`, `pipeline/__main__.py`
- 새 합성 fixture·테스트: `tests/conftest.py`, `tests/fixtures/legacy_schema.sql`, `tests/test_review_context.py`, `tests/test_schema.py`, `tests/test_stdio.py`
- 기존 테스트 확장·fixture SQL 명시: `tests/test_load.py`, `tests/test_server.py`, `tests/test_http.py`, `tests/test_feedback.py`, `tests/test_tagger.py`, `tests/test_check.py`

## 실제 실행한 검증

1. 변경 전 `uv run pytest`: **65 passed**.
2. 명세 → 테스트 순서로 작성한 뒤 신규 테스트 묶음을 실행: 조회 모듈과 전환 함수 미구현으로 수집 오류 2개. 이어 적재·등록 테스트를 직접 실행해 부모 열 부재와 새 도구 미등록으로 **2 failed**를 확인했다.
3. 구현 후 내부 키 전환의 동점 선정 회귀 테스트를 추가: **1 failed**를 확인하고 원본 ID 순 적재로 수정했다.
4. CI와 같은 `uv sync --locked` → `uv run pytest`: **130 passed** (최종 실행 1.25초). 합성 fixture와 임시 SQLite만 사용했다.
5. `git diff --check`: 통과.

자동 테스트가 확인한 것:

- 작성자 질문·후속 답변, 인용·300자 초과 원문·공백·링크·diff·시각 보존.
- 작성자·미션·UTC 날짜 경계 필터, 빈 PR·빈 결과, 태그 테이블 없이 조회.
- 다른 PR·미션·issue 부모 혼입 방지, 누락·NULL 부모와 순환 자료 구분.
- 댓글·문자·대화·빈 PR 페이지 경계, 큰 대화와 단일 큰 댓글, 커서 형식·범위·위치·버전·자료 변경, 누락·중복 없는 전체 이어 읽기.
- 조회 사이에 다른 연결이 자료를 갱신해도 한 응답이 같은 스냅샷을 사용하는지 확인.
- 재적재 중복 방지·답글 보존·실패 롤백·원본 ID 충돌, 기존 분류 FK와 집계, 대표 리뷰 동점 선정 회귀.
- 구 DB 명시적 전환·재전환·중간 실패 롤백·중간 스키마 거절·전환 후 재적재와 분류, 실제 전환 CLI(임시 DB).
- 새 도구의 등록·선정 기준·입력 스키마·DB/입력 오류와 읽기 전용 연결.
- 실제 stdio 자식 프로세스에 MCP ClientSession으로 연결해 두 도구 호출. HTTP MCP 호출·커서 이어 읽기와 기존 Host·Origin·POST 제한 회귀.

## 사용자가 실행할 DB 전환

이번 작업에서는 운영 DB를 열거나 바꾸지 않았다. 아래 절차는 사용자가 서버와 적재 작업을 멈춘 후 수행한다.

1. SQLite 백업 기능으로 원본을 별도 경로(`data/cholog-copy.db` 등)에 복사한다. 기존 백업을 덮어쓰지 않는다.
2. 복사본 전체 스키마를 명시적으로 전환한다.

```bash
CHOLOG_DB_PATH=data/cholog-copy.db uv run python -m pipeline migrate
```

3. 원본 JSON에 답글 부모 정보가 있으면 재적재한다. 정보가 없거나 오래된 원본의 완전성을 확인하지 못하면 원본도 보관한 뒤 전체 `fetch`를 먼저 실행한다. 최상위 댓글에는 원래 부모 필드가 없을 수 있다. `--only` 부분 수집만으로 전체 자료의 최신성을 보장하지 않는다.

```bash
# 부모 정보를 보완해야 할 때만 실행한다. GitHub에 접근하는 명령이다.
uv run python -m pipeline fetch java-racingcar

CHOLOG_DB_PATH=data/cholog-copy.db uv run python -m pipeline load java-racingcar
CHOLOG_DB_PATH=data/cholog-copy.db uv run python -m pipeline tag java-racingcar
CHOLOG_DB_PATH=data/cholog-copy.db uv run python -m pipeline check java-racingcar
```

4. 모든 저장 미션에 반복하고 복사본의 원문·답글·기존 집계를 확인한 뒤 서버의 `CHOLOG_DB_PATH`를 교체한다. `migrate`만으로 부모 관계는 복원되지 않는다. `load`는 해당 미션의 기존 분류 연결을 지우므로 기존 집계에는 `tag`가 필요하다. 새 조회는 태그 없이도 동작한다.

자세한 계약과 예외는 [명세 5번](../tool-spec.md#기존-db-전환과-답글-정보-보완)을 따른다.

## 미검증 항목과 재현 절차

**실제 자연어 에이전트 연결과 추천 유용성, 실제 스터디 준비·모임 사용은 미검증이다.** 자동 MCP 프로토콜 테스트 통과는 이 검증을 대신하지 않는다. 실제 자료에서 응답 크기·메모리·처리 시간도 측정하지 않았다. 현재는 매 호출마다 대상 자료 전체를 메모리에 읽어 정렬·분할한다. 페이지 문자 예산은 전체 JSON 크기의 절대 상한이 아니다.

에이전트 사전 점검에 쓸 공개 가능한 합성 DB를 재현하려면 저장소 루트에서 다음을 실행한다. 새 임시 디렉터리만 사용한다.

```bash
review_check_dir="$(mktemp -d /tmp/cholog-context-check.XXXXXX)"
uv run pytest tests/test_stdio.py --basetemp "$review_check_dir"
review_check_db="$(rg --files --hidden --no-ignore "$review_check_dir" -g context.db)"
printf '%s\n' "$review_check_db"
```

MCP 지원 에이전트의 **새 세션**에서 서버 실행 명령을 `uv run --directory <저장소 절대경로> cholog-mcp`로 설정하고 환경 변수 `CHOLOG_DB_PATH`에 위에서 출력한 DB 절대경로를 넣는다. 선정 기준은 사용자 프롬프트에 복사하지 않는다. 합성 DB의 ID·링크는 시험용이며 실제 리뷰 근거 링크로 사용하지 않는다.

> learner-01과 learner-02의 자동차 경주 리뷰를 보고, 다음 모임에서 함께 이야기할 주제를 추천해줘.

다음을 기록한다:

- 앱·모델·서버 코드 기준·프롬프트·도구 선택과 입력·DB 식별자·data_as_of.
- 작성자 질문과 후속 설명·합의를 반영했는지, 원문 주장과 추가 해석을 구분했는지.
- 선정 이유·근거 링크·시작 질문을 제안했는지, 근거가 적을 때 억지로 주제를 만들지 않았는지.
- 동일 입력을 새 세션에서 반복한 결과의 차이. `tests/test_http.py`의 큰 대화 사례처럼 50댓글 초과 자료에서도 후속 페이지를 실제로 읽는지 별도로 확인한다.

이후 사용자가 준비한 실제 DB 복사본에서 질문과 후속 설명, 대안의 장단점, 해결된 대화, 오타·스타일뿐인 대화 사례를 고정해 같은 절차를 반복한다. 실제 근거 링크가 주장을 뒷받침하는지는 이 단계에서 확인한다. 공개 기록에는 가짜 식별자와 필요한 PR 번호·원문 링크만 남긴다.

실제 스터디 준비에서는 리드가 채택·수정·제외한 질문과 이유, 추가로 필요했던 자료를 기록한다. 실제 모임에서는 질문을 사용했는지와 선택 이유·다른 관점에 관한 대화로 이어졌는지를 별도로 기록한다. 질문 채택과 실제 대화·학습의 도움을 구분한다.

## main 대상 PR 초안

제목: `feat: 스터디원 리뷰 대화 문맥 조회 도구 구현`

본문:

```markdown
스터디원이 리뷰에서 질문한 내용과 후속 설명을 함께 읽고 토론 주제를 고를 수 있도록 get_review_context를 추가합니다. PR·댓글 원문과 실제 답글 관계, 근거 링크·수집 기준 시각을 제공하고, 사용자 에이전트가 선정 이유와 시작 질문을 작성하도록 도구 설명에 기준을 담았습니다.

- 태그 없이 조회하며 원문과 작성자 답글을 보존합니다. 대화 단위 페이지, 큰 대화의 부분 범위, 범위·자료 변경을 검증하는 커서를 제공합니다.
- 댓글 내부 키와 GitHub 원본 ID를 분리해 review/issue ID 충돌을 처리합니다. 명시적 migrate와 원본 부모 ID 재적재 절차를 추가하고 기존 분류 참조를 보존합니다.
- 기존 집계·대표 리뷰 선정 계약과 읽기 전용 연결을 유지합니다.

검증: 명세와 실패 테스트를 먼저 작성한 후 구현했습니다. uv run pytest 전체 130개 통과. 실제 stdio 프로세스·HTTP MCP 호출, 전환·재적재·커서·기존 기능 회귀를 합성 자료와 임시 SQLite로 확인했습니다.

운영 반영 전 DB 백업 → 복사본 migrate → 필요한 원본 보완/재수집 → load → tag → check가 필요합니다. 운영 DB에는 실행하지 않았습니다.

실제 에이전트의 자연어 도구 선택·추천 유용성, 실제 스터디 준비·모임 사용과 큰 실제 자료 성능은 미검증입니다. 재현 절차와 한계는 docs/records/2026-11-18-review-context-implementation.md에 기록했습니다.

Refs #8
```
