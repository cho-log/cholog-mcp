"""AI 분류 고정본 파일 (pipeline/ai_topics/<mission>.json).

AI는 같은 코멘트도 돌릴 때마다 조금씩 다르게 분류한다. 그래서 한 번 돌린 결과를 파일로 고정하고,
tag는 AI를 다시 부르지 않고 이 파일을 읽는다.

- 키는 (kind, github_id)다. comments.id는 적재 방식에 따라 바뀔 수 있어서 쓰지 않는다.
- 값은 개념·세부 지적 id 목록과, 그 코멘트를 분류한 시각·프롬프트 버전·개념 목록 버전이다.
  빈 목록은 "AI가 보고 주제 없음으로 판단했다"는 뜻이다.
- 분류 시각은 날짜(2026-11-12)이거나 시각(2026-11-27T14:03:12+09:00)이다. 날짜만 있는 것은
  코멘트마다 버전을 남기기 전에 만든 항목이다.
- 리뷰 원문은 넣지 않는다 (공개 저장소).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

AI_TOPICS_DIR = Path(__file__).parent / "ai_topics"

Key = tuple[str, int]


@dataclass(frozen=True)
class Entry:
    topics: list[str]
    classified_at: str
    prompt_version: str
    concepts_version: str


@dataclass
class AiTopics:
    mission_id: str
    model: str
    entries: dict[Key, Entry] = field(default_factory=dict)

    @property
    def topics(self) -> dict[Key, list[str]]:
        return {key: entry.topics for key, entry in self.entries.items()}


def ai_topics_path(mission_id: str, directory: Path = AI_TOPICS_DIR) -> Path:
    return directory / f"{mission_id}.json"


def load_ai_topics(mission_id: str, directory: Path = AI_TOPICS_DIR) -> AiTopics | None:
    """미션의 고정본을 읽는다. 파일이 없으면 None.

    버전이 파일 머리에만 있는 옛 형식(값이 개념 id 목록)도 읽는다. 머리의 값을 각 코멘트에 붙인다.
    """
    path = ai_topics_path(mission_id, directory)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = {}
    for key, value in data["topics"].items():
        kind, github_id = key.split(":")
        if isinstance(value, list):
            value = {"topics": value, "classified_at": data["classified_at"],
                     "prompt_version": data["prompt_version"], "concepts_version": data["concepts_version"]}
        entries[(kind, int(github_id))] = Entry(
            topics=list(value["topics"]),
            classified_at=value["classified_at"],
            prompt_version=value["prompt_version"],
            concepts_version=value["concepts_version"],
        )
    return AiTopics(mission_id=data["mission_id"], model=data["model"], entries=entries)


def save_ai_topics(ai_topics: AiTopics, directory: Path = AI_TOPICS_DIR) -> Path:
    """고정본을 쓴다. 코멘트 하나를 한 줄에 써서 다시 분류했을 때 차이를 보기 쉽게 한다."""
    path = ai_topics_path(ai_topics.mission_id, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = {"mission_id": ai_topics.mission_id, "model": ai_topics.model}
    lines = [f"  {json.dumps(name)}: {json.dumps(value, ensure_ascii=False)}," for name, value in header.items()]
    entries = []
    for (kind, github_id), entry in sorted(ai_topics.entries.items()):
        value = {"topics": sorted(entry.topics), "classified_at": entry.classified_at,
                 "prompt_version": entry.prompt_version, "concepts_version": entry.concepts_version}
        entries.append(f"    {json.dumps(f'{kind}:{github_id}')}: {json.dumps(value, ensure_ascii=False)}")
    body = "{\n" + "\n".join(lines) + '\n  "topics": {\n' + ",\n".join(entries) + "\n  }\n}\n"
    path.write_text(body, encoding="utf-8")
    return path
