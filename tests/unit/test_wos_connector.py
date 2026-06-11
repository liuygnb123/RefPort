import json
from pathlib import Path

import pytest

from litsearch.config import Settings
from litsearch.connectors.base import SearchRequest
from litsearch.connectors.wos import WOS_DOCUMENTS_URL, WosConnector
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


def test_wos_connector_requires_api_key():
    connector = WosConnector(Settings(_env_file=None), FakeHttpClient({}))

    with pytest.raises(SourceNotConfiguredError):
        connector.search(SearchRequest(query="circular", limit=1))


def test_wos_connector_uses_endpoint_params_and_headers():
    client = FakeHttpClient({"hits": []})
    connector = WosConnector(Settings(wos_api_key="secret-key", _env_file=None), client)

    connector.search(SearchRequest(query="circular", limit=100))

    assert client.url == WOS_DOCUMENTS_URL
    assert client.params == {"q": "circular", "limit": 50, "page": 1}
    assert client.headers == {
        "Accept": "application/json",
        "X-ApiKey": "secret-key",
    }


def test_wos_connector_parses_search_fixture():
    payload = json.loads(Path("tests/fixtures/wos_search.json").read_text())
    connector = WosConnector(
        Settings(wos_api_key="secret-key", _env_file=None),
        FakeHttpClient(payload),
    )

    papers = connector.search(SearchRequest(query="circular", limit=1))

    assert papers[0].source == "wos"
    assert papers[0].source_paper_id == "WOS:000123456789001"
    assert papers[0].title == "Circular supply chain design for resilient manufacturing"
    assert papers[0].doi == "10.1000/wos.example"
    assert papers[0].authors == ["Ada Lovelace", "Grace Hopper"]
    assert papers[0].venue_name == "Journal of Web Science"
    assert papers[0].publication_year == 2024
    assert papers[0].publication_date == "2024-03-01"
    assert papers[0].citation_count == 9
    assert papers[0].is_open_access is True


def test_wos_connector_tolerates_documents_list_and_missing_optional_fields():
    payload = {"documents": [{"UT": "WOS:SPARSE", "title": ["Sparse WOS Record"]}]}
    connector = WosConnector(
        Settings(wos_api_key="secret-key", _env_file=None),
        FakeHttpClient(payload),
    )

    papers = connector.search(SearchRequest(query="sparse", limit=1))

    assert papers[0].source == "wos"
    assert papers[0].source_paper_id == "WOS:SPARSE"
    assert papers[0].title == "Sparse WOS Record"
    assert papers[0].doi is None
