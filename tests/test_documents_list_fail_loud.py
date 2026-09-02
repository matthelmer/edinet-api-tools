"""fetch_documents_list must fail loud on EDINET's in-body error answers.

EDINET reports failures INSIDE an HTTP 200 body, in two shapes:

    {"StatusCode": 401, "message": "Access denied due to invalid subscription key..."}
    {"metadata": {"status": "404", "message": "Not Found"}}

0.8.0 taught `EdinetClient.get_documents_by_date` to raise on these, after a
bad API key read as a quiet Saturday. But the low-level `fetch_documents_list`
kept handing the body back as data, so every caller that skips the client -- a
pipeline calling the function directly -- still saw an expired key as a day
with zero filings. This is the list-endpoint twin of the 0.8.1 fetch_document
fix: the client already raised, now the function it wraps raises too.

A healthy body with zero results stays a legitimate empty day (JP holidays are
real); only an explicit non-200 in-body status raises.
"""
from unittest.mock import Mock, patch

import pytest

from edinet_tools.api import fetch_documents_list
from edinet_tools.exceptions import APIError, AuthenticationError

BAD_KEY_BODY = (b'{"StatusCode": 401,"message": "Access denied due to invalid subscription '
                b'key.Make sure to provide a valid key for an active subscription."}')
HEALTHY_EMPTY = b'{"metadata": {"status": "200", "message": "OK"}, "results": []}'


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
    def test_bad_api_key_raises_authentication_error(self):
        """The real failure: an expired key must not look like an empty day."""
        with patch('urllib.request.urlopen', return_value=_urlopen_returning(BAD_KEY_BODY)):
            with pytest.raises(AuthenticationError) as exc_info:
                fetch_documents_list('2026-08-28', api_key='bad')
        assert 'invalid subscription key' in str(exc_info.value).lower()

    def test_metadata_status_error_raises_api_error(self):
        body = b'{"metadata": {"status": "404", "message": "Not Found"}}'
        with patch('urllib.request.urlopen', return_value=_urlopen_returning(body)):
            with pytest.raises(APIError) as exc_info:
                fetch_documents_list('2026-08-28', api_key='k')
        assert 'Not Found' in str(exc_info.value)
        assert '2026-08-28' in str(exc_info.value)

    def test_in_body_error_is_not_retried(self):
        """A rejected key is a definitive answer, not a transient failure."""
        with patch('urllib.request.urlopen', return_value=_urlopen_returning(BAD_KEY_BODY)) as mock_open, \
             patch('time.sleep') as mock_sleep:
            with pytest.raises(AuthenticationError):
                fetch_documents_list('2026-08-28', api_key='bad')
        assert mock_open.call_count == 1
        mock_sleep.assert_not_called()


class TestHealthyBodiesUnchanged:
    def test_empty_day_is_still_a_legitimate_empty_day(self):
        """JP holidays are real - zero results with a 200 status must not raise."""
        with patch('urllib.request.urlopen', return_value=_urlopen_returning(HEALTHY_EMPTY)):
            out = fetch_documents_list('2026-01-01', api_key='k')
        assert out['results'] == []

    def test_body_with_no_status_at_all_is_returned(self):
        """Older/leaner bodies carry no status key; absence is not an error."""
        with patch('urllib.request.urlopen', return_value=_urlopen_returning(b'{"results": [{"docID": "S100A"}]}')):
            out = fetch_documents_list('2026-08-28', api_key='k')
        assert out['results'][0]['docID'] == 'S100A'

    def test_results_returned_with_healthy_status(self):
        body = b'{"metadata": {"status": "200"}, "results": [{"docID": "S100A"}, {"docID": "S100B"}]}'
        with patch('urllib.request.urlopen', return_value=_urlopen_returning(body)):
            out = fetch_documents_list('2026-08-28', api_key='k')
        assert len(out['results']) == 2


class TestClientLayerStillRaises:
    """The 0.8.0 client contract must survive the function now raising first."""

    def test_client_still_raises_authentication_error(self):
        from edinet_tools._client import _ApiClient
        with patch('urllib.request.urlopen', return_value=_urlopen_returning(BAD_KEY_BODY)):
            with pytest.raises(AuthenticationError):
                _ApiClient(api_key='bad').get_documents_by_date('2026-08-28')
