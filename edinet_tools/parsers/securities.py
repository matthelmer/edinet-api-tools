"""
Parser for Securities Reports (Doc Type 120).

Extracts financial data, share information, and business descriptions
from 有価証券報告書 filings.

PROCESSING PHILOSOPHY: Store raw XBRL values faithfully. No interpretation.
- Financial values in yen
- Ratios as decimals (0.086 = 8.6%)
- Downstream consumers determine meaning
"""
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date
from typing import Any, Optional

from .base import ParsedReport
from .extraction import (
    Tier,
    resolve_tiers,
    get_dei,
    extract_csv_from_zip,
    extract_value,
    categorize_elements,
    parse_percentage,
    parse_date,
    coerce_numeric_value,
)
from .validation import Bound, Identity, IDENTITY_TOLERANCE, apply_validation


# XBRL Element ID mappings for Doc 120 (Securities Reports)
# Validated against jpcrp_cor, jppfs_cor, jpdei_cor taxonomies
ELEMENT_MAP = {
    # === DEI Elements (Identification) ===
    'edinet_code': 'jpdei_cor:EDINETCodeDEI',
    'security_code': 'jpdei_cor:SecurityCodeDEI',
    'company_name': 'jpdei_cor:FilerNameInJapaneseDEI',
    'company_name_en': 'jpdei_cor:FilerNameInEnglishDEI',
    'fiscal_year_start': 'jpdei_cor:CurrentFiscalYearStartDateDEI',
    'fiscal_year_end': 'jpdei_cor:CurrentFiscalYearEndDateDEI',
    'accounting_standard': 'jpdei_cor:AccountingStandardsDEI',
    'is_consolidated': 'jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI',

    # === SummaryOfBusinessResults Elements ===
    'net_sales_summary': 'jpcrp_cor:NetSalesSummaryOfBusinessResults',
    'ordinary_revenue_summary': 'jpcrp_cor:OrdinaryIncomeSummaryOfBusinessResults',  # 経常収益 — banks/insurers gross revenue (distinct from OrdinaryIncomeLoss... = ordinary profit)
    # Securities brokers (broker-ordinance filers): 営業収益 (GROSS operating
    # revenue) — summary table then FS-level fallback. 純営業収益
    # (NetOperatingRevenueSEC, after financial expenses) and 金融収益
    # (FinancialRevenueORSEC, a component) are deliberately NOT mapped here —
    # they are not the gross top-line every other net_sales tier represents.
    'operating_revenue1_summary': 'jpcrp_cor:OperatingRevenue1SummaryOfBusinessResults',
    'net_sales_broker_fs': 'jppfs_cor:OperatingRevenueSEC',
    'ordinary_income_summary': 'jpcrp_cor:OrdinaryIncomeLossSummaryOfBusinessResults',
    'net_income_summary': 'jpcrp_cor:ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults',
    'total_assets_summary': 'jpcrp_cor:TotalAssetsSummaryOfBusinessResults',
    'net_assets_summary': 'jpcrp_cor:NetAssetsSummaryOfBusinessResults',
    'net_assets_per_share': 'jpcrp_cor:NetAssetsPerShareSummaryOfBusinessResults',
    'earnings_per_share': 'jpcrp_cor:BasicEarningsLossPerShareSummaryOfBusinessResults',
    'equity_ratio': 'jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResults',
    'roe': 'jpcrp_cor:RateOfReturnOnEquitySummaryOfBusinessResults',
    'operating_cf_summary': 'jpcrp_cor:NetCashProvidedByUsedInOperatingActivitiesSummaryOfBusinessResults',
    'investing_cf_summary': 'jpcrp_cor:NetCashProvidedByUsedInInvestingActivitiesSummaryOfBusinessResults',
    'financing_cf_summary': 'jpcrp_cor:NetCashProvidedByUsedInFinancingActivitiesSummaryOfBusinessResults',

    # === Financial Statement Elements (Fallback) ===
    'operating_revenue_fs': 'jppfs_cor:OperatingRevenue1',
    'net_sales_fs': 'jppfs_cor:NetSales',
    'operating_income_fs': 'jppfs_cor:OperatingIncome',
    'ordinary_income_fs': 'jppfs_cor:OrdinaryIncome',
    'net_income_fs': 'jppfs_cor:ProfitLoss',
    'total_assets_fs': 'jppfs_cor:Assets',
    'net_assets_fs': 'jppfs_cor:NetAssets',
    'total_liabilities_fs': 'jppfs_cor:Liabilities',

    # === Ownership-basis split (v0.8.0+) ===
    # net_assets/net_income were split into *_owners (attributable to owners
    # of parent) and *_total (includes non-controlling interests) fields --
    # see SecuritiesReport for the field docs and __getattr__ for the
    # removed-name tombstone. These four entries are the NEW routing tiers
    # this split needed; the pre-existing net_assets_fs / net_income_fs /
    # net_assets_ifrs_summary / net_income_ifrs_summary / *_usgaap_summary
    # keys above already carry an unambiguous single ownership basis each
    # (see parse_securities_report()'s routing comments) and did not move.
    'net_income_owners_fs': 'jppfs_cor:ProfitLossAttributableToOwnersOfParent',
    'net_assets_owners_ifrs_fs': 'jpigp_cor:EquityAttributableToOwnersOfParentIFRS',
    # FS-level IFRS owners profit -- mirrors net_assets_owners_ifrs_fs's
    # equity sibling. Census: present in 89.1% of IFRS securities-report filings
    # (項目名 親会社の所有者、当期利益). Some filers (e.g. HOYA) tag this
    # FS-level element but not the *_ifrs_summary one, so it is a real,
    # non-redundant recovery tier, not a confirmation-only fallback.
    'net_income_owners_ifrs_fs': 'jpigp_cor:ProfitLossAttributableToOwnersOfParentIFRS',
    # Balance-sheet equity components (J-GAAP FS-level). Facts in their own
    # right -- never summed to derive net_assets_owners (J-GAAP has no
    # owners-only net-assets concept; components stay components).
    'shareholders_equity': 'jppfs_cor:ShareholdersEquity',
    'valuation_translation_adjustments': 'jppfs_cor:ValuationAndTranslationAdjustments',
    'non_controlling_interests': 'jppfs_cor:NonControllingInterests',

    # === Balance Sheet - Debt Details ===
    'short_term_loans_payable': 'jppfs_cor:ShortTermLoansPayable',
    'long_term_loans_payable': 'jppfs_cor:LongTermLoansPayable',
    'bonds_payable': 'jppfs_cor:BondsPayable',
    'current_portion_long_term_loans_payable': 'jppfs_cor:CurrentPortionOfLongTermLoansPayable',
    'lease_obligations_current': 'jppfs_cor:LeaseObligationsCL',
    'lease_obligations_noncurrent': 'jppfs_cor:LeaseObligationsNCL',
    'commercial_paper': 'jppfs_cor:CommercialPaper',

    # === IFRS balance-sheet debt (v0.8.0+) ===
    # IFRS filers report combined bonds-and-borrowings OR separate
    # borrowings-only lines -- neither maps cleanly onto the J-GAAP debt
    # fields above, so these are NEW fields, never an IFRS_FALLBACK_MAP
    # entry for them (that would coerce a different concept onto the
    # J-GAAP fields). Corpus survey of real filings (2026-08-01): the two
    # pairs are mutually exclusive per filer -- a filer reports one pair or the
    # other, never both, never 3+ of the 4 together.
    'bonds_and_borrowings_current_ifrs': 'jpigp_cor:BondsAndBorrowingsCLIFRS',
    'bonds_and_borrowings_noncurrent_ifrs': 'jpigp_cor:BondsAndBorrowingsNCLIFRS',
    'borrowings_current_ifrs': 'jpigp_cor:BorrowingsCLIFRS',
    'borrowings_noncurrent_ifrs': 'jpigp_cor:BorrowingsNCLIFRS',

    # === Cash Flow Statement Elements (J-GAAP FS fallback for companies without Summary section) ===
    # Note: the previous ids (jpcrp_cor:CashFlowsFrom{Operating,Investment,Financing}Activities)
    # did not exist in any real EDINET filing (0/15 sampled filings). The real J-GAAP
    # financial-statement CF element ids are in the jppfs_cor namespace.
    # Note spelling: "Investment" (not "Investing") in the middle element — matches the XBRL taxonomy.
    'operating_cf_cfs': 'jppfs_cor:NetCashProvidedByUsedInOperatingActivities',
    'investing_cf_cfs': 'jppfs_cor:NetCashProvidedByUsedInInvestmentActivities',
    'financing_cf_cfs': 'jppfs_cor:NetCashProvidedByUsedInFinancingActivities',

    # === IFRS Summary Elements (for ~6% of listed companies) ===
    'net_sales_ifrs_summary': 'jpcrp_cor:RevenueIFRSSummaryOfBusinessResults',
    'operating_income_ifrs_summary': 'jpcrp_cor:OperatingProfitLossIFRSSummaryOfBusinessResults',
    'operating_income_ifrs_fs': 'jpigp_cor:OperatingProfitLossIFRS',
    'net_income_ifrs_summary': 'jpcrp_cor:ProfitLossAttributableToOwnersOfParentIFRSSummaryOfBusinessResults',
    # TOTAL-basis (includes non-controlling interests) IFRS summary profit --
    # a last-resort-only mapping (see _DURATION_TIERS['net_income_total']).
    # Some IFRS filers tag this element but tag neither the owners-basis
    # summary element above nor the owners-basis FS element
    # (jpigp_cor:ProfitLossAttributableToOwnersOfParentIFRS) anywhere in the
    # filing -- net_income_total was structurally None for these filers
    # before this mapping, even though the filing states a real total-basis
    # figure.
    'net_income_ifrs_summary_total': 'jpcrp_cor:ProfitLossIFRSSummaryOfBusinessResults',
    'total_assets_ifrs_summary': 'jpcrp_cor:TotalAssetsIFRSSummaryOfBusinessResults',
    'net_assets_ifrs_summary': 'jpcrp_cor:EquityAttributableToOwnersOfParentIFRSSummaryOfBusinessResults',
    'earnings_per_share_ifrs': 'jpcrp_cor:BasicEarningsLossPerShareIFRSSummaryOfBusinessResults',
    # Real equity-ratio element (親会社所有者帰属持分比率（IFRS）; pure decimal, e.g. 0.3803).
    'equity_ratio_ifrs': 'jpcrp_cor:RatioOfOwnersEquityToGrossAssetsIFRSSummaryOfBusinessResults',
    # Taxonomy misnomer: element name says "EquityToAssetRatio" but its label is
    # 1株当たり親会社所有者帰属持分（IFRS）— equity attributable to owners of parent
    # PER SHARE, in JPY. Used only by ifrs_summary_bps; never as a ratio.
    'bps_ifrs': 'jpcrp_cor:EquityToAssetRatioIFRSSummaryOfBusinessResults',
    'roe_ifrs': 'jpcrp_cor:RateOfReturnOnEquityIFRSSummaryOfBusinessResults',

    # === US-GAAP Summary Elements (~18 listed filers; e.g. Sony FY20, pre-IFRS) ===
    # Some US-GAAP filers DO tag operating income via
    # OperatingIncomeLossUSGAAPSummaryOfBusinessResults; others report it only in
    # a TextBlock (-> honest None). Never fall back to the parent J-GAAP
    # jppfs_cor:OperatingIncome for IFRS/US-GAAP filers (it is the leak this gate closes).
    'net_sales_usgaap_summary': 'jpcrp_cor:RevenuesUSGAAPSummaryOfBusinessResults',
    'operating_income_usgaap_summary': 'jpcrp_cor:OperatingIncomeLossUSGAAPSummaryOfBusinessResults',
    'ordinary_income_usgaap_summary': 'jpcrp_cor:ProfitLossBeforeTaxUSGAAPSummaryOfBusinessResults',
    'net_income_usgaap_summary': 'jpcrp_cor:NetIncomeLossAttributableToOwnersOfParentUSGAAPSummaryOfBusinessResults',
    'earnings_per_share_usgaap': 'jpcrp_cor:BasicEarningsLossPerShareUSGAAPSummaryOfBusinessResults',
    'roe_usgaap': 'jpcrp_cor:RateOfReturnOnEquityUSGAAPSummaryOfBusinessResults',
    # Balance-sheet + per-share + CF elements for US-GAAP summary filers (R3, 2026-06-10).
    # Corpus scan (10 filings): TotalAssets 10/10, EquityToAssetRatio 10/10,
    # EquityAttributableToOwners 8/10, EquityPerShare 9/10, CF trio 10/10.
    'total_assets_usgaap_summary': 'jpcrp_cor:TotalAssetsUSGAAPSummaryOfBusinessResults',
    'net_assets_usgaap_summary': 'jpcrp_cor:EquityAttributableToOwnersOfParentUSGAAPSummaryOfBusinessResults',
    # EquityToAssetRatio (US-GAAP) is a GENUINE self-equity/total-assets ratio —
    # unlike its IFRS taxonomy namesake which is actually a BPS misnomer.
    'equity_ratio_usgaap': 'jpcrp_cor:EquityToAssetRatioUSGAAPSummaryOfBusinessResults',
    'net_assets_per_share_usgaap': 'jpcrp_cor:EquityAttributableToOwnersOfParentPerShareUSGAAPSummaryOfBusinessResults',
    'operating_cf_usgaap_summary': 'jpcrp_cor:CashFlowsFromUsedInOperatingActivitiesUSGAAPSummaryOfBusinessResults',
    'investing_cf_usgaap_summary': 'jpcrp_cor:CashFlowsFromUsedInInvestingActivitiesUSGAAPSummaryOfBusinessResults',
    'financing_cf_usgaap_summary': 'jpcrp_cor:CashFlowsFromUsedInFinancingActivitiesUSGAAPSummaryOfBusinessResults',

    # === IFRS Cash Flow Elements ===
    'operating_cf_ifrs_summary': 'jpcrp_cor:CashFlowsFromUsedInOperatingActivitiesIFRSSummaryOfBusinessResults',
    'investing_cf_ifrs_summary': 'jpcrp_cor:CashFlowsFromUsedInInvestingActivitiesIFRSSummaryOfBusinessResults',
    'financing_cf_ifrs_summary': 'jpcrp_cor:CashFlowsFromUsedInFinancingActivitiesIFRSSummaryOfBusinessResults',
    'operating_cf_ifrs': 'jpigp_cor:NetCashProvidedByUsedInOperatingActivitiesIFRS',
    'investing_cf_ifrs': 'jpigp_cor:NetCashProvidedByUsedInInvestingActivitiesIFRS',
    'financing_cf_ifrs': 'jpigp_cor:NetCashProvidedByUsedInFinancingActivitiesIFRS',

    # === Employment ===
    'num_employees': 'jpcrp_cor:NumberOfEmployees',

    # === Balance Sheet Detail ===
    'cash_and_deposits': 'jppfs_cor:CashAndDeposits',
    'current_assets': 'jppfs_cor:CurrentAssets',
    'noncurrent_assets': 'jppfs_cor:NoncurrentAssets',
    'property_plant_equipment': 'jppfs_cor:PropertyPlantAndEquipment',
    'deferred_tax_assets': 'jppfs_cor:DeferredTaxAssets',
    'current_liabilities': 'jppfs_cor:CurrentLiabilities',
    'accounts_payable_other': 'jppfs_cor:AccountsPayableOther',
    'retained_earnings': 'jppfs_cor:RetainedEarnings',

    # === Income Detail ===
    'income_before_taxes': 'jppfs_cor:IncomeBeforeIncomeTaxes',
    'non_operating_income': 'jppfs_cor:NonOperatingIncome',
    'non_operating_expenses': 'jppfs_cor:NonOperatingExpenses',
    'income_taxes': 'jppfs_cor:IncomeTaxes',

    # === Cash Flow Detail ===
    'depreciation_amortization_cfo': 'jppfs_cor:DepreciationAndAmortizationOpeCF',
}


