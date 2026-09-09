# edinet_tools.py
import datetime
import json
import os
import urllib.parse
import re
import urllib.request
import logging
import time
from typing import List, Dict, Union

from . import config
from .config import SUPPORTED_DOC_TYPES
from .exceptions import APIError, AuthenticationError, DocumentNotFoundError


def _require_api_key(override: str | None) -> str:
    """The key to send, or AuthenticationError before any request is made — a
    missing key must never be urlencoded as the string 'None' (0.8.4)."""
    key = config.api_key(override)
    if not key:
        raise AuthenticationError(
            "EDINET_API_KEY is not set. Set the environment variable, or call "
            "edinet_tools.configure(api_key=...), or pass api_key=. "
            "Get a key from https://api.edinet-fsa.go.jp/api/auth/index.aspx?mode=1")
    return key


def _redact_key(url: str) -> str:
    """The URL with the Subscription-Key value masked — for exceptions and logs."""
    return re.sub(r'(Subscription-Key=)[^&]*', r'\1***', url)

# EDINET API v2 lives on api.edinet-fsa.go.jp. The old disclosure.edinet-fsa.go.jp
# host stopped serving the API at the end of August 2026: it now 301s to
# disclosure2.edinet-fsa.go.jp, which 302s to an HTML error page, so every
# fetch came back as "Expecting value" JSON errors rather than a clean failure.
EDINET_API_BASE = "https://api.edinet-fsa.go.jp/api/v2"

# Use module-specific logger
logger = logging.getLogger(__name__)


def is_zip_payload(content: bytes) -> bool:
    """True when ``content`` starts with the ZIP magic bytes (``PK``)."""
    return bool(content) and len(content) > 2 and content[:2] == b'PK'


def _raise_for_error_body(doc_id: str, type: int, content: bytes) -> None:
    """Turn EDINET's in-body error envelope into a typed exception."""
    meta = json.loads(content.decode('utf-8')).get('metadata', {})
    status = str(meta.get('status', 'Unknown'))
    message = meta.get('message', 'Unknown error')
    if status == '404' or 'not found' in str(message).lower():
        raise DocumentNotFoundError(
            doc_id,
            f"EDINET has no type={type} form for document '{doc_id}' (status 404: {message}). "
            f"For type=5 this usually means the filing carries no XBRL (foreign-form filers, "
            f"parent-company reports, shelf-registration amendments); type=1 (HTML) or "
            f"type=2 (PDF) may still exist.")
    raise APIError(f"EDINET returned status {status} for document '{doc_id}' (type={type}): {message}")


def is_edinet_error_body(content: bytes) -> bool:
    """True when ``content`` is EDINET's in-body error envelope.

    EDINET reports "no such document / form" inside an HTTP 200 response as
    ``{"metadata": {"status": "404", "message": "Not Found"}}`` — e.g. a
    type=5 (XBRL-CSV) request for a filing that has no XBRL. A healthy
    document response is binary (ZIP or PDF), never this JSON shape.
    """
    try:
        data = json.loads(content.decode('utf-8'))
    except (UnicodeDecodeError, ValueError, AttributeError):
        return False
    meta = data.get('metadata') if isinstance(data, dict) else None
    return isinstance(meta, dict) and 'status' in meta


def _raise_for_list_error_body(date_str: str, data) -> None:
    """Raise when a documents-list body carries an in-body error status.

    EDINET reports failures inside an HTTP 200 body, in two shapes: a
    top-level ``StatusCode`` (``{"StatusCode": 401, "message": "Access
    denied..."}``) or ``metadata.status``. Read as data, a rejected API key
    is indistinguishable from a day with no filings -- the silent-failure
    trap 0.8.0 closed at the client layer and 0.8.1 closes here, so callers
    that use the function directly are covered too.

    A healthy body with zero results is a legitimate empty day (JP holidays),
    and a body carrying no status key at all is not an error either.
    """
    if not isinstance(data, dict):
        return
    status = data.get('StatusCode', (data.get('metadata') or {}).get('status'))
    if status is None or str(status) == '200':
        return
    message = (data.get('message')
               or (data.get('metadata') or {}).get('message')
               or 'no message in response body')
    if str(status) == '401':
        raise AuthenticationError(f"EDINET rejected the API key: {message}")
    raise APIError(f"EDINET error {status} for {date_str}: {message}")


