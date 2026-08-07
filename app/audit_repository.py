from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.models import AuditRecord


class DuplicateRequestIdError(Exception):
    """request_id 已存在。"""


class AuditRecordNotFoundError(Exception):
    """找不到审计记录。"""


class DatabaseUnavailableError(Exception):
    """数据库不可用。"""


def save_audit_record(session: Session, **record_data) -> AuditRecord:
    record = AuditRecord(**record_data)
    session.add(record)

    try:
        session.commit()
        session.refresh(record)
        return record
    except IntegrityError as exc:
        session.rollback()
        raise DuplicateRequestIdError(
            f"request_id 已存在：{record.request_id}"
        ) from exc
    except OperationalError as exc:
        session.rollback()
        raise DatabaseUnavailableError("数据库不可用") from exc


def get_audit_record(session: Session, request_id: str) -> AuditRecord:
    try:
        record = session.scalar(
            select(AuditRecord).where(AuditRecord.request_id == request_id)
        )
    except OperationalError as exc:
        raise DatabaseUnavailableError("数据库不可用") from exc

    if record is None:
        raise AuditRecordNotFoundError(
            f"找不到审计记录：{request_id}"
        )

    return record