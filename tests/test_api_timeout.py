"""Tests for API timeout and exponential backoff."""
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

from edinet_tools.api import fetch_documents_list, fetch_document


class TestApiTimeoutAndBackoff(unittest.TestCase):

    def _make_success_response(self, content=None):
        mock = MagicMock()
        mock.getcode.return_value = 200
        mock.read.return_value = content or b'{"metadata": {}, "results": []}'
        mock.__enter__ = MagicMock(return_value=mock)
        mock.__exit__ = MagicMock(return_value=False)
        return mock

    @patch('edinet_tools.api.urllib.request.urlopen')
    @patch.dict('os.environ', {'EDINET_API_KEY': 'test-key'})
    def test_fetch_documents_list_passes_timeout(self, mock_urlopen):
        mock_urlopen.return_value = self._make_success_response()
        fetch_documents_list('2024-01-01', timeout=30)
        _, kwargs = mock_urlopen.call_args
        self.assertEqual(kwargs['timeout'], 30)

    @patch('edinet_tools.api.urllib.request.urlopen')
    @patch.dict('os.environ', {'EDINET_API_KEY': 'test-key'})
    def test_fetch_document_passes_timeout(self, mock_urlopen):
        mock_urlopen.return_value = self._make_success_response(content=b'zip')
        fetch_document('S100ABC')
        _, kwargs = mock_urlopen.call_args
        self.assertEqual(kwargs['timeout'], 60)

    @patch('edinet_tools.api.time.sleep')
    @patch('edinet_tools.api.urllib.request.urlopen')
    @patch.dict('os.environ', {'EDINET_API_KEY': 'test-key'})
    def test_exponential_backoff_on_retry(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = [
            urllib.error.URLError('timeout'),
            urllib.error.URLError('timeout'),
            self._make_success_response(),
        ]
        fetch_documents_list('2024-01-01', max_retries=3)
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        self.assertEqual(delays, [2, 4])


if __name__ == '__main__':
    unittest.main()
