from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import main as main_module
from app.main import app
from app.models import Base
from app.model_provider import ModelResult
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