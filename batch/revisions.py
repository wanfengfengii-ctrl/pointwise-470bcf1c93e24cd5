from dataclasses import dataclass

from batch.manifest import Manifest
from station.revisions import GraphRevisionId


@dataclass(frozen=True, slots=True)
class BatchRevisionId:
    batch_id: str
    revision: int

    def __post_init__(self) -> None:
        if not isinstance(self.batch_id, str) or not self.batch_id.strip():
            raise ValueError("batch name must be a nonempty string")
        if type(self.revision) is not int or not 0 < self.revision < 1 << 63:
            raise ValueError("invalid batch revision number")


@dataclass(frozen=True, slots=True)
class FrozenBatch:
    key: BatchRevisionId
    freeze_id: str
    manifest: Manifest
    sender: GraphRevisionId
    receiver: GraphRevisionId

    @property
    def demand(self) -> int:
        return self.manifest.demand

    def reference_for(self, site: str) -> GraphRevisionId:
        if site == self.sender.site:
            return self.sender
        if site == self.receiver.site:
            return self.receiver
        raise ValueError(f"site {site!r} does not belong to this batch revision")


def build_frozen_batch(
    key: BatchRevisionId,
    freeze_id: str,
    manifest: Manifest,
    sender: GraphRevisionId,
    receiver: GraphRevisionId,
) -> FrozenBatch:
    if sender.site == receiver.site:
        raise ValueError("sender and receiver must be different stations")
    if not isinstance(freeze_id, str) or not freeze_id.strip():
        raise ValueError("missing freeze identity")
    return FrozenBatch(key, freeze_id, manifest, sender, receiver)
