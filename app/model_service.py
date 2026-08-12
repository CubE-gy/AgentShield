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
from app.security_checks import (
    SecurityCheckInput,
    check_prompt_injection,
    check_tool_allowlist,
    check_url_ssrf,
    mask_pii,
)

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
    tool_name: str | None = None,
    allowed_tools: tuple[str, ...] = (),
    target_url: str | None = None,
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

    started_at = perf_counter()
    check_input = SecurityCheckInput(
        prompt=prompt,
        tool_name=tool_name,
        target_url=target_url,
        allowed_tools=allowed_tools,
    )
    security_result = check_prompt_injection(check_input)

    if security_result.decision == "block":
        result = ModelResult(
            status="blocked",
            content=None,
            error_code=security_result.reason_code,
        )
        audit_risk_level = security_result.risk_level
        audit_risk_type = security_result.risk_type
        audit_security_action = "blocked"
    else:
        tool_result = check_tool_allowlist(check_input)

        if tool_result.decision == "block":
            result = ModelResult(
                status="blocked",
                content=None,
                error_code=tool_result.reason_code,
            )
            audit_risk_level = tool_result.risk_level
            audit_risk_type = tool_result.risk_type
            audit_security_action = "blocked"
        else:
            url_result = check_url_ssrf(check_input)

            if url_result.decision == "block":
                result = ModelResult(
                    status="blocked",
                    content=None,
                    error_code=url_result.reason_code,
                )
                audit_risk_level = url_result.risk_level
                audit_risk_type = url_result.risk_type
                audit_security_action = "blocked"
            else:
                pii_result = mask_pii(check_input)

                if provider is None:
                    provider = MockModelProvider(
                        scenario=scenario or "success",
                    )

                result = provider.call(
                    prompt=pii_result.masked_prompt,
                )
                audit_risk_level = (
                    "medium" if pii_result.detected_types else "low"
                )
                audit_risk_type = "pii" if pii_result.detected_types else None
                audit_security_action = (
                    "masked" if pii_result.detected_types else None
                )

    latency_ms = round((perf_counter() - started_at) * 1000)

    record_data = build_audit_record_data(
        request_id=request_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        result=result,
        latency_ms=latency_ms,
        risk_level=audit_risk_level,
        security_risk_type=audit_risk_type,
        security_action=audit_security_action,
    )

    save_record = save_audit_record(session, **record_data)

    return ModelServiceResult(
        model_result = result,
        audit_record = save_record,
    )
