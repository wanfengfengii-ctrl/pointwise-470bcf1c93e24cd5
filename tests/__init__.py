import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from batch.freeze import freeze_batch
from demo import graph_from_sample, load_sample, night_stores, source_stores
from issue.publish import issue_station
from receive.admit import accept_piece
from station.online_check import online_check


class Exchange:
    def __init__(self, case):
        self.case = case
        self.directory = Path(case.enterContext(TemporaryDirectory(prefix="archive-test-")))
        self.source_path = self.directory / "source.sqlite"
        self.parked_path = self.directory / "source.offline"
        self.sample = load_sample()
        self.open_source()
        self.open_night()

    def _connect(self, path):
        connection = sqlite3.connect(path)
        self.case.addCleanup(connection.close)
        return connection

    def open_source(self):
        self.source = self._connect(self.source_path)
        self.stations, self.batches, self.registry = source_stores(self.source)

    def open_night(self):
        self.intake = self._connect(self.directory / "intake.sqlite")
        self.reports = self._connect(self.directory / "reports.sqlite")
        self.receipts, self.archive = night_stores(self.intake, self.reports)

    def reopen_night(self):
        self.intake.close()
        self.reports.close()
        self.open_night()

    def offline(self):
        self.source.close()
        self.source_path.rename(self.parked_path)
        self.case.assertFalse(self.source_path.exists())

    def restore_source(self):
        self.parked_path.rename(self.source_path)
        self.open_source()

    def graph(self, name):
        return graph_from_sample(self.sample["graphs"][name])

    def register(self, name):
        return self.stations.register(self.graph(name))

    def freeze(self, name, sender, receiver, rows=None):
        if rows is None:
            rows = self.sample["archive_rows"]
        return freeze_batch(self.batches, self.stations, name, rows, sender, receiver)

    def online(self, key):
        return online_check(self.batches, self.stations, key)

    def issue(self, key, site):
        return issue_station(self.batches, self.stations, self.registry, key, site)

    def issue_pair(self, key):
        batch = self.batches.get(key)
        return self.issue(key, batch.sender.site), self.issue(key, batch.receiver.site)

    def accept_pair(self, originals):
        return tuple(accept_piece(self.receipts, raw) for raw in originals)


def counts(connection, *tables):
    return tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables)


def reject_commit_after_insert(connection, table):
    # The trigger writes a deferred foreign-key violation. SQLite rejects the commit itself.
    connection.executescript(f"""
        CREATE TABLE test_allowed (id INTEGER PRIMARY KEY);
        CREATE TABLE test_pending (
            id INTEGER REFERENCES test_allowed(id) DEFERRABLE INITIALLY DEFERRED
        );
        CREATE TRIGGER test_reject AFTER INSERT ON {table}
        BEGIN
            INSERT INTO test_pending VALUES (1);
        END;
    """)
