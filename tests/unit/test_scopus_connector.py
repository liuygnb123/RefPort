import json
from pathlib import Path

import pytest

from litsearch.config import Settings
from litsearch.connectors.base import SearchRequest
from litsearch.connectors.scopus import SCOPUS_SEARCH_URL, ScopusConnector
from litsearch.exceptions import SourceNotConfiguredError


class FakeHttpClient:
    def __init__(self, payload):
        self.payload = payload
        self.url = None
        self.params = None
        self.headers = None

    def get_json(self, url, params=None, headers=None):
        self.url = url
        self.params = params
        self.headers = headers
        return self.payload


def test_scopus_connector_requires_api_key():
    connector = ScopusConnector(Settings(_env_file=None), FakeHttpClient({}))

    with pytest.raises(SourceNotConfiguredError):
        connector.search(SearchRequest(query="circular", limit=1))


def test_scopus_connector_uses_endpoint_params_and_headers():
    client = FakeHttpClient({"search-results": {"entry": []}})
    settings = Settings(
        scopus_api_key="secret-key",
        scopus_inst_token="inst-token",
        _env_file=None,
    )
    connector = ScopusConnector(settings, client)

    connector.search(SearchRequest(query="circular", limit=50))

    assert client.url == SCOPUS_SEARCH_URL
    assert client.params == {"query": "circular", "count": 25}
    assert client.headers == {
        "Accept": "application/json",
        "X-ELS-APIKey": "secret-key",
        "X-ELS-Insttoken": "inst-token",
    }


def test_scopus_connector_parses_search_fixture():
    payload = json.loads(Path("tests/fixtures/scopus_search.json").read_text())
    connector = ScopusConnector(
        Settings(scopus_api_key="secret-key", _env_file=None),
        FakeHttpClient(payload),
    )

    papers = connector.search(SearchRequest(query="circular", limit=1))

    assert papers[0].source == "scopus"
    assert papers[0].source_paper_id == "2-s2.0-85123456789"
    assert papers[0].title == "Circular supply chain resilience"
    assert papers[0].doi == "10.1016/example.2024.01.001"
    assert papers[0].authors == ["Lovelace, Ada"]
    assert papers[0].venue_name == "Journal of Circular Supply Chains"
    assert papers[0].publication_year == 2024
    assert papers[0].publication_date == "2024-02-15"
    assert papers[0].citation_count == 7
    assert papers[0].is_open_access is True


def test_scopus_connector_tolerates_missing_optional_fields():
    payload = {"search-results": {"entry": [{"dc:title": "Sparse Scopus Record"}]}}
    connector = ScopusConnector(
        Settings(scopus_api_key="secret-key", _env_file=None),
        FakeHttpClient(payload),
    )

    papers = connector.search(SearchRequest(query="sparse", limit=1))

    assert papers[0].source == "scopus"
    assert papers[0].title == "Sparse Scopus Record"
    assert papers[0].doi is None
