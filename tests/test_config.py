import pytest
from pydantic import ValidationError

from api.config import Settings


def make(**overrides) -> Settings:
    values = {"database_url": "postgresql+psycopg://u:p@h/db"} | overrides
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize("scheme", ["postgres://", "postgresql://"])
def test_render_database_urls_use_psycopg(scheme):
    assert make(database_url=f"{scheme}u:p@h:5432/db").database_url == (
        "postgresql+psycopg://u:p@h:5432/db"
    )


def test_wildcard_cors_is_rejected():
    with pytest.raises(ValidationError):
        make(cors_origins=["*"])


def test_sandbox_is_the_default():
    settings = make()
    assert settings.paypal_env == "sandbox"
    assert settings.paypal_base_url == "https://api-m.sandbox.paypal.com"


def test_unknown_paypal_env_is_rejected():
    with pytest.raises(ValidationError):
        make(paypal_env="production")


def test_secrets_are_not_printed():
    settings = make(paypal_client_secret="super-secret-value")
    assert "super-secret-value" not in repr(settings)
