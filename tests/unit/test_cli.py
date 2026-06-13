import json

from typer.testing import CliRunner

from litsearch.cli import app
from litsearch.services.search_service import SearchSummary

runner = CliRunner()


def test_sources_outputs_builtin_sources(monkeypatch):
    monkeypatch.delenv("LITSEARCH_IEEE_API_KEY", raising=False)
    result = runner.invoke(app, ["sources"])

    assert result.exit_code == 0
    for source_id in ("crossref", "openalex", "unpaywall", "ieee", "scopus", "wos"):
        assert source_id in result.output


def test_commercial_source_unconfigured_without_api_key(monkeypatch):
    monkeypatch.delenv("LITSEARCH_IEEE_API_KEY", raising=False)
    result = runner.invoke(app, ["sources"])

    assert result.exit_code == 0
    assert "ieee" in result.output
    assert "false" in result.output


def test_commercial_source_configured_with_api_key(monkeypatch):
    monkeypatch.setenv("LITSEARCH_IEEE_API_KEY", "real-secret")
    result = runner.invoke(app, ["sources"])

    assert result.exit_code == 0
    assert "ieee" in result.output
    assert "true" in result.output
    assert "real-secret" not in result.output


def test_config_show_masks_secret(monkeypatch):
    monkeypatch.setenv("LITSEARCH_IEEE_API_KEY", "real-secret")
    monkeypatch.setenv("LITSEARCH_PROXY_URL", "http://user:pass@example.com")
    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert "***" in result.output
    assert "real-secret" not in result.output
    assert "pass@example" not in result.output


def test_search_help_runs():
    result = runner.invoke(app, ["search", "--help"])

    assert result.exit_code == 0
    assert "--sources" in result.output
    assert "ieee" in result.output
    assert "scopus" in result.output
    assert "wos" in result.output


def test_search_json_output_is_parseable(monkeypatch):
    class FakeSearchService:
        def __init__(self, settings):
            self.settings = settings

        def search(
            self,
            query,
            sources,
            limit,
            enrich_unpaywall,
            year_from=None,
            year_to=None,
            open_access_only=False,
        ):
            return SearchSummary(
                search_run_id=1,
                query=query,
                sources=sources,
                status="succeeded",
                total_raw=1,
                total_saved=1,
                total_deduped=0,
                errors={},
                papers=[],
            )

    monkeypatch.setattr("litsearch.cli.SearchService", FakeSearchService)

    result = runner.invoke(app, ["search", "circular", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output)["search_run_id"] == 1


def test_search_invalid_source_returns_non_zero():
    result = runner.invoke(app, ["search", "circular", "--sources", "unpaywall"])

    assert result.exit_code != 0


def test_new_command_help_runs():
    for command in ("searches", "papers", "library", "tags", "browser", "downloads", "files"):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0

    result = runner.invoke(app, ["export", "--help"])
    assert result.exit_code == 0
    assert "--format" in result.output

    result = runner.invoke(app, ["download", "--help"])
    assert result.exit_code == 0
    assert "--force" in result.output


def test_browser_downloads_json_lists_completed_files(tmp_path, monkeypatch):
    monkeypatch.setenv("LITSEARCH_DOWNLOAD_DIR", str(tmp_path))
    (tmp_path / "paper.pdf").write_bytes(b"%PDF-1.7\n")
    (tmp_path / "paper.pdf.crdownload").write_bytes(b"partial")

    result = runner.invoke(app, ["browser", "downloads", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert len(payload) == 1
    assert payload[0]["path"].endswith("paper.pdf")


def test_download_json_output(monkeypatch):
    class FakeDownloadResult:
        def model_dump_json(self, indent=None):
            return json.dumps({"id": 7, "paper_id": 1, "status": "downloaded"}, indent=indent)

    class FakeDownloadService:
        def __init__(self, settings):
            self.settings = settings

        def download_paper(self, paper_id, force=False, output_dir=None):
            assert paper_id == 1
            assert force is False
            assert output_dir is None
            return FakeDownloadResult()

    monkeypatch.setattr("litsearch.cli.DownloadService", FakeDownloadService)

    result = runner.invoke(app, ["download", "1", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output)["status"] == "downloaded"


def test_download_missing_paper_returns_exit_code_1(monkeypatch):
    from litsearch.exceptions import LitSearchValidationError

    class FakeDownloadService:
        def __init__(self, settings):
            self.settings = settings

        def download_paper(self, paper_id, force=False, output_dir=None):
            raise LitSearchValidationError(f"Paper not found: {paper_id}")

    monkeypatch.setattr("litsearch.cli.DownloadService", FakeDownloadService)

    result = runner.invoke(app, ["download", "999"])

    assert result.exit_code == 1
    assert "Paper not found: 999" in result.output


def test_downloads_list_and_get_json(monkeypatch):
    class FakeResult:
        def __init__(self, id):
            self.id = id
            self.paper_id = 1
            self.status = "skipped"
            self.source = None
            self.file_path = None
            self.size_bytes = None
            self.error = None

        def model_dump(self):
            return {"id": self.id, "paper_id": self.paper_id, "status": self.status}

        def model_dump_json(self, indent=None):
            return json.dumps(self.model_dump(), indent=indent)

    class FakeDownloadService:
        def __init__(self, settings):
            self.settings = settings

        def list_downloads(self, limit):
            return [FakeResult(3)]

        def get_download(self, download_id):
            return FakeResult(download_id)

    monkeypatch.setattr("litsearch.cli.DownloadService", FakeDownloadService)

    listed = runner.invoke(app, ["downloads", "list", "--json"])
    fetched = runner.invoke(app, ["downloads", "get", "3", "--json"])

    assert listed.exit_code == 0
    assert json.loads(listed.output)[0]["id"] == 3
    assert fetched.exit_code == 0
    assert json.loads(fetched.output)["id"] == 3


def test_files_list_and_open(monkeypatch, tmp_path):
    class FakeFile:
        paper_id = 1
        title = "Paper"
        year = 2024
        file_path = tmp_path / "paper.pdf"
        size_bytes = 9
        sha256 = "abc"
        download_id = 2

    class FakeFileService:
        def __init__(self, settings):
            self.settings = settings

        def list_files(self):
            return [FakeFile()]

        def open_file(self, paper_id):
            return tmp_path / f"{paper_id}.pdf"

    monkeypatch.setattr("litsearch.cli.FileService", FakeFileService)

    listed = runner.invoke(app, ["files", "list", "--json"])
    opened = runner.invoke(app, ["files", "open", "1"])

    assert listed.exit_code == 0
    assert json.loads(listed.output)[0]["paper_id"] == 1
    assert opened.exit_code == 0
    assert str(tmp_path / "1.pdf") in opened.output
