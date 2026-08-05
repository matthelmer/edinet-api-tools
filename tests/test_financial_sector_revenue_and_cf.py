"""Golden tests: banks/insurers get net_sales from 経常収益
(jpcrp_cor:OrdinaryIncomeSummaryOfBusinessResults), which is their gross-revenue
top line — distinct from 経常利益 (OrdinaryIncomeLoss...) = ordinary profit that
correctly populates ordinary_income. Also pins the real J-GAAP CF fallback element
ids (jppfs_cor:NetCashProvidedByUsedIn{Operating,Investment,Financing}Activities)
which replace the invented jpcrp_cor:CashFlowsFrom* ids that never existed in any
real EDINET filing.

Fixture route:
  - Bank revenue (net_sales + cross-contamination guard): MUFG FY filing S100W4FB
    → tests/fixtures/securities/mufg_fy_revenue.csv.
    MUFG also has CF Summary elements (tier 1 in the CF waterfall), so a
    MUFG-based fixture cannot red-test the tier-3 jppfs_cor CF fallback.

  - J-GAAP CF fallback ids: SYNTHETIC minimal csv_files (same pattern as
    _synthetic_filing in tests/test_operating_income_mapping.py), clearly labeled.
    Contains ONLY jppfs CF ids with no CF-summary rows, asserting the values land
    in operating_cash_flow / investing_cash_flow / financing_cash_flow when no
    summary or IFRS source is present.
"""
import pytest
from edinet_tools.parsers.securities import parse_securities_report
from tests.conftest import load_securities_fixture

def _load(name):
    return load_securities_fixture(name)


def _parse(name):
    return parse_securities_report(csv_files=_load(name), doc_id='TEST', doc_type_code='120')


# ---------------------------------------------------------------------------
# Bank/insurer gross-revenue (経常収益) → net_sales
# Fixture: MUFG FY S100W4FB (Japan GAAP, consolidated, doc_id E03606 / 8306)
# ---------------------------------------------------------------------------

def test_bank_net_sales_from_ordinary_income_summary():
    """MUFG: 経常収益 (OrdinaryIncomeSummaryOfBusinessResults) must land in
    net_sales / prior_net_sales. Also guards that ordinary_income receives 経常利益
    (OrdinaryIncomeLossSummaryOfBusinessResults) — the two same-prefix elements
    must not cross-contaminate each other.

    Exact pins (verified from mufg_fy_revenue.csv, bare CurrentYearDuration /
    Prior1YearDuration contexts):
      OrdinaryIncomeSummaryOfBusinessResults  CurrentYearDuration  13,629,997,000,000
      OrdinaryIncomeSummaryOfBusinessResults  Prior1YearDuration   11,890,350,000,000
      OrdinaryIncomeLossSummaryOfBusinessResults CurrentYearDuration  2,669,483,000,000
      OrdinaryIncomeLossSummaryOfBusinessResults Prior1YearDuration   2,127,958,000,000
    """
    r = _parse('mufg_fy_revenue')
    assert r.accounting_standard == 'Japan GAAP'

    # Primary fix: gross revenue must be 経常収益, not None.
    assert r.net_sales == 13_629_997_000_000, (
        f'net_sales: expected 13_629_997_000_000, got {r.net_sales}'
    )
    assert r.prior_net_sales == 11_890_350_000_000, (
        f'prior_net_sales: expected 11_890_350_000_000, got {r.prior_net_sales}'
    )

    # Cross-contamination guard: OrdinaryIncomeLoss... must still land in
    # ordinary_income — not bleed into net_sales and not be None.
    assert r.ordinary_income == 2_669_483_000_000, (
        f'ordinary_income: expected 2_669_483_000_000, got {r.ordinary_income}'
    )
    assert r.prior_ordinary_income == 2_127_958_000_000, (
        f'prior_ordinary_income: expected 2_127_958_000_000, got {r.prior_ordinary_income}'
    )


