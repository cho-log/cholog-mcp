"""get_repeated_feedback의 검증 기준 (docs/tool-spec.md 8-3)."""

import sqlite3
from datetime import date

import pytest

from cholog_mcp.feedback import get_repeated_feedback
from pipeline.schema import create_schema

MISSION = "test-mission"
SYNCED_AT = "2026-03-03T09:00:00+09:00"
LONG = "이 부분은 다시 생각해 보면 좋겠습니다. 이유를 함께 적어 주세요."  # 30자 이상


class Db:
    """테스트 데이터를 넣는 도우미."""

    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        create_schema(self.conn)
        self.conn.execute("INSERT INTO missions VALUES (?, 'owner/repo', '테스트 미션', ?)", (MISSION, SYNCED_AT))
        self.conn.executemany(
            "INSERT INTO topics (id, parent_id, mission_id, name) VALUES (?, ?, ?, ?)",
            [
                ("naming", None, None, "네이밍"),
                ("responsibility", None, None, "책임 분리"),
                ("testability", None, None, "테스트 용이성"),
                ("random-inherit", "testability", MISSION, "Random을 상속해서 테스트"),
            ],
        )
        self._next_comment_id = 1

    def pr(self, number: int, author: str, created_at: str = "2026-03-01T00:00:00Z") -> None:
        self.conn.execute(
            "INSERT INTO pull_requests VALUES (?, ?, ?, '미션 제출', ?, ?)",
            (MISSION, number, author, created_at, f"https://github.com/owner/repo/pull/{number}"),
        )

    def comment(self, pr: int, author: str, topics: dict[str, int] | None = None, body: str = LONG) -> int:
        comment_id = self._next_comment_id
        self._next_comment_id += 1
        pr_author = self.conn.execute(
            "SELECT author FROM pull_requests WHERE mission_id = ? AND number = ?", (MISSION, pr)
        ).fetchone()[0]
        self.conn.execute(
            "INSERT INTO comments VALUES (?, ?, ?, 'review', ?, ?, ?, 'Car.java', NULL, '2026-03-02', '2026-03-02', ?)",
            (comment_id, MISSION, pr, author, int(author == pr_author), body,
             f"https://github.com/owner/repo/pull/{pr}#discussion_r{comment_id}"),
        )
        self.conn.executemany(
            "INSERT INTO comment_topics VALUES (?, ?, 'keyword', ?)",
            [(comment_id, topic_id, score) for topic_id, score in (topics or {}).items()],
        )
        return comment_id

    def ask(self, **kwargs) -> dict:
        return get_repeated_feedback(self.conn, MISSION, **kwargs)


@pytest.fixture
def db() -> Db:
    return Db()


def topic(result: dict, topic_id: str) -> dict:
    return next(t for t in result["topics"] if t["id"] == topic_id)


def test_PR_작성자_본인의_답글은_세지_않는다(db):
    db.pr(1, "learner")
    db.comment(1, "reviewer", {"naming": 1})
    db.comment(1, "learner", {"naming": 1})

    result = db.ask()

    assert result["scope"]["reviewer_comment_count"] == 1
    assert topic(result, "naming")["comment_count"] == 1


def test_한_PR에서_같은_주제를_여러_번_지적받아도_PR_수는_1이다(db):
    db.pr(1, "learner")
    db.comment(1, "reviewer", {"naming": 1})
    db.comment(1, "reviewer", {"naming": 1})

    naming = topic(db.ask(), "naming")

    assert naming["pr_count"] == 1
    assert naming["comment_count"] == 2


def test_PR_수가_많은_순이고_같으면_코멘트가_많은_순이다(db):
    for number in (1, 2, 3):
        db.pr(number, f"learner{number}")
    db.comment(1, "reviewer", {"naming": 1})
    db.comment(1, "reviewer", {"responsibility": 1})
    db.comment(2, "reviewer", {"responsibility": 1})
    db.comment(2, "reviewer", {"testability": 1})
    db.comment(3, "reviewer", {"testability": 1})
    db.comment(3, "reviewer", {"testability": 1})

    result = db.ask()

    assert [t["id"] for t in result["topics"]] == ["testability", "responsibility", "naming"]


