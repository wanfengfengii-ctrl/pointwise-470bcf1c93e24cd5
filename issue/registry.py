import sqlite3
from uuid import uuid4

from issue.envelope import encode_v1


class IssueRegistry:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS issued_piece (
                issue_id TEXT PRIMARY KEY NOT NULL,
                batch_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                site TEXT NOT NULL,
                original BLOB NOT NULL,
                FOREIGN KEY (batch_id, revision) REFERENCES batch_snapshot (batch_id, revision)
            )
        """)

    def publish(self, body: dict[str, object]) -> bytes:
        issue_id = uuid4().hex
        raw = encode_v1(issue_id, body)
        self.connection.execute("BEGIN IMMEDIATE")
        with self.connection:
            self.connection.execute(
                "INSERT INTO issued_piece (issue_id, batch_id, revision, site, original) VALUES (?, ?, ?, ?, ?)",
                (issue_id, body["batch_id"], body["revision"], body["site"], raw),
            )
        return raw

    def get_original(self, issue_id: str) -> bytes:
        row = self.connection.execute(
            "SELECT original FROM issued_piece WHERE issue_id = ?", (issue_id,)
        ).fetchone()
        if row is None:
            raise KeyError(issue_id)
        return row[0]
