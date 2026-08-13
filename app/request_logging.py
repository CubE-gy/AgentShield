import logging


logger = logging.getLogger("agentshield.request")


def log_model_request_completed(
    *,
    trace_id: str,
    tenant_id: str,
    endpoint: str,
    status: str,
    error_code: str | None,
) -> None:
    """记录模型请求的安全摘要，不接收 API Key、提示词或模型回答。"""

    safe_error_code = error_code or "none"
    logger.info(
        "model_request_completed trace_id=%s tenant_id=%s endpoint=%s "
        "status=%s error_code=%s",
        trace_id,
        tenant_id,
        endpoint,
        status,
        safe_error_code,
    )


def log_request_failed(
    *,
    trace_id: str,
    tenant_id: str | None,
    endpoint: str,
    error_code: str,
) -> None:
    """记录失败请求的安全摘要，不接收原始请求内容。"""

    logger.warning(
        "request_failed trace_id=%s tenant_id=%s endpoint=%s error_code=%s",
        trace_id,
        tenant_id or "none",
        endpoint,
        error_code,
    )
