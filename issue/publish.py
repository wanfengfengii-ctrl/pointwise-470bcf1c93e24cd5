from batch.revisions import BatchRevisionId
from batch.storage import BatchStore
from issue.evidence import build_station_evidence
from issue.registry import IssueRegistry
from station.revisions import StationRevisionStore


def issue_station(
    batches: BatchStore,
    stations: StationRevisionStore,
    registry: IssueRegistry,
    key: BatchRevisionId,
    site: str,
) -> bytes:
    batch = batches.get(key)
    graph = stations.get(batch.reference_for(site))
    return registry.publish(build_station_evidence(batch, graph).to_body())
