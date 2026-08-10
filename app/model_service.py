from time import perf_counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.audit_repository import (
    AuditRecordNotFoundError,
    DuplicateRequestIdError,
    get_audit_record,
    save_audit_record,
)
from app.model_provider import (
    ModelProvider,
    MockModelProvider,
    ModelResult,
    build_audit_record_data,
)
from app.models import AuditRecord

@dataclass
class ModelServiceResult:
    model_result: ModelResult
    audit_record: AuditRecord

def call_model_and_save_audit(
    session: Session,
    request_id: str,
    tenant_id: str,
    agent_id: str,
    prompt: str,
    scenario: str | None = None,
    provider: ModelProvider | None = None,
):
    try:
        get_audit_record(
            session=session,
            request_id=request_id,
        )
    except AuditRecordNotFoundError:
        pass
    else:
        raise DuplicateRequestIdError(
            f"request_id 已存在：{request_id}"
        )

    if provider is None:
        provider = MockModelProvider(
            scenario=scenario or "success",
        )

    started_at = perf_counter()

    result = provider.call(
        prompt=prompt,
    )

    latency_ms = round((perf_counter() - started_at) * 1000)

    record_data = build_audit_record_data(
        request_id=request_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        result=result,
        latency_ms=latency_ms,
    )

    save_record = save_audit_record(session, **record_data)

    return ModelServiceResult(
        model_result = result,
        audit_record = save_record,
    )