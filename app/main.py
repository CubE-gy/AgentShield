from fastapi import FastAPI


app = FastAPI(title="AgentShield")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
