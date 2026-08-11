import pytest

from app.authentication import (
    ApiKeyAuthenticationError,
    ApiKeyRecord,
    authenticate_api_key,
    load_api_key_records,
)


def test_active_api_key_returns_its_tenant():
    record = authenticate_api_key(
        provided_key="test-active-key",
        records=[
            ApiKeyRecord(
                value="test-active-key",
                tenant_id="tenant-alpha",
                is_active=True,
            )
        ],
    )

    assert record.tenant_id == "tenant-alpha"


@pytest.mark.parametrize("provided_key", [None, ""])
def test_missing_api_key_is_rejected(provided_key: str | None):
    with pytest.raises(ApiKeyAuthenticationError) as error:
        authenticate_api_key(provided_key=provided_key, records=[])

    assert error.value.error_code == "API_KEY_MISSING"


def test_unknown_api_key_is_rejected():
    with pytest.raises(ApiKeyAuthenticationError) as error:
        authenticate_api_key(
            provided_key="test-unknown-key",
            records=[
                ApiKeyRecord(
                    value="test-active-key",
                    tenant_id="tenant-alpha",
                    is_active=True,
                )
            ],
        )

    assert error.value.error_code == "API_KEY_INVALID"


def test_disabled_api_key_is_rejected():
    with pytest.raises(ApiKeyAuthenticationError) as error:
        authenticate_api_key(
            provided_key="test-disabled-key",
            records=[
                ApiKeyRecord(
                    value="test-disabled-key",
                    tenant_id="tenant-alpha",
                    is_active=False,
                )
            ],
        )

    assert error.value.error_code == "API_KEY_DISABLED"


def test_load_api_key_records_reads_safe_configuration_format():
    records = load_api_key_records(
        '[{"value": "test-key", "tenant_id": "tenant-alpha", "is_active": true}]'
    )

    assert records == [
        ApiKeyRecord(
            value="test-key",
            tenant_id="tenant-alpha",
            is_active=True,
        )
    ]