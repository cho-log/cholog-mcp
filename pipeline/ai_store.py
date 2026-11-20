"""AI 분류 고정본 파일 (pipeline/ai_topics/<mission>.json).

AI는 같은 코멘트도 돌릴 때마다 조금씩 다르게 분류한다. 그래서 한 번 돌린 결과를 파일로 고정하고,
tag는 AI를 다시 부르지 않고 이 파일을 읽는다.

- 키는 (kind, github_id)다. comments.id는 적재 방식에 따라 바뀔 수 있어서 쓰지 않는다.
- 값은 개념·세부 지적 id 목록이다. 빈 목록은 "AI가 보고 주제 없음으로 판단했다"는 뜻이다.
- 리뷰 원문은 넣지 않는다 (공개 저장소).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

AI_TOPICS_DIR = Path(__file__).parent / "ai_topics"

Key = tuple[str, int]


@dataclass
class AiTopics:
    mission_id: str
    classified_at: str
    model: str
    prompt_version: str
    concepts_version: str
    topics: dict[Key, list[str]] = field(default_factory=dict)


def ai_topics_path(mission_id: str, directory: Path = AI_TOPICS_DIR) -> Path:
    return directory / f"{mission_id}.json"


def load_ai_topics(mission_id: str, directory: Path = AI_TOPICS_DIR) -> AiTopics | None:
    """미션의 고정본을 읽는다. 파일이 없으면 None."""
    path = ai_topics_path(mission_id, directory)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    topics = {}
    for key, topic_ids in data["topics"].items():
        kind, github_id = key.split(":")
        topics[(kind, int(github_id))] = list(topic_ids)
    return AiTopics(
        mission_id=data["mission_id"],
        classified_at=data["classified_at"],
        model=data["model"],
        prompt_version=data["prompt_version"],
        concepts_version=data["concepts_version"],
        topics=topics,
    )


def save_ai_topics(ai_topics: AiTopics, directory: Path = AI_TOPICS_DIR) -> Path:
    """고정본을 쓴다. 코멘트 하나를 한 줄에 써서 다시 분류했을 때 차이를 보기 쉽게 한다."""
    path = ai_topics_path(ai_topics.mission_id, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "mission_id": ai_topics.mission_id,
        "classified_at": ai_topics.classified_at,
        "model": ai_topics.model,
        "prompt_version": ai_topics.prompt_version,
        "concepts_version": ai_topics.concepts_version,
    }
    lines = [f"  {json.dumps(name)}: {json.dumps(value, ensure_ascii=False)}," for name, value in header.items()]
    entries = [
        f"    {json.dumps(f'{kind}:{github_id}')}: {json.dumps(sorted(topic_ids))}"
        for (kind, github_id), topic_ids in sorted(ai_topics.topics.items())
    ]
    body = "{\n" + "\n".join(lines) + '\n  "topics": {\n' + ",\n".join(entries) + "\n  }\n}\n"
    path.write_text(body, encoding="utf-8")
    return path
