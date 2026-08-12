import json
import re
import uuid
from pathlib import Path

from app.config import Settings, get_settings
from app.models.schemas import CaseRecord, CaseStatus

CASE_ID_RE = re.compile(r"^[a-f0-9]{12}$")


def _case_dir(case_id: str, settings: Settings) -> Path:
    if not CASE_ID_RE.fullmatch(case_id):
        raise FileNotFoundError(f"Case not found: {case_id}")
    return (settings.cases_dir / case_id).resolve()


def create_case(
    scan_bytes: bytes,
    filename: str,
    content_type: str | None = None,
    created_by_user_id: str | None = None,
    settings: Settings | None = None,
) -> CaseRecord:
    settings = settings or get_settings()
    case_id = uuid.uuid4().hex[:12]
    case_path = _case_dir(case_id, settings)
    case_path.mkdir(parents=True, exist_ok=True)

    safe_name = Path(filename).name or "scan.bin"
    safe_name = (
        safe_name.replace("\x00", "")
        .replace("\r", "")
        .replace("\n", "")
        .replace('"', "")
        .replace("\\", "")[:180]
        or "scan.bin"
    )
    scan_path = (case_path / safe_name).resolve()
    if not scan_path.is_relative_to(case_path):
        raise ValueError("Invalid filename")
    scan_path.write_bytes(scan_bytes)

    record = CaseRecord(
        id=case_id,
        status=CaseStatus.EXTRACTING,
        scan_filename=safe_name,
        scan_content_type=content_type,
        created_by_user_id=created_by_user_id,
    )
    save_case(record, settings=settings)
    return record


def save_case(record: CaseRecord, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    record.touch()
    case_path = _case_dir(record.id, settings)
    case_path.mkdir(parents=True, exist_ok=True)
    (case_path / "case.json").write_text(
        record.model_dump_json(indent=2),
        encoding="utf-8",
    )


def load_case(case_id: str, settings: Settings | None = None) -> CaseRecord:
    settings = settings or get_settings()
    json_path = _case_dir(case_id, settings) / "case.json"
    if not json_path.exists():
        raise FileNotFoundError(f"Case not found: {case_id}")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return CaseRecord.model_validate(data)


def list_cases(settings: Settings | None = None) -> list[CaseRecord]:
    settings = settings or get_settings()
    cases: list[CaseRecord] = []
    if not settings.cases_dir.exists():
        return cases
    for path in settings.cases_dir.iterdir():
        if not path.is_dir() or not CASE_ID_RE.fullmatch(path.name):
            continue
        json_path = path / "case.json"
        if not json_path.exists():
            continue
        try:
            cases.append(load_case(path.name, settings=settings))
        except Exception:
            continue
    cases.sort(key=lambda c: c.created_at, reverse=True)
    return cases


def scan_path(case_id: str, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    record = load_case(case_id, settings=settings)
    case_path = _case_dir(case_id, settings)
    name = Path(record.scan_filename).name
    path = (case_path / name).resolve()
    if not path.is_relative_to(case_path) or not path.is_file():
        raise FileNotFoundError(f"Scan file missing for case {case_id}")
    return path


def case_md_path(case_id: str, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return _case_dir(case_id, settings) / "case.md"


def find_case_by_conversation_id(
    conversation_id: str, settings: Settings | None = None
) -> CaseRecord | None:
    for case in list_cases(settings=settings):
        if case.call.conversation_id == conversation_id:
            return case
    return None
