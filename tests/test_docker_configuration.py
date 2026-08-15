from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_starts_fastapi_on_container_port_8000() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "EXPOSE 8000" in dockerfile
    assert "COPY alembic.ini ./" in dockerfile
    assert "COPY migrations ./migrations" in dockerfile
    assert "COPY docker-entrypoint.sh ./" in dockerfile
    assert 'ENTRYPOINT ["/app/docker-entrypoint.sh"]' in dockerfile
    assert '"uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"' in dockerfile


def test_compose_defines_fastapi_service_with_local_configuration() -> None:
    compose_file = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "  app:" in compose_file
    assert "    build: ." in compose_file
    assert "      - .env" in compose_file
    assert '      - "8000:8000"' in compose_file
    assert "      postgres-dev:" in compose_file
    assert "      redis:" in compose_file
    assert "        condition: service_healthy" in compose_file


def test_container_entrypoint_runs_migrations_before_starting_fastapi() -> None:
    entrypoint = (PROJECT_ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")

    assert "alembic upgrade head" in entrypoint
    assert 'exec "$@"' in entrypoint


def test_docker_build_excludes_local_secrets_and_virtual_environment() -> None:
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert ".env" in dockerignore
    assert ".venv/" in dockerignore
