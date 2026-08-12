from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Protocol, runtime_checkable
from collections.abc import Callable

import httpx

@dataclass
class ModelResult:
    status: str
    content: str | None
    error_code: str | None

@runtime_checkable
class ModelProvider(Protocol):
    def call(self, prompt: str) -> ModelResult:
        ...

class MockModelProvider:
    def __init__(self, scenario: str = "success"):
        self.scenario = scenario

    def call(
        self,
        prompt: str,
    ) -> ModelResult:
        active_scenario = self.scenario

        if active_scenario == "reject":
            return ModelResult(
                status="rejected",
                content=None,
                error_code="MODEL_REFUSED",
            )
        elif active_scenario == "failure":
            return ModelResult(
                status = "failed",
                content = None,
                error_code = "MODEL_UNAVAILABLE",
            )
        elif active_scenario == "timeout":
            return ModelResult(
                status = "timeout",
                content = None,
                error_code = "MODEL_TIMEOUT",
            )
        elif active_scenario == "malformed":
            return ModelResult(
                status = "failed",
                content = None,
                error_code = "MODEL_INVALID_RESPONSE",
            )
        elif active_scenario == "success":
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

def default_http_post(
    url: str,
    *,
    headers: dict,
    json: dict,
    timeout: float,
) -> httpx.Response:
    return httpx.post(
        url,
        headers=headers,
        json=json,
        timeout=timeout,
    )

class OpenAIModelProvider:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str,
        http_post: Callable | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.http_post = (
            default_http_post
            if http_post is None
            else http_post
        )

    def call(self, prompt: str) -> ModelResult:
        if not self.api_key:
            return ModelResult(
                status="failed",
                content=None,
                error_code="MODEL_API_KEY_MISSING",
            )

        url = f"{self.base_url.rstrip('/')}/chat/completions"

        try:
            response: httpx.Response = self.http_post(
                url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                },
                timeout=30.0,
            )

        except httpx.ConnectError:
            return ModelResult(
                status="failed",
                content=None,
                error_code="MODEL_API_UNAVAILABLE",
            )
        except httpx.ReadTimeout:
            return ModelResult(
                status="timeout",
                content=None,
                error_code="MODEL_API_TIMEOUT",
            )

        if response.status_code >= 400:
            return ModelResult(
                status="failed",
                content=None,
                error_code=f"MODEL_API_HTTP_{response.status_code}",
            )

        try:
            response_data = response.json()
            content = response_data["choices"][0]["message"]["content"]
        except(KeyError, IndexError, TypeError, ValueError):
            return ModelResult(
                status="failed",
                content=None,
                error_code="MODEL_INVALID_RESPONSE",
            )

        return ModelResult(
            status="success",
            content=content,
            error_code=None,
        )

def build_audit_summary(
    result: ModelResult,
    security_risk_type: str | None = None,
    security_action: str | None = None,
) -> str:
    # 这里不读取完整回答，避免敏感内容进入审计摘要
    summary = f"model_status={result.status}"

    if result.error_code is not None:
        summary += f";error_code={result.error_code}"

    if security_risk_type is not None:
        summary += f";security_risk_type={security_risk_type}"

    if security_action is not None:
        summary += f";security_action={security_action}"

    return summary

def build_audit_record_data(
    request_id: str,
    tenant_id: str,
    agent_id: str,
    result: ModelResult,
    latency_ms: int,
    risk_level: str = "low",
    security_risk_type: str | None = None,
    security_action: str | None = None,
) -> dict:
    summary = build_audit_summary(
        result,
        security_risk_type=security_risk_type,
        security_action=security_action,
    )
    summary_hash = hashlib.sha256(summary.encode("utf-8")).hexdigest()

    return {
        "request_id": request_id,
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "created_at": datetime.now(timezone.utc),
        "risk_level": risk_level,
        "status": result.status,
        "error_code": result.error_code,
        "latency_ms": latency_ms,
        "summary": summary,
        "summary_hash": summary_hash,
    }