# API interaction functions
def fetch_documents_list(date: Union[str, datetime.date],
                         type: int = 2,
                         max_retries: int = 3,
                         delay_seconds: int = 5,
                         api_key: str = None,
                         timeout: int = 60) -> Dict:
    """
    Retrieve disclosure documents from EDINET API for a specified date with retries.

    Args:
        date: Date string ('YYYY-MM-DD') or datetime.date object.
        type: EDINET API type parameter (1=metadata only, 2=metadata+results).
        max_retries: Maximum number of retry attempts on failure.
        delay_seconds: Kept for backwards compatibility; retries now use
            exponential backoff (2s, 4s, 8s, ... capped at 30s).
        api_key: Optional API key override.
        timeout: Timeout in seconds for the HTTP request (default 60).
    """
    if isinstance(date, str):
        try:
            datetime.datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            raise ValueError("Invalid date string. Use format 'YYYY-MM-DD'")
        date_str = date
    elif isinstance(date, datetime.date):
        date_str = date.strftime('%Y-%m-%d')
    else:
        raise TypeError("Date must be 'YYYY-MM-DD' or datetime.date")

    url = f"{EDINET_API_BASE}/documents.json"
    params = {
        "date": date_str,
        "type": type,   # '1' is metadata only; '2' is metadata and results
        "Subscription-Key": _require_api_key(api_key),
    }
    query_string = urllib.parse.urlencode(params)
    full_url = f"{url}?{query_string}"

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1} to fetch documents for {date_str}...")
            with urllib.request.urlopen(full_url, timeout=timeout) as response:
                # Check for non-200 status codes
                if response.getcode() != 200:
                    logger.error(f"API returned status code {response.getcode()} for date {date_str}.")
                    # Attempt to read error body if available
                    try:
                         error_body = response.read().decode('utf-8')
                         logger.error(f"Error body: {error_body}")
                    except Exception:
                         pass
                    # If it's a client error (4xx) or server error (5xx), might be retryable
                    if 400 <= response.getcode() < 600 and attempt < max_retries - 1:
                         backoff = min(2 ** (attempt + 1), 30)
                         logger.warning(f"Retrying in {backoff}s...")
                         time.sleep(backoff)
                         continue # Retry
                    else:
                         # Non-retryable error or last attempt
                         raise urllib.error.HTTPError(_redact_key(full_url), response.getcode(), f"HTTP Error: {response.getcode()}", response.headers, None)


                data = json.loads(response.read().decode('utf-8'))
                # EDINET answers 200 with an error body; a definitive answer,
                # so raise typed and do not spend the retry budget on it.
                _raise_for_list_error_body(date_str, data)
                logger.info(f"Successfully fetched documents for {date_str}.")
                return data

        except (AuthenticationError, APIError):
            raise
        except urllib.error.URLError as e:
            logger.error(f"URL Error fetching documents for {date_str}: {e}")
            if attempt < max_retries - 1:
                backoff = min(2 ** (attempt + 1), 30)
                logger.warning(f"Retrying in {backoff}s...")
                time.sleep(backoff)
            else:
                logger.error("Max retries reached for fetching documents.")
                raise # Re-raise the last exception
        except Exception as e:
            logger.error(f"An unexpected error occurred fetching documents for {date_str}: {e}")
            if attempt < max_retries - 1:
                 backoff = min(2 ** (attempt + 1), 30)
                 logger.warning(f"Retrying in {backoff}s...")
                 time.sleep(backoff)
            else:
                 logger.error("Max retries reached for fetching documents.")
                 raise # Re-raise

    # This line should theoretically not be reached if max_retries > 0
    raise Exception("Failed to fetch documents after multiple retries.")


