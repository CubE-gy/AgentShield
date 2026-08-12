from types import SimpleNamespace
from uuid import uuid4
from datetime import datetime, timezone

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
from app.audit_repository import (
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
        ),
    )

    yield

    test_engine.dispose()

client = TestClient(app)
client.headers.update(API_KEY_HEADERS)

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

    assert response.status_code == 401
    assert response.json() == {
        "detail": {
            "error_code": "API_KEY_MISSING",
        }
    }


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

    assert response.status_code == 401
    assert response.json() == {
        "detail": {
            "error_code": "API_KEY_INVALID",
        }
    }


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

    assert response.status_code == 403
    assert response.json() == {
        "detail": {
            "error_code": "API_KEY_DISABLED",
        }
    }

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

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "error_code": "AUDIT_RECORD_NOT_FOUND",
        }
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
