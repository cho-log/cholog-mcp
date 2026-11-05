"""사람이 검수한 채점표(md)의 정답 칸과 DB의 keyword 분류 결과를 비교한다.

    uv run python -m scripts.score_labels "채점표.md"
    uv run python -m scripts.score_labels "채점표.md" --sample data/labels/java-lotto-sample.json --db data/cholog.db

채점표의 표 행은 `| 번호 | PR | 파일 | 원문 | 정답 | AI 근거 |`이고, 번호 n은 표본 파일
comment_ids의 n번째 코멘트다. 정답 칸은 개념 id를 쉼표로 나눠 적고, 주제가 없으면 `없음`,
사전에 없는 지적은 `사전에 없음: 설명`으로 적는다.
"""

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.tagger import METHOD
from pipeline.topics import CONCEPTS

NONE = "없음"
UNKNOWN_PREFIX = "사전에 없음"
ROW = re.compile(r"^\|\s*(\d+)\s*\|")
ANSWER_COLUMN = 5  # "| 번호 | PR | 파일 | 원문 | 정답 | AI 근거 |"를 |로 나누면 정답은 5번째

NO_TOPIC, CORRECT, MISSED, WRONG = "원래 주제 없음", "맞음", "놓침", "잘못 붙음"


@dataclass(frozen=True)
class Answer:
    concepts: frozenset[str]
    unknowns: tuple[str, ...] = ()


@dataclass
class Judgement:
    missed: set[str] = field(default_factory=set)  # 사전에 있는데 키워드가 못 잡은 개념
    unknowns: tuple[str, ...] = ()  # 사전에 없어서 못 잡은 지적
    wrong: set[str] = field(default_factory=set)

    @property
    def labels(self) -> list[str]:
        """코멘트가 들어가는 칸. 놓침과 잘못 붙음은 함께 들어갈 수 있다."""
        found = []
        if self.missed or self.unknowns:
            found.append(MISSED)
        if self.wrong:
            found.append(WRONG)
        return found


def parse_answer(cell: str, concept_ids: set[str]) -> Answer:
    concepts, unknowns = set(), []
    for item in (part.strip() for part in cell.split(",")):
        if not item or item == NONE:
            continue
        if item.startswith(UNKNOWN_PREFIX):
            unknowns.append(item.split(":", 1)[1].strip() if ":" in item else "")
        elif item in concept_ids:
            concepts.add(item)
        else:
            raise ValueError(f"사전에 없는 개념 id: {item!r}")
    return Answer(frozenset(concepts), tuple(unknowns))


def read_answers(md: str, concept_ids: set[str]) -> dict[int, Answer]:
    answers = {}
    for line in md.splitlines():
        match = ROW.match(line)
        if not match:
            continue
        cells = line.split("|")
        number = int(match.group(1))
        try:
            answers[number] = parse_answer(cells[ANSWER_COLUMN], concept_ids)
        except (IndexError, ValueError) as error:
            raise ValueError(f"{number}번 행: {error}") from error
    return answers


def judge(answer: Answer, predicted: set[str]) -> Judgement:
    return Judgement(
        missed=set(answer.concepts) - predicted,
        unknowns=answer.unknowns,
        wrong=predicted - answer.concepts,
    )


def category(answer: Answer, judgement: Judgement) -> str | None:
    """놓침·잘못 붙음이 없을 때의 칸. 있으면 None."""
    if judgement.labels:
        return None
    return NO_TOPIC if not answer.concepts else CORRECT


def predicted_topics(conn: sqlite3.Connection, comment_id: int, concept_ids: set[str]) -> set[str]:
    rows = conn.execute(
        "SELECT topic_id FROM comment_topics WHERE comment_id = ? AND method = ?",
        (comment_id, METHOD),
    )
    # 세부 지적은 미션마다 다르므로 개념끼리만 비교한다.
    return {topic_id for (topic_id,) in rows if topic_id in concept_ids}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("labels", type=Path, help="검수한 채점표 md 파일")
    parser.add_argument("--sample", type=Path, default=Path("data/labels/java-lotto-sample.json"))
    parser.add_argument("--db", type=Path, default=Path("data/cholog.db"))
    args = parser.parse_args()

    concept_ids = {concept.id for concept in CONCEPTS}
    comment_ids = json.loads(args.sample.read_text())["comment_ids"]
    answers = read_answers(args.labels.read_text(), concept_ids)
    if sorted(answers) != list(range(1, len(comment_ids) + 1)):
        sys.exit(f"채점표 행 번호가 표본({len(comment_ids)}개)과 맞지 않는다")

    conn = sqlite3.connect(args.db)
    cells = Counter()
    both = 0
    missed_known = missed_unknown = 0
    missed_by_concept, wrong_by_concept, unknown_reasons = Counter(), Counter(), Counter()
    for number, comment_id in enumerate(comment_ids, 1):
        answer = answers[number]
        judgement = judge(answer, predicted_topics(conn, comment_id, concept_ids))
        if (single := category(answer, judgement)) is not None:
            cells[single] += 1
        for label in judgement.labels:
            cells[label] += 1
        if len(judgement.labels) == 2:
            both += 1
        missed_known += len(judgement.missed)
        missed_unknown += len(judgement.unknowns)
        missed_by_concept.update(judgement.missed)
        wrong_by_concept.update(judgement.wrong)
        unknown_reasons.update(judgement.unknowns)

    print(f"코멘트 {len(comment_ids)}개")
    for name in (NO_TOPIC, CORRECT, MISSED, WRONG):
        print(f"  {name}: {cells[name]}")
    print(f"  둘 다 (놓침이면서 잘못 붙음): {both}  ※ 놓침·잘못 붙음에 각각 들어가 있다")
    print(f"\n놓친 주제 {missed_known + missed_unknown}건")
    print(f"  사전에 있는데 키워드가 못 잡음: {missed_known}")
    print(f"  사전에 없어서 못 잡음: {missed_unknown}")
    for title, counter in (("놓침", missed_by_concept), ("잘못 붙음", wrong_by_concept),
                           ("사전에 없음", unknown_reasons)):
        print(f"\n{title} 많은 순")
        for key, count in counter.most_common():
            print(f"  {key}: {count}")


if __name__ == "__main__":
    main()
