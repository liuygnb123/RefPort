# RefPort

Literature search CLI for metadata sources. The current implementation can search
OpenAlex, Crossref, IEEE Xplore, Scopus, and Web of Science, normalize results,
deduplicate by DOI or title/year, persist records to SQLite, and record each
search run. It can also browse saved search history, filter the local paper
library, manage favorites/status/tags/notes, and export references to BibTeX,
RIS, or CSV. RefPort can download and manage open-access PDFs when a saved
paper has a public PDF URL, a public landing page advertises a PDF link, or
OpenAlex/Unpaywall returns an open-access PDF location. Browser collection
infrastructure is available for logged-in platform workflows: it can save page
HTML/screenshot diagnostics, inspect download folders, and archive
browser-downloaded files into the downloads table.

## Commands

```bash
uv run litsearch sources
uv run litsearch config show
uv run litsearch db init
uv run litsearch search "circular supply chain" --sources openalex,crossref --limit 5
uv run litsearch search "circular supply chain" --sources openalex,crossref --limit 5 --year-from 2020 --open-access-only
uv run litsearch searches list
uv run litsearch searches get 1
uv run litsearch papers list --query circular --limit 10
uv run litsearch papers get 1
uv run litsearch library add 1 --status reading --favorite --rating 4 --notes "Important seed paper"
uv run litsearch library update 1 --status read --no-favorite
uv run litsearch library remove 1
uv run litsearch tags list
uv run litsearch tags add circular-economy
uv run litsearch tags remove circular-economy
uv run litsearch papers tag 1 circular-economy
uv run litsearch papers untag 1 circular-economy
uv run litsearch export --format bibtex --tag circular-economy --output /tmp/refport.bib
uv run litsearch export --format ris --favorite --output /tmp/refport.ris
uv run litsearch export --format csv --output /tmp/refport.csv
uv run litsearch download 1 --json
uv run litsearch download 1 --force --output-dir ./data/papers
uv run litsearch downloads list
uv run litsearch downloads get 1
uv run litsearch files list
uv run litsearch files open 1
uv run litsearch browser inspect "https://scholar.google.com" --login-text "Sign in"
uv run litsearch browser downloads --dir ~/Downloads
uv run litsearch browser archive 1 ~/Downloads/paper.pdf
uv run litsearch search "circular supply chain" --sources ieee --limit 5 --json
uv run litsearch search "circular supply chain" --sources scopus --limit 5 --json
uv run litsearch search "circular supply chain" --sources wos --limit 5 --json
uv run litsearch search "circular supply chain" --sources openalex,crossref --limit 5 --json
uv run pytest
uv run ruff check .
```

OpenAlex and Crossref can be searched without an email address, though setting
`LITSEARCH_CONTACT_EMAIL` is recommended. Unpaywall is used only for DOI-based
open-access metadata enrichment and requires `LITSEARCH_UNPAYWALL_EMAIL` or
`LITSEARCH_CONTACT_EMAIL`.

Open-access PDF download lookup also uses `LITSEARCH_UNPAYWALL_EMAIL` or
`LITSEARCH_CONTACT_EMAIL` for DOI-based Unpaywall requests. By default PDFs and
metadata are stored under `LITSEARCH_PAPER_DIR`, which defaults to
`./data/papers`:

```dotenv
LITSEARCH_CONTACT_EMAIL=you@example.com
LITSEARCH_UNPAYWALL_EMAIL=you@example.com
LITSEARCH_PAPER_DIR=./data/papers
```

PDF downloads are limited to open-access locations: stored `pdf_url` metadata,
public landing page PDF meta tags or links, OpenAlex DOI open-access locations,
and Unpaywall open-access PDF locations. RefPort does not support Sci-Hub,
credential automation, CAPTCHA solving, institution access bypasses, or paywall
bypasses.

IEEE Xplore search uses the official IEEE Xplore Metadata API and requires
`LITSEARCH_IEEE_API_KEY`. Scopus search uses Elsevier's official Scopus Search API and requires
`LITSEARCH_SCOPUS_API_KEY`. `LITSEARCH_SCOPUS_INST_TOKEN` is optional for
institution-token setups. Commercial sources are not included in the default
search sources, so request them explicitly with `--sources ieee` or
`--sources scopus`. Web of Science Starter API search requires
`LITSEARCH_WOS_API_KEY` and can be requested explicitly with `--sources wos`.

Browser inspection uses Playwright. If Chromium has not been installed on the
machine yet, run:

```bash
uv run playwright install chromium
```

Browser workflows are intended for user-controlled, legitimate sessions. RefPort
does not automate credential entry, CAPTCHA solving, or access-control bypasses.
