from fastapi import Request
from fastapi.responses import JSONResponse

from app.request_logging import log_request_failed


def create_error_response(
    request: Request,
    *,
    status_code: int,
    error_code: str,
    message: str,
    retryable: bool,
    retry_after: int | None = None,
) -> JSONResponse:
    """创建不含请求原文或内部细节的统一错误响应。"""

    trace_id = getattr(request.state, "trace_id", "unavailable")
    tenant_id = getattr(request.state, "tenant_id", None)
    log_request_failed(
        trace_id=trace_id,
        tenant_id=tenant_id,
        endpoint=request.url.path,
        error_code=error_code,
    )
    headers = {"X-Request-Trace-Id": trace_id}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)

    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "error": {
                "code": error_code,
                "message": message,
                "retryable": retryable,
                "trace_id": trace_id,
            }
        },
    )