def fetch_document(doc_id: str, type: int = 5, max_retries: int = 3, delay_seconds: int = 5, api_key: str = None, timeout: int = 60) -> bytes:
    """
    Retrieve a specific document from EDINET API with retries and return raw bytes.

    Args:
        doc_id: EDINET document ID (e.g. 'S100ABC').
        type: EDINET document type to retrieve (default 5):
            1 = ZIP with HTML documents (PublicDoc, AuditDoc)
            2 = PDF
            3 = ZIP with attachments (AttachDoc)
            4 = ZIP with English documents (EnglishDoc)
            5 = XBRL to CSV (default, used by parsers)
        max_retries: Maximum number of retry attempts on failure.
        delay_seconds: Kept for backwards compatibility; retries now use
            exponential backoff (2s, 4s, 8s, ... capped at 30s).
        api_key: Optional API key override.
        timeout: Timeout in seconds for the HTTP request (default 60).
    """
    url = f'{EDINET_API_BASE}/documents/{doc_id}'
    params = {
      "type": type,
      "Subscription-Key": _require_api_key(api_key),
    }
    query_string = urllib.parse.urlencode(params)
    full_url = f'{url}?{query_string}'

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1} to fetch document {doc_id}...")
            with urllib.request.urlopen(full_url, timeout=timeout) as response:
                 # Check for non-200 status codes
                 if response.getcode() != 200:
                     logger.error(f"API returned status code {response.getcode()} for document {doc_id}.")
                     try:
                          error_body = response.read().decode('utf-8')
                          logger.error(f"Error body: {error_body}")
                     except Exception:
                          pass

                     if 400 <= response.getcode() < 600 and attempt < max_retries - 1:
                          backoff = min(2 ** (attempt + 1), 30)
                          logger.warning(f"Retrying in {backoff}s...")
                          time.sleep(backoff)
                          continue # Retry
                     else:
                          raise urllib.error.HTTPError(_redact_key(full_url), response.getcode(), f"HTTP Error: {response.getcode()}", response.headers, None)

                 content = response.read()
                 if is_edinet_error_body(content):
                     # EDINET reports "no such form" inside HTTP 200. A definitive
                     # answer — raise typed, do not retry, never hand back as bytes.
                     _raise_for_error_body(doc_id, type, content)
                 logger.info(f"Successfully fetched document {doc_id}.")
                 return content

        except (DocumentNotFoundError, APIError):
            raise
        except urllib.error.URLError as e:
            logger.error(f"URL Error fetching document {doc_id}: {e}")
            if attempt < max_retries - 1:
                backoff = min(2 ** (attempt + 1), 30)
                logger.warning(f"Retrying in {backoff}s...")
                time.sleep(backoff)
            else:
                logger.error("Max retries reached for fetching document.")
                raise
        except Exception as e:
            logger.error(f"An unexpected error occurred fetching document {doc_id}: {e}")
            if attempt < max_retries - 1:
                 backoff = min(2 ** (attempt + 1), 30)
                 logger.warning(f"Retrying in {backoff}s...")
                 time.sleep(backoff)
            else:
                 logger.error("Max retries reached for fetching document.")
                 raise

    raise Exception(f"Failed to fetch document {doc_id} after multiple retries.")


def save_document_content(doc_content: bytes, output_path: str) -> None:
    """Save the document content (bytes) to file."""
    try:
        with open(output_path, 'wb') as file_out:
            file_out.write(doc_content)
        logger.info(f"Saved document content to {output_path}")
    except IOError as e:
        logger.error(f"Error saving document content to {output_path}: {e}")
        raise # Re-raise to indicate failure

def download_documents(docs: List[Dict], download_dir: str = './downloads') -> None:
    """
    Download all documents in the provided list.
    """
    os.makedirs(download_dir, exist_ok=True)
    logger.info(f"Ensured download directory exists: {download_dir}")

    total_docs = len(docs)
    logger.info(f"Starting download of {total_docs} documents.")

    for i, doc in enumerate(docs, 1):
        doc_id = doc.get('docID')
        doc_type_code = doc.get('docTypeCode')
        filer = doc.get('filerName')

        if not doc_id or not doc_type_code or not filer:
            logger.warning(f"Skipping document {i}/{total_docs} due to missing metadata: {doc}")
            continue

        save_name = f'{doc_id}-{doc_type_code}-{filer}.zip'
        output_path = os.path.join(download_dir, save_name)

        logger.info(f"Downloading {i}/{total_docs}: `{save_name}`")

        if not os.path.exists(output_path):
            try:
                # make GET request to `documents/{docID}` endpoint
                doc_content = fetch_document(doc_id)
                save_document_content(doc_content, output_path)
            except Exception as e:
                logger.error(f"Error downloading and saving {save_name}: {e}")
        else:
            # logger.info(f"File already exists: {save_name}")
            pass # Keep this silent unless debugging needed

    logger.info(f"Download process complete. Files saved to: `{download_dir}`")


