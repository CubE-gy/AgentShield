from types import SimpleNamespace
from uuid import uuid4
from datetime import datetime, timezone
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import main as main_module
from app.main import app
from app.models import Base
from app.model_provider import ModelResult, MockModelProvider
from app.models import AuditRecord
from app.authentication import ApiKeyRecord
from app.rate_limiter import (
    RateLimitExceededError,
    RateLimitUnavailableError,
    enforce_tenant_rate_limit,
)
from app.audit_repository import (
    DatabaseUnavailableError,
    get_audit_record,
    save_audit_record,
)


TEST_DATABASE_URL = (
    "postgresql+psycopg://"
    "agentshield_test:test_password_change_me@127.0.0.1:5433/agentshield_test"
)

API_KEY_HEADERS = {
    "X-API-Key": "test-active-key",
}

TEST_API_KEY_RECORDS = [
    ApiKeyRecord(
        value="test-active-key",
        tenant_id="tenant-alpha",
        is_active=True,
    )
]

@pytest.fixture(autouse=True)
def use_test_database(monkeypatch):
    test_engine = create_engine(TEST_DATABASE_URL)

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    def test_session_local():
        return Session(test_engine)

    monkeypatch.setattr(
        main_module,
        "SessionLocal",
        test_session_local,
    )

    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(
            model_provider="mock",
            api_key_records=TEST_API_KEY_RECORDS,
            allowed_tools=(),
            redis_url="redis://unused-for-tests",
            rate_limit_max_requests=100,
            rate_limit_window_seconds=60,
        ),
    )
    monkeypatch.setattr(
        main_module,
        "enforce_model_rate_limit",
        lambda tenant_id: None,
    )

    yield

    test_engine.dispose()

client = TestClient(app)
client.headers.update(API_KEY_HEADERS)


def assert_error_response(
    response,
    *,
    status_code,
    code,
    message,
    retryable,
    retry_after=None,
):
    body = response.json()

    assert response.status_code == status_code
    assert body["error"]["code"] == code
    assert body["error"]["message"] == message
    assert body["error"]["retryable"] is retryable
    assert body["error"]["trace_id"] == response.headers[
        "X-Request-Trace-Id"
    ]
    assert len(body["error"]["trace_id"]) == 32
    if retry_after is None:
        assert "Retry-After" not in response.headers
    else:
        assert response.headers["Retry-After"] == str(retry_after)

def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_model_test_endpoint_mock_result():
    response = client.post(
        "/model/test",
        json = {
            "request_id": f"req-api-success-{uuid4().hex}",
            "prompt": "请查询订单状态",
            "scenario": "success",
        }
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "content": "这是Mock模型的正常回答",
        "error_code": None,
    }


def test_model_test_endpoint_writes_safe_request_log(caplog):
    api_key = "test-active-key"
    prompt = "请查询订单状态，客户邮箱是 user@example.com"

    with caplog.at_level(logging.INFO, logger="agentshield.request"):
        response = client.post(
            "/model/test",
            json={
                "request_id": f"req-api-log-{uuid4().hex}",
                "prompt": prompt,
                "scenario": "success",
            },
            headers={"X-API-Key": api_key},
        )

    assert response.status_code == 200
    log_text = "\n".join(caplog.messages)
    assert "model_request_completed" in log_text
    assert "tenant_id=tenant-alpha" in log_text
    assert "endpoint=/model/test" in log_text
    assert api_key not in log_text
    assert prompt not in log_text

def test_model_test_endpoint_returns_rejection():
    response = client.post(
        "/model/test",
        json = {
            "request_id": f"req-api-rejected-{uuid4().hex}",
            "prompt": "请查询订单状态",
            "scenario": "reject",
        }
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "rejected",
        "content": None,
        "error_code": "MODEL_REFUSED"
    }

