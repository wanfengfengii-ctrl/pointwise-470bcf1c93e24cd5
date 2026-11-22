from collections.abc import Collection, Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PortBinding:
    name: str
    node: str


def validate_ports(ports: Iterable[PortBinding], nodes: Collection[str]) -> tuple[PortBinding, ...]:
    bindings = {}
    for port in ports:
        if not isinstance(port, PortBinding) or not isinstance(port.name, str) or not port.name.strip():
            raise ValueError("port binding must carry a nonempty name")
        if not isinstance(port.node, str) or port.node not in nodes:
            raise ValueError(f"port {port.name!r} references an unknown node")
        if port.name in bindings:
            raise ValueError(f"duplicate port {port.name!r}")
        bindings[port.name] = port
    return tuple(bindings[name] for name in sorted(bindings))


def match_port_names(
    sending: Iterable[PortBinding], receiving: Iterable[PortBinding]
) -> tuple[tuple[PortBinding, PortBinding], ...]:
    left = {port.name: port for port in sending}
    right = {port.name: port for port in receiving}
    if left.keys() != right.keys():
        missing = sorted(left.keys() - right.keys())
        extra = sorted(right.keys() - left.keys())
        raise ValueError(f"port names differ: receiver missing {missing!r}, sender missing {extra!r}")
    return tuple((left[name], right[name]) for name in sorted(left))