def _equity_ratio_reconciles(er, na, ta):
    if ta == 0:
        return None
    return abs(er - na / ta) <= IDENTITY_TOLERANCE


def _equity_ratio_reconciles_jgaap(er, se, vta, ta):
    """J-GAAP has no owners-only net-assets element, so the owners-basis
    instrument for this identity is computed on the fly as
    shareholders_equity + valuation_translation_adjustments -- an
    in-check-only sum, never written back to any field or shipped as data.
    If either component is None, apply_identities' any-None-skips loop over
    identity.operands already skips the whole identity before this function
    is ever called -- no special-casing needed here."""
    if ta == 0:
        return None
    return abs(er - (se + vta) / ta) <= IDENTITY_TOLERANCE


def _net_assets_le_total_assets(na, ta):
    return na <= ta


def _current_le_total_liabilities(cl, tl):
    return cl <= tl


# Structural bounds: possibility, never plausibility. No lower bound on
# equity_ratio (insolvency is real). standards=None = applies to all.
SECURITIES_BOUNDS = [
    Bound(field='equity_ratio', max_value=Decimal('1')),
    Bound(field='total_assets', min_value=0),
    Bound(field='total_liabilities', min_value=0),
    Bound(field='current_liabilities', min_value=0),
    Bound(field='num_employees', min_value=0),
]

