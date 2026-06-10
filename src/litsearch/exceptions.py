"""Project-specific exceptions."""


class LitSearchError(Exception):
    """Base exception for litsearch."""


class ConfigurationError(LitSearchError):
    """Raised when configuration cannot be loaded or used."""


class DatabaseError(LitSearchError):
    """Raised when database setup or access fails."""


class ConnectorError(LitSearchError):
    """Raised by source connector code."""


class SourceNotConfiguredError(ConnectorError):
    """Raised when a source is requested without required settings."""


class LitSearchValidationError(LitSearchError):
    """Raised when user input fails validation."""
