from app.model_provider import (
    ModelProvider,
    MockModelProvider,
    ModelResult,
    OpenAIModelProvider,
    build_audit_summary,
    build_audit_record_data,
)
import httpx

def test_mock_model_return_success():
    provider = MockModelProvider(scenario = "success")

    result = provider.call(
        prompt = "请查询订单状态",
    )

    assert result.status == "success"
    assert result.content == "这是Mock模型的正常回答"
    assert result.error_code is None

def test_mock_model_returns_rejection():
    provider = MockModelProvider(scenario = "reject")

    result = provider.call(
        prompt = "请执行不允许的操作",
    )

    assert result.status == "rejected"
    assert result.content is None
    assert  result.error_code == "MODEL_REFUSED"

def test_mock_model_returns_failure():
    provider = MockModelProvider(scenario="failure")

    result = provider.call(
        prompt="请查询订单状态",
    )

    assert result.status == "failed"
    assert result.content is None
    assert result.error_code == "MODEL_UNAVAILABLE"

def test_mock_model_returns_timeout():
    provider = MockModelProvider(scenario="timeout")

    result = provider.call(
        prompt="请查询订单状态",
    )

    assert result.status == "timeout"
    assert result.content is None
    assert result.error_code == "MODEL_TIMEOUT"

def test_mock_model_returns_malformed_response_error():
    provider = MockModelProvider(scenario="malformed")

    result = provider.call(
        prompt="请查询订单状态",
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

def test_mock_model_rejects_unknown_scenario():
    provider = MockModelProvider(scenario="abc")

    result = provider.call(
        prompt="请查询订单状态",
    )

    assert result.status == "failed"
    assert result.content is None
    assert result.error_code == "MODEL_INVALID_SCENARIO"

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


def test_mock_provider_matches_model_provider_protocol():
    provider : ModelProvider = MockModelProvider(
        scenario="success",
    )

    result = provider.call(
        prompt="请查询订单状态",
    )

    assert isinstance(provider, ModelProvider)
    assert isinstance(result, ModelResult)
    assert result.status == "success"

def test_mock_provider_stores_scenario_on_creation():
    provider = MockModelProvider(scenario="timeout")

    result = provider.call(
        prompt="请查询订单状态",
    )

    assert result.status == "timeout"
    assert result.content is None
    assert result.error_code == "MODEL_TIMEOUT"

def test_openai_provider_without_api_key_returns_safe_error():
    provider = OpenAIModelProvider(
        api_key=None,
        model="test-model",
        base_url="https://example.invalid",
    )

    assert isinstance(provider, ModelProvider)

    result = provider.call(
        prompt="请查询订单状态",
    )

    assert result.status == "failed"
    assert result.content is None
    assert result.error_code == "MODEL_API_KEY_MISSING"

def test_openai_provider_default_http_failure_does_not_leak_key():
    placeholder_key = "test-placeholder-key"

    provider = OpenAIModelProvider(
        api_key=placeholder_key,
        model="test-model",
        base_url="https://example.invalid",
    )

    result = provider.call(
        prompt="请查询订单状态",
    )

    assert result.status == "failed"
    assert result.content is None
    assert result.error_code == "MODEL_API_UNAVAILABLE"

    assert placeholder_key not in result.error_code

def test_openai_provider_uses_injected_http_post():
    captured = {}

    def fake_http_post(
        url: str,
        *,
        headers: dict,
        json: dict,
        timeout: float,
    ) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout

        request = httpx.Request("POST", url)

        return httpx.Response(
            status_code=200,
            request=request,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "假的真实模型回答",
                        }
                    }
                ]
            },
        )

    provider = OpenAIModelProvider(
        api_key="test-placeholder-key",
        model="test-model",
        base_url="https://example.invalid",
        http_post=fake_http_post,
    )

    result = provider.call(
        prompt="请查询订单状态",
    )

    assert result.status == "success"
    assert result.content == "假的真实模型回答"
    assert result.error_code is None

    assert captured["url"] == (
        "https://example.invalid/chat/completions"
    )
    assert captured["headers"]["Authorization"] == (
        "Bearer test-placeholder-key"
    )
    assert captured["json"]["model"] == "test-model"
    assert captured["json"]["messages"] == [
        {
            "role": "user",
            "content": "请查询订单状态",
        }
    ]

