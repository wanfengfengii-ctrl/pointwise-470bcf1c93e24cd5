from collections.abc import Iterable, Mapping

from batch.import_rows import parse_archive_rows
from batch.manifest import build_manifest
from batch.revisions import BatchRevisionId
from batch.storage import BatchStore
from station.revisions import GraphRevisionId, StationRevisionStore


def freeze_batch(
    batches: BatchStore,
    stations: StationRevisionStore,
    batch_id: str,
    rows: Iterable[Mapping[str, object]],
    sender: GraphRevisionId,
    receiver: GraphRevisionId,
) -> BatchRevisionId:
    manifest = build_manifest(parse_archive_rows(rows))
    stations.get(sender)
    stations.get(receiver)
    snapshot = batches.insert_snapshot(batch_id, manifest, sender, receiver)
    return snapshot.key
