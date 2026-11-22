from report.archive import ReportArchive, StoredReport


class ReportNotFound(KeyError):
    pass


def read_report(archive: ReportArchive, report_id: int) -> StoredReport:
    report = archive.get(report_id)
    if report is None:
        raise ReportNotFound(report_id)
    return report
