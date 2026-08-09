from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib

@dataclass
class ModelResult:
    status: str
    content: str | None
    error_code: str | None

class MockModelProvider:
    def call(self, prompt: str, scenario: str) -> ModelResult:
        if scenario == "reject":
            return ModelResult(
                status = "rejected",
                content = None,
                error_code = "MODEL_REFUSED",
            )
        elif scenario == "failure":
            return ModelResult(
                status = "failed",
                content = None,
                error_code = "MODEL_UNAVAILABLE",
            )
        elif scenario == "timeout":
            return ModelResult(
                status = "timeout",
                content = None,
                error_code = "MODEL_TIMEOUT",
            )
        elif scenario == "malformed":
            return ModelResult(
                status = "failed",
                content = None,
                error_code = "MODEL_INVALID_RESPONSE",
            )
        elif scenario == "success":
            return ModelResult(
                status="success",
                content="这是Mock模型的正常回答",
                error_code=None,
            )

        return ModelResult(
            status="failed",
            content=None,
            error_code="MODEL_INVALID_SCENARIO",
        )


def build_audit_summary(result: ModelResult) -> str:
    # 这里不读取完整回答，避免敏感内容进入审计摘要
    summary = f"model_status={result.status}"

    if result.error_code is not None:
        summary += f";error_code={result.error_code}"

    return summary

def build_audit_record_data(
    request_id: str,
    tenant_id: str,
    agent_id: str,
    result: ModelResult,
    latency_ms: int,
) -> dict:
    summary = build_audit_summary(result)
    summary_hash = hashlib.sha256(summary.encode("utf-8")).hexdigest()

    return {
        "request_id": request_id,
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "created_at": datetime.now(timezone.utc),
        "risk_level": "low",
        "status": result.status,
        "error_code": result.error_code,
        "latency_ms": latency_ms,
        "summary": summary,
        "summary_hash": summary_hash,
    }