def test_model_test_endpoint_returns_failure():
    response = client.post(
        "/model/test",
        json = {
            "request_id": f"req-api-failure-{uuid4().hex}",
            "prompt": "请查询订单状态",
            "scenario": "failure",
        }
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "failed",
        "content": None,
        "error_code": "MODEL_UNAVAILABLE"
    }

def test_model_test_endpoint_returns_timeout():
    response = client.post(
        "/model/test",
        json = {
            "request_id": f"req-api-timeout-{uuid4().hex}",
            "prompt": "请查询订单状态",
            "scenario": "timeout",
        }
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "timeout",
        "content": None,
        "error_code": "MODEL_TIMEOUT"
    }

def test_model_test_endpoint_returns_malformed_error():
    response = client.post(
        "/model/test",
        json = {
            "request_id": f"req-api-malformed-{uuid4().hex}",
            "prompt": "请查询订单状态",
            "scenario": "malformed",
        }
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "failed",
        "content": None,
        "error_code": "MODEL_INVALID_RESPONSE"
    }

def test_model_test_endpoint_calls_model_service(monkeypatch):
    called = {}

    def fake_call_model_and_save_audit(**kwargs):
        called.update(kwargs)
        return SimpleNamespace(
            model_result=ModelResult(
                status="success",
                content="这是Mock模型的正常回答",
                error_code=None,
            ),
            audit_record=SimpleNamespace(
                request_id=kwargs["request_id"],
                tenant_id=kwargs["tenant_id"],
                agent_id=kwargs["agent_id"],
                status="success",
                error_code=None,
                latency_ms=5,
                summary="model_status=success",
                summary_hash="a" * 64,
            ),
        )

    monkeypatch.setattr(
        main_module,
        "call_model_and_save_audit",
        fake_call_model_and_save_audit,
    )

    response = client.post(
        "/model/test",
        json={
            "request_id": "req-api-001",
            "tenant_id": "tenant-forged",
            "agent_id": "agent-support",
            "prompt": "请查询订单状态",
            "scenario": "success",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert called["request_id"] == "req-api-001"
    assert called["tenant_id"] == "tenant-alpha"
    assert called["agent_id"] == "agent-support"
    assert called["prompt"] == "请查询订单状态"
    assert called["scenario"] == "success"
    assert isinstance(called["provider"], MockModelProvider)
    assert called["provider"].scenario == "success"

def test_model_test_endpoint_rejects_unknown_scenario():
    response = client.post(
        "/model/test",
        json={
            "request_id": f"req-api-invalid-{uuid4().hex}",
            "tenant_id": "tenant-demo",
            "agent_id": "agent-support",
            "prompt": "请查询订单状态",
            "scenario": "abc",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "failed",
        "content": None,
        "error_code": "MODEL_INVALID_SCENARIO",
    }

def test_model_call_endpoint_uses_provider_factory(monkeypatch):
    captured = {}

    class FakeSettings:
        model_provider = "real"
        api_key_records = TEST_API_KEY_RECORDS

    fake_provider = MockModelProvider(scenario="success")

    def fake_create_provider(settings):
        captured["settings"] = settings
        return fake_provider

    monkeypatch.setattr(
        main_module,
        "create_provider",
        fake_create_provider,
    )

    monkeypatch.setattr(
        main_module,
        "settings",
        FakeSettings(),
    )

    response = client.post(
        "/model/call",
        json={
            "request_id": f"req-api-factory-{uuid4().hex}",
            "tenant_id": "tenant-demo",
            "agent_id": "agent-support",
            "prompt": "请查询订单状态",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert captured["settings"].model_provider == "real"

def test_model_call_endpoint_does_not_require_scenario(monkeypatch):
    captured = {}

    fake_provider = MockModelProvider(scenario="success")

    def fake_create_provider(settings):
        return fake_provider

    def fake_call_model_and_save_audit(**kwargs):
        captured.update(kwargs)

        return SimpleNamespace(
            model_result=ModelResult(
                status="success",
                content="正式接口的模拟回答",
                error_code=None,
            ),
            audit_record=SimpleNamespace(
                request_id=kwargs["request_id"],
            ),
        )

    monkeypatch.setattr(
        main_module,
        "create_provider",
        fake_create_provider,
    )
    monkeypatch.setattr(
        main_module,
        "call_model_and_save_audit",
        fake_call_model_and_save_audit,
    )

    response = client.post(
        "/model/call",
        json={
            "request_id": "req-real-api-001",
            "tenant_id": "tenant-demo",
            "agent_id": "agent-support",
            "prompt": "请查询订单状态",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "content": "正式接口的模拟回答",
        "error_code": None,
    }
    assert captured["request_id"] == "req-real-api-001"
    assert captured["prompt"] == "请查询订单状态"
    assert captured["provider"] is fake_provider
    assert "scenario" not in captured
    assert captured["tenant_id"] == "tenant-alpha"

def test_model_test_endpoint_never_uses_provider_factory(
    monkeypatch,
):
    def fail_if_factory_is_called(settings):
        raise AssertionError(
            "/model/test 不应该创建真实 Provider"
        )

    monkeypatch.setattr(
        main_module,
        "create_provider",
        fail_if_factory_is_called,
    )

    response = client.post(
        "/model/test",
        json={
            "request_id": "req-mock-safety-001",
            "tenant_id": "tenant-demo",
            "agent_id": "agent-support",
            "prompt": "这条内容只能交给 Mock",
            "scenario": "success",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "content": "这是Mock模型的正常回答",
        "error_code": None,
    }

@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/model/test",
            {
                "request_id": "req-missing-key-test",
                "prompt": "测试请求",
                "scenario": "success",
            },
        ),
        (
            "/model/call",
            {
                "request_id": "req-missing-key-call",
                "prompt": "测试请求",
            },
        ),
    ],
)
def test_model_endpoints_reject_missing_api_key(path, payload):
    unauthenticated_client = TestClient(app)

    response = unauthenticated_client.post(
        path,
        json=payload,
    )

    assert_error_response(
        response,
        status_code=401,
        code="API_KEY_MISSING",
        message="缺少 API Key",
        retryable=False,
    )


def test_model_test_endpoint_rejects_unknown_api_key():
    response = client.post(
        "/model/test",
        headers={"X-API-Key": "test-unknown-key"},
        json={
            "request_id": "req-unknown-key",
            "prompt": "测试请求",
            "scenario": "success",
        },
    )

    assert_error_response(
        response,
        status_code=401,
        code="API_KEY_INVALID",
        message="API Key 无效",
        retryable=False,
    )


def test_model_test_endpoint_rejects_disabled_api_key(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(
            model_provider="mock",
            api_key_records=[
                ApiKeyRecord(
                    value="test-active-key",
                    tenant_id="tenant-alpha",
                    is_active=False,
                )
            ],
        ),
    )

    response = client.post(
        "/model/test",
        json={
            "request_id": "req-disabled-key",
            "prompt": "测试请求",
            "scenario": "success",
        },
    )

    assert_error_response(
        response,
        status_code=403,
        code="API_KEY_DISABLED",
        message="API Key 已停用",
        retryable=False,
    )

def create_test_audit_record(
    request_id: str,
    tenant_id: str,
) -> None:
    session = main_module.SessionLocal()

    try:
        save_audit_record(
            session,
            request_id=request_id,
            tenant_id=tenant_id,
            agent_id="agent-support",
            created_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
            risk_level="low",
            status="success",
            error_code=None,
            latency_ms=120,
            summary="model_status=success",
            summary_hash="a" * 64,
        )
    finally:
        session.close()


def test_audit_endpoint_returns_authenticated_tenant_record():
    create_test_audit_record(
        request_id="req-audit-alpha",
        tenant_id="tenant-alpha",
    )

    response = client.get("/audit/req-audit-alpha")

    assert response.status_code == 200
    assert response.json()["request_id"] == "req-audit-alpha"
    assert response.json()["agent_id"] == "agent-support"
    assert response.json()["status"] == "success"
    assert response.json()["summary"] == "model_status=success"
    assert "tenant_id" not in response.json()


def test_audit_endpoint_hides_other_tenant_record(monkeypatch):
    create_test_audit_record(
        request_id="req-audit-alpha",
        tenant_id="tenant-alpha",
    )
    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(
            model_provider="mock",
            api_key_records=[
                ApiKeyRecord(
                    value="test-active-key",
                    tenant_id="tenant-alpha",
                    is_active=True,
                ),
                ApiKeyRecord(
                    value="test-beta-key",
                    tenant_id="tenant-beta",
                    is_active=True,
                ),
            ],
        ),
    )

    response = client.get(
        "/audit/req-audit-alpha",
        headers={"X-API-Key": "test-beta-key"},
    )

    assert_error_response(
        response,
        status_code=404,
        code="AUDIT_RECORD_NOT_FOUND",
        message="未找到审计记录",
        retryable=False,
    )


def create_dashboard_audit_record(
    *,
    request_id: str,
    tenant_id: str,
    created_at: datetime,
    risk_level: str,
    status: str,
    summary: str,
) -> None:
    session = main_module.SessionLocal()

    try:
        save_audit_record(
            session,
            request_id=request_id,
            tenant_id=tenant_id,
            agent_id="agent-support",
            created_at=created_at,
            risk_level=risk_level,
            status=status,
            error_code=None,
            latency_ms=120,
            summary=summary,
            summary_hash="d" * 64,
        )
    finally:
        session.close()


def test_dashboard_summary_returns_only_authenticated_tenant_data():
    create_dashboard_audit_record(
        request_id="req-dashboard-success",
        tenant_id="tenant-alpha",
        created_at=datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc),
        risk_level="low",
        status="success",
        summary="model_status=success",
    )
    create_dashboard_audit_record(
        request_id="req-dashboard-blocked",
        tenant_id="tenant-alpha",
        created_at=datetime(2026, 8, 7, 11, 0, tzinfo=timezone.utc),
        risk_level="high",
        status="blocked",
        summary=(
            "model_status=blocked;security_risk_type=prompt_injection;"
            "security_action=blocked"
        ),
    )
    create_dashboard_audit_record(
        request_id="req-dashboard-masked",
        tenant_id="tenant-alpha",
        created_at=datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc),
        risk_level="medium",
        status="success",
        summary=(
            "model_status=success;security_risk_type=pii;"
            "security_action=masked"
        ),
    )
    create_dashboard_audit_record(
        request_id="req-dashboard-other-tenant",
        tenant_id="tenant-beta",
        created_at=datetime(2026, 8, 7, 13, 0, tzinfo=timezone.utc),
        risk_level="high",
        status="blocked",
        summary=(
            "model_status=blocked;security_risk_type=url_ssrf;"
            "security_action=blocked"
        ),
    )

    response = client.get("/dashboard/summary")

    assert response.status_code == 200
    assert response.json() == {
        "total_requests": 3,
        "blocked_requests": 1,
        "risk_type_counts": {
            "pii": 1,
            "prompt_injection": 1,
        },
        "pagination": {
            "page": 1,
            "page_size": 10,
            "total_pages": 1,
        },
        "recent_audit_records": [
            {
                "request_id": "req-dashboard-masked",
                "agent_id": "agent-support",
                "created_at": "2026-08-07T12:00:00",
                "risk_level": "medium",
                "status": "success",
                "error_code": None,
                "latency_ms": 120,
                "summary": (
                    "model_status=success;security_risk_type=pii;"
                    "security_action=masked"
                ),
            },
            {
                "request_id": "req-dashboard-blocked",
                "agent_id": "agent-support",
                "created_at": "2026-08-07T11:00:00",
                "risk_level": "high",
                "status": "blocked",
                "error_code": None,
                "latency_ms": 120,
                "summary": (
                    "model_status=blocked;security_risk_type=prompt_injection;"
                    "security_action=blocked"
                ),
            },
            {
                "request_id": "req-dashboard-success",
                "agent_id": "agent-support",
                "created_at": "2026-08-07T10:00:00",
                "risk_level": "low",
                "status": "success",
                "error_code": None,
                "latency_ms": 120,
                "summary": "model_status=success",
            },
        ],
    }


def test_dashboard_summary_returns_stable_empty_result():
    response = client.get("/dashboard/summary")

    assert response.status_code == 200
    assert response.json() == {
        "total_requests": 0,
        "blocked_requests": 0,
        "risk_type_counts": {},
        "pagination": {
            "page": 1,
            "page_size": 10,
            "total_pages": 1,
        },
        "recent_audit_records": [],
    }


def test_dashboard_summary_rejects_missing_api_key():
    unauthenticated_client = TestClient(app)

    response = unauthenticated_client.get("/dashboard/summary")

    assert_error_response(
        response,
        status_code=401,
        code="API_KEY_MISSING",
        message="缺少 API Key",
        retryable=False,
    )


def test_dashboard_page_loads_without_embedded_key_or_audit_data():
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "AgentShield 本地演示看板" in response.text
    assert 'id="risk-type-list"' in response.text
    assert 'class="table-wrapper"' in response.text
    assert "statusLabels" in response.text
    assert "setLoadingState" in response.text
    assert 'id="toggle-api-key"' in response.text
    assert 'id="clear-api-key"' in response.text
    assert 'id="previous-page"' in response.text
    assert 'id="next-page"' in response.text
    assert "table-layout: fixed" in response.text
    assert 'createElement("colgroup")' in response.text
    assert ".time-column { overflow: hidden" in response.text
    assert "test-active-key" not in response.text


def test_dashboard_summary_returns_requested_page_for_authenticated_tenant():
    for index in range(11):
        create_dashboard_audit_record(
            request_id=f"req-dashboard-page-{index:02d}",
            tenant_id="tenant-alpha",
            created_at=datetime(2026, 8, 7, 10, index, tzinfo=timezone.utc),
            risk_level="low",
            status="success",
            summary="model_status=success",
        )
    create_dashboard_audit_record(
        request_id="req-dashboard-page-other-tenant",
        tenant_id="tenant-beta",
        created_at=datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc),
        risk_level="high",
        status="blocked",
        summary=(
            "model_status=blocked;security_risk_type=ssrf;"
            "security_action=blocked"
        ),
    )

    response = client.get("/dashboard/summary?page=2")

    assert response.status_code == 200
    body = response.json()
    assert body["total_requests"] == 11
    assert body["blocked_requests"] == 0
    assert body["risk_type_counts"] == {}
    assert body["pagination"] == {
        "page": 2,
        "page_size": 10,
        "total_pages": 2,
    }
    assert [record["request_id"] for record in body["recent_audit_records"]] == [
        "req-dashboard-page-00"
    ]
    assert "req-dashboard-success" not in response.text