def test_비율의_분모는_리뷰받은_PR_수다(db):
    db.pr(1, "learner1")
    db.pr(2, "learner2")
    db.pr(3, "learner3")  # 리뷰가 없는 PR
    db.comment(1, "reviewer", {"naming": 1})
    db.comment(2, "reviewer")

    result = db.ask()

    assert result["scope"]["pr_count"] == 3
    assert result["scope"]["reviewed_pr_count"] == 2
    assert topic(result, "naming")["pr_ratio"] == 0.5


def test_authors를_주면_그_사람들의_PR만_본다(db):
    db.pr(1, "Learner-One")
    db.pr(2, "learner-two")
    db.comment(1, "reviewer", {"naming": 1})
    db.comment(2, "reviewer", {"responsibility": 1})

    result = db.ask(authors=["learner-one"])  # 대소문자가 달라도 찾는다

    assert result["scope"]["pr_count"] == 1
    assert [t["id"] for t in result["topics"]] == ["naming"]


def test_PR이_없는_ID는_authors_not_found에_나온다(db):
    db.pr(1, "learner")
    db.comment(1, "reviewer", {"naming": 1})

    result = db.ask(authors=["learner", "tpyo-id"])

    assert result["scope"]["authors_requested"] == 2
    assert result["scope"]["authors_not_found"] == ["tpyo-id"]


def test_한_문자열에_ID_여러_개가_들어와도_나눠서_찾는다(db):
    db.pr(1, "learner-one")
    db.pr(2, "learner-two")
    db.comment(1, "reviewer", {"naming": 1})
    db.comment(2, "reviewer", {"naming": 1})

    result = db.ask(authors=["@learner-one, learner-two typo-id"])

    assert result["scope"]["authors_requested"] == 3
    assert result["scope"]["pr_count"] == 2
    assert result["scope"]["authors_not_found"] == ["typo-id"]


def test_authors를_주면_전체_비율이_채워지고_안_주면_비어_있다(db):
    for number in (1, 2, 3, 4):
        db.pr(number, f"learner{number}")
        db.comment(number, "reviewer", {"naming": 1} if number <= 3 else None)

    narrowed = db.ask(authors=["learner1"])
    everyone = db.ask()

    assert topic(narrowed, "naming")["pr_ratio"] == 1.0
    assert topic(narrowed, "naming")["overall_pr_ratio"] == 0.75
    assert topic(everyone, "naming")["overall_pr_ratio"] is None


def test_since를_주면_그_날짜_이후에_만든_PR만_본다(db):
    db.pr(1, "learner", created_at="2025-03-01T00:00:00Z")
    db.pr(2, "learner", created_at="2026-03-01T00:00:00Z")
    db.comment(1, "reviewer", {"naming": 1})
    db.comment(2, "reviewer", {"responsibility": 1})

    result = db.ask(since=date(2026, 1, 1))

    assert result["scope"]["pr_count"] == 1
    assert [t["id"] for t in result["topics"]] == ["responsibility"]


def test_조건에_맞는_PR이_없으면_빈_결과를_돌려준다(db):
    db.pr(1, "learner")
    db.comment(1, "reviewer", {"naming": 1})

    result = db.ask(authors=["nobody"])

    assert result["scope"]["pr_count"] == 0
    assert result["scope"]["authors_not_found"] == ["nobody"]
    assert result["topics"] == []


def test_대표_리뷰는_서로_다른_PR에서_점수가_큰_순으로_고른다(db):
    for number in (1, 2, 3):
        db.pr(number, f"learner{number}")
    db.comment(1, "reviewer", {"naming": 5})
    best_of_pr1 = db.comment(1, "reviewer", {"naming": 9})
    best_of_pr2 = db.comment(2, "reviewer", {"naming": 7})
    db.comment(3, "reviewer", {"naming": 1})

    examples = topic(db.ask(examples_per_topic=2), "naming")["examples"]

    assert [e["pr"] for e in examples] == [1, 2]
    assert examples[0]["url"].endswith(f"#discussion_r{best_of_pr1}")
    assert examples[1]["url"].endswith(f"#discussion_r{best_of_pr2}")


