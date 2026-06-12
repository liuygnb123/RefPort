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
    for command in ("searches", "papers", "library", "tags"):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0

    result = runner.invoke(app, ["export", "--help"])
    assert result.exit_code == 0
    assert "--format" in result.output