# Accounting identities: annotate only. The equity-ratio identity is split
# per ownership basis (Decision 4, 0.8.0 stage-4 rewire): IFRS/US-GAAP's
# equity_ratio element is owners-only-attributable (RatioOfOwnersEquity...
# IFRS, EquityToAssetRatioUSGAAP...), so it is checked against
# net_assets_owners; J-GAAP has no owners-only net-assets element, so its
# equity_ratio is checked against shareholders_equity +
# valuation_translation_adjustments (an in-check-only sum -- see
# _equity_ratio_reconciles_jgaap's docstring). The pre-0.8.0 single identity
# annotated ~15% of J-GAAP rows on an owners-equity-vs-total-net-assets
# ownership-basis mismatch that was a correctly-filed disagreement, not an
# extraction bug -- this rewire is what actually resolves that class rather
# than continuing to annotate it. The 0.8.0 IFRS/US-GAAP total-equity
# fallbacks (get_net_assets_ifrs_total_by_suffix /
# get_net_assets_usgaap_total_by_suffix, below) fill net_assets_total (incl.
# NCI) for filers with no owners/NCI split in their highlights table at
# all; net_assets_owners stays honest-None for those rows, so the
# owners-basis identity now correctly SKIPS them (no operand to compare)
# instead of annotating a false ownership-basis mismatch. See the fallback
# functions' docstrings for the per-filer reasoning.
#
# DELIBERATELY no owners<=total containment rule for any field pair
# (net_assets_owners/net_assets_total, net_income_owners/net_income_total,
# prior_net_income_owners/prior_net_income_total): non-controlling interests
# can themselves post a loss, so a filer's owners-attributable figure can
# legitimately EXCEED its total-including-NCI figure -- HOYA's FYE2026-03
# filing is exactly this shape (net_income_owners 253,085 > net_income_total
# 251,451; NCI's own profit share is -1,633). An owners<=total rule would
# incorrectly flag a real, correctly-filed inversion. See
# TestHoyaOwnersExceedsTotalNoFalseFlag in tests/test_grain_split.py.
SECURITIES_IDENTITIES = [
    Identity(name='identity:equity_ratio~net_assets_owners/total_assets',
             operands=('equity_ratio', 'net_assets_owners', 'total_assets'),
             check=_equity_ratio_reconciles,
             standards=('IFRS', 'US GAAP')),
    Identity(name='identity:equity_ratio~shareholders_equity+valuation_translation_adjustments/total_assets',
             operands=('equity_ratio', 'shareholders_equity',
                       'valuation_translation_adjustments', 'total_assets'),
             check=_equity_ratio_reconciles_jgaap,
             standards=('Japan GAAP',)),
    Identity(name='identity:net_assets<=total_assets',
             operands=('net_assets_total', 'total_assets'),
             check=_net_assets_le_total_assets),
    Identity(name='identity:current_liabilities<=total_liabilities',
             operands=('current_liabilities', 'total_liabilities'),
             check=_current_le_total_liabilities),
]

