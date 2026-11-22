from batch.revisions import BatchRevisionId
from batch.storage import BatchStore
from station.flow import max_flow
from station.ports import match_port_names
from station.revisions import StationRevisionStore
from station.topology import StationGraph

NetworkNode = tuple[int, str]
NetworkArc = tuple[NetworkNode, NetworkNode, int]


def compose_station_network(
    sending: StationGraph, receiving: StationGraph, demand: int
) -> tuple[list[NetworkArc], NetworkNode, NetworkNode]:
    pairs = match_port_names(sending.ports, receiving.ports)
    arcs = []
    for side, graph in enumerate((sending, receiving)):
        arcs.extend(((side, link.start), (side, link.end), link.capacity) for link in graph.links)
    # A transfer edge of capacity demand enforces a shared port in every cut below demand.
    for left, right in pairs:
        left_node, right_node = (0, left.node), (1, right.node)
        arcs.append((left_node, right_node, demand))
        arcs.append((right_node, left_node, demand))
    return arcs, (0, sending.terminal), (1, receiving.terminal)


def online_check(batches: BatchStore, stations: StationRevisionStore, key: BatchRevisionId) -> int:
    batch = batches.get(key)
    sending = stations.get(batch.sender)
    receiving = stations.get(batch.receiver)
    arcs, source, sink = compose_station_network(sending, receiving, batch.demand)
    return max_flow(arcs, source, sink, batch.demand)
