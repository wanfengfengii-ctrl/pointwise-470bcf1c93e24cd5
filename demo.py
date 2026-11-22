import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from batch.freeze import freeze_batch
from batch.storage import BatchStore
from issue.envelope import decode_v1
from issue.publish import issue_station
from issue.registry import IssueRegistry
from issue.reissue import reissue_station
from receive.admit import accept_piece
from receive.receipts import ReceiptStore
from report.archive import ReportArchive
from report.readback import read_report
from report.sign import sign_capacity
from station.online_check import online_check
from station.ports import PortBinding
from station.revisions import StationRevisionStore
from station.topology import DirectedLink, StationGraph, build_station_graph


def load_sample() -> dict:
    path = Path(__file__).resolve().parent / "samples" / "shift.json"
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def graph_from_sample(data: dict) -> StationGraph:
    return build_station_graph(
        data["site"], data["terminal"], data["nodes"],
        (DirectedLink(*link) for link in data["links"]),
        (PortBinding(*port) for port in data["ports"]),
    )


def source_stores(connection: sqlite3.Connection) -> tuple[StationRevisionStore, BatchStore, IssueRegistry]:
    stations = StationRevisionStore(connection)
    batches = BatchStore(connection)
    registry = IssueRegistry(connection)
    for store in (stations, batches, registry):
        store.initialize()
    return stations, batches, registry


def night_stores(intake: sqlite3.Connection, reports: sqlite3.Connection) -> tuple[ReceiptStore, ReportArchive]:
    receipts = ReceiptStore(intake)
    archive = ReportArchive(reports)
    receipts.initialize()
    archive.initialize()
    return receipts, archive


def run_demo(directory: Path) -> None:
    sample = load_sample()
    source = directory / "source.sqlite"
    parked = directory / "source.offline"
    intake = directory / "intake.sqlite"
    reports = directory / "reports.sqlite"
    old_and_new = []
    online_values = []
    issued_indexes = []
    reissued_unchanged = False

    for profile, expected in (("shared", 1), ("independent", 2)):
        with closing(sqlite3.connect(source)) as connection:
            stations, batches, registry = source_stores(connection)
            sending = stations.register(graph_from_sample(sample["graphs"][profile]))
            if profile == "shared":
                receiving = stations.register(graph_from_sample(sample["graphs"]["receiver"]))
            key = freeze_batch(batches, stations, sample["batch_id"], sample["archive_rows"], sending, receiving)
            online = online_check(batches, stations, key)
            sender_bytes = issue_station(batches, stations, registry, key, sending.site)
            receiver_bytes = issue_station(batches, stations, registry, key, receiving.site)
            issue_id = decode_v1(sender_bytes).issue_id
            reissued_unchanged = reissue_station(registry, issue_id) == sender_bytes
            if online != expected or not reissued_unchanged:
                raise AssertionError(f"unexpected white-shift result for {profile}: {online}")
            online_values.append(online)
            issued_indexes.append((key.revision, sending.revision))

        source.rename(parked)
        with closing(sqlite3.connect(intake)) as inbox, closing(sqlite3.connect(reports)) as outbox:
            receipts, archive = night_stores(inbox, outbox)
            left = accept_piece(receipts, sender_bytes)
            right = accept_piece(receipts, receiver_bytes)
            report = sign_capacity(receipts, archive, right.receipt_id, left.receipt_id)
            expected_origins = [(item.receipt_id, item.piece.issue_id) for item in (left, right)]
            origins = [(item.receipt_id, item.issue_id) for item in report.origins]
            if report.blocks != expected or origins != expected_origins:
                raise AssertionError(f"unexpected signed result for {profile}: {report.blocks}")
            old_and_new.append(report)
        if profile == "shared":
            parked.rename(source)

    with closing(sqlite3.connect(intake)) as inbox, closing(sqlite3.connect(reports)) as outbox:
        receipts, archive = night_stores(inbox, outbox)
        read_back = [read_report(archive, item.report_id) for item in old_and_new]
        if read_back != old_and_new or source.exists():
            raise AssertionError("historical readback changed after the source went offline")
        for report in read_back:
            for origin in report.origins:
                receipt = receipts.fetch(origin.receipt_id)
                if receipt is None or receipt.piece.issue_id != origin.issue_id:
                    raise AssertionError("report origin differs from the actual receipt")

    corrected = read_back[1]
    print("POINTWISE_SCENARIO " + json.dumps({
        "case_id": "v1",
        "input": {"demand": len(sample["archive_rows"]), "sender": sample["graphs"]["independent"],
                  "receiver": sample["graphs"]["receiver"]},
        "expected": 2,
        "actual": online_values[1],
        "downstream_expected": {"original_reissue": True, "signed_blocks": 2},
        "downstream_actual": {"original_reissue": reissued_unchanged, "signed_blocks": corrected.blocks},
        "code_paths": ["batch/freeze.py", "station/online_check.py", "issue/publish.py",
                       "issue/reissue.py", "report/sign.py"],
        "oracle": "Two disjoint unit paths reach the receiver, and the saved issue is compared byte for byte."
    }, sort_keys=True))
    print("POINTWISE_SCENARIO " + json.dumps({
        "case_id": "v9",
        "input": {"profiles": ["shared", "independent"], "batch_and_station_revisions": issued_indexes,
                  "report_ids": [item.report_id for item in old_and_new]},
        "expected": [1, 2],
        "actual": [item.blocks for item in old_and_new],
        "downstream_expected": {"blocks": [1, 2], "same_snapshots": True},
        "downstream_actual": {"blocks": [item.blocks for item in read_back],
                              "same_snapshots": read_back == old_and_new},
        "code_paths": ["batch/storage.py", "station/revisions.py", "report/archive.py", "report/readback.py"],
        "oracle": "A shared unit link limits the old revision. Two disjoint unit paths serve the new one."
    }, sort_keys=True))
    for report in read_back:
        receipt_ids = [origin.receipt_id for origin in report.origins]
        print(f"Report {report.report_id}, revision {report.revision}: {report.blocks} blocks, "
              f"receipts {receipt_ids}, acknowledgment {report.acknowledgment}")


if __name__ == "__main__":
    with TemporaryDirectory(prefix="archive-exchange-") as temporary:
        run_demo(Path(temporary))
