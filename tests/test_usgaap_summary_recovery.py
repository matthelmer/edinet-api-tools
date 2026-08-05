"""US-GAAP summary balance-sheet + cash-flow recovery (R3).

~95 US-GAAP filers (e.g. Sony pre-IFRS years) report total_assets, net_assets,
equity_ratio, net_assets_per_share, and the CF trio via dedicated US-GAAP summary
elements in the jpcrp_cor namespace. Before this fix they returned None because those
elements were absent from the parser waterfalls.

Sony FY20 fixture element-presence audit (2026-06-10):
  Element                                                             Present?  Context / Value
  -------                                                             --------  ---------------
  TotalAssetsUSGAAPSummaryOfBusinessResults                           MISSING   — not in fixture
  EquityAttributableToOwnersOfParentUSGAAPSummaryOfBusinessResults    MISSING   — not in fixture
  EquityToAssetRatioUSGAAPSummaryOfBusinessResults                    PRESENT   CurrentYearInstant / 0.179
  EquityAttributableToOwnersOfParentPerShareUSGAAPSummaryOfBR         MISSING   — company-custom ns only
  CashFlowsFromUsedInOperatingActivitiesUSGAAPSummaryOfBR             MISSING   — not in fixture
  CashFlowsFromUsedInInvestingActivitiesUSGAAPSummaryOfBR             MISSING   — not in fixture
  CashFlowsFromUsedInFinancingActivitiesUSGAAPSummaryOfBR             PRESENT   Prior2YearDuration only
                                                                                (not CurrentYearDuration)

Pinned exact values from Sony fixture for present elements:
  equity_ratio == Decimal('0.179')  (genuine self-equity/total-assets ratio, not BPS)

All other fields remain None for the Sony fixture (elements not present), but the
waterfall extension is verified to work correctly once elements exist — confirmed via
a corpus scan of 10 real US-GAAP filings.

Canon FY24 fixture element-presence audit (filing S100XTLJ, 2026-06-10):
  Element                                                             Present?  Context / Value
  -------                                                             --------  ---------------
  TotalAssetsUSGAAPSummaryOfBusinessResults                           PRESENT   CurrentYearInstant / 6135044000000
  EquityAttributableToOwnersOfParentUSGAAPSummaryOfBusinessResults    PRESENT   CurrentYearInstant / 3491808000000
  EquityToAssetRatioUSGAAPSummaryOfBusinessResults                    PRESENT   CurrentYearInstant / 0.569
  EquityAttributableToOwnersOfParentPerShareUSGAAPSummaryOfBR         PRESENT   CurrentYearInstant / 3974.81
  CashFlowsFromUsedInOperatingActivitiesUSGAAPSummaryOfBR             PRESENT   CurrentYearDuration / 475903000000
  CashFlowsFromUsedInInvestingActivitiesUSGAAPSummaryOfBR             PRESENT   CurrentYearDuration / -237450000000
  CashFlowsFromUsedInFinancingActivitiesUSGAAPSummaryOfBR             PRESENT   CurrentYearDuration / -179221000000
  RevenuesUSGAAPSummaryOfBusinessResults                              PRESENT   CurrentYearDuration / 4624727000000
  NetIncomeLossAttributableToOwnersOfParentUSGAAPSummaryOfBR          MISSING   — Canon omits; net_income is None
  OperatingIncomeLossUSGAAPSummaryOfBusinessResults                   MISSING   — Canon omits; operating_income is None
"""
from decimal import Decimal

from edinet_tools.parsers.securities import parse_securities_report
from tests.conftest import load_securities_fixture

def _parse(name: str):
    cf = load_securities_fixture(name)
    return parse_securities_report(csv_files=cf, doc_id='TEST', doc_type_code='120')


def test_usgaap_equity_ratio_recovered():
    """Sony FY20: EquityToAssetRatioUSGAAPSummaryOfBusinessResults is a genuine
    self-equity/total-assets ratio (not BPS as the IFRS misnomer element is).
    Value: 0.179 at CurrentYearInstant.
    Before fix: equity_ratio is None because the waterfall only tried J-GAAP
    and IFRS variants; the US-GAAP element was never attempted.
    """
    r = _parse('sony_fy20_usgaap_revenue')
    assert r.accounting_standard == 'US GAAP'
    assert r.equity_ratio == Decimal('0.179')


