import sqlite3

from pipeline.schema import create_schema
from pipeline.tagger import clean, tag_body, tag_mission

MISSION = "java-racingcar"


def test_키워드가_있으면_개념이_붙고_걸린_횟수가_점수가_된다():
    scores = tag_body("책임을 나누면 좋겠어요. 이 클래스의 책임이 너무 많아요.", MISSION)

    assert scores == {"responsibility": 2}


def test_코드와_인용과_링크_안의_단어는_세지_않는다():
    body = "> 책임이 뭔가요\n\n`getter`\n\n```java\nList<Car> cars;\n```\n\nhttps://example.com/naming 참고하세요"

    assert tag_body(body, MISSION) == {}


def test_영어_키워드는_대소문자를_구분하지_않는다():
    assert "exception" in tag_body("IllegalArgumentException을 던지면 어떨까요", MISSION)


def test_clean은_소문자로_바꾼다():
    assert clean("README") == "readme"


def test_세부_지적이_붙으면_개념도_붙는다():
    scores = tag_body("난수 생성기를 상속해서 테스트하셨네요", MISSION)

    assert scores["random-inherit"] == 1
    assert scores["testability-random"] == 1


def test_난수_이야기가_아닌_리뷰에는_세부_지적이_붙지_않는다():
    scores = tag_body("부모 클래스를 상속하는 구조가 어색해요", MISSION)

    assert "random-inherit" not in scores


def test_다른_미션에는_세부_지적이_붙지_않는다():
    scores = tag_body("난수 생성기를 상속해서 테스트하셨네요", "java-lotto")

    assert "random-inherit" not in scores


def _db_with_comments(comments: list[tuple[int, int, str]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    conn.execute("INSERT INTO missions VALUES (?, 'owner/repo', '미션', '2026-01-01T00:00:00+09:00')", (MISSION,))
    conn.executemany(
        "INSERT INTO comments VALUES (?, ?, 1, 'review', 'someone', ?, ?, NULL, NULL, '2026-01-01', '2026-01-01', "
        "'https://github.com/owner/repo/pull/1#discussion_r1')",
        [(comment_id, MISSION, is_pr_author, body) for comment_id, is_pr_author, body in comments],
    )
    return conn


def test_PR_작성자_본인의_답글에는_주제를_붙이지_않는다():
    conn = _db_with_comments([(1, 0, "네이밍을 다시 생각해 보세요"), (2, 1, "네이밍을 고쳤습니다")])

    tag_mission(conn, MISSION)

    assert conn.execute("SELECT comment_id, topic_id, method FROM comment_topics").fetchall() == [
        (1, "naming", "keyword")
    ]


def test_다시_분류해도_결과가_쌓이지_않는다():
    conn = _db_with_comments([(1, 0, "네이밍을 다시 생각해 보세요")])

    tag_mission(conn, MISSION)
    tag_mission(conn, MISSION)

    assert conn.execute("SELECT COUNT(*) FROM comment_topics").fetchone()[0] == 1
