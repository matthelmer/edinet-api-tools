"""0.8.1 made the low-level fetchers raise on EDINET's in-body errors so a
rejected key could never read as a quiet day. Two convenience paths above them
still caught `Exception` and continued: `Entity.documents()` (the README's
first example) and `api.get_documents_for_date_range()`. A rejected key over
30 days returned `[]` (found 2026-09-09). Per-day tolerance of transient
network errors is kept; authentication failures propagate at once, and a
range where every day failed raises rather than returning an empty list."""
import datetime
import urllib.error
from unittest.mock import Mock, patch

import pytest

from edinet_tools import api, entity
from edinet_tools.exceptions import APIError, AuthenticationError


class TestEntityDocuments:
    def _toyota_with(self, side_effect):
        t = entity('7203')
        c = Mock()
        c.get_documents_by_date.side_effect = side_effect
        t._client = c
        return t, c

    def test_authentication_error_propagates_immediately(self):
        t, c = self._toyota_with(AuthenticationError())
        with pytest.raises(AuthenticationError):
            t.documents(days=30)
        assert c.get_documents_by_date.call_count == 1  # no 29 more doomed calls

    def test_transient_error_on_one_day_is_tolerated(self):
        good = [{'docID': 'S1', 'docTypeCode': '350', 'submitDateTime': '2026-01-15 09:30',
                 'edinetCode': 'E02144', 'filerName': 'トヨタ'}]
        t, _ = self._toyota_with([urllib.error.URLError('blip'), good])
        assert len(t.documents(days=2)) == 1

    def test_every_day_failing_raises_instead_of_empty_list(self):
        t, _ = self._toyota_with(urllib.error.URLError('down'))
        with pytest.raises(APIError) as ei:
            t.documents(days=3)
        assert isinstance(ei.value.__cause__, urllib.error.URLError)

    def test_a_window_of_legitimate_empty_days_is_still_an_empty_list(self):
        """Holidays are not failures: the client returns [] for a healthy
        zero-result day, and fail-loud must not turn that into an error."""
        t, c = self._toyota_with(None)
        c.get_documents_by_date.side_effect = None
        c.get_documents_by_date.return_value = []
        assert t.documents(days=3) == []
        assert c.get_documents_by_date.call_count == 3


class TestDateRange:
    D = datetime.date(2026, 9, 1)

    def test_authentication_error_propagates_immediately(self):
        with patch.object(api, 'fetch_documents_list', side_effect=AuthenticationError()) as m:
            with pytest.raises(AuthenticationError):
                api.get_documents_for_date_range(self.D, self.D + datetime.timedelta(days=9))
        assert m.call_count == 1

    def test_transient_error_on_one_day_is_tolerated(self):
        ok = {'results': [{'docID': 'S1', 'docTypeCode': '350', 'filerName': 'x', 'secCode': '12340'}]}
        with patch.object(api, 'fetch_documents_list', side_effect=[urllib.error.URLError('blip'), ok]):
            docs = api.get_documents_for_date_range(self.D, self.D + datetime.timedelta(days=1))
        assert [d['docID'] for d in docs] == ['S1']

    def test_every_day_failing_raises(self):
        with patch.object(api, 'fetch_documents_list', side_effect=urllib.error.URLError('down')):
            with pytest.raises(APIError):
                api.get_documents_for_date_range(self.D, self.D + datetime.timedelta(days=2))
