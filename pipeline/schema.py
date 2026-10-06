"""SQLite 테이블 정의. docs/tool-spec.md의 "데이터 구조"와 같아야 한다."""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS missions (
    id        TEXT PRIMARY KEY,
    repo      TEXT NOT NULL,
    name      TEXT NOT NULL,
    synced_at TEXT
);

CREATE TABLE IF NOT EXISTS pull_requests (
    mission_id TEXT NOT NULL REFERENCES missions(id),
    number     INTEGER NOT NULL,
    author     TEXT,
    title      TEXT NOT NULL,
    created_at TEXT NOT NULL,
    url        TEXT NOT NULL,
    PRIMARY KEY (mission_id, number)
);

CREATE TABLE IF NOT EXISTS comments (
    id           INTEGER PRIMARY KEY,
    mission_id   TEXT NOT NULL REFERENCES missions(id),
    pr_number    INTEGER NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN ('review', 'issue')),
    author       TEXT,
    is_pr_author INTEGER NOT NULL CHECK (is_pr_author IN (0, 1)),
    body         TEXT NOT NULL,
    path         TEXT,
    diff_hunk    TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    url          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topics (
    id         TEXT PRIMARY KEY,
    parent_id  TEXT REFERENCES topics(id),
    mission_id TEXT REFERENCES missions(id),
    name       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS comment_topics (
    comment_id INTEGER NOT NULL REFERENCES comments(id),
    topic_id   TEXT NOT NULL REFERENCES topics(id),
    method     TEXT NOT NULL,
    score      INTEGER NOT NULL,
    PRIMARY KEY (comment_id, topic_id)
);

CREATE INDEX IF NOT EXISTS idx_comments_pr ON comments (mission_id, pr_number);
CREATE INDEX IF NOT EXISTS idx_comment_topics_topic ON comment_topics (topic_id);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
