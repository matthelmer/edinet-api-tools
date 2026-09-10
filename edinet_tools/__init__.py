"""
EDINET Tools - Python package for accessing Japanese corporate financial data.

Python library for Japanese financial disclosure data.
"""

__version__ = "0.8.4"
__author__ = "Matt Helmer"
__description__ = "Python package for accessing Japanese corporate financial data from EDINET"

# Core API
from ._client import configure, documents, fetch_and_parse
from .timezone import today_jst
from .config import SUPPORTED_DOC_TYPES as DOCUMENT_TYPES

# Entity classification
from .entity_classifier import EntityClassifier, EntityType, StaleDataWarning

# Entity-first API
from .entity import (
    Entity,
    entity,
    entity_by_ticker,
    entity_by_edinet_code,
    entity_by_code,  # Shorter alias
    entity_by_corporate_number,
    search_entities,
    search,
    Fund,
    fund,
    funds_by_issuer,
)
from .normalize import normalize_for_matching
from .document import Document
from .doc_types import DocType, doc_type, list_doc_types, doc_types

# Parsers
from .parsers import (
    parse,
    supported_doc_types,
    ParsedReport,
    RawReport,
    LargeHoldingReport,
    SecuritiesReport,
    QuarterlyReport,
    SemiAnnualReport,
    ExtraordinaryReport,
    TreasuryStockReport,
    TenderOfferReport,
    InternalControlReport,
    ConfirmationReport,
    ParentCompanyReport,
    LargeHoldingChangeReport,
    GenericReport,  # Backwards compatibility alias
)

__all__ = [
    # Configuration
    "configure",
    "documents",
    "fetch_and_parse",
    "today_jst",
    "DOCUMENT_TYPES",
    "__version__",
    # Entity lookup
    "Entity",
    "entity",
    "entity_by_ticker",
    "entity_by_edinet_code",
    "entity_by_code",  # Shorter alias
    "entity_by_corporate_number",
    "search_entities",
    "search",
    "Fund",
    "fund",
    "funds_by_issuer",
    "normalize_for_matching",
    # Documents
    "Document",
    "DocType",
    "doc_type",
    "list_doc_types",
    "doc_types",
    # Parsers
    "parse",
    "supported_doc_types",
    "ParsedReport",
    "RawReport",
    "LargeHoldingReport",
    "SecuritiesReport",
    "QuarterlyReport",
    "SemiAnnualReport",
    "ExtraordinaryReport",
    "TreasuryStockReport",
    "TenderOfferReport",
    "InternalControlReport",
    "ConfirmationReport",
    "ParentCompanyReport",
    "LargeHoldingChangeReport",
    # Legacy (deprecated)
    "EntityClassifier",
    "EntityType",
    "StaleDataWarning",
    "GenericReport",  # Backwards compatibility alias
]
