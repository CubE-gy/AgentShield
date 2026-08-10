from app.model_provider import MockModelProvider, OpenAIModelProvider
from app.provider_factory import create_provider
from app.settings import Settings


def test_factory_creates_mock_provider_by_default():
    settings = Settings(
        _env_file=None,
        dev_database_url="postgresql+psycopg://dev_user:dev_password@127.0.0.1:5432/dev_db",
        test_database_url="postgresql+psycopg://test_user:test_password@127.0.0.1:5433/test_db",
    )

    provider = create_provider(settings)

    assert isinstance(provider, MockModelProvider)


def test_factory_creates_openai_provider_when_selected():
    settings = Settings(
        _env_file=None,
        dev_database_url="postgresql+psycopg://dev_user:dev_password@127.0.0.1:5432/dev_db",
        test_database_url="postgresql+psycopg://test_user:test_password@127.0.0.1:5433/test_db",
        model_provider="real",
        model_api_key=None,
        model_name="test-model",
        model_base_url="https://example.invalid",
    )

    provider = create_provider(settings)

    assert isinstance(provider, OpenAIModelProvider)

def test_real_provider_without_api_key_returns_safe_error():
    settings = Settings(
        _env_file=None,
        dev_database_url=(
            "postgresql+psycopg://dev_user:dev_password@127.0.0.1:5432/dev_db"
        ),
        test_database_url=(
            "postgresql+psycopg://test_user:test_password@127.0.0.1:5433/test_db"
        ),
        model_provider="real",
        model_api_key=None,
        model_name="test-model",
        model_base_url="https://example.invalid",
    )

    provider = create_provider(settings)

    result = provider.call(
        prompt="请查询订单状态",
    )

    assert result.status == "failed"
    assert result.content is None
    assert result.error_code == "MODEL_API_KEY_MISSING"