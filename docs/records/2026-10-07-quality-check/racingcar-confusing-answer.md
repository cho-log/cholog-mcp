# 자동차 경주 미션: 사람들이 가장 헷갈려하는 것 (답변 전문)

> 기록 문서다. 맥락 없는 새 Claude Code 세션이 쓴 글을 그대로 옮겼고, GitHub ID만 가렸다. 배경은 [품질 확인](README.md)에 있다.

> 질문: 초록스터디 자동차경주에서 사람들이 제일 헷갈려하는게 뭐야?

리뷰가 달린 PR 173개 기준으로 한 주제가 압도적이지는 않고, 상위 4개 주제가 거의 동률입니다. 그중 "헷갈린다"에 가장 가까운 건 **난수(Random) 때문에 테스트를 어떻게 짜야 할지 모르는 문제**로 보입니다.

이 데이터는 리뷰어가 반복해서 지적한 횟수를 키워드로 센 값이라, 헷갈림 자체를 잰 것은 아니고 숫자도 실제보다 적게 잡힙니다 (주제가 안 붙은 리뷰 1231개, 데이터 기준 시각 2026-09-15 15:27 KST).

## 많이 지적받은 주제

| 순위 | 주제 | 지적받은 PR | 비율 |
|---|---|---|---|
| 1 | 네이밍 | 약 122개 | 71% |
| 2 | 예외 처리 / 검증 | 약 120개 | 69% |
| 3 | 책임 분리 / SRP | 약 119개 | 69% |
| 4 | 테스트 용이성 (난수 분리) | 약 116개 | 67% |
| 5 | 가독성 | 약 115개 | 66% |
| 6 | 자료구조 선택 (배열 vs List) | 약 90개 | 52% |
| 7 | 테스트 작성 / 보강 | 약 78개 | 45% |
| 8 | MVC / 레이어 분리 | 약 72개 | 42% |

## 왜 난수 테스트를 꼽았나

네이밍이나 가독성은 "고치면 되는" 지적인 반면, 난수 쪽은 리뷰에서 같은 질문과 시행착오가 여러 갈래로 반복됩니다.

- **테스트를 위해 프로덕션 코드를 바꿔도 되나?** (약 22개 PR): [PR #127 리뷰](https://github.com/next-step/java-racingcar-simple-playground/pull/127#issuecomment-2868625796)에서 리뷰어는 "그렇다"고 답합니다.
- **의존성 주입을 제안받음** (약 21개 PR)
- **Random 객체를 매번 `new`로 생성** (약 16개 PR)
- **테스트 대역(Stub, Mock, Fake)을 제안받음** (약 11개 PR): [PR #183 리뷰](https://github.com/next-step/java-racingcar-simple-playground/pull/183#discussion_r2992627681)는 값만 고정하면 되는 상황에 정말 Mock이 필요한지 되묻습니다.
- **운에 기대는 테스트, 난수 자체를 테스트하려는 시도** (각 약 9개 PR)
- **Random을 상속해서 테스트** (약 8개 PR)

## 그다음으로 질문이 많은 두 가지

- **검증을 어디에 둘 것인가**: 입력 단계에서 할지, 값을 가진 객체가 스스로 할지에 대한 질문입니다. [PR #114 리뷰](https://github.com/next-step/java-racingcar-simple-playground/pull/114#discussion_r2008783611)와 [PR #200 리뷰](https://github.com/next-step/java-racingcar-simple-playground/pull/200#issuecomment-5010683262)가 "이 검증 책임을 누가 갖는 게 자연스러운가"를 기준으로 답합니다.
- **SRP를 메서드 단위로 오해**: [PR #85 리뷰](https://github.com/next-step/java-racingcar-simple-playground/pull/85#discussion_r1957108457)는 SRP를 객체 단위부터 생각하라고 하고, [PR #153 리뷰](https://github.com/next-step/java-racingcar-simple-playground/pull/153#discussion_r2345300101)는 "움직일지 결정하는 조건"과 "움직이는 동작"을 분리하라고 합니다.

특정 스터디원들의 PR만 따로 보거나 최근 기수만 보고 싶으면 GitHub ID나 기준 날짜를 알려주세요.
