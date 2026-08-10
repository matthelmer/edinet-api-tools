"""
Module-level client for EDINET API access.

Holds the configured API key and provides the thin fetch helpers the
functional API (documents(), Document.fetch()) is built on. Lazily
initialized from EDINET_API_KEY or an explicit configure() call.
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional, Union
import datetime

from .api import fetch_documents_list, fetch_document
from .exceptions import (
    AuthenticationError, DocumentNotFoundError, ProcessingError, APIError,
)

logger = logging.getLogger(__name__)


class _ApiClient:
    """Internal API-key holder plus the two fetch helpers the functional
    API is built on. Not part of the public surface — use the module-level
    functions (configure, documents) and Document.fetch()/parse() instead.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('EDINET_API_KEY')

    def get_documents_by_date(self,
                              date: Union[str, datetime.date],
                              doc_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return the metadata dicts for every document filed on `date`,
        optionally filtered to a single document type code."""
        try:
            response = fetch_documents_list(date, api_key=self.api_key)

            # EDINET reports failures INSIDE a 200 body — either a top-level
            # StatusCode ({"StatusCode": 401, "message": "Access denied..."})
            # or metadata.status. Reading those as an empty filing day is a
            # silent-failure trap (a bad API key looked exactly like a quiet
            # Saturday); fail loud instead. A healthy body with zero results
            # remains a legitimate empty day.
            status = response.get('StatusCode',
                                  (response.get('metadata') or {}).get('status'))
            if status is not None and str(status) != '200':
                message = (response.get('message')
                           or (response.get('metadata') or {}).get('message')
                           or 'no message in response body')
                if str(status) == '401':
                    raise AuthenticationError(
                        f"EDINET rejected the API key: {message}")
                raise APIError(
                    f"EDINET error {status} for {date}: {message}")

            documents = response.get('results', [])

            if doc_type:
                documents = [d for d in documents if d.get('docTypeCode') == doc_type]

            return documents
        except (AuthenticationError, APIError):
            raise
        except Exception as e:
            logger.error(f"Error fetching documents for {date}: {e}")
            if "401" in str(e) or "unauthorized" in str(e).lower():
                raise AuthenticationError()
            elif "429" in str(e) or "rate limit" in str(e).lower():
                raise APIError("Rate limit exceeded. Please wait before making more requests.")
            else:
                raise APIError(f"Failed to fetch documents for {date}: {e}")

    def download_filing_raw(self, doc_id: str, raise_on_error: bool = True) -> Optional[bytes]:
        """Fetch a filing and return its raw ZIP bytes, without saving to disk.

        Returns None (when raise_on_error=False) or raises on a JSON error
        body or a response that is not a valid ZIP.
        """
        try:
            doc_response = fetch_document(doc_id, api_key=self.api_key)

            if self._is_json_error_response(doc_response):
                error_data = json.loads(doc_response.decode('utf-8'))
                error_message = error_data.get('metadata', {}).get('message', 'Unknown error')
                status = error_data.get('metadata', {}).get('status', 'Unknown')

                logger.error(f"API returned error for document {doc_id}: {status} - {error_message}")

                if not raise_on_error:
                    return None
                if status == '404' or 'not found' in error_message.lower():
                    raise DocumentNotFoundError(doc_id)
                raise APIError(f"API error for document {doc_id}: {status} - {error_message}")

            if not self._is_zip_response(doc_response):
                logger.error(f"Document {doc_id} response does not appear to be a valid ZIP file")
                if not raise_on_error:
                    return None
                raise ProcessingError(
                    f"Invalid response format for document {doc_id}", doc_id,
                    "Response is not a ZIP file",
                )

            logger.info(f"Downloaded {doc_id} raw bytes ({len(doc_response)} bytes)")
            return doc_response

        except (DocumentNotFoundError, APIError, ProcessingError):
            if raise_on_error:
                raise
            return None
        except Exception as e:
            logger.error(f"Error downloading filing {doc_id}: {e}")
            if not raise_on_error:
                return None
            if "404" in str(e) or "not found" in str(e).lower():
                raise DocumentNotFoundError(doc_id)
            elif "401" in str(e) or "unauthorized" in str(e).lower():
                raise AuthenticationError()
            else:
                raise APIError(f"Failed to download filing {doc_id}: {e}")

    @staticmethod
    def _is_json_error_response(response_bytes: bytes) -> bool:
        """True when the response is a JSON error body rather than a ZIP."""
        try:
            data = json.loads(response_bytes.decode('utf-8'))
            return 'metadata' in data and 'status' in data.get('metadata', {})
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            return False

    @staticmethod
    def _is_zip_response(response_bytes: bytes) -> bool:
        """True when the response starts with the ZIP magic bytes (PK)."""
        return len(response_bytes) > 2 and response_bytes[:2] == b'PK'


# Module-level state
_client: Optional[_ApiClient] = None
_configured_api_key: Optional[str] = None


def _get_client() -> _ApiClient:
    """Get the module-level API client, lazily built from configure() or
    the EDINET_API_KEY env var."""
    global _client
    if _client is None:
        api_key = _configured_api_key or os.environ.get('EDINET_API_KEY')
        _client = _ApiClient(api_key=api_key)
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
