from litsearch.normalization import extract_year, normalize_doi, normalize_name, normalize_title


def test_normalize_doi_handles_urls_prefixes_and_punctuation():
    assert normalize_doi(" https://doi.org/10.1234/ABC. ") == "10.1234/abc"
    assert normalize_doi("doi:10.5555/Test;") == "10.5555/test"


def test_normalize_title_removes_html_and_collapses_space():
    assert normalize_title("<b>Circular</b>   Supply\nChain") == "circular supply chain"


def test_normalize_name_and_empty_values():
    assert normalize_name(" Ada   Lovelace ") == "ada lovelace"
    assert normalize_name(None) is None


def test_extract_year_from_date_strings():
    assert extract_year("2024-01-31") == 2024
    assert extract_year("2023") == 2023
    assert extract_year("not a date") is None
