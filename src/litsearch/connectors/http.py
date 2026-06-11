"""HTTP helper for source connectors."""

from __future__ import annotations

import logging

import httpx

from litsearch.config import Settings
from litsearch.exceptions import ConnectorError
from litsearch.log_utils import mask_secret

logger = logging.getLogger(__name__)

RETRY_STATUS_CODES = {429, 502, 503, 504}


class HttpClient:
    """Small synchronous JSON client with limited retry behavior."""

    def __init__(self, settings: Settings):
        self.settings = settings
        email = settings.contact_email or settings.openalex_email or settings.crossref_email
        user_agent = "RefPort/litsearch"
        if email:
            user_agent = f"{user_agent} (mailto:{email})"
        self.default_headers = {"User-Agent": user_agent}

    def get_json(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        request_headers = {**self.default_headers, **(headers or {})}
        proxy = self.settings.proxy_url
        client_kwargs = {"timeout": self.settings.http_timeout_seconds, "trust_env": False}
        if proxy:
            client_kwargs["proxy"] = proxy

        try:
            with httpx.Client(**client_kwargs) as client:
                response = None
                for attempt in range(3):
                    response = client.get(url, params=params, headers=request_headers)
                    if response.status_code not in RETRY_STATUS_CODES or attempt == 2:
                        break
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            logger.debug("HTTP request failed for %s", url)
            status_code = exc.response.status_code
            raise ConnectorError(f"HTTP request failed with status {status_code}") from exc
        except httpx.HTTPError as exc:
            logger.debug("HTTP request failed for %s", url)
            raise ConnectorError(f"HTTP request failed: {mask_secret(str(exc))}") from exc
        except ValueError as exc:
            raise ConnectorError("HTTP response was not valid JSON") from exc

        if not isinstance(payload, dict):
            raise ConnectorError("HTTP response JSON was not an object")
        return payload
