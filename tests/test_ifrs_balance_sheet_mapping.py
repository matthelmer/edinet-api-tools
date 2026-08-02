"""IFRS balance-sheet fallbacks: element NAMES must exist in the real jpigp
taxonomy. The old map pointed current_liabilities at a non-existent
CurrentLiabilitiesIFRS (the real element is TotalCurrentLiabilitiesIFRS) and
had no DeferredTaxAssets / depreciation fallbacks at all.

Pinned values (verified against the real MHI / Toyota filings, 2026-06-09):
  current_liabilities    = 3_146_299_000_000  (jpigp_cor:TotalCurrentLiabilitiesIFRS,
                                                CurrentYearInstant, MHI)
  deferred_tax_assets    =   259_942_000_000  (jpigp_cor:DeferredTaxAssetsIFRS,
                                                CurrentYearInstant, MHI)
  depreciation_amortization = 2_251_233_000_000 (jpigp_cor:DepreciationAndAmortizationOpeCFIFRS,
                                                  CurrentYearDuration, Toyota)
"""
import csv as _csv
from decimal import Decimal
from pathlib import Path
from edinet_tools.parsers.securities import parse_securities_report

_COLS = ['要素ID', '項目名', 'コンテキストID', '相対年度',
         '連結・個別', '期間・時点', 'ユニットID', '単位', '値']


def _parse(name):
    p = Path(__file__).parent / 'fixtures' / 'securities' / f'{name}.csv'
    with open(p, encoding='utf-8') as fh:
        rows = list(_csv.reader(fh, delimiter='\t'))
    cf = [{'filename': f'{name}.csv', 'data': [dict(zip(_COLS, r)) for r in rows[1:]]}]
    return parse_securities_report(csv_files=cf, doc_id='TEST', doc_type_code='120')


def test_ifrs_current_liabilities_recovered():
    # MHI (IFRS): current_liabilities must come from jpigp_cor:TotalCurrentLiabilitiesIFRS
    # (the previously-mapped CurrentLiabilitiesIFRS does not exist in the taxonomy).
    r = _parse('mhi_ifrs_blast_radius')
    assert r.accounting_standard == 'IFRS'
    assert r.current_liabilities == 3_146_299_000_000


def test_ifrs_deferred_tax_assets_recovered():
    # jpigp_cor:DeferredTaxAssetsIFRS, CurrentYearInstant, MHI
    r = _parse('mhi_ifrs_blast_radius')
    assert r.accounting_standard == 'IFRS'
    assert r.deferred_tax_assets == 259_942_000_000


def test_ifrs_depreciation_recovered():
    # jpigp_cor:DepreciationAndAmortizationOpeCFIFRS, CurrentYearDuration, Toyota
    r = _parse('toyota_fy25_revenue')
    assert r.accounting_standard == 'IFRS'
    assert r.depreciation_amortization == 2_251_233_000_000


def test_ifrs_equity_ratio_is_a_ratio_not_bps():
    # jpcrp_cor:EquityToAssetRatioIFRSSummaryOfBusinessResults is a taxonomy
    # misnomer: its label is 1株当たり親会社所有者帰属持分 (BPS, yen). The real
    # ratio element is RatioOfOwnersEquityToGrossAssetsIFRSSummaryOfBusinessResults.
    # Before this fix, IFRS filers got BPS-in-yen stored as equity_ratio.
    # Itochu fixture: RatioOfOwnersEquityToGrossAssets... = 0.3803 at CurrentYearInstant.
    r = _parse('itochu_fy25_op_income')
    assert r.accounting_standard == 'IFRS'
    assert r.equity_ratio == Decimal('0.3803')


def test_ifrs_summary_bps_still_reads_per_share_element():
    # The misnomer element (EquityToAssetRatioIFRS...) genuinely IS per-share equity
    # (1株当たり親会社所有者帰属持分, JPYPerShares). ifrs_summary_bps keeps reading it.
    # Itochu fixture: EquityToAssetRatioIFRS... = 4059.19 at CurrentYearInstant.
    r = _parse('itochu_fy25_op_income')
    assert r.ifrs_summary_bps == Decimal('4059.19')


