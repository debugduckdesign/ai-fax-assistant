from app.models.schemas import CaseRecord
from app.services import case_store


def render_case_md(record: CaseRecord) -> str:
    lines: list[str] = [
        f"# Case {record.id}",
        "",
        "## Status",
        record.status.value,
        "",
        "## Source scan",
        f"![{record.scan_filename}](./{record.scan_filename})",
        "",
        "## Extracted from fax",
        "",
        "| field | value | confidence | source |",
        "| --- | --- | --- | --- |",
    ]

    if record.fields:
        for name, field in sorted(record.fields.items()):
            value = (field.value or "").replace("|", "\\|")
            lines.append(
                f"| {name} | {value} | {field.confidence:.2f} | {field.source} |"
            )
    else:
        lines.append("| _(none)_ |  |  |  |")

    lines.extend(
        [
            "",
            "## Missing required",
            (
                ", ".join(record.missing_required)
                if record.missing_required
                else "_(none)_"
            ),
            "",
            "## Call",
            f"- to: {record.call.to or '_'}",
            f"- conversation_id: {record.call.conversation_id or '_'}",
            f"- status: {record.call.status or '_'}",
            f"- reason: {record.call.reason or '_'}",
            "",
            "### Transcript",
            "",
            record.call.transcript or "_(no transcript)_",
            "",
            "## Final required data",
            "",
        ]
    )

    if record.fields:
        for name, field in sorted(record.fields.items()):
            lines.append(f"- {name}: {field.value or ''}")
    else:
        lines.append("- _(none)_")

    if record.error:
        lines.extend(["", "## Error", "", record.error])

    lines.append("")
    return "\n".join(lines)


def write_case_artifacts(record: CaseRecord) -> CaseRecord:
    md = render_case_md(record)
    record.case_md = md
    case_store.save_case(record)
    case_store.case_md_path(record.id).write_text(md, encoding="utf-8")
    return record
