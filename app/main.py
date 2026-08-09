from fastapi import FastAPI
from pydantic import BaseModel

from app.model_provider import MockModelProvider
from app.model_service import call_model_and_save_audit
from app.provider_factory import create_provider
from app.settings import Settings
from app.db import SessionLocal

class ModelTestRequest(BaseModel):
    request_id: str = "req-api-default"
    tenant_id: str = "tenant-demo"
    agent_id: str = "agent-support"
    prompt: str
    scenario: str

settings = Settings()

app = FastAPI(title="AgentShield")

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/model/test")
def model_test(request: ModelTestRequest):
    session = SessionLocal()

    provider = create_provider(settings)

    if isinstance(provider, MockModelProvider):
        provider.scenario = request.scenario

    try:
        service_record = call_model_and_save_audit(
            session=session,
            request_id=request.request_id,
            tenant_id=request.tenant_id,
            agent_id=request.agent_id,
            prompt=request.prompt,
            scenario=request.scenario,
            provider=provider,
        )

        return {
            "status": service_record.model_result.status,
            "content":service_record.model_result.content,
            "error_code": service_record.model_result.error_code,
        }
    finally:
        session.close()