def test_usgaap_equity_ratio_is_ratio_not_bps():
    """Sanity check: equity_ratio for a US-GAAP filer must be a fraction (< 1),
    not a yen-per-share BPS figure (which would be in the thousands).
    """
    r = _parse('sony_fy20_usgaap_revenue')
    assert r.equity_ratio is not None
    assert r.equity_ratio < 1, (
        f"equity_ratio={r.equity_ratio!r} looks like a BPS figure, not a ratio"
    )


def test_usgaap_total_assets_absent_in_fixture_is_honest_none():
    """TotalAssetsUSGAAPSummaryOfBusinessResults is missing from the Sony fixture.
    Verifies no regression: field stays None (not a stale J-GAAP parent value).
    Real US-GAAP filers that DO have this element will be covered by the waterfall
    extension once those fixtures / real filing data are exercised.
    """
    r = _parse('sony_fy20_usgaap_revenue')
    # The J-GAAP summary and IFRS summary elements are also absent in the Sony
    # fixture; only the non-consolidated jppfs_cor:LiabilitiesAndNetAssets exists.
    # total_assets should come from jppfs_cor:Assets at a consolidated context —
    # which is also absent, so it stays None (honest unknown, not parent borrowing).
    assert r.total_assets is None


def test_usgaap_net_assets_absent_in_fixture_is_honest_none():
    """EquityAttributableToOwnersOfParentUSGAAPSummaryOfBusinessResults is missing
    from the Sony fixture. net_assets_owners must remain None (not the
    non-consolidated value).
    """
    r = _parse('sony_fy20_usgaap_revenue')
    assert r.net_assets_owners is None


def test_usgaap_net_assets_per_share_from_custom_namespace_variant():
    """EquityAttributableToOwnersOfParentPerShareUSGAAPSummaryOfBusinessResults is
    absent from the Sony fixture; only a company-custom-namespace variant
    (jpcrp030000-asr_E01777-000:StockholdersEquityPerShareOfCommonStock
    USGAAPSummaryOfBusinessResults) exists. As of the per-share fix
    (tests/test_per_share_mapping.py), a suffix-matched tier picks this up.
    IR-verified from the primary EDINET filing PDF (Sony Group FY2020/3,
    主要な経営指標等の推移 table, 2019年度 column): 1株当たり純資産額 = 3,380.96円.
    """
    r = _parse('sony_fy20_usgaap_revenue')
    assert r.net_assets_per_share == Decimal('3380.96')


def test_usgaap_operating_cf_absent_in_fixture_is_honest_none():
    """CashFlowsFromUsedInOperatingActivitiesUSGAAPSummaryOfBusinessResults is
    missing from the Sony fixture. operating_cash_flow must remain None.
    """
    r = _parse('sony_fy20_usgaap_revenue')
    assert r.operating_cash_flow is None


def test_usgaap_investing_cf_absent_in_fixture_is_honest_none():
    """CashFlowsFromUsedInInvestingActivitiesUSGAAPSummaryOfBusinessResults is
    missing from the Sony fixture. investing_cash_flow must remain None.
    """
    r = _parse('sony_fy20_usgaap_revenue')
    assert r.investing_cash_flow is None


def test_usgaap_financing_cf_prior_year_only_is_honest_none():
    """CashFlowsFromUsedInFinancingActivitiesUSGAAPSummaryOfBusinessResults is
    present in the Sony fixture but only at Prior2YearDuration (not CurrentYearDuration).
    financing_cash_flow must remain None — the parser must not read the wrong period.
    """
    r = _parse('sony_fy20_usgaap_revenue')
    assert r.financing_cash_flow is None


# ---------------------------------------------------------------------------
# Canon FY24 (S100XTLJ) — second US-GAAP filer with the full summary set
# Pins every R3-mapped element that is present in this filing.
# ---------------------------------------------------------------------------

