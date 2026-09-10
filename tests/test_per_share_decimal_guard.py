"""A thousands separator in a per-share figure must parse (as `parse_int`
already does for share counts), not take down the whole annual-report parse. `coerce_numeric_value` keeps null
markers away from `Decimal()` but does not strip separators; the quarterly
parser guards the conversion, the securities parser did not (found 2026-09-09).
"""
from decimal import Decimal

import pytest

from edinet_tools.parsers.extraction import parse_decimal
from edinet_tools.parsers.securities import parse_securities_report
from tests.test_parser_extraction import make_csv_row

DEI = [
    ('jpdei_cor:EDINETCodeDEI', 'FilingDateInstant', 'E12345'),
    ('jpdei_cor:SecurityCodeDEI', 'FilingDateInstant', '79210'),
    ('jpdei_cor:FilerNameInJapaneseDEI', 'FilingDateInstant', 'テスト株式会社'),
    ('jpdei_cor:CurrentFiscalYearStartDateDEI', 'FilingDateInstant', '2024-04-01'),
    ('jpdei_cor:CurrentFiscalYearEndDateDEI', 'FilingDateInstant', '2025-03-31'),
    ('jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI', 'FilingDateInstant', 'true'),
    ('jpdei_cor:AccountingStandardsDEI', 'FilingDateInstant', 'Japan GAAP'),
]


def _parse(extra):
    files = [{'filename': 'x.csv', 'data': [make_csv_row(*r) for r in DEI + extra]}]
    return parse_securities_report(csv_files=files, doc_id='X', doc_type_code='120')


@pytest.mark.parametrize('raw,expected', [
    ('1234.56', Decimal('1234.56')),
    ('１２３４', Decimal('1234')),
    ('1,234', Decimal('1234')),   # separator removed, as parse_int does
    ('１，２３４．５', Decimal('1234.5')),
    ('NaN', None), ('Infinity', None),
    ('－', None), ('', None), (None, None),
])
def test_parse_decimal_returns_none_instead_of_raising(raw, expected):
    assert parse_decimal(raw) == expected


def test_comma_in_net_assets_per_share_does_not_abort_the_parse():
    r = _parse([
        ('jpcrp_cor:NetAssetsPerShareSummaryOfBusinessResults', 'CurrentYearInstant', '1,234.5'),
        ('jpcrp_cor:NetSalesSummaryOfBusinessResults', 'CurrentYearDuration', '100000'),
    ])
    assert r.net_assets_per_share == Decimal('1234.5')
    assert r.net_sales == 100000


def test_comma_in_eps_does_not_abort_the_parse():
    r = _parse([('jpcrp_cor:BasicEarningsLossPerShareSummaryOfBusinessResults', 'CurrentYearDuration', '1,001.2')])
    assert r.earnings_per_share == Decimal('1001.2')
    assert r.filer_edinet_code == 'E12345'
