import json
from pathlib import Path

from litsearch.config import Settings
from litsearch.connectors.base import SearchRequest
from litsearch.connectors.openalex import OpenAlexConnector


class FakeHttpClient:
    def __init__(self, payload):
        self.payload = payload

    def get_json(self, url, params=None, headers=None):
        self.url = url
        self.params = params
        return self.payload


def test_openalex_connector_parses_search_fixture():
    payload = json.loads(Path("tests/fixtures/openalex_search.json").read_text())
    client = FakeHttpClient(payload)
    connector = OpenAlexConnector(Settings(_env_file=None), client)

    papers = connector.search(SearchRequest(query="circular", limit=1))

    assert papers[0].source == "openalex"
    assert papers[0].doi == "https://doi.org/10.1234/example"
    assert papers[0].abstract == "Circular supply chains"
    assert papers[0].authors == ["Ada Lovelace"]
    assert papers[0].venue_name == "Journal of Circularity"
    assert papers[0].is_open_access is True