def test_openapi_configures_reusable_api_key_authorization():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["components"]["securitySchemes"]["AgentShieldApiKey"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }
    assert schema["paths"]["/model/test"]["post"]["security"] == [
        {"AgentShieldApiKey": []}
    ]
    assert schema["paths"]["/audit/{request_id}"]["get"]["security"] == [
        {"AgentShieldApiKey": []}
    ]
    assert schema["paths"]["/dashboard/summary"]["get"]["security"] == [
        {"AgentShieldApiKey": []}
    ]


def test_model_endpoint_returns_unified_rate_limit_error(monkeypatch):
    def raise_rate_limit_error(tenant_id):
        raise RateLimitExceededError("limit exceeded")

    monkeypatch.setattr(
        main_module,
        "enforce_model_rate_limit",
        raise_rate_limit_error,
    )

    response = client.post(
        "/model/test",
        json={
            "request_id": "req-rate-limit-error",
            "prompt": "提示词不应出现在错误响应中",
            "scenario": "success",
        },
    )

    assert_error_response(
        response,
        status_code=429,
        code="RATE_LIMIT_EXCEEDED",
        message="请求次数超过限制",
        retryable=True,
        retry_after=60,
    )
    assert "提示词不应出现在错误响应中" not in response.text


def test_model_endpoint_returns_unified_redis_unavailable_error(monkeypatch):
    def raise_redis_unavailable_error(tenant_id):
        raise RateLimitUnavailableError("Redis unavailable")

    monkeypatch.setattr(
        main_module,
        "enforce_model_rate_limit",
        raise_redis_unavailable_error,
    )

    response = client.post(
        "/model/test",
        json={
            "request_id": "req-redis-unavailable-error",
            "prompt": "正常提示词",
            "scenario": "success",
        },
    )

    assert_error_response(
        response,
        status_code=503,
        code="RATE_LIMIT_UNAVAILABLE",
        message="限流服务暂时不可用",
        retryable=True,
    )


