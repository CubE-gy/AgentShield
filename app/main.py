from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.authentication import (
    ApiKeyAuthenticationError,
    authenticate_api_key,
)
from app.db import SessionLocal
from app.model_provider import MockModelProvider
from app.model_service import call_model_and_save_audit
from app.provider_factory import create_provider
from app.request_logging import log_model_request_completed
from app.rate_limiter import (
    RateLimitExceededError,
    RateLimitUnavailableError,
    create_redis_client,
    enforce_tenant_rate_limit,
)
from app.settings import Settings
from app.audit_repository import (
    AuditRecordNotFoundError,
    DatabaseUnavailableError,
    DuplicateRequestIdError,
    get_audit_record_for_tenant,
)
from app.error_handling import create_error_response


class ModelTestRequest(BaseModel):
    request_id: str = "req-api-default"
    tenant_id: str = "tenant-demo"
    agent_id: str = "agent-support"
    prompt: str
    scenario: str
    tool_name: str | None = None
    target_url: str | None = None


class ModelCallRequest(BaseModel):
    request_id: str = "req-api-default"
    tenant_id: str = "tenant-demo"
    agent_id: str = "agent-support"
    prompt: str
    tool_name: str | None = None
    target_url: str | None = None


settings = Settings()

app = FastAPI(title="AgentShield")


@app.middleware("http")
async def add_request_trace_id(request: Request, call_next):
    """为每个 HTTP 请求创建追踪编号，并放入响应头。"""

    request.state.trace_id = uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-Trace-Id"] = request.state.trace_id
    return response


def get_authenticated_tenant(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> str:
    """验证请求头中的 Key，并返回认证后的租户编号。"""

    record = authenticate_api_key(
        provided_key=x_api_key,
        records=settings.api_key_records,
    )

    request.state.tenant_id = record.tenant_id
    return record.tenant_id


@app.exception_handler(ApiKeyAuthenticationError)
async def handle_api_key_authentication_error(
    request: Request,
    error: ApiKeyAuthenticationError,
):
    messages = {
        "API_KEY_MISSING": "缺少 API Key",
        "API_KEY_INVALID": "API Key 无效",
        "API_KEY_DISABLED": "API Key 已停用",
    }
    status_code = 403 if error.error_code == "API_KEY_DISABLED" else 401
    return create_error_response(
        request,
        status_code=status_code,
        error_code=error.error_code,
        message=messages[error.error_code],
        retryable=False,
    )


@app.exception_handler(RateLimitExceededError)
async def handle_rate_limit_exceeded_error(
    request: Request,
    error: RateLimitExceededError,
):
    return create_error_response(
        request,
        status_code=429,
        error_code="RATE_LIMIT_EXCEEDED",
        message="请求次数超过限制",
        retryable=True,
        retry_after=settings.rate_limit_window_seconds,
    )


@app.exception_handler(RateLimitUnavailableError)
async def handle_rate_limit_unavailable_error(
    request: Request,
    error: RateLimitUnavailableError,
):
    return create_error_response(
        request,
        status_code=503,
        error_code="RATE_LIMIT_UNAVAILABLE",
        message="限流服务暂时不可用",
        retryable=True,
    )


@app.exception_handler(AuditRecordNotFoundError)
async def handle_audit_record_not_found_error(
    request: Request,
    error: AuditRecordNotFoundError,
):
    return create_error_response(
        request,
        status_code=404,
        error_code="AUDIT_RECORD_NOT_FOUND",
        message="未找到审计记录",
        retryable=False,
    )


@app.exception_handler(DuplicateRequestIdError)
async def handle_duplicate_request_id_error(
    request: Request,
    error: DuplicateRequestIdError,
):
    return create_error_response(
        request,
        status_code=409,
        error_code="DUPLICATE_REQUEST_ID",
        message="request_id 已存在",
        retryable=False,
    )


@app.exception_handler(DatabaseUnavailableError)
async def handle_database_unavailable_error(
    request: Request,
    error: DatabaseUnavailableError,
):
    return create_error_response(
        request,
        status_code=503,
        error_code="DATABASE_UNAVAILABLE",
        message="数据库暂时不可用",
        retryable=True,
    )


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request,
    error: RequestValidationError,
):
    return create_error_response(
        request,
        status_code=422,
        error_code="REQUEST_VALIDATION_ERROR",
        message="请求格式不正确",
        retryable=False,
    )


@app.exception_handler(StarletteHTTPException)
async def handle_framework_http_error(
    request: Request,
    error: StarletteHTTPException,
):
    errors = {
        404: ("ROUTE_NOT_FOUND", "接口不存在"),
        405: ("METHOD_NOT_ALLOWED", "请求方法不被允许"),
    }
    error_code, message = errors.get(
        error.status_code,
        ("HTTP_ERROR", "请求无法处理"),
    )
    return create_error_response(
        request,
        status_code=error.status_code,
        error_code=error_code,
        message=message,
        retryable=False,
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, error: Exception):
    return create_error_response(
        request,
        status_code=500,
        error_code="INTERNAL_SERVER_ERROR",
        message="服务器暂时无法处理请求",
        retryable=True,
    )


def enforce_model_rate_limit(tenant_id: str) -> None:
    """在模型调用前按已认证租户执行限流。"""

    redis_client = create_redis_client(settings.redis_url)
    enforce_tenant_rate_limit(
        redis_client=redis_client,
        tenant_id=tenant_id,
        max_requests=settings.rate_limit_max_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/model/test")
def model_test(
    request: ModelTestRequest,
    http_request: Request,
    tenant_id: str = Depends(get_authenticated_tenant),
):
    enforce_model_rate_limit(tenant_id)

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
            tool_name=request.tool_name,
            allowed_tools=getattr(settings, "allowed_tools", ()),
            target_url=request.target_url,
            provider=provider,
        )

        log_model_request_completed(
            trace_id=http_request.state.trace_id,
            tenant_id=tenant_id,
            endpoint="/model/test",
            status=service_record.model_result.status,
            error_code=service_record.model_result.error_code,
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
    http_request: Request,
    tenant_id: str = Depends(get_authenticated_tenant),
):
    enforce_model_rate_limit(tenant_id)

    session = SessionLocal()
    provider = create_provider(settings)

    try:
        service_record = call_model_and_save_audit(
            session=session,
            request_id=request.request_id,
            tenant_id=tenant_id,
            agent_id=request.agent_id,
            prompt=request.prompt,
            tool_name=request.tool_name,
            allowed_tools=getattr(settings, "allowed_tools", ()),
            target_url=request.target_url,
            provider=provider,
        )

        log_model_request_completed(
            trace_id=http_request.state.trace_id,
            tenant_id=tenant_id,
            endpoint="/model/call",
            status=service_record.model_result.status,
            error_code=service_record.model_result.error_code,
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
