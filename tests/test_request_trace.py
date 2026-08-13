from app.main import app
from fastapi.testclient import TestClient


def test_response_has_a_unique_request_trace_id():
    client = TestClient(app)

    first_response = client.get("/health")
    second_response = client.get("/health")

    first_trace_id = first_response.headers["X-Request-Trace-Id"]
    second_trace_id = second_response.headers["X-Request-Trace-Id"]

    assert len(first_trace_id) == 32
    assert first_trace_id != second_trace_id
