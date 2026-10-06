"""지원하는 미션. 미션을 추가할 때 MissionId와 MISSIONS를 함께 고친다."""

from dataclasses import dataclass
from typing import Literal

# 도구가 입력으로 받는 값. 도구의 입력 스키마에 그대로 드러난다.
MissionId = Literal["java-racingcar"]


@dataclass(frozen=True)
class Mission:
    id: str
    repo: str
    name: str


MISSIONS = {
    mission.id: mission
    for mission in (
        Mission(
            id="java-racingcar",
            repo="next-step/java-racingcar-simple-playground",
            name="자바 자동차 경주",
        ),
    )
}