# IFRS fallback elements (jpigp_cor namespace)
# extract_financial() supports both single string and list values.
# Lists are tried in order at each context level.
IFRS_FALLBACK_MAP = {
    # === Financial Statement Core ===
    'jppfs_cor:NetSales': [
        'jpigp_cor:RevenueIFRS',
        'jpigp_cor:Revenue2IFRS',
        'jpigp_cor:NetSalesIFRS',
    ],
    'jppfs_cor:OperatingIncome': 'jpigp_cor:OperatingProfitLossIFRS',  # safety net for DEI-missing filers; gated filers reach jpigp via ELEMENT_MAP's operating_income_ifrs_fs
    # IFRS has no "ordinary income" — profit before tax is the closest analogue
    'jppfs_cor:OrdinaryIncome': 'jpigp_cor:ProfitLossBeforeTaxIFRS',
    'jppfs_cor:ProfitLoss': 'jpigp_cor:ProfitLossIFRS',
    'jppfs_cor:Assets': 'jpigp_cor:AssetsIFRS',
    'jppfs_cor:NetAssets': 'jpigp_cor:EquityIFRS',
    'jppfs_cor:Liabilities': 'jpigp_cor:LiabilitiesIFRS',
    # Component (not owners/total basis): same concept, IFRS taxonomy name.
    'jppfs_cor:NonControllingInterests': 'jpigp_cor:NonControllingInterestsIFRS',

    # === Balance Sheet Detail ===
    'jppfs_cor:CashAndDeposits': 'jpigp_cor:CashAndCashEquivalentsIFRS',
    'jppfs_cor:CurrentAssets': 'jpigp_cor:CurrentAssetsIFRS',
    'jppfs_cor:NoncurrentAssets': 'jpigp_cor:NonCurrentAssetsIFRS',
    'jppfs_cor:PropertyPlantAndEquipment': 'jpigp_cor:PropertyPlantAndEquipmentIFRS',
    'jppfs_cor:CurrentLiabilities': 'jpigp_cor:TotalCurrentLiabilitiesIFRS',
    'jppfs_cor:DeferredTaxAssets': 'jpigp_cor:DeferredTaxAssetsIFRS',
    'jppfs_cor:RetainedEarnings': 'jpigp_cor:RetainedEarningsIFRS',

    # === Income Detail ===
    'jppfs_cor:IncomeBeforeIncomeTaxes': 'jpigp_cor:ProfitLossBeforeTaxIFRS',
    'jppfs_cor:IncomeTaxes': 'jpigp_cor:IncomeTaxExpenseIFRS',

    # === Debt Detail ===
    'jppfs_cor:ShortTermLoansPayable': 'jpigp_cor:ShortTermBorrowingsIFRS',
    'jppfs_cor:LongTermLoansPayable': 'jpigp_cor:LongTermBorrowingsIFRS',
    'jppfs_cor:BondsPayable': 'jpigp_cor:BondsPayableIFRS',

    # === Cash Flow Detail ===
    'jppfs_cor:DepreciationAndAmortizationOpeCF': 'jpigp_cor:DepreciationAndAmortizationOpeCFIFRS',
}