# --- net_assets: IFRS/US-GAAP total-equity fallback (0.8.0, C14 gate) ---
#
# Census (corpjapan prod, 2026-08-01): 9 IFRS + 23 US-GAAP securities_reports
# rows had net_assets NULL despite the existing net_assets_ifrs_summary /
# net_assets_usgaap_summary tiers (EquityAttributableToOwnersOfParent...,
# owners-of-parent only). These filers' 経営指標等 highlight table discloses
# only a single combined equity line — no owners/NCI split at all — so that
# element is genuinely absent, not misnamed.
#
# Two elements were adjudicated as REAL fallback candidates (concept:
# total equity INCLUDING non-controlling interest == J-GAAP NetAssets, which
# also includes NCI):
#   - IFRS:     TotalEquityIFRSSummaryOfBusinessResults (custom per-filer
#               namespace, e.g. jpcrp030000-asr_E00492-000:...; suffix-matched)
#   - US GAAP:  EquityIncludingPortionAttributableToNonControllingInterest
#               USGAAPSummaryOfBusinessResults (label: 純資産額（US GAAP）、
#               経営指標等 = "net assets amount"; standard jpcrp_cor: namespace
#               in the sampled fixture, matched by suffix for parity)
#
# REJECTED candidates from the same census (concept mismatches — never mapped):
#   - LiabilitiesAndNetAssets (負債純資産): balance-sheet TOTAL (= total assets
#     by identity: liabilities + net assets combined), AND tagged only at the
#     _NonConsolidatedMember (parent-only) context in every sampled fixture.
#     Two independent reasons to reject: wrong concept, wrong consolidation scope.
#   - ShareholdersEquity (株主資本): a sub-component of net assets (owners'
#     capital only, excludes OCI/NCI/subscription rights), also non-consolidated.
#   - StockholdersEquityPerShareOfCommonStockUSGAAPSummaryOfBusinessResults:
#     per-share BPS, wrong grain entirely (already used for net_assets_per_share).

def test_ifrs_net_assets_recovers_total_equity_by_suffix():
    # S100CUBT (IFRS, net_assets NULL in prod): TotalEquityIFRSSummaryOfBusinessResults
    # CurrentYearInstant = 2,842,027,000,000 under the custom
    # jpcrp030000-asr_E00492-000: namespace. The primary tier
    # (EquityAttributableToOwnersOfParentIFRS...) is entirely absent from this
    # filing — this is not a naming variant of it, so both tiers coexist safely.
    r = _parse('ifrs_net_assets_fixture_1')
    assert r.accounting_standard == 'IFRS'
    assert r.net_assets == 2_842_027_000_000


def test_ifrs_net_assets_second_fixture():
    # S100DDYF (IFRS, net_assets NULL in prod): TotalEquityIFRSSummaryOfBusinessResults
    # CurrentYearInstant = 720,546,000,000 (jpcrp030000-asr_E00436-000: namespace).
    r = _parse('ifrs_net_assets_fixture_2')
    assert r.accounting_standard == 'IFRS'
    assert r.net_assets == 720_546_000_000


def test_ifrs_net_assets_rejects_liabilities_and_net_assets_concept_mismatch():
    # Both fixture 1 and 2 also carry jppfs_cor:LiabilitiesAndNetAssets
    # (non-consolidated, balance-sheet-total concept) at a higher raw census
    # frequency than TotalEquityIFRS — confirming the fix picked the right
    # element by concept/context, not by frequency rank. net_assets must NOT
    # equal that non-consolidated total (2,885,760,000,000 for fixture 1).
    r = _parse('ifrs_net_assets_fixture_1')
    assert r.net_assets != 2_885_760_000_000
    assert r.net_assets == 2_842_027_000_000


def test_ifrs_total_liabilities_stays_honest_none_despite_present_element():
    # Zero adjudicated candidates survived for total_liabilities on IFRS/US-GAAP
    # (LiabilitiesAndNetAssets = concept mismatch; NoncurrentLiabilities /
    # DeferredTaxLiabilitiesNCL / CommercialPapersLiabilities = sub-components,
    # not the total; DescriptionOfFactAndReasonWhy...NotPresented = narrative
    # TextBlock, not numeric). No map added — this fixture carries
    # LiabilitiesAndNetAssets (present, non-NULL) yet total_liabilities must
    # remain honestly None, confirming we did not invent a mapping.
    r = _parse('ifrs_net_assets_fixture_1')
    assert r.total_liabilities is None


def test_usgaap_net_assets_recovers_total_equity_by_suffix():
    # S100TTEY (US GAAP, net_assets NULL in prod):
    # EquityIncludingPortionAttributableToNonControllingInterestUSGAAP
    # SummaryOfBusinessResults, label 純資産額（US GAAP）、経営指標等
    # ("net assets amount"), CurrentYearInstant = 3,448,513,000,000.
    # The primary tier (net_assets_usgaap_summary /
    # EquityAttributableToOwnersOfParentUSGAAP...) is entirely absent from
    # this filing.
    r = _parse('usgaap_net_assets_fixture_1')
    assert r.accounting_standard == 'US GAAP'
    assert r.net_assets == 3_448_513_000_000


def test_usgaap_net_assets_rejects_shareholders_equity_subcomponent():
    # jppfs_cor:ShareholdersEquity (株主資本) is present in the fixture at
    # 2,654,986,000,000 (non-consolidated) — a sub-component of net assets,
    # not the total. net_assets must come from the total-equity element, not
    # this narrower/non-consolidated one.
    r = _parse('usgaap_net_assets_fixture_1')
    assert r.net_assets != 2_654_986_000_000
    assert r.net_assets == 3_448_513_000_000
