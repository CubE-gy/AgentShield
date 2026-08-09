from app.model_provider import (
    MockModelProvider,
    ModelResult,
    build_audit_summary,
    build_audit_record_data,
)

def test_mock_model_return_success():
    provider = MockModelProvider()

    result = provider.call(
        prompt = "请查询订单状态",
        scenario = "success",
    )

    assert result.status == "success"
    assert result.content == "这是Mock模型的正常回答"
    assert result.error_code is None

def test_mock_model_returns_rejection():
    provider = MockModelProvider()

    result = provider.call(
        prompt = "请执行不允许的操作",
        scenario = "reject",
    )

    assert result.status == "rejected"
    assert result.content is None
    assert  result.error_code == "MODEL_REFUSED"

def test_mock_model_returns_failure():
    provider = MockModelProvider()

    result = provider.call(
        prompt="请查询订单状态",
        scenario="failure",
    )

    assert result.status == "failed"
    assert result.content is None
    assert result.error_code == "MODEL_UNAVAILABLE"

def test_mock_model_returns_timeout():
    provider = MockModelProvider()

    result = provider.call(
        prompt="请查询订单状态",
        scenario="timeout",
    )

    assert result.status == "timeout"
    assert result.content is None
    assert result.error_code == "MODEL_TIMEOUT"

def test_mock_model_returns_malformed_response_error():
    provider = MockModelProvider()

    result = provider.call(
        prompt="请查询订单状态",
        scenario="malformed",
    )

    assert result.status == "failed"
    assert result.content is None
    assert result.error_code == "MODEL_INVALID_RESPONSE"

def test_build_audit_summary_for_success():
    result = ModelResult(
        status = "success",
        content = "这是模型的完整回答，不应该进入审计摘要",
        error_code = None,
    )

    summary = build_audit_summary(result)

    assert summary == "model_status=success"
    assert "完整回答" not in summary

def test_build_audit_summary_for_failure():
    result = ModelResult(
        status = "failed",
        content = "这段内容不应该进入审计摘要",
        error_code = "MODEL_UNAVAILABLE",
    )

    summary = build_audit_summary(result)

    assert summary == (
        "model_status=failed;error_code=MODEL_UNAVAILABLE"
    )
    assert "这段内容" not in summary

def test_build_audit_summary_for_time():
    result = ModelResult(
        status = "timeout",
        content = "超时情况下不应该保存模型内容",
        error_code = "MODEL_TIMEOUT",
    )

    summary = build_audit_summary(result)

    assert summary == (
        "model_status=timeout;error_code=MODEL_TIMEOUT"
    )
    assert "超时情况下" not in summary

def test_build_audit_summary_for_malformed_response():
    result = ModelResult(
        status = "failed",
        content = "格式错误的模型原文不应该被保存",
        error_code = "MODEL_INVALID_RESPONSE",
    )

    summary = build_audit_summary(result)

    assert summary == (
        "model_status=failed;error_code=MODEL_INVALID_RESPONSE"
    )
    assert "格式错误" not in summary

def test_build_audit_record_data_from_model_result():
    result = ModelResult(
        status="success",
        content="这段完整回答不能进入审计记录摘要",
        error_code=None,
    )

    record_data = build_audit_record_data(
        request_id="req-001",
        tenant_id="tenant-demo",
        agent_id="agent-support",
        result=result,
        latency_ms=120,
    )

    assert record_data["request_id"] == "req-001"
    assert record_data["tenant_id"] == "tenant-demo"
    assert record_data["agent_id"] == "agent-support"
    assert record_data["status"] == "success"
    assert record_data["risk_level"] == "low"
    assert record_data["latency_ms"] == 120
    assert record_data["summary"] == "model_status=success"
    assert len(record_data["summary_hash"]) == 64
    assert "完整回答" not in record_data["summary"]

def test_build_audit_record_data_keeps_failure_details():
    result = ModelResult(
        status="failed",
        content="模型失败时的原文不能进入审计记录摘要",
        error_code="MODEL_UNAVAILABLE",
    )

    record_data = build_audit_record_data(
        request_id="req-failure",
        tenant_id="tenant-demo",
        agent_id="agent-support",
        result=result,
        latency_ms=250,
    )

    assert record_data["status"] == "failed"
    assert record_data["error_code"] == "MODEL_UNAVAILABLE"
    assert record_data["summary"] == (
        "model_status=failed;error_code=MODEL_UNAVAILABLE"
    )
    assert "模型失败时的原文" not in record_data["summary"]

def test_mock_model_rejects_unknown_scenario():
    provider = MockModelProvider()

    result = provider.call(
        prompt="请查询订单状态",
        scenario="abc",
    )

    assert result.status == "failed"
    assert result.content is None
    assert result.error_code == "MODEL_INVALID_SCENARIO"