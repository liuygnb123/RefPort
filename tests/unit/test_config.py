from litsearch.config import Settings


def test_default_config_loads():
    settings = Settings(_env_file=None)

    assert settings.db_url == "sqlite:///./data/litsearch.db"
    assert settings.log_level == "INFO"


def test_environment_can_override_defaults(monkeypatch):
    monkeypatch.setenv("LITSEARCH_DB_URL", "sqlite:///./tmp/test.db")
    monkeypatch.setenv("LITSEARCH_LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.db_url == "sqlite:///./tmp/test.db"
    assert settings.log_level == "DEBUG"


def test_contact_email_is_fallback_for_public_sources():
    settings = Settings(contact_email="team@example.com", _env_file=None)

    assert settings.source_email("crossref") == "team@example.com"
    assert settings.source_email("openalex") == "team@example.com"
    assert settings.source_email("unpaywall") == "team@example.com"


def test_api_keys_are_masked():
    settings = Settings(ieee_api_key="secret-key", _env_file=None)

    safe = settings.safe_dump()

    assert safe["ieee_api_key"] == "***"
    assert "secret-key" not in str(safe)


def test_proxy_password_is_masked():
    settings = Settings(proxy_url="http://user:pass@example.com:8080", _env_file=None)

    safe = settings.safe_dump()

    assert safe["proxy_url"] == "http://user:***@example.com:8080"
    assert "pass" not in safe["proxy_url"]