def test_canon_usgaap_accounting_standard():
    """Canon FY24 is filed under US GAAP — accounting_standard must reflect that."""
    r = _parse('canon_fy_usgaap')
    assert r.accounting_standard == 'US GAAP'


def test_canon_usgaap_total_assets():
    """TotalAssetsUSGAAPSummaryOfBusinessResults @ CurrentYearInstant: 6,135,044,000,000 JPY."""
    r = _parse('canon_fy_usgaap')
    assert r.total_assets == 6_135_044_000_000


def test_canon_usgaap_net_assets():
    """EquityAttributableToOwnersOfParentUSGAAPSummaryOfBusinessResults @ CurrentYearInstant:
    3,491,808,000,000 JPY -- owners-of-parent basis.
    """
    r = _parse('canon_fy_usgaap')
    assert r.net_assets_owners == 3_491_808_000_000


def test_canon_usgaap_equity_ratio():
    """EquityToAssetRatioUSGAAPSummaryOfBusinessResults @ CurrentYearInstant: 0.569."""
    r = _parse('canon_fy_usgaap')
    assert r.equity_ratio == Decimal('0.569')


def test_canon_usgaap_equity_ratio_is_ratio_not_bps():
    """Sanity check: Canon equity_ratio must be a fraction (< 1), not a yen-per-share figure."""
    r = _parse('canon_fy_usgaap')
    assert r.equity_ratio is not None
    assert r.equity_ratio < 1, (
        f"equity_ratio={r.equity_ratio!r} looks like a BPS figure, not a ratio"
    )


def test_canon_usgaap_net_assets_per_share():
    """EquityAttributableToOwnersOfParentPerShareUSGAAPSummaryOfBusinessResults
    @ CurrentYearInstant: 3974.81 JPY/share.
    """
    r = _parse('canon_fy_usgaap')
    assert r.net_assets_per_share == Decimal('3974.81')


def test_canon_usgaap_operating_cash_flow():
    """CashFlowsFromUsedInOperatingActivitiesUSGAAPSummaryOfBusinessResults
    @ CurrentYearDuration: 475,903,000,000 JPY.
    """
    r = _parse('canon_fy_usgaap')
    assert r.operating_cash_flow == 475_903_000_000


def test_canon_usgaap_investing_cash_flow():
    """CashFlowsFromUsedInInvestingActivitiesUSGAAPSummaryOfBusinessResults
    @ CurrentYearDuration: -237,450,000,000 JPY.
    """
    r = _parse('canon_fy_usgaap')
    assert r.investing_cash_flow == -237_450_000_000


def test_canon_usgaap_financing_cash_flow():
    """CashFlowsFromUsedInFinancingActivitiesUSGAAPSummaryOfBusinessResults
    @ CurrentYearDuration: -179,221,000,000 JPY.
    """
    r = _parse('canon_fy_usgaap')
    assert r.financing_cash_flow == -179_221_000_000


def test_canon_usgaap_net_sales():
    """RevenuesUSGAAPSummaryOfBusinessResults @ CurrentYearDuration: 4,624,727,000,000 JPY."""
    r = _parse('canon_fy_usgaap')
    assert r.net_sales == 4_624_727_000_000


def test_canon_usgaap_net_income_absent_is_honest_none():
    """NetIncomeLossAttributableToOwnersOfParentUSGAAPSummaryOfBusinessResults is not
    tagged in the Canon filing. net_income_owners must be None — no fallback to
    non-consolidated jppfs_cor:ProfitLoss or ProfitLossBeforeTax.
    """
    r = _parse('canon_fy_usgaap')
    assert r.net_income_owners is None


def test_canon_usgaap_operating_income_absent_is_honest_none():
    """OperatingIncomeLossUSGAAPSummaryOfBusinessResults is not tagged in the Canon
    filing (Canon uses ProfitLossBeforeTax instead). operating_income must be None —
    no fallback to non-consolidated jppfs_cor:OperatingIncome.
    """
    r = _parse('canon_fy_usgaap')
    assert r.operating_income is None