def test_대표_리뷰는_다른_주제에서_쓰지_않은_PR을_먼저_고른다(db):
    db.pr(1, "learner1")
    db.pr(2, "learner2")
    db.comment(1, "reviewer", {"naming": 9, "responsibility": 9})
    db.comment(1, "reviewer", {"naming": 1})  # naming이 PR 수는 같고 코멘트가 많아 먼저 온다
    db.comment(2, "reviewer", {"naming": 1, "responsibility": 1})

    result = db.ask(examples_per_topic=1)

    assert [e["pr"] for e in topic(result, "naming")["examples"]] == [1]
    assert [e["pr"] for e in topic(result, "responsibility")["examples"]] == [2]


def test_쓰지_않은_PR이_모자라면_이미_쓴_PR에서도_고른다(db):
    db.pr(1, "learner1")
    db.comment(1, "reviewer", {"naming": 1, "responsibility": 1})
    db.comment(1, "reviewer", {"naming": 1})

    result = db.ask(examples_per_topic=1)

    assert [e["pr"] for e in topic(result, "responsibility")["examples"]] == [1]


def test_대표_리뷰는_300자_이하이고_링크와_작성자와_리뷰어와_파일이_있다(db):
    db.pr(1, "learner")
    db.comment(1, "reviewer", {"naming": 1}, body="가" * 1000)

    example = topic(db.ask(), "naming")["examples"][0]

    assert len(example["excerpt"]) == 300
    assert example["url"] == "https://github.com/owner/repo/pull/1#discussion_r1"
    assert example["author"] == "learner"
    assert example["reviewer"] == "reviewer"
    assert example["path"] == "Car.java"


def test_대표_리뷰에서_인용한_줄은_빼고_빈_줄과_이어진_공백은_줄인다(db):
    db.pr(1, "learner")
    db.comment(1, "reviewer", {"naming": 1}, body="> 이름을 어떻게 지으면 좋을까요?\r\n\r\n\r\n역할이 드러나게      지어 보세요.\r\n\r\n\r\n예를 들면 이렇습니다.")

    example = topic(db.ask(), "naming")["examples"][0]

    assert example["excerpt"] == "역할이 드러나게 지어 보세요.\n\n예를 들면 이렇습니다."


def test_30자_미만인_리뷰는_대표가_되지_않는다(db):
    db.pr(1, "learner")
    db.comment(1, "reviewer", {"naming": 9}, body="이름 변경!")

    naming = topic(db.ask(), "naming")

    assert naming["pr_count"] == 1
    assert naming["examples"] == []


def test_examples_per_topic이_0이면_대표_리뷰를_붙이지_않는다(db):
    db.pr(1, "learner")
    db.comment(1, "reviewer", {"naming": 1})

    assert topic(db.ask(examples_per_topic=0), "naming")["examples"] == []


def test_max_topics개까지만_돌려준다(db):
    db.pr(1, "learner")
    db.comment(1, "reviewer", {"naming": 1, "responsibility": 1, "testability": 1})

    assert len(db.ask(max_topics=2)["topics"]) == 2


def test_세부_지적은_개념의_subtopics에_나온다(db):
    db.pr(1, "learner")
    db.comment(1, "reviewer", {"testability": 1, "random-inherit": 1})

    result = db.ask()

    assert [t["id"] for t in result["topics"]] == ["testability"]
    assert topic(result, "testability")["subtopics"] == [
        {"id": "random-inherit", "name": "Random을 상속해서 테스트", "pr_count": 1}
    ]


def test_주제가_붙지_않은_리뷰어_코멘트_수와_세는_방법을_알려준다(db):
    db.pr(1, "learner")
    db.comment(1, "reviewer", {"naming": 1})
    db.comment(1, "reviewer")
    db.comment(1, "learner")  # 작성자 답글은 대상이 아니다

    counting = db.ask()["counting"]

    assert counting["method"] == "keyword"
    assert counting["untagged_comment_count"] == 1
    assert "1개" in counting["note"]


def test_data_as_of는_마지막으로_수집한_시각이다(db):
    db.pr(1, "learner")

    assert db.ask()["scope"]["data_as_of"] == SYNCED_AT


def test_데이터가_없는_미션이면_알려준다(db):
    with pytest.raises(ValueError, match="없는 미션"):
        get_repeated_feedback(db.conn, "unknown-mission")
