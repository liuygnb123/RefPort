import json
from pathlib import Path

from litsearch.config import Settings
from litsearch.connectors.base import SearchRequest
from litsearch.connectors.crossref import CrossrefConnector


class FakeHttpClient:
    def __init__(self, payload):
        self.payload = payload

    def get_json(self, url, params=None, headers=None):
        self.url = url
        self.params = params
        return self.payload


def test_crossref_connector_parses_search_fixture():
    payload = json.loads(Path("tests/fixtures/crossref_search.json").read_text())
    connector = CrossrefConnector(Settings(_env_file=None), FakeHttpClient(payload))

    papers = connector.search(SearchRequest(query="closed loop", limit=1))

    assert papers[0].source == "crossref"
    assert papers[0].doi == "10.5678/crossref"
    assert papers[0].title == "Closed-Loop Supply Chain Review"
    assert papers[0].abstract == "a review paper."
    assert papers[0].authors == ["Grace Hopper"]
    assert papers[0].venue_name == "Supply Chain Journal"
    assert papers[0].publication_year == 2023
