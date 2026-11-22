import sqlite3
from uuid import uuid4

from batch.import_rows import ArchiveRow
from batch.manifest import Manifest, build_manifest
from batch.revisions import BatchRevisionId, FrozenBatch, build_frozen_batch
from station.revisions import GraphRevisionId


class BatchStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS batch_snapshot (
                batch_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                freeze_id TEXT NOT NULL UNIQUE,
                demand INTEGER NOT NULL CHECK (demand >= 0),
                sender_site TEXT NOT NULL,
                sender_revision INTEGER NOT NULL,
                receiver_site TEXT NOT NULL,
                receiver_revision INTEGER NOT NULL,
                PRIMARY KEY (batch_id, revision),
                FOREIGN KEY (sender_site, sender_revision) REFERENCES station_revision (site, revision),
                FOREIGN KEY (receiver_site, receiver_revision) REFERENCES station_revision (site, revision),
                CHECK (sender_site <> receiver_site)
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS archive_block (
                batch_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                line_number INTEGER NOT NULL,
                block_id TEXT NOT NULL,
                locator TEXT NOT NULL,
                PRIMARY KEY (batch_id, revision, line_number),
                UNIQUE (batch_id, revision, block_id),
                FOREIGN KEY (batch_id, revision) REFERENCES batch_snapshot (batch_id, revision)
            )
        """)

    def insert_snapshot(
        self,
        batch_id: str,
        manifest: Manifest,
        sender: GraphRevisionId,
        receiver: GraphRevisionId,
    ) -> FrozenBatch:
        manifest = build_manifest(manifest.rows)
        self.connection.execute("BEGIN IMMEDIATE")
        with self.connection:
            previous, = self.connection.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM batch_snapshot WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
            key = BatchRevisionId(batch_id, previous + 1)
            snapshot = build_frozen_batch(key, uuid4().hex, manifest, sender, receiver)
            self.connection.execute(
                """INSERT INTO batch_snapshot
                   (batch_id, revision, freeze_id, demand, sender_site, sender_revision,
                    receiver_site, receiver_revision) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (key.batch_id, key.revision, snapshot.freeze_id, snapshot.demand,
                 sender.site, sender.revision, receiver.site, receiver.revision),
            )
            self.connection.executemany(
                """INSERT INTO archive_block (batch_id, revision, line_number, block_id, locator)
                   VALUES (?, ?, ?, ?, ?)""",
                ((key.batch_id, key.revision, row.line_number, row.block_id, row.locator)
                 for row in manifest.rows),
            )
        return snapshot

    def get(self, key: BatchRevisionId) -> FrozenBatch:
        identity = (key.batch_id, key.revision)
        snapshot = self.connection.execute(
            """SELECT freeze_id, demand, sender_site, sender_revision, receiver_site, receiver_revision
               FROM batch_snapshot WHERE batch_id = ? AND revision = ?""",
            identity,
        ).fetchone()
        if snapshot is None:
            raise KeyError(f"unknown batch revision {key!r}")
        freeze_id, demand, sender_site, sender_revision, receiver_site, receiver_revision = snapshot
        rows = self.connection.execute(
            """SELECT line_number, block_id, locator FROM archive_block
               WHERE batch_id = ? AND revision = ? ORDER BY line_number""",
            identity,
        )
        manifest = build_manifest(ArchiveRow(*row) for row in rows)
        if manifest.demand != demand:
            raise ValueError(f"stored manifest disagrees with demand for {key!r}")
        return build_frozen_batch(
            key, freeze_id, manifest,
            GraphRevisionId(sender_site, sender_revision),
            GraphRevisionId(receiver_site, receiver_revision),
        )
