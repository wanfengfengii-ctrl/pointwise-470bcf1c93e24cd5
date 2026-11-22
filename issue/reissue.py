from issue.registry import IssueRegistry


class IssueNotFound(KeyError):
    pass


def reissue_station(registry: IssueRegistry, issue_id: str) -> bytes:
    if not isinstance(issue_id, str) or not issue_id.strip():
        raise IssueNotFound(issue_id)
    try:
        return registry.get_original(issue_id)
    except KeyError as exc:
        raise IssueNotFound(issue_id) from exc
