from collections import defaultdict, deque
from collections.abc import Hashable, Iterable
from typing import TypeVar

Node = TypeVar("Node", bound=Hashable)


def max_flow(arcs: Iterable[tuple[Node, Node, int]], source: Node, sink: Node, limit: int) -> int:
    """Return the integer flow up to limit using shortest residual augmenting paths."""
    if type(limit) is not int or limit < 0:
        raise ValueError("flow limit must be a nonnegative integer")
    residual: dict[Node, dict[Node, int]] = defaultdict(dict)
    for start, end, capacity in arcs:
        if type(capacity) is not int or capacity < 0:
            raise ValueError("arc capacity must be a nonnegative integer")
        if start == end or capacity == 0:
            continue
        residual[start][end] = residual[start].get(end, 0) + capacity
        residual[end].setdefault(start, 0)

    if source == sink:
        return limit
    total = 0
    while total < limit:
        parents = {source: source}
        frontier = deque([source])
        while frontier and sink not in parents:
            start = frontier.popleft()
            for end, available in residual[start].items():
                if available > 0 and end not in parents:
                    parents[end] = start
                    frontier.append(end)
        if sink not in parents:
            break

        amount = limit - total
        end = sink
        while end != source:
            start = parents[end]
            amount = min(amount, residual[start][end])
            end = start
        end = sink
        while end != source:
            start = parents[end]
            residual[start][end] -= amount
            residual[end][start] += amount
            end = start
        total += amount
    return total
