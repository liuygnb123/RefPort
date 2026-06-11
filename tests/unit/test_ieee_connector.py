import json
from pathlib import Path

import pytest

from litsearch.config import Settings
from litsearch.connectors.base import SearchRequest
from litsearch.connectors.ieee import IEEE_SEARCH_URL, IEEEConnector
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


def test_ieee_connector_requires_api_key():
    connector = IEEEConnector(Settings(_env_file=None), FakeHttpClient({}))

    with pytest.raises(SourceNotConfiguredError):
        connector.search(SearchRequest(query="circular", limit=1))


def test_ieee_connector_uses_endpoint_and_params():
    client = FakeHttpClient({"articles": []})
    connector = IEEEConnector(Settings(ieee_api_key="secret-key", _env_file=None), client)

    connector.search(SearchRequest(query="circular", limit=5))

    assert client.url == IEEE_SEARCH_URL
    assert client.params == {
        "querytext": "circular",
        "max_records": 5,
        "apikey": "secret-key",
    }
    assert client.headers is None


def test_ieee_connector_parses_search_fixture():
    payload = json.loads(Path("tests/fixtures/ieee_search.json").read_text())
    connector = IEEEConnector(
        Settings(ieee_api_key="secret-key", _env_file=None),
        FakeHttpClient(payload),
    )

    papers = connector.search(SearchRequest(query="circular", limit=1))

    assert papers[0].source == "ieee"
    assert papers[0].source_paper_id == "9876543"
    assert papers[0].title == "Circular supply chain optimization using digital twins"
    assert papers[0].doi == "10.1109/example.2024.9876543"
    assert papers[0].authors == ["Ada Lovelace", "Grace Hopper"]
    assert papers[0].venue_name == "IEEE Transactions on Engineering Management"
    assert papers[0].publication_year == 2024
    assert papers[0].publication_date == "2024-05-12"
    assert papers[0].citation_count == 12
    assert papers[0].is_open_access is True


def test_ieee_connector_tolerates_missing_optional_fields():
    payload = {"articles": [{"title": "Sparse IEEE Record", "article_number": 123}]}
    connector = IEEEConnector(
        Settings(ieee_api_key="secret-key", _env_file=None),
        FakeHttpClient(payload),
    )

    papers = connector.search(SearchRequest(query="sparse", limit=1))

    assert papers[0].source == "ieee"
    assert papers[0].source_paper_id == "123"
    assert papers[0].source_url == "https://ieeexplore.ieee.org/document/123"
    assert papers[0].doi is None
