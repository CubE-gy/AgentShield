from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
from app.audit_repository import (
    AuditRecordNotFoundError,
    DuplicateRequestIdError,
    DatabaseUnavailableError,
    get_audit_record,
    save_audit_record,
)

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


def test_save_and_get_audit_record(test_session: Session):
    saved_record = save_audit_record(
        test_session,
        request_id="req-001",
        tenant_id="tenant-demo",
        agent_id="agent-support",
        created_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
        risk_level="medium",
        status="allowed",
        error_code=None,
        latency_ms=120,
        summary="用户询问订单状态",
        summary_hash="a" * 64,
    )

    found_record = get_audit_record(test_session, "req-001")

    assert saved_record.request_id == "req-001"
    assert found_record.tenant_id == "tenant-demo"
    assert found_record.summary == "用户询问订单状态"


def test_duplicate_request_id_is_rejected(test_session: Session):
    save_audit_record(
        test_session,
        request_id="req-duplicate",
        tenant_id="tenant-demo",
        agent_id="agent-support",
        created_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
        risk_level="medium",
        status="allowed",
        error_code=None,
        latency_ms=120,
        summary="已脱敏摘要",
        summary_hash="b" * 64,
    )

    with pytest.raises(DuplicateRequestIdError):
        save_audit_record(
            test_session,
            request_id="req-duplicate",
            tenant_id="tenant-demo",
            agent_id="agent-support",
            created_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
            risk_level="medium",
            status="allowed",
            error_code=None,
            latency_ms=130,
            summary="另一条已脱敏摘要",
            summary_hash="c" * 64,
        )


def test_missing_request_id_is_not_found(test_session: Session):
    with pytest.raises(AuditRecordNotFoundError):
        get_audit_record(test_session, "req-missing")


def test_database_unavailable_is_reported():
    unavailable_session = Session(
        create_engine(
            "postgresql+psycopg://wrong:wrong@127.0.0.1:5999/missing",
            connect_args={"connect_timeout": 1},
        )
    )

    with pytest.raises(DatabaseUnavailableError):
        get_audit_record(unavailable_session, "req-001")