def test_openai_provider_handles_network_failure():
    def fake_http_post(
        url: str,
        *,
        headers: dict,
        json: dict,
        timeout: float,
    ) -> httpx.Response:
        request = httpx.Request("POST", url)

        raise httpx.ConnectError(
            "模拟网络连接失败",
            request=request,
        )

    provider = OpenAIModelProvider(
        api_key="test-placeholder-key",
        model="test-model",
        base_url="https://example.invalid",
        http_post=fake_http_post,
    )

    result = provider.call(
        prompt="请查询订单状态",
    )

    assert result.status == "failed"
    assert result.content is None
    assert result.error_code == "MODEL_API_UNAVAILABLE"

def test_openai_provider_handles_network_timeout():
    def fake_http_post(
        url: str,
        *,
        headers: dict,
        json: dict,
        timeout: float,
    ) -> httpx.Response:
        request = httpx.Request("POST", url)

        raise httpx.ReadTimeout(
            "模拟网络连接超时",
            request=request,
        )

    provider = OpenAIModelProvider(
        api_key="test-placeholder-key",
        model="test-model",
        base_url="https://example.invalid",
        http_post=fake_http_post,
    )

    result = provider.call(
        prompt="请查询订单状态",
    )

    assert result.status == "timeout"
    assert result.content is None
    assert result.error_code == "MODEL_API_TIMEOUT"

def test_openai_provider_handles_malformed_response():
    def fake_http_post(
        url: str,
        *,
        headers: dict,
        json: dict,
        timeout: float,
    ) -> httpx.Response:
        request = httpx.Request("POST", url)

        return httpx.Response(
            status_code=200,
            request=request,
            json={
                "unexpected": "missing choices",
            },
        )

    provider = OpenAIModelProvider(
        api_key="test-placeholder-key",
        model="test-model",
        base_url="https://example.invalid",
        http_post=fake_http_post,
    )

    result = provider.call(
        prompt="请查询订单状态",
    )

    assert result.status == "failed"
    assert result.content is None
    assert result.error_code == "MODEL_INVALID_RESPONSE"

def test_openai_provider_handles_http_error_status():
    def fake_http_post(
        url: str,
        *,
        headers: dict,
        json: dict,
        timeout: float,
    ) -> httpx.Response:
        request = httpx.Request("POST", url)

        return httpx.Response(
            status_code=401,
            request=request,
            json={
                "error": {
                    "message": "模拟认证失败",
                }
            },
        )

    provider = OpenAIModelProvider(
        api_key="test-placeholder-key",
        model="test-model",
        base_url="https://example.invalid",
        http_post=fake_http_post,
    )

    result = provider.call(
        prompt="请查询订单状态",
    )

    assert result.status == "failed"
    assert result.content is None
    assert result.error_code == "MODEL_API_HTTP_401"


def test_openai_provider_uses_default_http_post_when_not_injected(
    monkeypatch,
):
    captured = {}

    def fake_default_http_post(
        url: str,
        *,
        headers: dict,
        json: dict,
        timeout: float,
    ) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout

        request = httpx.Request("POST", url)

        return httpx.Response(
            status_code=200,
            request=request,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "默认 HTTP 函数的模拟回答",
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(
        "app.model_provider.default_http_post",
        fake_default_http_post,
    )

    provider = OpenAIModelProvider(
        api_key="test-placeholder-key",
        model="test-model",
        base_url="https://example.invalid",
    )

    result = provider.call(
        prompt="请查询订单状态",
    )

    assert result.status == "success"
    assert result.content == "默认 HTTP 函数的模拟回答"
    assert result.error_code is None
    assert captured["url"] == (
        "https://example.invalid/chat/completions"
    )