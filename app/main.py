from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.authentication import (
    ApiKeyAuthenticationError,
    authenticate_api_key,
)
from app.db import SessionLocal
from app.model_provider import MockModelProvider
from app.model_service import call_model_and_save_audit
from app.provider_factory import create_provider
from app.settings import Settings
from app.audit_repository import (
    AuditRecordNotFoundError,
    get_audit_record_for_tenant,
)


class ModelTestRequest(BaseModel):
    request_id: str = "req-api-default"
    tenant_id: str = "tenant-demo"
    agent_id: str = "agent-support"
    prompt: str
    scenario: str


class ModelCallRequest(BaseModel):
    request_id: str = "req-api-default"
    tenant_id: str = "tenant-demo"
    agent_id: str = "agent-support"
    prompt: str


settings = Settings()

app = FastAPI(title="AgentShield")


def get_authenticated_tenant(
    x_api_key: str | None = Header(default=None),
) -> str:
    """验证请求头中的 Key，并返回认证后的租户编号。"""

    try:
        record = authenticate_api_key(
            provided_key=x_api_key,
            records=settings.api_key_records,
        )
    except ApiKeyAuthenticationError as error:
        status_code = (
            403
            if error.error_code == "API_KEY_DISABLED"
            else 401
        )
        raise HTTPException(
            status_code=status_code,
            detail={"error_code": error.error_code},
        ) from error

    return record.tenant_id


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/model/test")
def model_test(
    request: ModelTestRequest,
    tenant_id: str = Depends(get_authenticated_tenant),
):
    session = SessionLocal()
    provider = MockModelProvider(scenario=request.scenario)

    try:
        service_record = call_model_and_save_audit(
            session=session,
            request_id=request.request_id,
            tenant_id=tenant_id,
            agent_id=request.agent_id,
            prompt=request.prompt,
            scenario=request.scenario,
            provider=provider,
        )

        return {
            "status": service_record.model_result.status,
            "content": service_record.model_result.content,
            "error_code": service_record.model_result.error_code,
        }
    finally:
        session.close()


@app.post("/model/call")
def model_call(
    request: ModelCallRequest,
    tenant_id: str = Depends(get_authenticated_tenant),
):
    session = SessionLocal()
    provider = create_provider(settings)

    try:
        service_record = call_model_and_save_audit(
            session=session,
            request_id=request.request_id,
            tenant_id=tenant_id,
            agent_id=request.agent_id,
            prompt=request.prompt,
            provider=provider,
        )

        return {
            "status": service_record.model_result.status,
            "content": service_record.model_result.content,
            "error_code": service_record.model_result.error_code,
        }
    finally:
        session.close()

@app.get("/audit/{request_id}")
def get_audit_record(
    request_id: str,
    tenant_id: str = Depends(get_authenticated_tenant),
):
    session = SessionLocal()

    try:
        record = get_audit_record_for_tenant(
            session=session,
            request_id=request_id,
            tenant_id=tenant_id,
        )
    except AuditRecordNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "AUDIT_RECORD_NOT_FOUND"},
        ) from error
    finally:
        session.close()

    return {
        "request_id": record.request_id,
        "agent_id": record.agent_id,
        "created_at": record.created_at.isoformat(),
        "risk_level": record.risk_level,
        "status": record.status,
        "error_code": record.error_code,
        "latency_ms": record.latency_ms,
        "summary": record.summary,
    }