def test_invalid_request_uses_safe_unified_error_format():
    response = client.post(
        "/model/test",
        json={
            "request_id": "req-invalid-request",
            "prompt": "提示词不应出现在错误响应中",
        },
    )

    assert_error_response(
        response,
        status_code=422,
        code="REQUEST_VALIDATION_ERROR",
        message="请求格式不正确",
        retryable=False,
    )
    assert "提示词不应出现在错误响应中" not in response.text


@pytest.mark.parametrize(
    ("method", "path", "status_code", "code", "message"),
    [
        ("get", "/does-not-exist", 404, "ROUTE_NOT_FOUND", "接口不存在"),
        (
            "get",
            "/model/test",
            405,
            "METHOD_NOT_ALLOWED",
            "请求方法不被允许",
        ),
    ],
)
def test_framework_http_errors_use_unified_format(
    method,
    path,
    status_code,
    code,
    message,
):
    response = getattr(client, method)(path)

    assert_error_response(
        response,
        status_code=status_code,
        code=code,
        message=message,
        retryable=False,
    )


def test_unhandled_error_uses_safe_unified_format(monkeypatch):
    def raise_unhandled_error():
        raise RuntimeError(
            "postgresql://internal_user:internal_password@db.internal/secret"
        )

    safe_client = TestClient(app, raise_server_exceptions=False)

    app.add_api_route(
        "/test-unhandled-error",
        raise_unhandled_error,
        methods=["GET"],
    )
    try:
        response = safe_client.get("/test-unhandled-error")
    finally:
        app.router.routes.pop()

    assert_error_response(
        response,
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="服务器暂时无法处理请求",
        retryable=True,
    )
    assert "internal_password" not in response.text


