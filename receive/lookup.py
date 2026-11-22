from receive.receipts import Receipt, ReceiptStore


class ReceiptNotFound(KeyError):
    pass


def lookup_receipts(receipts: ReceiptStore, first_id: int, second_id: int) -> tuple[Receipt, Receipt]:
    first = receipts.fetch(first_id)
    if first is None:
        raise ReceiptNotFound(first_id)
    second = receipts.fetch(second_id)
    if second is None:
        raise ReceiptNotFound(second_id)
    return first, second
