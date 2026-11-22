import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from batch.freeze import freeze_batch
from demo import graph_from_sample, load_sample, night_stores, source_stores
from issue.publish import issue_station
from receive.admit import accept_piece
from report.sign import sign_capacity
from station.online_check import online_check


CASES = (
    ("shared", "receiver", 1),
    ("independent", "receiver", 2),
    ("relay_sender", "relay_receiver", 1),
    ("relay_sender", "relay_receiver_broken", 0),
)


def run_incident(directory: Path) -> int:
    sample = load_sample()
    source = directory / "source.sqlite"
    prepared = []
    with closing(sqlite3.connect(source)) as db:
        stations, batches, registry = source_stores(db)
        for sender_name, receiver_name, expected in CASES:
            sender = stations.register(graph_from_sample(sample["graphs"][sender_name]))
            receiver = stations.register(graph_from_sample(sample["graphs"][receiver_name]))
            key = freeze_batch(batches, stations, sample["batch_id"], sample["archive_rows"][:2], sender, receiver)
            online = online_check(batches, stations, key)
            if online != expected:
                raise AssertionError(f"unexpected online reference for {sender_name}/{receiver_name}: {online}")
            originals = tuple(issue_station(batches, stations, registry, key, site)
                              for site in (sender.site, receiver.site))
            prepared.append((originals, online))
    source.rename(directory / "source.offline")
    if source.exists():
        raise AssertionError("source is still present at its original path")

    signed = []
    with closing(sqlite3.connect(directory / "intake.sqlite")) as intake, closing(
        sqlite3.connect(directory / "reports.sqlite")
    ) as reports:
        receipts, archive = night_stores(intake, reports)
        for (sender_name, receiver_name, expected), (originals, online) in zip(CASES, prepared, strict=True):
            left, right = (accept_piece(receipts, raw) for raw in originals)
            report = sign_capacity(receipts, archive, right.receipt_id, left.receipt_id)
            wanted = [(item.receipt_id, item.piece.issue_id, item.piece.freeze_id) for item in (left, right)]
            origins = [(item.receipt_id, item.issue_id, item.freeze_id) for item in report.origins]
            if origins != wanted:
                raise AssertionError(f"report origins differ from actual receipts: {origins!r}")
            print(f"{sender_name}/{receiver_name}: online={online} signed={report.blocks} expected={expected}")
            signed.append(report.blocks)

    if signed[0] > CASES[0][2]:
        print("OFFLINE_CAPACITY_OVERSTATED")
    if signed[2] < CASES[2][2]:
        print("OFFLINE_RETURN_PATH_UNDERSTATED")
    return int(any(actual != case[2] for actual, case in zip(signed, CASES, strict=True)))


if __name__ == "__main__":
    with TemporaryDirectory(prefix="archive-incident-") as temporary:
        raise SystemExit(run_incident(Path(temporary)))
