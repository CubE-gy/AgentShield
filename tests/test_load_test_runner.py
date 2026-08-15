import pytest

from scripts import run_load_test
from scripts.run_load_test import RequestResult, build_report, get_api_key


def test_build_report_calculates_success_errors_throughput_and_latency() -> None:
    report = build_report(
        results=[
            RequestResult(success=True, latency_ms=100.0, error_type=None),
            RequestResult(success=True, latency_ms=200.0, error_type=None),
            RequestResult(success=False, latency_ms=300.0, error_type="http_500"),
        ],
        elapsed_seconds=0.5,
        request_count=3,
        concurrency=2,
        base_url="http://127.0.0.1:8000",
        git_revision="test-revision",
    )

    assert report["results"] == {
        "success_count": 2,
        "error_count": 1,
        "throughput_requests_per_second": 6.0,
        "latency_ms": {"average": 200.0, "maximum": 300.0},
        "error_types": {"http_500": 1},
    }
    assert report["parameters"] == {"request_count": 3, "concurrency": 2}
    assert report["environment"]["git_revision"] == "test-revision"


def test_get_api_key_requires_local_environment_variable(monkeypatch) -> None:
    monkeypatch.delenv("AGENTSHIELD_LOAD_TEST_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="AGENTSHIELD_LOAD_TEST_API_KEY"):
        get_api_key()


def test_load_test_client_does_not_use_system_proxy(monkeypatch) -> None:
    captured_arguments = {}

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured_arguments.update(kwargs)

    monkeypatch.setattr(run_load_test.httpx, "Client", FakeClient)

    run_load_test.create_http_client()

    assert captured_arguments["trust_env"] is False
