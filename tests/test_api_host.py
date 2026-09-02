"""EDINET API v2 host pin.

disclosure.edinet-fsa.go.jp stopped serving /api/v2 at the end of August 2026
(301 -> disclosure2 -> 302 -> HTML error page). The documented v2 host is
api.edinet-fsa.go.jp. Both fetch paths must use it.
"""
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

from edinet_tools import api


API_HOST = "api.edinet-fsa.go.jp"


def _mock_response(body: bytes):
    resp = MagicMock()
    resp.read.return_value = body
    resp.getcode.return_value = 200
    return resp


def _called_url(mock_urlopen):
    called = mock_urlopen.call_args[0][0]
    return called if isinstance(called, str) else called.full_url


def test_api_base_is_the_documented_v2_host():
    assert api.EDINET_API_BASE == f"https://{API_HOST}/api/v2"


def test_fetch_documents_list_uses_api_host():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = _mock_response(
            b'{"metadata": {"status": "200"}, "results": []}'
        )
        api.fetch_documents_list("2026-08-31", api_key="k", max_retries=1)
        url = _called_url(mock_urlopen)
        assert urlparse(url).netloc == API_HOST
        assert "/api/v2/documents.json" in url


def test_fetch_document_uses_api_host():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = _mock_response(b"PK\x03\x04zip")
        api.fetch_document("S100TEST", api_key="k", max_retries=1)
        url = _called_url(mock_urlopen)
        assert urlparse(url).netloc == API_HOST
        assert "/api/v2/documents/S100TEST" in url
