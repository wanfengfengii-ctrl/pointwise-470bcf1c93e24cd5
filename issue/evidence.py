from dataclasses import dataclass

from batch.revisions import BatchRevisionId, FrozenBatch
from station.flow import max_flow
from station.ports import port_subsets
from station.topology import StationGraph


@dataclass(frozen=True, slots=True)
class SubsetCut:
    ports: tuple[str, ...]
    limit: int


@dataclass(frozen=True, slots=True)
class StationEvidence:
    batch: BatchRevisionId
    freeze_id: str
    site: str
    sender: str
    receiver: str
    demand: int
    ports: tuple[str, ...]
    cuts: tuple[SubsetCut, ...]

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
            "capacity": {
                "scheme": "port-cut-v2",
                "cuts": [{"ports": list(cut.ports), "limit": cut.limit} for cut in self.cuts],
            },
        }


def _boundary_limit(graph: StationGraph, sources: set[str], sinks: set[str], limit: int) -> int:
    # Synthetic endpoints cannot collide with station node names, which are plain strings.
    super_source, super_sink = object(), object()
    arcs = [(link.start, link.end, link.capacity) for link in graph.links]
    arcs.extend((super_source, node, limit) for node in sources)
    arcs.extend((node, super_sink, limit) for node in sinks)
    return max_flow(arcs, super_source, super_sink, limit)


def build_station_evidence(batch: FrozenBatch, graph: StationGraph) -> StationEvidence:
    batch.reference_for(graph.site)
    demand = batch.demand
    sending = graph.site == batch.sender.site
    node_of = {port.name: port.node for port in graph.ports}
    ports = tuple(port.name for port in graph.ports)
    cuts = []
    for subset in port_subsets(ports):
        kept = {node_of[name] for name in subset}
        rest = {node_of[name] for name in ports if name not in subset}
        if sending:
            sources, sinks = {graph.terminal} | kept, rest
        else:
            sources, sinks = kept, {graph.terminal} | rest
        cuts.append(SubsetCut(subset, _boundary_limit(graph, sources, sinks, demand)))
    return StationEvidence(
        batch.key, batch.freeze_id, graph.site, batch.sender.site, batch.receiver.site,
        demand, ports, tuple(cuts),
    )
