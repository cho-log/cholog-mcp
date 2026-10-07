# 자동차 경주 미션: 스터디원 공통 지적 사항 (답변 전문)

> 기록 문서다. 맥락 없는 새 Claude Code 세션이 쓴 글을 그대로 옮겼고, GitHub ID만 가렸다. 배경은 [품질 확인](README.md)에 있다.

> 질문: 자동차 경주 미션 끝나고 리뷰 수업 자료를 만들려고 해. 우리 스터디원들이 공통으로 지적받은 게 뭐야?
> 대상 GitHub ID: learner-09, learner-06, learner-07, learner-10, learner-01, learner-08, learner-04, learner-02, learner-05, learner-03

스터디원 10명의 자동차 경주 미션 리뷰를 조회했습니다. 가장 많이 지적받은 주제는 **난수 분리(테스트 용이성), 가독성, 책임 분리**로, 각각 리뷰받은 PR 10개 중 8개에서 나왔습니다.

## 조회 범위

- 데이터 기준 시각: 2026-09-15 15:27 (KST)
- 스터디원 10명 모두 조회됨, PR 11개 중 리뷰가 달린 PR 10개, 리뷰어 코멘트 246개
- 숫자는 키워드로 센 **대략적인 값**이라 실제보다 적게 잡힙니다. 246개 중 117개는 어떤 주제에도 분류되지 않았습니다.

## 공통 지적 주제

| 순위 | 주제 | 지적받은 PR | 코멘트 수 | 미션 전체 비율 | 대표 리뷰 |
|---|---|---|---|---|---|
| 1 | 테스트 용이성 (난수 분리) | 8/10 | 25 | 67% | [#189](https://github.com/next-step/java-racingcar-simple-playground/pull/189#discussion_r3004241535) |
| 2 | 가독성 | 8/10 | 21 | 66% | [#191](https://github.com/next-step/java-racingcar-simple-playground/pull/191#discussion_r2995448448) |
| 3 | 책임 분리 / SRP | 8/10 | 19 | 69% | [#188](https://github.com/next-step/java-racingcar-simple-playground/pull/188#discussion_r2993976721) |
| 4 | 예외 처리 / 검증 | 7/10 | 28 | 69% | [#192](https://github.com/next-step/java-racingcar-simple-playground/pull/192#discussion_r3003487170) |
| 5 | 네이밍 | 7/10 | 19 | 71% | [#188](https://github.com/next-step/java-racingcar-simple-playground/pull/188#discussion_r2993799972) |
| 6 | 자료구조 선택 | 7/10 | 16 | 52% | [#188](https://github.com/next-step/java-racingcar-simple-playground/pull/188#discussion_r3007433121) |
| 7 | 인터페이스 / 추상화 | 6/10 | 15 | 40% | [#193](https://github.com/next-step/java-racingcar-simple-playground/pull/193#discussion_r3004690523) |
| 8 | 테스트 작성 / 보강 | 6/10 | 10 | 45% | [#189](https://github.com/next-step/java-racingcar-simple-playground/pull/189#discussion_r2994893277) |
| 9 | 원시값 포장 / 일급 컬렉션 | 4/10 | 8 | 27% | [#184](https://github.com/next-step/java-racingcar-simple-playground/pull/184#discussion_r3007630107) |
| 10 | 접근 제어자 | 4/10 | 7 | 31% | [#193](https://github.com/next-step/java-racingcar-simple-playground/pull/193#discussion_r2995514377) |

"미션 전체 비율"은 이 미션의 과거 참가자 전체에서 같은 주제를 지적받은 PR 비율입니다.

## 여기서 알 수 있는 것

### 1. 난수 분리가 수업의 중심 주제로 적합합니다

1위이면서 세부 유형까지 나뉘어 있습니다.

- 난수 자체를 테스트하려 함: PR 3개 ([#187](https://github.com/next-step/java-racingcar-simple-playground/pull/187#discussion_r3005471418))
- `random`이라는 단어가 이름에 남음: PR 2개
- 운에 기대는 테스트, 항상 성공하는 테스트: PR 2개
- 테스트 대역(Stub, Mock, Fake)을 제안받음: PR 2개 ([#183](https://github.com/next-step/java-racingcar-simple-playground/pull/183#discussion_r2992627681))
- 테스트를 위해 프로덕션 코드를 추가: PR 2개

### 2. 우리 스터디가 전체 평균보다 유독 많이 지적받은 주제가 있습니다

- 인터페이스 / 추상화: 60% (전체 40%)
- 자료구조 선택: 70% (전체 52%), 배열 대신 `List`, `List` 상속, 일급 컬렉션 관련
- 테스트 작성 / 보강: 60% (전체 45%)

반대로 네이밍과 예외 처리는 전체 평균과 비슷한 수준입니다.

### 3. 예외 처리는 PR 수는 4위지만 코멘트 수는 28개로 가장 많습니다

검증 위치([#184](https://github.com/next-step/java-racingcar-simple-playground/pull/184#discussion_r2998429300)), `RuntimeException` 사용, 커스텀 예외 기준([#188](https://github.com/next-step/java-racingcar-simple-playground/pull/188#discussion_r2993810090))처럼 한 PR 안에서 여러 번 지적된 주제입니다.

### 4. 주제끼리 겹칩니다

같은 코멘트가 두 주제에 동시에 잡힌 경우가 있습니다(예: [#183 일급 컬렉션 리뷰](https://github.com/next-step/java-racingcar-simple-playground/pull/183#discussion_r2999312011)는 자료구조와 원시값 포장 양쪽). 난수 분리, 추상화, 테스트 작성도 사실상 한 흐름(난수를 밖으로 빼고, 인터페이스로 주입하고, 테스트에서 값을 고정)이라 수업에서는 하나로 묶을 수 있습니다.

## 다음 단계 제안

수업 자료 목차를 이렇게 묶는 안을 추천합니다.

1. 난수와 테스트 (1, 7, 8위 묶음)
2. 책임 분리와 일급 컬렉션 (3, 6, 9위 묶음)
3. 예외와 검증 위치 (4위)
4. 읽기 좋은 코드 (2, 5, 10위 묶음)

## 로드맵

- [완료] 1단계: 스터디원 공통 지적 사항 조회
- [확인 대기] 2단계: 수업 자료 목차와 형태 확정
- [예정] 3단계: 주제별 대표 리뷰 추가 수집 (필요 시 주제당 5개까지)
- [예정] 4단계: 수업 자료 작성
