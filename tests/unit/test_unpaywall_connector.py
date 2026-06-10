import json
from pathlib import Path

from litsearch.config import Settings
from litsearch.connectors.unpaywall import UnpaywallConnector


class FakeHttpClient:
    def __init__(self, payload):
        self.payload = payload

    def get_json(self, url, params=None, headers=None):
        self.url = url
        self.params = params
        return self.payload


def test_unpaywall_connector_parses_lookup_fixture():
    payload = json.loads(Path("tests/fixtures/unpaywall_lookup.json").read_text())
    settings = Settings(contact_email="me@example.com", _env_file=None)
    connector = UnpaywallConnector(settings, FakeHttpClient(payload))

    paper = connector.lookup_by_doi("10.1234/example")

    assert paper.pdf_url == "https://example.org/oa.pdf"
    assert paper.is_open_access is True
    assert paper.authors == ["Ada Lovelace"]
