from collections.abc import Iterable
from dataclasses import dataclass

from station.ports import PortBinding, validate_ports


@dataclass(frozen=True, slots=True)
class DirectedLink:
    start: str
    end: str
    capacity: int


@dataclass(frozen=True, slots=True)
class StationGraph:
    site: str
    terminal: str
    nodes: tuple[str, ...]
    links: tuple[DirectedLink, ...]
    ports: tuple[PortBinding, ...]


def build_station_graph(
    site: str,
    terminal: str,
    nodes: Iterable[str],
    links: Iterable[DirectedLink],
    ports: Iterable[PortBinding],
) -> StationGraph:
    if not isinstance(site, str) or not site.strip():
        raise ValueError("site must be a nonempty string")
    names = tuple(nodes)
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError("node names must be nonempty strings")
    known = set(names)
    if len(known) != len(names):
        raise ValueError("duplicate station node")
    if not isinstance(terminal, str) or terminal not in known:
        raise ValueError("task terminal must reference a station node")
    directed = tuple(links)
    for link in directed:
        if not isinstance(link, DirectedLink):
            raise ValueError("invalid directed link")
        if any(not isinstance(node, str) or node not in known for node in (link.start, link.end)):
            raise ValueError(f"link references an unknown node: {link!r}")
        if type(link.capacity) is not int or link.capacity < 0:
            raise ValueError("link capacity must be a nonnegative integer")
    bindings = validate_ports(ports, known)
    return StationGraph(site, terminal, tuple(sorted(known)), directed, bindings)
