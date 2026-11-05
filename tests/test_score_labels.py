import pytest

from scripts.score_labels import CORRECT, MISSED, NO_TOPIC, WRONG, Answer, category, judge, parse_answer, read_answers

IDS = {"naming", "stream", "exception"}


def test_정답과_분류가_둘_다_없으면_원래_주제_없음():
    answer = parse_answer("없음", IDS)

    assert category(answer, judge(answer, set())) == NO_TOPIC


def test_정답과_분류가_같으면_맞음():
    answer = parse_answer("naming, stream", IDS)

    assert category(answer, judge(answer, {"stream", "naming"})) == CORRECT


def test_놓침과_잘못_붙음은_한_코멘트에서_함께_나온다():
    answer = parse_answer("naming", IDS)
    judgement = judge(answer, {"stream"})

    assert judgement.labels == [MISSED, WRONG]
    assert category(answer, judgement) is None


def test_사전에_없음은_놓침으로_세되_따로_모은다():
    answer = parse_answer("사전에 없음: 디미터 법칙", IDS)
    judgement = judge(answer, set())

    assert answer == Answer(frozenset(), ("디미터 법칙",))
    assert judgement.labels == [MISSED]
    assert judgement.missed == set()


def test_사전에_없는_개념_id는_막는다():
    with pytest.raises(ValueError):
        parse_answer("tda", IDS)


def test_표에서_정답_칸만_읽는다():
    md = "\n".join([
        "| 번호 | PR | 파일 | 원문 | 정답 | AI 근거 |",
        "|---|---|---|---|---|---|",
        "| 1 | 3 | A.java | 이름을 바꿔요 | naming | 네이밍 |",
        "| 2 | 4 | B.java | 👍 | 없음 | 칭찬 |",
    ])

    assert read_answers(md, IDS) == {1: Answer(frozenset({"naming"})), 2: Answer(frozenset())}
