# RefPort

Phase 1 literature search CLI for open metadata sources. The current implementation
can search OpenAlex and Crossref, normalize results, deduplicate by DOI or
title/year, persist records to SQLite, and record each search run.

## Commands

```bash
uv run litsearch sources
uv run litsearch config show
uv run litsearch db init
uv run litsearch search "circular supply chain" --sources openalex,crossref --limit 5
uv run litsearch search "circular supply chain" --sources openalex,crossref --limit 5 --json
uv run pytest
uv run ruff check .
```

OpenAlex and Crossref can be searched without an email address, though setting
`LITSEARCH_CONTACT_EMAIL` is recommended. Unpaywall is used only for DOI-based
open-access metadata enrichment and requires `LITSEARCH_UNPAYWALL_EMAIL` or
`LITSEARCH_CONTACT_EMAIL`.
