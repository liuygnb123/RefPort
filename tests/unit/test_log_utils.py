from litsearch.log_utils import mask_mapping, mask_secret


def test_api_key_is_masked():
    assert mask_mapping({"api_key": "abc123"})["api_key"] == "***"


def test_authorization_is_masked():
    assert mask_mapping({"Authorization": "Bearer abc123"})["Authorization"] == "***"


def test_bearer_token_is_masked():
    assert mask_secret("Bearer abc123") == "Bearer ***"


def test_proxy_credentials_are_masked():
    assert mask_secret("https://user:pass@proxy.example.com") == "https://user:***@proxy.example.com"


def test_empty_values_do_not_error():
    assert mask_secret(None) is None
    assert mask_secret("") == ""
    assert mask_mapping({"api_key": ""})["api_key"] == ""