# Document filtering and processing
def filter_documents(docs: List[Dict],
                     edinet_codes: Union[List[str], str] = [],
                     doc_type_codes: Union[List[str], str] = [],
                     excluded_doc_type_codes: Union[List[str], str] = [],
                     require_sec_code: bool = True) -> List[Dict]:
    """Filter list of documents by EDINET codes and document type codes."""
    if isinstance(edinet_codes, str):
        edinet_codes = [edinet_codes]
    if isinstance(doc_type_codes, str):
        doc_type_codes = [doc_type_codes]
    if isinstance(excluded_doc_type_codes, str):
        excluded_doc_type_codes = [excluded_doc_type_codes]

    filtered_list = []
    for doc in docs:
         # Basic checks
        if 'docID' not in doc or 'docTypeCode' not in doc or 'filerName' not in doc:
            logger.warning(f"Skipping document with incomplete metadata: {doc}")
            continue

        # Check for supported document types (optional, but good practice)
        if doc['docTypeCode'] not in SUPPORTED_DOC_TYPES:
             # logger.debug(f"Skipping document type {doc['docTypeCode']} ({doc['filerName']}) - not supported.")
             continue # Skip document types we don't explicitly support analysis for

        # Apply EDINET code filter
        if edinet_codes and doc.get('edinetCode') not in edinet_codes:
            continue

        # Apply document type code filter
        if doc_type_codes and doc['docTypeCode'] not in doc_type_codes:
            continue

        # Apply excluded document type code filter
        if doc['docTypeCode'] in excluded_doc_type_codes:
            continue

        # Apply require securities code filter
        if require_sec_code and doc.get('secCode') is None:
            continue

        filtered_list.append(doc)

    logger.info(f"Filtered down to {len(filtered_list)} documents from initial list of {len(docs)}.")
    return filtered_list


def get_documents_for_date_range(start_date: datetime.date,
                                 end_date: datetime.date,
                                 edinet_codes: List[str] = [],
                                 doc_type_codes: List[str] = [],
                                 excluded_doc_type_codes: List[str] = [],
                                 require_sec_code: bool = True,
                                 api_key: str = None) -> List[Dict]:
    """Retrieve and filter documents for a date range."""
    matching_docs = []
    failures: list = []
    days_attempted = 0
    current_date = start_date
    while current_date <= end_date:
        days_attempted += 1
        try:
            docs_res = fetch_documents_list(date=current_date, api_key=api_key)
            if docs_res and docs_res.get('results'):
                logger.info(f"Found {len(docs_res['results'])} documents on EDINET for {current_date}.")
                filtered_docs = filter_documents(
                        docs_res['results'], edinet_codes,
                        doc_type_codes, excluded_doc_type_codes, require_sec_code
                )
                matching_docs.extend(filtered_docs)
                logger.info(f"Added {len(filtered_docs)} matching documents for {current_date}.")
            elif docs_res and docs_res.get('results') is None:
                 logger.info(f"No documents listed for {current_date}.")
            elif not docs_res:
                 logger.warning(f"Empty response received for {current_date}.")

        except AuthenticationError:
            raise  # a rejected key is not a bad day; every further date would fail the same way
        except (APIError, OSError, json.JSONDecodeError) as e:
            # Transient per-day failure: tolerate it, but never let a range where
            # EVERY day failed read as a quiet period (the silent-empty class
            # 0.8.1 closed at the fetcher layer).
            failures.append((current_date, e))
            logger.warning(f"Failed to fetch documents for {current_date}: {e}")
        finally:
             current_date += datetime.timedelta(days=1)

    if failures and len(failures) == days_attempted:
        first_date, first_err = failures[0]
        raise APIError(f"Every date in the range failed ({len(failures)} days); first: {first_date}: {first_err}") from first_err
    logger.info(f"Finished retrieving documents for date range. Total matching documents: {len(matching_docs)}")
    return matching_docs