@dataclass
class SecuritiesReport(ParsedReport):
    """Parsed Securities Report (Doc 120)."""

    # Identification
    filer_name: str | None = None
    filer_name_en: str | None = None
    filer_edinet_code: str | None = None
    ticker: str | None = None
    accounting_standard: str | None = None
    is_consolidated: bool | None = None

    # Period
    fiscal_year_start: date | None = None
    fiscal_year_end: date | None = None

    # Income Statement (Current Year)
    net_sales: int | None = None
    operating_income: int | None = None
    ordinary_income: int | None = None
    # net_income split by ownership basis (v0.8.0+): net_income_owners is
    # attributable to owners of parent (親会社株主に帰属する当期純利益 / IFRS
    # and US-GAAP owners equivalents); net_income_total includes
    # non-controlling interests' share. Routed per accounting standard in
    # parse_securities_report(), never cross-basis coalesced --
    # net_income_total is structurally None for nearly all US-GAAP filers
    # (no total-basis element exists in that taxonomy tier). See
    # SecuritiesReport.__getattr__ for the removed 'net_income' tombstone.
    net_income_owners: int | None = None
    net_income_total: int | None = None

    # Income Statement (Prior Year)
    prior_net_sales: int | None = None
    prior_operating_income: int | None = None
    prior_ordinary_income: int | None = None
    # Same ownership-basis split as net_income, read from the prior-year
    # XBRL context.
    prior_net_income_owners: int | None = None
    prior_net_income_total: int | None = None

    # Balance Sheet
    total_assets: int | None = None
    # net_assets split by ownership basis (v0.8.0+): net_assets_owners is
    # equity attributable to owners of parent; net_assets_total includes
    # non-controlling interests. net_assets_owners is ALWAYS None for
    # J-GAAP filers -- there is no J-GAAP owners-only net-assets element,
    # and it is never derived by summing the component fields below (honest
    # absence, not a computed stand-in). See SecuritiesReport.__getattr__
    # for the removed 'net_assets' tombstone.
    net_assets_owners: int | None = None
    net_assets_total: int | None = None
    # Balance-sheet equity components (J-GAAP FS-level; non_controlling_interests
    # also fed by its own IFRS element via IFRS_FALLBACK_MAP). Facts as filed,
    # not used to derive net_assets_owners/net_assets_total.
    shareholders_equity: int | None = None
    valuation_translation_adjustments: int | None = None
    non_controlling_interests: int | None = None
    total_liabilities: int | None = None

    # Balance Sheet - Debt Details
    short_term_loans_payable: int | None = None
    long_term_loans_payable: int | None = None
    bonds_payable: int | None = None
    current_portion_long_term_loans_payable: int | None = None
    lease_obligations_current: int | None = None
    lease_obligations_noncurrent: int | None = None
    commercial_paper: int | None = None

    # IFRS balance-sheet debt (v0.8.0+). IFRS filers report combined
    # bonds-and-borrowings lines with no clean mapping onto the J-GAAP debt
    # fields above — distinct line-item definitions get distinct fields
    # (never coerced onto each other).
    bonds_and_borrowings_current_ifrs: int | None = None
    bonds_and_borrowings_noncurrent_ifrs: int | None = None
    borrowings_current_ifrs: int | None = None
    borrowings_noncurrent_ifrs: int | None = None

    # Cash Flow
    operating_cash_flow: int | None = None
    investing_cash_flow: int | None = None
    financing_cash_flow: int | None = None

    # Per-Share Metrics
    net_assets_per_share: Decimal | None = None
    earnings_per_share: Decimal | None = None

    # Ratios
    equity_ratio: Decimal | None = None
    roe: Decimal | None = None

    # IFRS summary metrics (v0.7.1+). Populated from
    # jpcrp_cor:*IFRSSummaryOfBusinessResults XBRL elements at
    # CurrentYearDuration / CurrentYearInstant context. None when
    # the filing is not IFRS or the field is absent / null-marker.
    ifrs_summary_basic_eps: Decimal | None = None
    ifrs_summary_roe: Decimal | None = None
    ifrs_summary_bps: Decimal | None = None

    # Employment
    num_employees: int | None = None

    # Balance Sheet Detail
    cash_and_deposits: int | None = None
    current_assets: int | None = None
    noncurrent_assets: int | None = None
    property_plant_equipment: int | None = None
    deferred_tax_assets: int | None = None
    current_liabilities: int | None = None
    accounts_payable_other: int | None = None
    retained_earnings: int | None = None

    # Income Detail
    income_before_taxes: int | None = None
    non_operating_income: int | None = None
    non_operating_expenses: int | None = None
    income_taxes: int | None = None

    # Cash Flow Detail
    depreciation_amortization: int | None = None

    # Operating segments (v0.7.0+). Empty list when filer is US-GAAP-shape
    # or Toyota-IFRS-shape — those use TextBlock fallback signaled by
    # segments_text_only=True. Per spec §5.1.
    segments: list = field(default_factory=list)
    # True when segment data lives in monolithic TextBlock rather than
    # axis-discrete CSV rows (US-GAAP Komatsu-shape, Toyota IFRS-shape).
    # Downstream consumers can extract from text_blocks or defer typed
    # parsing to 0.8.0+ iXBRL HTML path.
    segments_text_only: bool = False
    # True when segment-specific aggregation rows are present (a segment table
    # exists) but no individual segments could be extracted — an honest flag for a
    # residual miss, so an empty `segments` is not silently read as single-segment.
    segments_extraction_incomplete: bool = False

    # Guided errors for the three fields removed by the v0.8.0 ownership-basis
    # split. Not a dataclass field (no type annotation) -- a plain class
    # attribute the dataclass decorator leaves untouched.
    _TOMBSTONES = {
        'net_assets': (
            "'net_assets' was split by ownership basis in edinet-tools 0.8.0. "
            "Use 'net_assets_total' (includes non-controlling interests -- "
            "J-GAAP 純資産, jppfs_cor:NetAssets) or 'net_assets_owners' "
            "(equity attributable to owners of parent; always None for "
            "J-GAAP filers -- see 'shareholders_equity' plus "
            "'valuation_translation_adjustments' instead)."
        ),
        'net_income': (
            "'net_income' was split by ownership basis in edinet-tools 0.8.0. "
            "Use 'net_income_total' (includes non-controlling interests' "
            "share; structurally None for nearly all US-GAAP filers) or "
            "'net_income_owners' (親会社株主に帰属する当期純利益 -- attributable "
            "to owners of parent)."
        ),
        'prior_net_income': (
            "'prior_net_income' was split by ownership basis in edinet-tools "
            "0.8.0, matching 'net_income'. Use 'prior_net_income_total' or "
            "'prior_net_income_owners' -- same routing, read from the "
            "prior-year XBRL context."
        ),
    }

    def __getattr__(self, name):
        """Guide readers of the three removed fields to their ownership-basis
        replacement(s). Only called when normal attribute lookup fails (i.e.
        never for a real field), so this cannot shadow anything else."""
        message = self._TOMBSTONES.get(name)
        if message is not None:
            raise AttributeError(message)
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )

    @property
    def filer(self):
        """Resolve filer to Entity if possible."""
        if self.filer_edinet_code:
            from edinet_tools.entity import entity_by_edinet_code
            return entity_by_edinet_code(self.filer_edinet_code)
        return None

    def __repr__(self) -> str:
        filer = self.filer_name or 'Unknown'
        if len(filer) > 25:
            filer = filer[:22] + '...'
        fy = self.fiscal_year_end.strftime('%Y-%m') if self.fiscal_year_end else '?'
        return f"SecuritiesReport(filer='{filer}', fy_end={fy})"


def _chain(key: str):
    """ELEMENT_MAP[key] plus its IFRS_FALLBACK_MAP fallback chain as ONE
    tier's element tuple — the declarative form of extract_financial's
    primary-plus-fallbacks call. The chain is resolved pattern-major within
    the tier (a fallback element at the preferred context beats the primary
    at a weaker context), exactly the pre-migration behavior."""
    element_id = ELEMENT_MAP[key]
    fallbacks = IFRS_FALLBACK_MAP.get(element_id)
    if not fallbacks:
        return element_id
    if isinstance(fallbacks, str):
        fallbacks = [fallbacks]
    return (element_id, *fallbacks)


# ---------------------------------------------------------------------------
# Per-field tier tables (v0.8.0 stage-5 migration)
#
# Tier order IS the pre-migration waterfall order — proven equivalent by the
# full-corpus old-vs-new re-parse — EXCEPT the ratified C1 per-standard
# scoping tiers marked "C1" below: IFRS-transition dual-table filings carry
# BOTH a legacy J-GAAP highlights table and an IFRS one at the same
# contexts, and the standard-agnostic order served the J-GAAP figures on
# IFRS rows for exactly three fields (equity_ratio / total_assets /
# net_assets_total). IFRS filers now try the IFRS-specific elements first;
# the neutral/legacy tiers still serve every other standard unchanged, and
# still serve IFRS rows that carry no IFRS-specific value (honest fallback).
# ---------------------------------------------------------------------------