# ---------------------------------------------------------------------------
# J-GAAP CF fallback — SYNTHETIC test
#
# MUFG has CF-Summary elements that win tier 1 of the CF waterfall; its fixture
# cannot exercise the tier-3 jppfs_cor fallback. We use a minimal synthetic
# csv_files (no CF-summary rows, no IFRS rows) to prove the corrected jppfs CF
# element ids fire when they are the only source present.
#
# Real J-GAAP CF element ids verified against a corpus scan (15/15 operating, 8/8
# investing, 15/15 financing — note "Investment" not "Investing" for the middle
# element, matching the XBRL taxonomy spelling):
#   jppfs_cor:NetCashProvidedByUsedInOperatingActivities
#   jppfs_cor:NetCashProvidedByUsedInInvestmentActivities   ← "Investment"
#   jppfs_cor:NetCashProvidedByUsedInFinancingActivities
#
# The three ids in ELEMENT_MAP before this fix were:
#   jpcrp_cor:CashFlowsFromOperatingActivities    — does not exist in any real filing
#   jpcrp_cor:CashFlowsFromInvestmentActivities   — does not exist in any real filing
#   jpcrp_cor:CashFlowsFromFinancingActivities    — does not exist in any real filing
# ---------------------------------------------------------------------------

def _synthetic_jgaap_cf_only():
    """Minimal SYNTHETIC csv_files — Japan GAAP consolidated filer with ONLY
    jppfs_cor CF statement rows and no CF-summary, no IFRS rows. Exercises the
    tier-3 J-GAAP CF fallback in the coalesce waterfall."""
    rows = [
        # DEI
        {'要素ID': 'jpdei_cor:AccountingStandardsDEI', '項目名': '会計基準',
         'コンテキストID': 'FilingDateInstant', '値': 'Japan GAAP'},
        {'要素ID': 'jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI',
         '項目名': '連結決算の有無', 'コンテキストID': 'FilingDateInstant', '値': 'true'},
        # CF statement — jppfs_cor ids (the real taxonomy ids)
        {'要素ID': 'jppfs_cor:NetCashProvidedByUsedInOperatingActivities',
         '項目名': '営業活動によるキャッシュ・フロー',
         'コンテキストID': 'CurrentYearDuration', 'ユニットID': 'JPY', '値': '1234000000'},
        {'要素ID': 'jppfs_cor:NetCashProvidedByUsedInInvestmentActivities',
         '項目名': '投資活動によるキャッシュ・フロー',
         'コンテキストID': 'CurrentYearDuration', 'ユニットID': 'JPY', '値': '-567000000'},
        {'要素ID': 'jppfs_cor:NetCashProvidedByUsedInFinancingActivities',
         '項目名': '財務活動によるキャッシュ・フロー',
         'コンテキストID': 'CurrentYearDuration', 'ユニットID': 'JPY', '値': '-890000000'},
    ]
    return [{'filename': 'synthetic_cf.csv', 'data': rows}]


def test_jgaap_cf_fallback_real_jppfs_ids():
    """SYNTHETIC: when only jppfs_cor CF statement elements are present (no
    summary, no IFRS), the corrected tier-3 fallback ids must deliver the values
    into operating_cash_flow / investing_cash_flow / financing_cash_flow.

    Before the fix: all three are None (invented jpcrp_cor:CashFlowsFrom* ids
    match nothing in any real filing or in this synthetic data).
    After the fix: values from jppfs_cor ids land correctly.
    """
    r = parse_securities_report(
        csv_files=_synthetic_jgaap_cf_only(),
        doc_id='SYNTH-CF', doc_type_code='120',
    )
    assert r.accounting_standard == 'Japan GAAP'
    assert r.operating_cash_flow == 1_234_000_000, (
        f'operating_cash_flow: expected 1_234_000_000, got {r.operating_cash_flow}'
    )
    assert r.investing_cash_flow == -567_000_000, (
        f'investing_cash_flow: expected -567_000_000, got {r.investing_cash_flow}'
    )
    assert r.financing_cash_flow == -890_000_000, (
        f'financing_cash_flow: expected -890_000_000, got {r.financing_cash_flow}'
    )
