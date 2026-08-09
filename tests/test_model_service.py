import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
from app.model_service import call_model_and_save_audit
from app.model_provider import MockModelProvider, ModelResult


TEST_DATABASE_URL = (
    "postgresql+psycopg://"
    "agentshield_test:test_password_change_me@127.0.0.1:5433/agentshield_test"
)


@pytest.fixture
def test_session() -> Session:
    engine = create_engine(TEST_DATABASE_URL)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


def test_successful_model_call_is_saved_to_audit_table(
    test_session: Session,
):
    service_record = call_model_and_save_audit(
        session=test_session,
        request_id="req-model-success",
        tenant_id="tenant-demo",
        agent_id="agent-support",
        prompt="请查询订单状态",
        scenario="success",
    )

    saved_record = service_record.audit_record

    assert saved_record.request_id == "req-model-success"
    assert saved_record.tenant_id == "tenant-demo"
    assert saved_record.agent_id == "agent-support"
    assert saved_record.status == "success"
    assert saved_record.error_code is None
    assert saved_record.latency_ms >= 0
    assert saved_record.summary == "model_status=success"
    assert len(saved_record.summary_hash) == 64

    assert "请查询订单状态" not in saved_record.summary
    assert "这是Mock模型的正常回答" not in saved_record.summary

def test_rejected_model_call_is_saved_to_audit_table(
    test_session: Session,
):
    service_record = call_model_and_save_audit(
        session=test_session,
        request_id="req-model-rejected",
        tenant_id="tenant-demo",
        agent_id="agent-support",
        prompt="请执行不允许的操作",
        scenario="reject",
    )

    saved_record = service_record.audit_record

    assert saved_record.status == "rejected"
    assert saved_record.error_code == "MODEL_REFUSED"
    assert saved_record.summary == (
        "model_status=rejected;error_code=MODEL_REFUSED"
    )
    assert "请执行不允许的操作" not in saved_record.summary

def test_failed_model_call_is_saved_to_audit_table(
    test_session: Session,
):
    service_record = call_model_and_save_audit(
        session=test_session,
        request_id="req-model-failure",
        tenant_id="tenant-demo",
        agent_id="agent-support",
        prompt="请查询订单状态",
        scenario="failure",
    )

    saved_record = service_record.audit_record

    assert saved_record.status == "failed"
    assert saved_record.error_code == "MODEL_UNAVAILABLE"
    assert saved_record.summary == (
        "model_status=failed;error_code=MODEL_UNAVAILABLE"
    )
    assert "请查询订单状态" not in saved_record.summary

def test_timeout_model_call_is_saved_to_audit_table(
    test_session: Session,
):
    service_record = call_model_and_save_audit(
        session=test_session,
        request_id="req-model-timeout",
        tenant_id="tenant-demo",
        agent_id="agent-support",
        prompt="请查询订单状态",
        scenario="timeout",
    )

    saved_record = service_record.audit_record

    assert saved_record.status == "timeout"
    assert saved_record.error_code == "MODEL_TIMEOUT"
    assert saved_record.summary == (
        "model_status=timeout;error_code=MODEL_TIMEOUT"
    )
    assert "请查询订单状态" not in saved_record.summary

def test_malformed_model_call_is_saved_to_audit_table(
    test_session: Session,
):
    service_record = call_model_and_save_audit(
        session=test_session,
        request_id="req-model-malformed",
        tenant_id="tenant-demo",
        agent_id="agent-support",
        prompt="请查询订单状态",
        scenario="malformed",
    )

    saved_record = service_record.audit_record

    assert saved_record.status == "failed"
    assert saved_record.error_code == "MODEL_INVALID_RESPONSE"
    assert saved_record.summary == (
        "model_status=failed;error_code=MODEL_INVALID_RESPONSE"
    )
    assert "请查询订单状态" not in saved_record.summary

def test_model_service_returns_model_result_and_saved_record(
    test_session: Session,
):
    service_result = call_model_and_save_audit(
        session=test_session,
        request_id="req-model-both-results",
        tenant_id="tenant-demo",
        agent_id="agent-support",
        prompt="请查询订单状态",
        scenario="success",
    )

    assert service_result.model_result == ModelResult(
        status="success",
        content="这是Mock模型的正常回答",
        error_code=None,
    )
    assert service_result.audit_record.request_id == (
        "req-model-both-results"
    )
    assert service_result.audit_record.summary == "model_status=success"

def test_unknown_scenario_is_saved_as_invalid_scenario(
    test_session: Session,
):
    service_result = call_model_and_save_audit(
        session=test_session,
        request_id="req-model-invalid-scenario",
        tenant_id="tenant-demo",
        agent_id="agent-support",
        prompt="请查询订单状态",
        scenario="abc",
    )

    saved_record = service_result.audit_record

    assert saved_record.status == "failed"
    assert saved_record.error_code == "MODEL_INVALID_SCENARIO"
    assert saved_record.summary == (
        "model_status=failed;error_code=MODEL_INVALID_SCENARIO"
    )
    assert "请查询订单状态" not in saved_record.summary

    def test_model_service_uses_injected_provider(
            test_session: Session,
    ):
        provider = MockModelProvider()

        service_result = call_model_and_save_audit(
            session=test_session,
            request_id="req-injected-provider",
            tenant_id="tenant-demo",
            agent_id="agent-support",
            prompt="请查询订单状态",
            scenario="success",
            provider=provider,
        )

        assert service_result.model_result.status == "success"
        assert service_result.model_result.content == "这是Mock模型的正常回答"
        assert service_result.audit_record.status == "success"

def test_model_service_uses_injected_provider(
    test_session: Session,
):
    provider = MockModelProvider(scenario="success")

    service_result = call_model_and_save_audit(
        session=test_session,
        request_id="req-injected-provider",
        tenant_id="tenant-demo",
        agent_id="agent-support",
        prompt="请查询订单状态",
        scenario="success",
        provider=provider,
    )

    assert service_result.model_result.status == "success"
    assert service_result.model_result.content == "这是Mock模型的正常回答"
    assert service_result.audit_record.status == "success"