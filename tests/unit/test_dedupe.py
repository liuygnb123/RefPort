from litsearch.connectors.base import SourcePaper
from litsearch.services.dedupe import paper_identity


def test_paper_identity_prefers_doi():
    paper = SourcePaper(source="crossref", title="A", doi="https://doi.org/10.1/ABC")

    assert paper_identity(paper) == ("doi", "10.1/abc")


def test_paper_identity_uses_title_and_year_without_doi():
    paper = SourcePaper(source="openalex", title="<b>A Paper</b>", publication_year=2024)

    assert paper_identity(paper) == ("title_year", "a paper|2024")
