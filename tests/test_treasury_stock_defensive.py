"""Deprecation-warning pins for the treasury_stock authorization shims.

has_board_authorization / has_shareholder_authorization are deprecated
since v0.6.1; these tests pin the warnings and die with the shims.
(The 2026-07 test audit removed eight refactored-into-tautology tests
that asserted pure-Python expressions on values they had just set.)
"""
import warnings

import pytest

from edinet_tools.parsers.treasury_stock import TreasuryStockReport


def _make_report(by_board: str | None = None, by_shareholders: str | None = None) -> TreasuryStockReport:
    return TreasuryStockReport(
        doc_id='S100TEST',
        doc_type_code='220',
        by_board_meeting=by_board,
        by_shareholders_meeting=by_shareholders,
    )


# --- deprecation warning tests ---

def test_has_board_authorization_emits_deprecation_warning():
    """has_board_authorization is deprecated in v0.6.1."""
    report = _make_report(by_board='取締役会決議による取得...')
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _ = report.has_board_authorization
        dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(dep_warnings) >= 1
        msg = str(dep_warnings[0].message)
        assert 'has_board_authorization' in msg
        assert 'by_board_meeting' in msg


def test_has_shareholder_authorization_emits_deprecation_warning():
    """has_shareholder_authorization is deprecated in v0.6.1."""
    report = _make_report(by_shareholders='株主総会決議による取得...')
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _ = report.has_shareholder_authorization
        dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(dep_warnings) >= 1
        msg = str(dep_warnings[0].message)
        assert 'has_shareholder_authorization' in msg
        assert 'by_shareholders_meeting' in msg