# Duration-context fields. The same tables serve the current-year and
# prior-year reads (the period is a resolve_tiers argument).
_DURATION_TIERS = {
    # Revenue: J-GAAP summary -> IFRS summary -> US-GAAP summary -> bank/
    # insurer 経常収益 -> broker 営業収益 (summary then FS) -> custom-namespace
    # IFRS suffix hatch -> securities-firm FS -> FS NetSales (+ IFRS chain).
    'net_sales': (
        Tier(_chain('net_sales_summary')),
        Tier(_chain('net_sales_ifrs_summary')),
        Tier(_chain('net_sales_usgaap_summary')),
        Tier(_chain('ordinary_revenue_summary')),
        Tier(_chain('operating_revenue1_summary')),
        Tier(_chain('net_sales_broker_fs')),
        # Custom-namespace consolidated IFRS revenue (e.g. Toyota's
        # jpcrp030000-asr_E02144-000:SalesRevenuesIFRS) — bare context only,
        # so the parent figure can never win.
        Tier(('SalesRevenuesIFRS', 'TotalNetRevenuesIFRS',
              'RevenueIFRSSummaryOfBusinessResults'), suffix_match=True),
        Tier(_chain('operating_revenue_fs')),
        Tier(_chain('net_sales_fs')),
    ),
    # IFRS/US-GAAP filers NEVER fall back to the parent J-GAAP
    # jppfs_cor:OperatingIncome (the 0.7.1 leak class) — the last tier's
    # exclude_standards is that gate. DEI-missing filers keep it, with its
    # jpigp safety-net fallback from IFRS_FALLBACK_MAP. Filers with no
    # operating-profit concept (trading houses, US-GAAP TextBlock-only)
    # resolve to honest None.
    'operating_income': (
        Tier(_chain('operating_income_ifrs_summary')),
        Tier(_chain('operating_income_ifrs_fs')),
        # Custom-namespace IFRS/US-GAAP operating profit (e.g. JXTG's
        # filer-local namespace) — bare context only.
        Tier(('OperatingProfitLossIFRSSummaryOfBusinessResults',
              'OperatingIncomeIFRSSummaryOfBusinessResults',
              'OperatingIncomeLossIFRSSummaryOfBusinessResults',
              'OperatingProfitIFRSSummaryOfBusinessResults'),
             suffix_match=True),
        Tier(_chain('operating_income_usgaap_summary')),
        Tier(_chain('operating_income_fs'),
             exclude_standards=('IFRS', 'US GAAP')),
    ),
    'ordinary_income': (
        Tier(_chain('ordinary_income_summary')),
        Tier(_chain('ordinary_income_usgaap_summary')),
        Tier(_chain('ordinary_income_fs')),
    ),
    # net_income split by ownership basis (v0.8.0+): owners-basis sources
    # fill ONLY net_income_owners; the single total-basis source (jppfs
    # ProfitLoss + its IFRS chain) fills ONLY net_income_total. No
    # cross-basis coalescing — net_income_total stays honest-None for
    # US-GAAP (no total-basis element exists in that taxonomy tier).
    'net_income_owners': (
        Tier(_chain('net_income_summary')),
        Tier(_chain('net_income_ifrs_summary')),
        Tier(_chain('net_income_owners_ifrs_fs')),
        Tier(_chain('net_income_usgaap_summary')),
        Tier(_chain('net_income_owners_fs')),
    ),
    'net_income_total': (
        Tier(_chain('net_income_fs')),
        # Last-resort-only: tried strictly after the tier above, and only
        # engages when it resolved to None. IFRS-only -- a J-GAAP filing
        # tagging this element (which should never happen, but tier scoping
        # does not depend on that) must not read it.
        Tier(_chain('net_income_ifrs_summary_total'), standards=('IFRS',),
             last_resort=True),
    ),
    # Cash flow: J-GAAP summary -> IFRS summary -> US-GAAP summary ->
    # J-GAAP FS statement -> IFRS FS statement.
    'operating_cash_flow': (
        Tier(_chain('operating_cf_summary')),
        Tier(_chain('operating_cf_ifrs_summary')),
        Tier(_chain('operating_cf_usgaap_summary')),
        Tier(_chain('operating_cf_cfs')),
        Tier(_chain('operating_cf_ifrs')),
    ),
    'investing_cash_flow': (
        Tier(_chain('investing_cf_summary')),
        Tier(_chain('investing_cf_ifrs_summary')),
        Tier(_chain('investing_cf_usgaap_summary')),
        Tier(_chain('investing_cf_cfs')),
        Tier(_chain('investing_cf_ifrs')),
    ),
    'financing_cash_flow': (
        Tier(_chain('financing_cf_summary')),
        Tier(_chain('financing_cf_ifrs_summary')),
        Tier(_chain('financing_cf_usgaap_summary')),
        Tier(_chain('financing_cf_cfs')),
        Tier(_chain('financing_cf_ifrs')),
    ),
    # Income detail.
    'income_before_taxes': (Tier(_chain('income_before_taxes')),),
    'non_operating_income': (Tier(_chain('non_operating_income')),),
    'non_operating_expenses': (Tier(_chain('non_operating_expenses')),),
    'income_taxes': (Tier(_chain('income_taxes')),),
    # Cash flow detail.
    'depreciation_amortization': (Tier(_chain('depreciation_amortization_cfo')),),
}

# The five duration fields that also get a Prior1YearDuration read.
_PRIOR_YEAR_FIELDS = ('net_sales', 'operating_income', 'ordinary_income',
                      'net_income_owners', 'net_income_total')

