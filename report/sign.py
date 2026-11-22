from receive.lookup import lookup_receipts
from receive.receipts import ReceiptStore
from report.archive import ReportArchive, StoredReport
from report.capacity import compute_joint_capacity
from report.provenance import prepare_signing_inputs


def sign_capacity(
    receipts: ReceiptStore, archive: ReportArchive, first_id: int, second_id: int
) -> StoredReport:
    first, second = lookup_receipts(receipts, first_id, second_id)
    inputs = prepare_signing_inputs(first, second)
    blocks = compute_joint_capacity(inputs)
    return archive.publish(inputs, blocks)
