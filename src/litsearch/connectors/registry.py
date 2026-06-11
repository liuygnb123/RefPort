"""Built-in source registry."""

from __future__ import annotations

from litsearch.config import Settings
from litsearch.connectors.base import SourceDefinition, SourceStatus

SOURCE_DEFINITIONS = [
    SourceDefinition(
        id="crossref",
        display_name="Crossref",
        requires=["email"],
        capabilities=["metadata", "search"],
    ),
    SourceDefinition(
        id="openalex",
        display_name="OpenAlex",
        requires=["email"],
        capabilities=["metadata", "search"],
    ),
    SourceDefinition(
        id="unpaywall",
        display_name="Unpaywall",
        requires=["email"],
        capabilities=["open_access_metadata", "doi_lookup"],
    ),
    SourceDefinition(
        id="ieee",
        display_name="IEEE Xplore",
        requires=["api_key"],
        capabilities=["metadata", "search", "doi_lookup"],
    ),
    SourceDefinition(
        id="scopus",
        display_name="Scopus",
        requires=["api_key"],
        capabilities=["metadata", "search", "doi_lookup"],
    ),
    SourceDefinition(
        id="wos",
        display_name="Web of Science",
        requires=["api_key"],
        capabilities=["metadata", "search", "doi_lookup"],
    ),
]


def _is_configured(source_id: str, settings: Settings) -> bool:
    if source_id in {"crossref", "openalex", "unpaywall"}:
        return bool(settings.source_email(source_id))
    if source_id == "ieee":
        return bool(settings.ieee_api_key)
    if source_id == "scopus":
        return bool(settings.scopus_api_key)
    if source_id == "wos":
        return bool(settings.wos_api_key)
    return False


def list_sources(settings: Settings) -> list[SourceStatus]:
    """Return all built-in sources with their configured state."""

    return [
        SourceStatus(
            id=definition.id,
            display_name=definition.display_name,
            requires=definition.requires,
            capabilities=definition.capabilities,
            configured=_is_configured(definition.id, settings),
        )
        for definition in SOURCE_DEFINITIONS
    ]
