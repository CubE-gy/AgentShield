from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import main as main_module
from app.main import app
from app.models import Base
from app.model_provider import ModelResult, MockModelProvider
from app.models import AuditRecord

TEST_DATABASE_URL = (
    "postgresql+psycopg://"
    "agentshield_test:test_password_change_me@127.0.0.1:5433/agentshield_test"
)

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

    yield

    test_engine.dispose()

client = TestClient(app)

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
            "tenant_id": "tenant-demo",
            "agent_id": "agent-support",
            "prompt": "请查询订单状态",
            "scenario": "success",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert called["request_id"] == "req-api-001"
    assert called["tenant_id"] == "tenant-demo"
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
