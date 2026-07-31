"""
Module-level client singleton for EDINET API access.

Provides lazy initialization of EdinetClient from environment variables
or explicit configuration.
"""
import os
import warnings
from typing import Optional

from .client import EdinetClient

# Module-level state
_client: Optional[EdinetClient] = None
_configured_api_key: Optional[str] = None


def _get_client() -> EdinetClient:
    """
    Get the module-level EdinetClient instance.

    Lazily initializes from EDINET_API_KEY env var or configure() call.

    Returns:
        EdinetClient instance
    """
    global _client
    if _client is None:
        api_key = _configured_api_key or os.environ.get('EDINET_API_KEY')
        # Suppress deprecation warning for internal usage
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            _client = EdinetClient(api_key=api_key)
    return _client


def _reset_client() -> None:
    """Reset the client singleton and configured key (for testing)."""
    global _client, _configured_api_key
    _client = None
    _configured_api_key = None


def configure(api_key: Optional[str] = None) -> None:
    """
    Configure the module-level client.

    Args:
        api_key: EDINET API key (if None, uses EDINET_API_KEY env var)
    """
    global _configured_api_key, _client
    _configured_api_key = api_key
    _client = None  # Reset so next _get_client() uses new config


def fetch_and_parse(doc_id: str, doc_type_code: str):
    """
    Fetch and parse a specific EDINET document by ID.

    Useful when you already know the document ID (e.g., from a cached filing
    index) and want to skip the date-based document listing.

    Args:
        doc_id: EDINET document ID (e.g., 'S100ABC')
        doc_type_code: Document type code (e.g., '120', '180', '350')

    Returns:
        ParsedReport subclass appropriate for the document type
    """
    from .document import Document

    doc = Document({'docID': doc_id, 'docTypeCode': doc_type_code}, client=_get_client())
    return doc.parse()


def documents(date: Optional[str] = None, doc_type: Optional[str] = None) -> list:
    """
    Get all documents filed on a specific date.

    Args:
        date: Date string (YYYY-MM-DD). Defaults to today in JST.
        doc_type: Optional filter by document type code

    Returns:
        List of Document objects
    """
    from .document import Document
    from .timezone import today_jst

    if date is None:
        date = today_jst().isoformat()

    client = _get_client()
    filings = client.get_documents_by_date(date)

    if doc_type:
        filings = [f for f in filings if f.get('docTypeCode') == doc_type]

    return [Document(f, client=client) for f in filings]
