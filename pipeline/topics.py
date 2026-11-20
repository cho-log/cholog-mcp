"""키워드 분류에 쓰는 주제 사전.

개념은 모든 미션에 공통이고, 세부 지적은 미션마다 따로 찾아 채운다.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Description:
    """AI 분류 프롬프트에만 들어가는 개념 설명. 키워드 분류에는 쓰지 않는다.

    예시는 채점 표본(data/labels/의 두 sample json) 밖에서 가져오거나 직접 만든다.
    표본에서 가져오면 채점 점수가 부풀려진다.
    """

    definition: str  # 리뷰어가 이 개념을 "지적"했다고 볼 기준
    example: str
    example_source: str  # 예시를 어디서 가져왔는지. 프롬프트에는 넣지 않는다
    contrast: str  # 헷갈리는 이웃 개념과의 차이


@dataclass(frozen=True)
class Concept:
    """본문에 keywords 중 하나라도 있으면 붙는다. 본문은 소문자로 바꿔 비교한다."""

    id: str
    name: str
    keywords: tuple[str, ...]
    description: Description | None = None


@dataclass(frozen=True)
class Subtopic:
    """gate에 걸린 리뷰 중 pattern에도 걸리면 붙는다. 붙으면 parent_id의 개념도 함께 붙는다.

    gate나 pattern이 없으면 정규식으로는 붙지 않고, AI 분류 고정본(pipeline/ai_topics/)으로만 붙는다.
    """

    id: str
    name: str
    parent_id: str
    mission_id: str
    gate: re.Pattern[str] | None = None
    pattern: re.Pattern[str] | None = None


# 개념 목록을 바꾸면 날짜를 고친다. AI 분류 고정본이 어느 목록으로 분류됐는지 확인하는 데 쓴다.
CONCEPTS_VERSION = "2026-11-12"

CONCEPTS = (
    Concept("test-writing", "테스트 작성 / 보강",
            ("테스트를 작성", "테스트 코드", "단위 테스트", "테스트가 없", "테스트를 추가", "@test", "테스트해", "테스트를 통해",
             "테스트는 작성", "junit", "단언", "경계값"),
            description=Description(
                definition="테스트 코드 자체에 대한 지적. 테스트가 없거나 부족하다(경계값·예외 경우를 더하라), 테스트가 무엇을 어떻게 검증하는지(assert 방식, 기대값 만드는 법, 파라미터화), "
                           "테스트 구성·불필요한 테스트를 말한다.",
                example="0으로 나누는 경우에 대한 테스트도 추가하면 좋겠어요.",
                example_source="계산기 PR 8 코멘트 요지",
                contrast="난수·시간처럼 제어할 수 없는 값 때문에 테스트하기 어려운 구조를 고치라는 건 testability-random이다. 테스트 코드 안의 이름만 지적하면 naming이고, 테스트 "
                         "메서드 배치 순서만 지적하면 member-order다.",
            )),
    Concept("testability-random", "테스트 용이성 (난수 분리)",
            ("테스트하기 어려", "테스트가 어려", "테스트하기 힘", "랜덤", "random", "예측 가능", "제어할 수 없"),
            description=Description(
                definition="난수·현재 시각처럼 제어할 수 없는 값을 객체 안에서 직접 만들어서 테스트하기 어렵다는 지적. 생성 전략을 인터페이스나 주입으로 밖에서 넣으라는 지적, 테스트용 고정 생성기를 "
                           "어디에 둘지도 여기에 든다.",
                example="Random을 메서드 안에서 바로 만들면 결과를 테스트할 수 없지 않을까요? 번호 생성기를 밖에서 넣어 주면 어떨까요?",
                example_source="직접 만든 문장",
                contrast="테스트 경우를 더 쓰라는 건 test-writing이다. 인터페이스 도입 자체를 묻는 건 abstraction이고, 그 이유가 난수 제어·테스트라고 말하면 이 개념도 붙인다.",
            )),
    Concept("responsibility", "책임 분리 / SRP",
            ("책임", "역할을", "단일 책임", "srp", "관심사"),
            description=Description(
                definition="어떤 로직·데이터가 어느 객체에 있어야 하는지, 한 클래스가 너무 많은 일을 한다는 지적. 도메인 객체끼리 책임을 어떻게 나눌지를 말한다.",
                example="로또가 자동 번호까지 스스로 만드는 건 어색해 보여요. 로또를 발급하는 객체를 따로 두면 어떨까요?",
                example_source="로또 PR 84 코멘트 요지 (채점 표본 밖)",
                contrast="Controller·View·도메인 같은 계층 사이 경계(도메인이 출력을 앎, 컨트롤러에 비즈니스 로직)를 말하면 layering이다. 한 메서드가 길거나 여러 일을 해서 "
                         "메서드로 나누라는 건 method-extraction이다. 계층 문제와 특정 객체의 책임을 함께 말하면 둘 다 붙인다.",
            )),
    Concept("encapsulation", "캡슐화 / getter 최소화",
            ("캡슐화", "getter", "게터", "정보 은닉", "은닉"),
            description=Description(
                definition="내부 값을 getter로 꺼내 밖에서 계산·판단하지 말고 객체에게 시키라는 지적. 내부 상태를 불필요하게 드러낸다는 지적.",
                example="price를 꺼내서 컨트롤러가 곱하지 말고, 객체에게 총액을 물어보면 어떨까요?",
                example_source="로또 PR 157 코멘트 요지 (채점 표본 밖)",
                contrast="필드·메서드에 private을 붙이라는 건 access-modifier다. 꺼낸 컬렉션을 밖에서 바꿀 수 있다(방어적 복사, 불변 컬렉션)는 건 immutability다. "
                         "a.getB().getC()처럼 연쇄로 타고 들어가는 건 law-of-demeter다.",
            )),
    Concept("value-object", "원시값 포장 / 일급 컬렉션",
            ("일급 컬렉션", "일급컬렉션", "원시값", "원시 값", "포장", "값 객체", "vo ", "vo란", "vo는", "vo를", "vo가"),
            description=Description(
                definition="int·String·List 같은 원시값이나 컬렉션을 의미 있는 클래스로 감싸라는 지적, 또는 감싼 객체(값 객체, 일급 컬렉션)의 설계를 말한다.",
                example="구입 금액을 int로 들고 다니지 말고 Money 같은 객체로 감싸 보면 어떨까요?",
                example_source="로또 PR 117 코멘트 요지 (채점 표본 밖)",
                contrast="List·Set·Map 중 어떤 자료구조를 쓸지는 data-structure다. 감싼 객체의 equals·hashCode는 equals-hashcode다. 숫자를 상수로 빼라는 "
                         "건 magic-number다.",
            )),
    Concept("immutability", "불변 / 방어적 복사",
            ("불변", "immutable", "방어적 복사", "final로", "final은", "변경할 수 없"),
            description=Description(
                definition="값이 바뀌지 않게 하라는 지적. final, 불변 컬렉션(unmodifiableList, List.copyOf), 방어적 복사, setter로 바뀌는 상태를 말한다.",
                example="필드 리스트를 그대로 반환하면 밖에서 내용을 바꿀 수 있지 않을까요?",
                example_source="계산기 PR 76 코멘트 요지",
                contrast="getter 자체를 줄이라는 건 encapsulation이다. 필드로 상태를 두지 말고 계산해서 바로 반환하라는 건 state-consistency다.",
            )),
    Concept("exception", "예외 처리 / 검증",
            ("예외", "exception", "검증", "validate", "유효성", "illegalargument"),
            description=Description(
                definition="잘못된 입력·상태에 대한 검증이 없거나 방식이 어색하다는 지적. 예외 종류와 메시지, try-catch, 잘못 입력했을 때의 처리(재입력 등)를 말한다.",
                example="커스텀 구분자 형식이 틀리면 substring에서 예외가 날 수 있어요. 형식을 먼저 검증하면 어떨까요?",
                example_source="계산기 PR 73 코멘트 요지",
                contrast="검증을 View·도메인 중 어디에 둘지 말하면 layering도, 어느 객체에 둘지 말하면 responsibility도 함께 붙인다. 예외 경우의 테스트를 추가하라는 건 "
                         "test-writing이다.",
            )),
    Concept("layering", "MVC / 레이어 분리",
            ("mvc", "컨트롤러", "controller", "뷰와", "view와", "계층", "레이어", "도메인 로직", "뷰의 역할", "패키지로 분리"),
            description=Description(
                definition="Model·View·Controller 같은 계층 사이 경계에 대한 지적. 도메인이 입출력 형식을 알거나, Controller에 비즈니스 로직이 있거나, View에 도메인 "
                           "규칙이 있거나, 패키지 구조가 계층과 맞지 않는다는 지적.",
                example="도메인 enum이 출력 문구까지 들고 있으면 도메인이 View에 의존하게 되지 않을까요?",
                example_source="로또 PR 150 코멘트 요지 (채점 표본 밖)",
                contrast="도메인 객체끼리 책임을 어디에 둘지는 responsibility다. 출력용으로 toString을 오버라이드하는 것도 도메인과 출력의 경계 문제라 layering이다.",
            )),
    Concept("naming", "네이밍",
            ("네이밍", "이름을", "이름이", "메서드명", "변수명", "네임"),
            description=Description(
                definition="클래스·메서드·변수·상수·패키지 이름이 의도를 드러내지 않거나, 오타·축약·관례 위반이라는 지적.",
                example="matchSecond라는 이름을 보고 2개 맞은 걸로 읽었어요. 다른 이름은 어떨까요?",
                example_source="로또 PR 144 코멘트 요지 (채점 표본 밖)",
                contrast="이름이 아니라 코드 흐름·구조가 읽기 어렵다는 건 readability다. 리터럴을 상수로 빼라는 건 magic-number이고, 상수 이름까지 지적하면 둘 다 붙인다.",
            )),
    Concept("magic-number", "매직넘버 / 상수화",
            ("매직", "상수로", "상수화", "static final", "하드코딩", "스태틱 변수"),
            description=Description(
                definition="의미 있는 숫자·문자열 리터럴을 상수로 빼라는 지적, 상수 선언 방식(static final)을 말한다.",
                example="기본 구분자 \"[,:]\"를 DEFAULT_DELIMITERS 같은 상수로 두면 어떨까요?",
                example_source="계산기 PR 75 코멘트 요지",
                contrast="관련 상수를 enum으로 묶으라는 건 enum이다. 상수가 어느 클래스에 있어야 하는지 말하면 responsibility도 붙인다.",
            )),
    Concept("stream", "스트림 / 함수형",
            ("스트림", "stream", "람다", "lambda", "for문 대신"),
            description=Description(
                definition="반복문을 Stream·람다·메서드 참조로 바꾸라는 지적, 또는 스트림을 쓰는 방식(부작용, 과한 체이닝)에 대한 지적.",
                example="values().stream().filter(...).findAny()로 한 번에 찾을 수 있어 보여요.",
                example_source="로또 PR 27 코멘트 요지 (채점 표본 밖)",
                contrast="어떤 컬렉션을 쓸지는 data-structure다. 스트림과 상관없이 읽기 쉽게 바꾸라는 건 readability다.",
            )),
    Concept("access-modifier", "접근 제어자",
            ("접근 제어자", "접근제어자", "private으로", "private로", "public으로"),
            description=Description(
                definition="private·public·protected·default 중 무엇을 쓸지에 대한 지적. 내부에서만 쓰는 메서드·필드를 private으로 하라는 지적.",
                example="내부에서만 쓰는 메서드라면 private을 붙여 보면 어떨까요?",
                example_source="계산기 PR 87 코멘트 요지",
                contrast="getter로 값을 드러내는 설계 문제는 encapsulation이다.",
            )),
    Concept("method-extraction", "메서드 분리 / 길이",
            ("메서드로 분리", "메소드로 분리", "메서드를 분리", "함수로 분리", "메서드가 길", "메서드 길이",
             "메서드를 나눠", "한 가지 일"),
            description=Description(
                definition="메서드가 길거나 들여쓰기(depth)가 깊거나 여러 일을 한다며 작은 메서드로 나누라는 지적. 메서드 길이·depth 요구사항 위반도 여기에 든다.",
                example="검증 로직이 들어가면서 depth가 2가 됐어요. 어떻게 줄일 수 있을까요?",
                example_source="로또 PR 153 코멘트 요지 (채점 표본 밖)",
                contrast="같은 코드가 여러 곳에 반복되니 하나로 모으라는 건 duplication이다(나눈 메서드로 중복을 없애라고 하면 둘 다). 클래스 단위로 나누라는 건 "
                         "responsibility다.",
            )),
    Concept("constructor", "정적 팩토리 / 생성자",
            ("정적 팩토리", "팩토리 메서드", "생성자를", "생성자에서"),
            description=Description(
                definition="객체를 만드는 방식에 대한 지적. 생성자 설계·오버로딩, 정적 팩토리 메서드, 생성자에서의 초기화, 자주 쓰는 객체의 캐싱을 말한다.",
                example="1~45 번호 객체를 매번 new 하지 말고 미리 만들어 두고 꺼내 쓰면 어떨까요?",
                example_source="로또 PR 117 코멘트 요지 (채점 표본 밖)",
                contrast="생성자 안에 검증이 없다는 것만 말하면 exception이다.",
            )),
    Concept("duplication", "중복 제거",
            ("중복 코드", "코드 중복", "코드가 중복", "로직 중복", "로직이 중복", "중복되고 있", "중복으로 작성",
             "반복되는", "재사용"),
            description=Description(
                definition="같거나 비슷한 코드·로직·검증이 두 곳 이상 반복된다는 지적.",
                example="같은 도메인 규칙을 두 곳에서 검증하고 있어요. 한 곳에서 관리할 방법이 있을까요?",
                example_source="로또 PR 208 코멘트 요지 (채점 표본 밖)",
                contrast="한 곳에 있는 긴 메서드를 나누라는 건 method-extraction이다. 같은 숫자가 여러 곳에 하드코딩되어 있다는 건 magic-number다.",
            )),
    Concept("abstraction", "인터페이스 / 추상화",
            ("인터페이스", "추상화", "abstract", "구현체"),
            description=Description(
                definition="인터페이스·추상 클래스를 도입하거나 그 필요성을 묻는 지적. 구현체 대신 추상화에 의존하라는 지적, default 메서드·상속 구조에 대한 지적.",
                example="구현체에 바로 의존하기보다 인터페이스에 의존해 보면 어떨까요?",
                example_source="로또 PR 33 코멘트 요지 (채점 표본 밖)",
                contrast="인터페이스를 두는 이유가 난수 제어·테스트라면 testability-random도 붙인다.",
            )),
    Concept("data-structure", "자료구조 선택",
            ("list", "map<", "set<", "배열", "컬렉션", "자료구조", "해시맵"),
            description=Description(
                definition="List·Set·Map·EnumMap·배열 중 어떤 자료구조를 쓸지, 그 자료구조가 주는 기능(contains, merge, 정렬)을 활용하라는 지적.",
                example="중복을 없애고 정렬까지 해 주는 자료구조를 쓰면 더 단순해지지 않을까요?",
                example_source="로또 PR 91 코멘트 요지 (채점 표본 밖)",
                contrast="컬렉션을 감싸는 클래스를 만들라는 건 value-object다. 리스트를 불변으로 반환하라는 건 immutability다. 본문에 List가 나온다는 이유만으로 붙이지 않는다.",
            )),
    Concept("readme", "README / 기능 목록",
            ("readme", "리드미", "기능 목록", "기능목록", "문서"),
            description=Description(
                definition="README·기능 목록·요구사항 문서의 작성, 갱신, 위치에 대한 지적.",
                example="구현이 끝난 기능은 기능 목록에 체크해서 살아 있는 문서로 만들어 주세요.",
                example_source="계산기 PR 120 코멘트 요지",
                contrast="코드 안의 주석은 readme가 아니다.",
            )),
    Concept("commit", "커밋 / PR 단위",
            ("커밋", "commit", "pr 단위"),
            description=Description(
                definition="커밋 메시지·커밋 단위, push 누락, .gitignore, PR을 올리는 방식처럼 git과 PR 진행에 대한 지적.",
                example="커밋 메시지가 깨져 보여요. 한 번 확인해 보세요.",
                example_source="로또 PR 195 코멘트 요지 (채점 표본 밖)",
                contrast="README 내용은 readme다.",
            )),
    Concept("readability", "가독성",
            ("가독성", "읽기", "읽히지 않", "명확"),
            description=Description(
                definition="이름이 아닌 이유로 코드가 읽기 어렵다는 지적. 조건문·return 단순화, 한 줄에 너무 많은 일, 불필요한 변수·else, 따라가기 어려운 흐름을 말한다.",
                example="한 줄에 변환과 검증이 같이 들어 있어서 읽기 어려워요. 나눠 보면 어떨까요?",
                example_source="로또 PR 107 코멘트 요지 (채점 표본 밖)",
                contrast="이름 때문이면 naming이다. 메서드를 따로 뽑으라고 하면 method-extraction이다. 공백·줄바꿈·컨벤션은 formatting이다. '가독성'이라는 말이 있어도 "
                         "실제 지적이 다른 개념이면 그 개념만 붙인다.",
            )),
    Concept("formatting", "코드 포맷팅 / 컨벤션", (),
            description=Description(
                definition="들여쓰기·공백·빈 줄·마지막 줄 개행·자동 정렬, import 정리, 코딩 컨벤션을 통일하라는 지적.",
                example="마지막 줄 개행이 빠졌어요. IDE 자동 정렬을 적용해 보세요.",
                example_source="로또 PR 183 코멘트 요지 (채점 표본 밖)",
                contrast="필드·메서드 선언 순서는 member-order다. 이름 규칙은 naming이다. this를 붙이는 기준은 this-usage다.",
            )),
    Concept("equals-hashcode", "equals·hashCode·record", (),
            description=Description(
                definition="equals·hashCode를 재정의할지와 그 방식, 동등성과 동일성, record를 쓰는 이유에 대한 지적.",
                example="equals만 재정의하고 hashCode는 안 하면 어떤 일이 생길까요?",
                example_source="로또 PR 151 코멘트 요지 (채점 표본 밖)",
                contrast="원시값을 값 객체로 감싸라는 건 value-object다.",
            )),
    Concept("enum", "enum 활용", (),
            description=Description(
                definition="상수·등수·연산자처럼 정해진 값의 묶음을 enum으로 표현하라는 지적, 또는 enum 설계(필드, 값으로 찾는 메서드, values() 순회)에 대한 지적.",
                example="사칙연산 기호를 enum으로 묶고, 각 상수가 계산을 하도록 해 보면 어떨까요?",
                example_source="직접 만든 문장",
                contrast="enum이 출력 문구를 들고 있는 계층 문제는 layering이다. 리터럴을 상수로 빼라는 것만 말하면 magic-number다.",
            )),
    Concept("unused-code", "미사용 코드 제거", (),
            description=Description(
                definition="쓰지 않는 메서드·변수·import, 주석 처리한 코드, 쓰이지 않는 초기화를 지우라는 지적.",
                example="사용하지 않는 메서드로 보여요. 남겨 둔 이유가 있을까요?",
                example_source="계산기 PR 85 코멘트 요지",
                contrast="같은 코드가 반복된다는 건 duplication이다.",
            )),
    Concept("law-of-demeter", "디미터 법칙", (),
            description=Description(
                definition="a.getB().getC()처럼 다른 객체의 내부를 연쇄로 타고 들어가는 호출을 줄이라는 지적.",
                example="lotto.getNumbers().contains(n) 대신 lotto.contains(n)처럼 물어보면 어떨까요?",
                example_source="직접 만든 문장",
                contrast="getter 한 번으로 값을 꺼내 밖에서 계산하는 건 encapsulation이다. 둘 다 말하면 둘 다 붙인다.",
            )),
    Concept("member-order", "메서드 배치 순서", (),
            description=Description(
                definition="클래스 안에서 필드·생성자·메서드를 선언하는 순서, 호출 순서대로 배치하기, getter 위치에 대한 지적.",
                example="자바 스타일 가이드는 필드, 생성자, 메서드 순으로 둬요. 생성자 위치가 조금 어색해요.",
                example_source="로또 PR 83 코멘트 요지 (채점 표본 밖)",
                contrast="공백·개행 같은 모양은 formatting이다.",
            )),
    Concept("comparable", "Comparable 구현", (),
            description=Description(
                definition="객체의 비교·정렬을 위해 Comparable이나 Comparator를 구현하거나 고르라는 지적.",
                example="번호 객체가 Comparable을 구현하면 값을 꺼내서 정렬할 필요가 없어요.",
                example_source="로또 PR 179 코멘트 요지 (채점 표본 밖)",
                contrast="정렬된 자료구조(TreeSet 등)를 쓰라는 건 data-structure다.",
            )),
    Concept("state-consistency", "상태 일관성", (),
            description=Description(
                definition="객체가 필요 없는 상태(필드)를 갖거나, 바뀌는 값을 static 변수에 두거나, 상태 때문에 한 번만 쓸 수 있거나 여러 번 실행·여러 사용자에게 문제가 생긴다는 지적.",
                example="계산 결과를 필드에 두면 계산을 한 번밖에 못 하지 않을까요? 바로 반환하면 어떨까요?",
                example_source="계산기 PR 118 코멘트 요지",
                contrast="값을 final·불변 컬렉션으로 막으라는 건 immutability다.",
            )),
    Concept("this-usage", "this 사용 규칙", (),
            description=Description(
                definition="this 키워드를 붙이는 기준이 섞여 있거나 불필요하게 붙였다는 지적.",
                example="어떤 곳은 this를 붙이고 어떤 곳은 안 붙였네요. 기준이 있나요?",
                example_source="계산기 PR 97 코멘트 요지",
                contrast="this 말고 일반적인 코드 스타일 통일은 formatting이다.",
            )),
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