# Instant-context fields (current year only).
_INSTANT_TIERS = {
    'total_assets': (
        # C1: IFRS filers read the IFRS highlights table first.
        Tier(ELEMENT_MAP['total_assets_ifrs_summary'], standards=('IFRS',)),
        Tier(_chain('total_assets_summary')),
        Tier(_chain('total_assets_ifrs_summary')),
        Tier(_chain('total_assets_usgaap_summary')),
        Tier(_chain('total_assets_fs')),
    ),
    # net_assets split by ownership basis (v0.8.0+): owners-basis sources
    # fill ONLY net_assets_owners — J-GAAP has no owners-only net-assets
    # element, so it stays honest-None for J-GAAP filers (never derived
    # from the component fields). Total-basis sources fill ONLY
    # net_assets_total. No cross-basis coalescing anywhere.
    'net_assets_owners': (
        Tier(_chain('net_assets_ifrs_summary')),
        Tier(_chain('net_assets_owners_ifrs_fs')),
        Tier(_chain('net_assets_usgaap_summary')),
    ),
    'net_assets_total': (
        # C1: IFRS filers read the IFRS-specific total-equity sources first
        # (summary-level combined-equity hatch, then FS-level EquityIFRS).
        Tier('TotalEquityIFRSSummaryOfBusinessResults',
             standards=('IFRS',), suffix_match=True),
        Tier('jpigp_cor:EquityIFRS', standards=('IFRS',)),
        Tier(_chain('net_assets_summary')),
        # Combined-equity highlights line for filers with no owners/NCI
        # split (e.g. TotalEquityIFRS... in a filer-local namespace) —
        # TotalEquity is the correct IFRS analog of J-GAAP NetAssets (both
        # include NCI). net_assets_owners stays honest-None on such rows,
        # so the owners-basis equity-ratio identity SKIPS them.
        Tier('TotalEquityIFRSSummaryOfBusinessResults', suffix_match=True),
        # US-GAAP combined total (純資産額（US GAAP）) — after the owners-only
        # net_assets_usgaap_summary tier in net_assets_owners.
        Tier('EquityIncludingPortionAttributableToNonControllingInterest'
             'USGAAPSummaryOfBusinessResults', suffix_match=True),
        Tier(_chain('net_assets_fs')),
    ),
    'total_liabilities': (Tier(_chain('total_liabilities_fs')),),
    # Balance-sheet equity components (J-GAAP FS-level;
    # non_controlling_interests also fed by its IFRS element via the
    # chain). Facts as filed — never summed to derive the net-assets
    # fields.
    'shareholders_equity': (Tier(_chain('shareholders_equity')),),
    'valuation_translation_adjustments': (
        Tier(_chain('valuation_translation_adjustments')),),
    'non_controlling_interests': (Tier(_chain('non_controlling_interests')),),
    # Debt details.
    'short_term_loans_payable': (Tier(_chain('short_term_loans_payable')),),
    'long_term_loans_payable': (Tier(_chain('long_term_loans_payable')),),
    'bonds_payable': (Tier(_chain('bonds_payable')),),
    'current_portion_long_term_loans_payable': (
        Tier(_chain('current_portion_long_term_loans_payable')),),
    'lease_obligations_current': (Tier(_chain('lease_obligations_current')),),
    'lease_obligations_noncurrent': (
        Tier(_chain('lease_obligations_noncurrent')),),
    'commercial_paper': (Tier(_chain('commercial_paper')),),
    # IFRS balance-sheet debt (v0.8.0+): new concepts, never fallbacks for
    # the J-GAAP fields — distinct line items get distinct fields.
    'bonds_and_borrowings_current_ifrs': (
        Tier(_chain('bonds_and_borrowings_current_ifrs')),),
    'bonds_and_borrowings_noncurrent_ifrs': (
        Tier(_chain('bonds_and_borrowings_noncurrent_ifrs')),),
    'borrowings_current_ifrs': (Tier(_chain('borrowings_current_ifrs')),),
    'borrowings_noncurrent_ifrs': (Tier(_chain('borrowings_noncurrent_ifrs')),),
    # Employment.
    'num_employees': (Tier(_chain('num_employees')),),
    # Balance sheet detail.
    'cash_and_deposits': (Tier(_chain('cash_and_deposits')),),
    'current_assets': (Tier(_chain('current_assets')),),
    'noncurrent_assets': (Tier(_chain('noncurrent_assets')),),
    'property_plant_equipment': (Tier(_chain('property_plant_equipment')),),
    'deferred_tax_assets': (Tier(_chain('deferred_tax_assets')),),
    'current_liabilities': (Tier(_chain('current_liabilities')),),
    'accounts_payable_other': (Tier(_chain('accounts_payable_other')),),
    'retained_earnings': (Tier(_chain('retained_earnings')),),
}

# Per-share / ratio tier tables ('string' mode — the caller parses).
_NAV_TIERS = (
    Tier(ELEMENT_MAP['net_assets_per_share']),
    # bps_ifrs's element name is a taxonomy misnomer ("EquityToAssetRatio")
    # but its label is 1株当たり親会社所有者帰属持分 — per-share equity in JPY,
    # the same concept as net_assets_per_share for IFRS filers.
    Tier(ELEMENT_MAP['bps_ifrs']),
    Tier(ELEMENT_MAP['net_assets_per_share_usgaap']),
    # US-GAAP custom-namespace variant (e.g. Sony's per-filer namespace) —
    # suffix tiers read the bare period only, so a parent figure can never
    # win even for non-consolidated filers.
    Tier('StockholdersEquityPerShareOfCommonStockUSGAAP'
         'SummaryOfBusinessResults', suffix_match=True),
)
_EPS_TIERS = (
    Tier(ELEMENT_MAP['earnings_per_share']),
    Tier(ELEMENT_MAP['earnings_per_share_ifrs']),
    Tier(ELEMENT_MAP['earnings_per_share_usgaap']),
)
# C1 preference stage for equity_ratio: coerce semantics, so a
# marker-valued IFRS ratio falls through to the legacy scan instead of
# blanking the field.
_EQUITY_RATIO_IFRS_FIRST = (
    Tier(ELEMENT_MAP['equity_ratio_ifrs'], standards=('IFRS',)),
)
# The legacy scan keeps its historical first-non-empty-raw-string behavior
# (coerce=False): a null-marker J-GAAP ratio still stops the scan and
# parses to None — bit-identical to pre-migration for non-IFRS filers.
# Note: EquityToAssetRatioUSGAAPSummaryOfBusinessResults IS a genuine ratio
# (unlike its IFRS taxonomy namesake, which is the BPS misnomer above).
_EQUITY_RATIO_LEGACY = (
    Tier(ELEMENT_MAP['equity_ratio']),
    Tier(ELEMENT_MAP['equity_ratio_ifrs']),
    Tier(ELEMENT_MAP['equity_ratio_usgaap']),
)
_ROE_TIERS = (
    Tier(ELEMENT_MAP['roe']),
    Tier(ELEMENT_MAP['roe_ifrs']),
    Tier(ELEMENT_MAP['roe_usgaap']),
)


# ---------------------------------------------------------------------------
# Extraction blocks (module-level, independently testable)
# ---------------------------------------------------------------------------

def _extract_dei_block(csv_files) -> dict:
    """DEI identification facts (FilingDateInstant context)."""
    security_code = get_dei(csv_files, ELEMENT_MAP, 'security_code')
    is_consolidated_raw = get_dei(csv_files, ELEMENT_MAP, 'is_consolidated')

    ticker = None
    if security_code and security_code != '－':
        ticker = f"{security_code.strip()[:4]}.T"

    return {
        'filer_name': get_dei(csv_files, ELEMENT_MAP, 'company_name'),
        'filer_name_en': get_dei(csv_files, ELEMENT_MAP, 'company_name_en'),
        'filer_edinet_code': get_dei(csv_files, ELEMENT_MAP, 'edinet_code'),
        'ticker': ticker,
        'accounting_standard': get_dei(csv_files, ELEMENT_MAP,
                                       'accounting_standard'),
        'is_consolidated': ((is_consolidated_raw == 'true')
                            if is_consolidated_raw else None),
        'fiscal_year_start': parse_date(
            get_dei(csv_files, ELEMENT_MAP, 'fiscal_year_start')),
        'fiscal_year_end': parse_date(
            get_dei(csv_files, ELEMENT_MAP, 'fiscal_year_end')),
    }


