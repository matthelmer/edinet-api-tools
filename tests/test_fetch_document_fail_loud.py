"""fetch_document must fail loud on EDINET's in-body "no document" answers.

EDINET answers HTTP 200 with a small JSON envelope when a filing has no
machine-readable form for the requested type — e.g. type=5 (XBRL-CSV) for a
foreign-form filer or a parent-company report:

    {"metadata": {"title": "...", "status": "404", "message": "Not Found"}}

Before this fix `fetch_document` handed those bytes back as if they were the
document; callers that wrote them to disk got a 142-byte "zip" that fails
`zipfile.BadZipFile` later, far from the cause. The 0.8.0 release made the
documents LIST endpoint fail loud on the same pattern; this extends the rule
to the per-document endpoint. The `_ApiClient` layer already raised on this
case; the low-level function now does too, so every caller benefits.

Fixture is the real 142-byte body (captured 2026-08-21, S100YXSU type=5).
"""
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from edinet_tools.api import fetch_document, is_edinet_error_body, is_zip_payload
from edinet_tools.exceptions import APIError, DocumentNotFoundError

NO_CSV_BODY = (Path(__file__).parent / 'fixtures' / 'edinet_no_csv_404_body.json').read_bytes()
REAL_ZIP_HEAD = b'PK\x03\x04' + b'\x00' * 26 + b'XBRL_TO_CSV/x.csv'


def _urlopen_returning(body: bytes, code: int = 200):
    resp = Mock()
    resp.getcode.return_value = code
    resp.read.return_value = body
    resp.headers = {}
    ctx = Mock()
    ctx.__enter__ = Mock(return_value=resp)
    ctx.__exit__ = Mock(return_value=False)
    return ctx


class TestInBodyErrorsRaise:
    def test_404_envelope_raises_document_not_found(self):
        with patch('urllib.request.urlopen', return_value=_urlopen_returning(NO_CSV_BODY)):
            with pytest.raises(DocumentNotFoundError) as exc_info:
                fetch_document('S100YXSU', 5, api_key='test_key')
        assert exc_info.value.doc_id == 'S100YXSU'
        assert '5' in str(exc_info.value) or 'type' in str(exc_info.value).lower()

    def test_non_404_envelope_raises_api_error(self):
        body = b'{"metadata": {"status": "500", "message": "Internal Server Error"}}'
        with patch('urllib.request.urlopen', return_value=_urlopen_returning(body)):
            with pytest.raises(APIError) as exc_info:
                fetch_document('S100YXSU', 5, api_key='test_key')
        assert 'Internal Server Error' in str(exc_info.value)

    def test_error_envelope_is_not_retried(self):
        """A definitive 'not found' answer must not burn the retry/backoff budget."""
        with patch('urllib.request.urlopen', return_value=_urlopen_returning(NO_CSV_BODY)) as mock_open, \
             patch('time.sleep') as mock_sleep:
            with pytest.raises(DocumentNotFoundError):
                fetch_document('S100YXSU', 5, api_key='test_key')
        assert mock_open.call_count == 1
        mock_sleep.assert_not_called()


class TestRealDocumentsStillReturnBytes:
    def test_zip_bytes_returned_unchanged(self):
        with patch('urllib.request.urlopen', return_value=_urlopen_returning(REAL_ZIP_HEAD)):
            out = fetch_document('S100YXW9', 5, api_key='test_key')
        assert out == REAL_ZIP_HEAD

    def test_pdf_bytes_returned_unchanged(self):
        pdf = b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n'
        with patch('urllib.request.urlopen', return_value=_urlopen_returning(pdf)):
            out = fetch_document('S100YXW9', 2, api_key='test_key')
        assert out == pdf


class TestPayloadPrimitives:
    def test_is_edinet_error_body(self):
        assert is_edinet_error_body(NO_CSV_BODY) is True
        assert is_edinet_error_body(REAL_ZIP_HEAD) is False
        assert is_edinet_error_body(b'{"results": []}') is False
        assert is_edinet_error_body(b'') is False

    def test_is_zip_payload(self):
        assert is_zip_payload(REAL_ZIP_HEAD) is True
        assert is_zip_payload(NO_CSV_BODY) is False
        assert is_zip_payload(b'') is False
