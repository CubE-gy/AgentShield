from collections import Counter

from sqlalchemy import desc, select
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

def get_audit_record_for_tenant(
    session: Session,
    request_id: str,
    tenant_id: str,
) -> AuditRecord:
    """只查询指定租户自己的审计记录。"""

    try:
        record = session.scalar(
            select(AuditRecord).where(
                AuditRecord.request_id == request_id,
                AuditRecord.tenant_id == tenant_id,
            )
        )
    except OperationalError as exc:
        raise DatabaseUnavailableError("数据库不可用") from exc

    if record is None:
        raise AuditRecordNotFoundError(
            f"找不到审计记录：{request_id}"
        )

    return record


def get_dashboard_summary_for_tenant(
    session: Session,
    tenant_id: str,
    page: int = 1,
    page_size: int = 10,
) -> dict:
    """返回指定租户的看板汇总和最近审计记录。"""

    try:
        recent_records = list(
            session.scalars(
                select(AuditRecord)
                .where(AuditRecord.tenant_id == tenant_id)
                .order_by(desc(AuditRecord.created_at))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        all_records = list(
            session.scalars(
                select(AuditRecord)
                .where(AuditRecord.tenant_id == tenant_id)
            )
        )
    except OperationalError as exc:
        raise DatabaseUnavailableError("数据库不可用") from exc

    risk_type_counts = Counter(
        risk_type
        for record in all_records
        if (risk_type := _get_security_risk_type(record.summary)) is not None
    )

    return {
        "total_requests": len(all_records),
        "blocked_requests": sum(
            record.status == "blocked" for record in all_records
        ),
        "risk_type_counts": dict(sorted(risk_type_counts.items())),
        "recent_audit_records": recent_records,
    }


def _get_security_risk_type(summary: str) -> str | None:
    """从不含完整提示词的审计摘要中读取已记录的风险类型。"""

    prefix = "security_risk_type="
    for part in summary.split(";"):
        if part.startswith(prefix):
            return part.removeprefix(prefix)

    return None
