# RefPort

Literature search CLI for metadata sources. The current implementation can search
OpenAlex, Crossref, IEEE Xplore, and Scopus, normalize results, deduplicate by DOI or
title/year, persist records to SQLite, and record each search run.

## Commands

```bash
uv run litsearch sources
uv run litsearch config show
uv run litsearch db init
uv run litsearch search "circular supply chain" --sources openalex,crossref --limit 5
uv run litsearch search "circular supply chain" --sources ieee --limit 5 --json
uv run litsearch search "circular supply chain" --sources scopus --limit 5 --json
uv run litsearch search "circular supply chain" --sources openalex,crossref --limit 5 --json
uv run pytest
uv run ruff check .
```

OpenAlex and Crossref can be searched without an email address, though setting
`LITSEARCH_CONTACT_EMAIL` is recommended. Unpaywall is used only for DOI-based
open-access metadata enrichment and requires `LITSEARCH_UNPAYWALL_EMAIL` or
`LITSEARCH_CONTACT_EMAIL`.

IEEE Xplore search uses the official IEEE Xplore Metadata API and requires
`LITSEARCH_IEEE_API_KEY`. Scopus search uses Elsevier's official Scopus Search API and requires
`LITSEARCH_SCOPUS_API_KEY`. `LITSEARCH_SCOPUS_INST_TOKEN` is optional for
institution-token setups. Commercial sources are not included in the default
search sources, so request them explicitly with `--sources ieee` or
`--sources scopus`.

Web of Science remains listed as a reserved commercial metadata source, but its
search connector is not enabled until API access is ready.