def _extract_financials(csv_files, standard, is_consolidated) -> dict:
    """Every integer financial field, resolved from the tier tables."""
    def fin(tiers, period):
        hit = resolve_tiers(csv_files, tiers, standard=standard,
                            period=period, is_consolidated=is_consolidated)
        return hit.value if hit else None

    out = {}
    for field_name, tiers in _DURATION_TIERS.items():
        out[field_name] = fin(tiers, 'CurrentYearDuration')
    for field_name in _PRIOR_YEAR_FIELDS:
        out[f'prior_{field_name}'] = fin(_DURATION_TIERS[field_name],
                                         'Prior1YearDuration')
    for field_name, tiers in _INSTANT_TIERS.items():
        out[field_name] = fin(tiers, 'CurrentYearInstant')
    return out


def _extract_per_share_block(csv_files, standard, is_consolidated):
    """Per-share metrics, ratios, and the independent IFRS summary trio.
    Returns (values, provenance) — provenance feeds apply_validation."""
    def string_hit(tiers, period, coerce):
        return resolve_tiers(csv_files, tiers, standard=standard,
                             period=period, is_consolidated=is_consolidated,
                             mode='string', coerce=coerce)

    values = {}
    provenance = {}

    nav_hit = string_hit(_NAV_TIERS, 'CurrentYearInstant', True)
    values['net_assets_per_share'] = Decimal(nav_hit.value) if nav_hit else None

    eps_hit = string_hit(_EPS_TIERS, 'CurrentYearDuration', True)
    values['earnings_per_share'] = Decimal(eps_hit.value) if eps_hit else None

    # equity_ratio: C1 IFRS-preference stage (coerce), then the legacy
    # first-non-empty-raw-string scan (see the tier-table comments).
    er_hit = string_hit(_EQUITY_RATIO_IFRS_FIRST, 'CurrentYearInstant', True)
    if er_hit is None:
        er_hit = string_hit(_EQUITY_RATIO_LEGACY, 'CurrentYearInstant', False)
    if er_hit is not None:
        provenance['equity_ratio'] = er_hit.element_id
    values['equity_ratio'] = parse_percentage(er_hit.value) if er_hit else None

    roe_hit = string_hit(_ROE_TIERS, 'CurrentYearDuration', False)
    values['roe'] = parse_percentage(roe_hit.value) if roe_hit else None

    # IFRS summary CurrentYear metrics (v0.7.1+): single fixed-bare-context
    # elements, not waterfalls — extracted independently of the tier tables
    # so consumers can distinguish IFRS-summary truth from waterfall-picked
    # values. coerce_numeric_value() keeps null markers away from Decimal().
    ifrs_eps_str = coerce_numeric_value(extract_value(
        csv_files, ELEMENT_MAP['earnings_per_share_ifrs'],
        context_patterns=['CurrentYearDuration'],
    ))
    values['ifrs_summary_basic_eps'] = Decimal(ifrs_eps_str) if ifrs_eps_str else None

    ifrs_roe_str = coerce_numeric_value(extract_value(
        csv_files, ELEMENT_MAP['roe_ifrs'],
        context_patterns=['CurrentYearDuration'],
    ))
    values['ifrs_summary_roe'] = Decimal(ifrs_roe_str) if ifrs_roe_str else None

    ifrs_bps_str = coerce_numeric_value(extract_value(
        csv_files, ELEMENT_MAP['bps_ifrs'],
        context_patterns=['CurrentYearInstant'],
    ))
    values['ifrs_summary_bps'] = Decimal(ifrs_bps_str) if ifrs_bps_str else None

    return values, provenance


def parse_securities_report(document=None, *, csv_files=None, doc_id=None, doc_type_code=None) -> SecuritiesReport:
    """
    Parse a Securities Report document.

    Args:
        document: Document object with fetch() method (optional if csv_files provided)
        csv_files: Pre-extracted CSV data (list of dicts with 'filename' and 'data' keys)
        doc_id: Document ID (required if csv_files provided)
        doc_type_code: Document type code (required if csv_files provided)

    Returns:
        SecuritiesReport with extracted fields
    """
    # Fetch and extract CSV data (unless pre-extracted)
    if csv_files is None:
        zip_bytes = document.fetch()
        csv_files = extract_csv_from_zip(zip_bytes)
        doc_id = document.doc_id
        doc_type_code = document.doc_type_code

    if not csv_files:
        return SecuritiesReport(
            doc_id=doc_id,
            doc_type_code=doc_type_code,
            source_files=[],
            raw_fields={},
            unmapped_fields={},
            text_blocks={},
        )

    source_files = [f['filename'] for f in csv_files]

    dei = _extract_dei_block(csv_files)
    standard = dei['accounting_standard']
    is_consolidated = dei['is_consolidated']

    financials = _extract_financials(csv_files, standard, is_consolidated)
    per_share, provenance = _extract_per_share_block(
        csv_files, standard, is_consolidated)

    # Categorize all elements
    raw_fields, text_blocks, unmapped_fields, raw_facts = categorize_elements(csv_files, ELEMENT_MAP)

    # Parse segments matrix (v0.7.0+)
    from .segments import parse_segments_from_csv
    segments, segments_text_only, segments_extraction_incomplete = parse_segments_from_csv(csv_files)

    report = SecuritiesReport(
        doc_id=doc_id,
        doc_type_code=doc_type_code,
        source_files=source_files,
        raw_fields=raw_fields,
        unmapped_fields=unmapped_fields,
        text_blocks=text_blocks,
        raw_facts=raw_facts,

        # Identification (document metadata fills DEI gaps)
        **{**dei,
           'filer_name': dei['filer_name'] or getattr(document, 'filer_name', None),
           'filer_edinet_code': (dei['filer_edinet_code']
                                 or getattr(document, 'filer_edinet_code', None))},

        # Financials (tier tables) + per-share/ratios
        **financials,
        **per_share,

        # Segments (v0.7.0+)
        segments=segments,
        segments_text_only=segments_text_only,
        segments_extraction_incomplete=segments_extraction_incomplete,
    )
    apply_validation(report, SECURITIES_BOUNDS, SECURITIES_IDENTITIES,
                     provenance=provenance)
    return report