def test_redis_failure_does_not_create_provider_or_call_model(monkeypatch):
    def raise_redis_unavailable_error(tenant_id):
        raise RateLimitUnavailableError("Redis unavailable")

    def provider_must_not_be_created(settings):
        raise AssertionError("Redis 故障时不应创建 Provider")

    monkeypatch.setattr(
        main_module,
        "enforce_model_rate_limit",
        raise_redis_unavailable_error,
    )
    monkeypatch.setattr(
        main_module,
        "create_provider",
        provider_must_not_be_created,
    )

    response = client.post(
        "/model/call",
        json={
            "request_id": "req-redis-stops-provider",
            "prompt": "正常提示词",
        },
    )

    assert_error_response(
        response,
        status_code=503,
        code="RATE_LIMIT_UNAVAILABLE",
        message="限流服务暂时不可用",
        retryable=True,
    )


def test_database_failure_returns_retryable_unified_error(monkeypatch):
    def raise_database_unavailable(*, session, request_id, tenant_id):
        raise DatabaseUnavailableError("database unavailable")

    monkeypatch.setattr(
        main_module,
        "get_audit_record_for_tenant",
        raise_database_unavailable,
    )

    response = client.get("/audit/req-database-unavailable")

    assert_error_response(
        response,
        status_code=503,
        code="DATABASE_UNAVAILABLE",
        message="数据库暂时不可用",
        retryable=True,
    )


