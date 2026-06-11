import httpx
import pytest

from litsearch.config import Settings
from litsearch.connectors.http import HttpClient
from litsearch.exceptions import ConnectorError


def test_http_client_status_error_does_not_include_sensitive_headers(monkeypatch):
    def fake_get(self, url, params=None, headers=None):
        request = httpx.Request("GET", url, headers=headers)
        response = httpx.Response(403, request=request)
        return response

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    client = HttpClient(Settings(_env_file=None))

    with pytest.raises(ConnectorError) as exc_info:
        client.get_json(
            "https://api.example.test/search",
            headers={"Authorization": "Bearer secret-token", "X-ELS-APIKey": "secret-key"},
        )

    message = str(exc_info.value)
    assert "403" in message
    assert "secret-token" not in message
    assert "secret-key" not in message
