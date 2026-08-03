"""Golden tests for consolidated revenue selection (IFRS / US-GAAP / J-GAAP).

These pin the consolidated-selection invariant: for a consolidated filer, the parser
must never silently substitute the non-consolidated (parent) value. Each fixture is
derived verbatim from a real EDINET securities report (the financial rows the parser
reads at consolidated + non-consolidated contexts, plus a real noise cross-section);
no values are hand-fabricated.

Confirmed golden values (consolidated, yen) and the element each lives under:
  Toyota FY25  48,036,704,000,000  custom-ns SalesRevenuesIFRS / TotalNetRevenuesIFRS
               (parent NetSalesSummaryOfBusinessResults @ _NonConsolidatedMember = 18,277,671,000,000)
  Takeda FY25   4,581,551,000,000  standard RevenueIFRSSummaryOfBusinessResults
               (parent = 580,360,000,000)
  Sony FY20     8,259,885,000,000  RevenuesUSGAAPSummaryOfBusinessResults
               (parent jppfs_cor:NetSales = 158,662,000,000)
  7466 FY25        68,720,867,000  J-GAAP NetSalesSummaryOfBusinessResults @ bare context
               (control: J-GAAP is unaffected; must stay correct after the fix)

Written TDD-first: at authoring time Toyota/Takeda/Sony returned the parent
figure; the v0.7.0 strict-consolidated selection fixed that, and these tests
now pin the corrected behavior.
"""
import csv as _csv
from pathlib import Path

import pytest

from edinet_tools.parsers.securities import parse_securities_report

_COLS = ['要素ID', '項目名', 'コンテキストID', '相対年度',
         '連結・個別', '期間・時点', 'ユニットID', '単位', '値']


def _load(name: str):
    p = Path(__file__).parent / 'fixtures' / 'securities' / f'{name}.csv'
    with open(p, encoding='utf-8') as f:
        rows = list(_csv.reader(f, delimiter='\t'))
    data = [dict(zip(_COLS, r)) for r in rows[1:]]
    return [{'filename': f'{name}.csv', 'data': data}]


@pytest.mark.parametrize('name,expected_rev', [
    ('toyota_fy25_revenue', 48_036_704_000_000),
    ('takeda_fy25_revenue',  4_581_551_000_000),
    ('sony_fy20_usgaap_revenue', 8_259_885_000_000),
])
def test_consolidated_revenue_selected(name, expected_rev):
    r = parse_securities_report(csv_files=_load(name), doc_id='TEST', doc_type_code='120')
    assert r.net_sales == expected_rev, \
        f'{name}: got {r.net_sales:,}, want consolidated {expected_rev:,} (not the parent figure)'


@pytest.mark.parametrize('name', [
    'toyota_fy25_revenue', 'takeda_fy25_revenue', 'sony_fy20_usgaap_revenue',
])
def test_revenue_invariant_holds(name):
    """Consolidated invariant: revenue >= operating income and >= net income.
    op_income > net_sales is the parent-revenue tell (mixed-scale rows)."""
    r = parse_securities_report(csv_files=_load(name), doc_id='TEST', doc_type_code='120')
    assert r.net_sales is not None
    if r.operating_income is not None:
        assert r.operating_income <= r.net_sales, \
            f'{name}: op_income {r.operating_income:,} > net_sales {r.net_sales:,} = parent-revenue tell'
    if r.net_income_owners is not None:
        assert r.net_income_owners <= r.net_sales, \
            f'{name}: net_income_owners {r.net_income_owners:,} > net_sales {r.net_sales:,}'


def test_jgaap_control_unaffected():
    """J-GAAP consolidated revenue lives at the bare context and must stay correct."""
    r = parse_securities_report(csv_files=_load('jgaap_control_revenue'),
                                doc_id='TEST', doc_type_code='120')
    assert r.net_sales == 68_720_867_000


def test_usgaap_income_statement_mapped_sony():
    """US-GAAP filers (Sony FY20) carry consolidated revenue/net-income/EPS/ROE.

    Sony FY20 tags OperatingIncomeLossUSGAAPSummaryOfBusinessResults, so operating_income
    is populated with the correct value (not None). US-GAAP filers that use only a
    TextBlock for operating income will get honest None; Sony is not that case."""
    r = parse_securities_report(csv_files=_load('sony_fy20_usgaap_revenue'),
                                doc_id='TEST', doc_type_code='120')
    assert r.net_sales == 8_259_885_000_000
    assert r.ordinary_income == 799_450_000_000   # profit-before-tax (US-GAAP analogue)
    assert r.net_income_owners == 582_191_000_000
    assert r.earnings_per_share is not None and abs(float(r.earnings_per_share) - 471.64) < 0.01
    assert r.roe is not None and abs(float(r.roe) - 0.148) < 0.001
    assert r.operating_income == 845_459_000_000  # OperatingIncomeLossUSGAAPSummaryOfBusinessResults


def test_strict_consolidated_nulls_are_honest_mhi():
    """Characterize the strict-consolidated blast radius on a real IFRS filer (MHI).

    Under the strict invariant, fields with a mapped consolidated source carry the
    correct CONSOLIDATED value; fields with NO consolidated source become honest
    None instead of the parent figure they used to silently borrow. None is correct
    here — the parent value was a silent lie. The parent values remain in the
    fact-bag (nothing is lost).
    """
    r = parse_securities_report(csv_files=_load('mhi_ifrs_blast_radius'),
                                doc_id='TEST', doc_type_code='120')

    # Recovered / correct consolidated values (revenue is standard IFRS-summary, like Takeda):
    assert r.net_sales == 5_027_176_000_000        # consolidated, NOT parent 1,947,178,000,000
    assert r.ordinary_income == 374_531_000_000
    assert r.net_income_owners == 245_447_000_000
    assert r.total_assets == 6_658_924_000_000
    assert r.net_assets_owners == 2_346_702_000_000

    # Honest-None: no consolidated source exists; these were the parent figure before.
    # operating_income: MHI reports a custom "business profit", no standard consolidated
    # operating-profit element — Task 3 income-statement mapping may revisit; honest None for now.
    assert r.operating_income is None
    # Balance-sheet detail recovered via IFRS fallback map (jpigp_cor namespace):
    assert r.current_liabilities == 3_146_299_000_000   # jpigp_cor:TotalCurrentLiabilitiesIFRS
    assert r.deferred_tax_assets == 259_942_000_000     # jpigp_cor:DeferredTaxAssetsIFRS
    # Remaining balance-sheet detail — honest None (no jpigp_cor fallback yet):
    for field in ('short_term_loans_payable', 'long_term_loans_payable', 'bonds_payable',
                  'current_portion_long_term_loans_payable', 'accounts_payable_other',
                  'non_operating_income', 'non_operating_expenses'):
        assert getattr(r, field) is None, f'{field} should be honest None under strict, not parent'

    # Nothing lost: the parent net_sales is still preserved in the fact-bag.
    assert any(getattr(f, 'value', '') == '1947178000000'
               and 'NonConsolidatedMember' in (getattr(f, 'context_id', '') or '')
               for f in (r.raw_facts or [])), 'parent value must remain in the fact-bag'