def test_rate_limit_uses_authenticated_tenant_not_request_tenant_id(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.values = {}

        def incr(self, key):
            self.values[key] = self.values.get(key, 0) + 1
            return self.values[key]

        def expire(self, key, seconds):
            pass

    fake_redis = FakeRedis()
    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(
            model_provider="mock",
            api_key_records=[
                ApiKeyRecord("test-active-key", "tenant-alpha", True),
                ApiKeyRecord("test-beta-key", "tenant-beta", True),
            ],
            allowed_tools=(),
            redis_url="redis://unused-for-tests",
            rate_limit_max_requests=1,
            rate_limit_window_seconds=60,
        ),
    )
    monkeypatch.setattr(
        main_module,
        "create_redis_client",
        lambda redis_url: fake_redis,
    )
    monkeypatch.setattr(
        main_module,
        "enforce_model_rate_limit",
        lambda tenant_id: enforce_tenant_rate_limit(
            redis_client=fake_redis,
            tenant_id=tenant_id,
            max_requests=1,
            window_seconds=60,
        ),
    )

    first_alpha_response = client.post(
        "/model/test",
        json={
            "request_id": "req-alpha-rate-limit-1",
            "tenant_id": "tenant-beta",
            "prompt": "正常提示词",
            "scenario": "success",
        },
    )
    second_alpha_response = client.post(
        "/model/test",
        json={
            "request_id": "req-alpha-rate-limit-2",
            "tenant_id": "tenant-beta",
            "prompt": "正常提示词",
            "scenario": "success",
        },
    )
    beta_response = client.post(
        "/model/test",
        headers={"X-API-Key": "test-beta-key"},
        json={
            "request_id": "req-beta-rate-limit-1",
            "tenant_id": "tenant-alpha",
            "prompt": "正常提示词",
            "scenario": "success",
        },
    )

    assert first_alpha_response.status_code == 200
    assert_error_response(
        second_alpha_response,
        status_code=429,
        code="RATE_LIMIT_EXCEEDED",
        message="请求次数超过限制",
        retryable=True,
        retry_after=60,
    )
    assert beta_response.status_code == 200
    assert fake_redis.values == {
        "agentshield:rate-limit:tenant-alpha": 2,
        "agentshield:rate-limit:tenant-beta": 1,
    }

def test_model_response_and_audit_record_do_not_store_full_api_key(
    monkeypatch,
):
    test_api_key = "test-secret-key-must-not-be-stored"

    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(
            model_provider="mock",
            api_key_records=[
                ApiKeyRecord(
                    value=test_api_key,
                    tenant_id="tenant-alpha",
                    is_active=True,
                )
            ],
        ),
    )

    response = client.post(
        "/model/test",
        headers={"X-API-Key": test_api_key},
        json={
            "request_id": "req-api-key-not-stored",
            "prompt": "请查询订单状态",
            "scenario": "success",
        },
    )

    assert response.status_code == 200
    assert test_api_key not in response.text

    session = main_module.SessionLocal()

    try:
        record = get_audit_record(
            session,
            request_id="req-api-key-not-stored",
        )
    finally:
        session.close()

    stored_values = [
        record.request_id,
        record.tenant_id,
        record.agent_id,
        record.risk_level,
        record.status,
        record.error_code or "",
        record.summary,
        record.summary_hash,
    ]

    assert all(test_api_key not in value for value in stored_values)
