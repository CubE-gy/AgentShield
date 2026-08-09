from app.model_provider import (
    MockModelProvider,
    OpenAIModelProvider,
    ModelProvider,
)
from app.settings import Settings


def create_provider(settings: Settings) -> ModelProvider:
    if settings.model_provider == "real":
        return OpenAIModelProvider(
            api_key=settings.model_api_key,
            model=settings.model_name,
            base_url=settings.model_base_url,
        )

    return MockModelProvider()