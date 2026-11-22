from dataclasses import dataclass

from batch.revisions import BatchRevisionId, FrozenBatch
from station.flow import max_flow
from station.topology import StationGraph


@dataclass(frozen=True, slots=True)
class StationEvidence:
    batch: BatchRevisionId
    freeze_id: str
    site: str
    sender: str
    receiver: str
    demand: int
    ports: tuple[str, ...]
    port_limits: tuple[int, ...]

    def to_body(self) -> dict[str, object]:
        return {
            "batch_id": self.batch.batch_id,
            "revision": self.batch.revision,
            "freeze_id": self.freeze_id,
            "site": self.site,
            "sender": self.sender,
            "receiver": self.receiver,
            "demand": self.demand,
            "ports": list(self.ports),
            "capacity": {"scheme": "port-limit-v1", "limits": list(self.port_limits)},
        }


def build_station_evidence(batch: FrozenBatch, graph: StationGraph) -> StationEvidence:
    batch.reference_for(graph.site)
    demand = batch.demand
    sending = graph.site == batch.sender.site
    arcs = [(link.start, link.end, link.capacity) for link in graph.links]
    limits = []
    for port in graph.ports:
        start, end = (graph.terminal, port.node) if sending else (port.node, graph.terminal)
        limits.append(max_flow(arcs, start, end, demand))

    return StationEvidence(
        batch.key, batch.freeze_id, graph.site, batch.sender.site, batch.receiver.site,
        demand, tuple(port.name for port in graph.ports), tuple(limits),
    )
