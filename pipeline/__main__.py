"""파이프라인 명령.

    uv run python -m pipeline fetch java-racingcar    GitHub에서 원본을 받는다
    uv run python -m pipeline load java-racingcar     원본을 SQLite에 넣는다
    uv run python -m pipeline tag java-racingcar      리뷰에 주제를 붙인다
    uv run python -m pipeline verify java-racingcar   기준값과 비교한다
    uv run python -m pipeline check java-racingcar    기본 점검을 한다 (배포 전)
"""

import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from cholog_mcp.config import db_path
from pipeline.check import print_check
from pipeline.fetch import fetch_mission
from pipeline.load import load_mission
from cholog_mcp.missions import MISSIONS
from pipeline.schema import create_schema
from pipeline.tagger import tag_mission
from pipeline.verify import verify_mission

RAW_ROOT = Path("data/raw")


def main() -> int:
    parser = argparse.ArgumentParser(prog="pipeline", description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("fetch", "load", "tag", "verify", "check"))
    parser.add_argument("mission", choices=sorted(MISSIONS))
    parser.add_argument("--only", type=int, nargs="+", metavar="PR", help="fetch: 이 PR의 코멘트만 받는다")
    parser.add_argument("--previous", type=Path, metavar="DB", help="check: 직전 DB와도 비교한다. 파일이 없으면 건너뛴다")
    args = parser.parse_args()

    mission = MISSIONS[args.mission]
    raw_dir = RAW_ROOT / mission.id

    if args.command == "fetch":
        count = fetch_mission(mission, raw_dir, args.only)
        print(f"PR {count}개의 코멘트를 {raw_dir}에 받았다")
        return 0

    if args.command == "check":
        return _check(mission.id, args.previous)

    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        create_schema(conn)
        if args.command == "load":
            loaded = load_mission(conn, mission, raw_dir)
            print(f"PR {loaded['pull_requests']}개, 코멘트 {loaded['comments']}개를 {path}에 넣었다")
            print("주제는 지워졌다. 이어서 tag를 실행한다")
        elif args.command == "tag":
            print(f"주제 {tag_mission(conn, mission.id)}개를 붙였다")
        elif args.command == "verify":
            return 0 if verify_mission(conn, mission.id) else 1
    finally:
        conn.close()
    return 0


def _open_read_only(path: Path) -> sqlite3.Connection:
    # 경로를 URI로 바꿀 때 #, ? 같은 글자가 섞여도 그대로 열리게 as_uri()를 쓴다.
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _check(mission_id: str, previous_path: Path | None) -> int:
    """점검은 읽기만 한다. DB가 없으면 새로 만들지 않고 실패한다."""
    path = db_path()
    if not path.exists():
        print(f"DB가 없다: {path}. load와 tag를 먼저 돌린다")
        return 1
    if previous_path is not None and not previous_path.exists():
        print(f"직전 DB가 없어서({previous_path}) 직전 비교는 건너뛴다")
        previous_path = None

    with closing(_open_read_only(path)) as conn:
        if previous_path is None:
            return 0 if print_check(conn, mission_id) else 1
        try:
            with closing(_open_read_only(previous_path)) as previous:
                return 0 if print_check(conn, mission_id, previous) else 1
        except sqlite3.DatabaseError as error:
            print(f"직전 DB를 읽을 수 없다({previous_path}): {error}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
