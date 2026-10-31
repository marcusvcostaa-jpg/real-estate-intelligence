"""Importing this package registers every table on Base.metadata (used by Alembic)."""

from app.models.audit import AgentExecution, DataQualityIssue, User
from app.models.geography import City, Country, Region
from app.models.properties import (
    DedupCandidate,
    Property,
    PropertyFeature,
    PropertyHistory,
    PropertyListing,
    PropertyTransaction,
)
from app.models.search import CrawlLog, SearchCoverage, SearchJob
from app.models.sources import Source, SourcePermission

__all__ = [
    "AgentExecution",
    "City",
    "Country",
    "CrawlLog",
    "DataQualityIssue",
    "DedupCandidate",
    "Property",
    "PropertyFeature",
    "PropertyHistory",
    "PropertyListing",
    "PropertyTransaction",
    "Region",
    "SearchCoverage",
    "SearchJob",
    "Source",
    "SourcePermission",
    "User",
]
