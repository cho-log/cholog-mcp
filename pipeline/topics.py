"""키워드 분류에 쓰는 주제 사전.

개념은 모든 미션에 공통이고, 세부 지적은 미션마다 따로 찾아 채운다.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Concept:
    """본문에 keywords 중 하나라도 있으면 붙는다. 본문은 소문자로 바꿔 비교한다."""

    id: str
    name: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class Subtopic:
    """gate에 걸린 리뷰 중 pattern에도 걸리면 붙는다. 붙으면 parent_id의 개념도 함께 붙는다."""

    id: str
    name: str
    parent_id: str
    mission_id: str
    gate: re.Pattern[str]
    pattern: re.Pattern[str]


CONCEPTS = (
    Concept("test-writing", "테스트 작성 / 보강",
            ("테스트를 작성", "테스트 코드", "단위 테스트", "테스트가 없", "테스트를 추가", "@test", "테스트해", "테스트를 통해")),
    Concept("testability-random", "테스트 용이성 (난수 분리)",
            ("테스트하기 어려", "테스트가 어려", "테스트하기 힘", "랜덤", "random")),
    Concept("responsibility", "책임 분리 / SRP",
            ("책임", "역할을", "단일 책임", "srp", "관심사")),
    Concept("encapsulation", "캡슐화 / getter 최소화",
            ("캡슐화", "getter", "게터", "정보 은닉", "은닉")),
    Concept("value-object", "원시값 포장 / 일급 컬렉션",
            ("일급 컬렉션", "일급컬렉션", "원시값", "원시 값", "포장", "값 객체", "vo ")),
    Concept("immutability", "불변 / 방어적 복사",
            ("불변", "immutable", "방어적 복사", "final로", "변경할 수 없")),
    Concept("exception", "예외 처리 / 검증",
            ("예외", "exception", "검증", "validate", "유효성", "illegalargument")),
    Concept("layering", "MVC / 레이어 분리",
            ("mvc", "컨트롤러", "controller", "뷰와", "view와", "계층", "레이어", "도메인 로직")),
    Concept("naming", "네이밍",
            ("네이밍", "이름을", "이름이", "메서드명", "변수명", "네임")),
    Concept("magic-number", "매직넘버 / 상수화",
            ("매직", "상수로", "상수화", "static final", "하드코딩")),
    Concept("stream", "스트림 / 함수형",
            ("스트림", "stream", "람다", "lambda", "for문 대신")),
    Concept("access-modifier", "접근 제어자",
            ("접근 제어자", "접근제어자", "private으로", "private로", "public으로")),
    Concept("method-extraction", "메서드 분리 / 길이",
            ("메서드로 분리", "분리하면", "분리해", "메서드가 길", "한 가지 일")),
    Concept("constructor", "정적 팩토리 / 생성자",
            ("정적 팩토리", "팩토리 메서드", "생성자를", "생성자에서")),
    Concept("duplication", "중복 제거",
            ("중복", "반복되는", "재사용")),
    Concept("abstraction", "인터페이스 / 추상화",
            ("인터페이스", "추상화", "abstract", "구현체")),
    Concept("data-structure", "자료구조 선택",
            ("list", "map<", "set<", "배열", "컬렉션")),
    Concept("readme", "README / 기능 목록",
            ("readme", "기능 목록", "기능목록", "문서")),
    Concept("commit", "커밋 / PR 단위",
            ("커밋", "commit", "pr 단위")),
    Concept("readability", "가독성",
            ("가독성", "읽기", "명확")),
)

# 자동차 경주: 난수 처리에 관한 리뷰만 세부 지적의 대상으로 본다.
RACINGCAR_RANDOM_GATE = re.compile(
    r"랜덤|random|난수|무작위|숫자 ?생성|numbergenerator|numberpicker|"
    r"테스트하기 (어렵|어려|힘들)|테스트가 (어렵|어려|힘들)|테스트 ?불가|"
    r"math\.random|threadlocalrandom|randoms\.|주입|의존성 주입|di ",
    re.IGNORECASE,
)


def _racingcar_random(topic_id: str, name: str, pattern: str) -> Subtopic:
    return Subtopic(
        id=topic_id,
        name=name,
        parent_id="testability-random",
        mission_id="java-racingcar",
        gate=RACINGCAR_RANDOM_GATE,
        pattern=re.compile(pattern, re.IGNORECASE),
    )


SUBTOPICS = (
    _racingcar_random(
        "random-direct", "자동차나 진행 객체가 난수를 직접 생성",
        r"(자동차|Car)(의|가|는)?\s*(입장|책임|역할).{0,40}(난수|랜덤|random)|난수.{0,20}(생성).{0,20}(자동차|Car)의 (책임|역할)"
        r"|랜덤.{0,15}(생성).{0,25}(책임|역할)|Random.{0,25}직접 (생성|사용|호출)"),
    _racingcar_random(
        "random-new-each-time", "Random 객체를 매번 new",
        r"(매번|계속|호출될 때마다|생성될 때마다).{0,40}(Random|random).{0,20}(생성|만들)|Random.{0,20}(매번|계속).{0,15}(생성|새로)"
        r"|불필요한 객체\s*생성|재사용"),
    _racingcar_random(
        "random-inherit", "Random을 상속해서 테스트",
        r"상속"),
    _racingcar_random(
        "random-test-itself", "난수 자체를 테스트하려 함",
        r"랜덤(한)?\s*(값|결과)?(을|를)?\s*(직접)?\s*테스트|Random 클래스 자체|테스트할 (필요|이유)(가)?\s*(없|거의)|테스트하지 않아도"),
    _racingcar_random(
        "random-luck-test", "운에 기대는 테스트, 항상 성공하는 테스트",
        r"항상 성공|운(이 좋|에 의존|적인 요소)|확률적으로 (실패|통과)|극악의 확률|여러 번 돌려야"),
    _racingcar_random(
        "random-test-only-code", "테스트를 위해 프로덕션 코드를 추가",
        r"테스트(를|만을)? 위한|테스트를 위해(서)?|테스트 전용|테스트 때문에"),
    _racingcar_random(
        "random-in-name", "random이라는 단어가 이름에 남음",
        r"(랜덤|random)(이|인지|한 값이)?\s*(라는 것을|인지)?\s*(꼭)?\s*알(아야|\s*필요)|randomValue|random이라는"),
    _racingcar_random(
        "random-new-inside", "인터페이스를 만들고 내부에서 new (주입 안 됨)",
        r"(인터페이스|추상화).{0,60}(직접 (생성|만들)|new\s)|new\s+\w*(Random|Strategy|Generator|Movement)\w*\(\).{0,40}직접"),
    _racingcar_random(
        "random-di", "의존성 주입(DIP)을 제안받음",
        r"의존성 역전|DIP|의존성 주입|주입받"),
    _racingcar_random(
        "random-strategy", "전략 패턴을 제안받음",
        r"전략\s*패턴|Strategy 패턴|전략패턴"),
    _racingcar_random(
        "random-test-double", "테스트 대역(Stub, Mock, Fake)을 제안받음",
        r"테스트 대역|스텁|Stub|Mock|모킹|Fake|가짜 객체"),
)
