"""Import all models so SQLModel metadata is complete."""

from sqlmodel import SQLModel

import litsearch.models  # noqa: F401

metadata = SQLModel.metadata
