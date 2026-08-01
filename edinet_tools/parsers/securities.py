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
    extract_csv_from_zip,
    extract_value,
    categorize_elements,
    get_context_patterns,
    extract_financial,
    parse_percentage,
    parse_int,
    parse_date,
    coerce_numeric_value,
    match_element_by_suffix,
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

    # === Balance Sheet - Debt Details ===
    'short_term_loans_payable': 'jppfs_cor:ShortTermLoansPayable',
    'long_term_loans_payable': 'jppfs_cor:LongTermLoansPayable',
    'bonds_payable': 'jppfs_cor:BondsPayable',
    'current_portion_long_term_loans_payable': 'jppfs_cor:CurrentPortionOfLongTermLoansPayable',
    'lease_obligations_current': 'jppfs_cor:LeaseObligationsCL',
    'lease_obligations_noncurrent': 'jppfs_cor:LeaseObligationsNCL',
    'commercial_paper': 'jppfs_cor:CommercialPaper',

    # === Cash Flow Statement Elements (J-GAAP FS fallback for companies without Summary section) ===
    # Note: the previous ids (jpcrp_cor:CashFlowsFrom{Operating,Investment,Financing}Activities)
    # did not exist in any real EDINET filing (0/15 prod scan). The real J-GAAP
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
    # Prod scan (10 filings): TotalAssets 10/10, EquityToAssetRatio 10/10,
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

# Accounting identities: annotate only. The J-GAAP equity-ratio identity is
# expected to annotate ~15% of rows pre-0.8.0 (owners-equity vs total
# net-assets grain); that cohort is the baseline for the planned
# owners-equity grain split.
SECURITIES_IDENTITIES = [
    Identity(name='identity:equity_ratio~net_assets/total_assets',
             operands=('equity_ratio', 'net_assets', 'total_assets'),
             check=_equity_ratio_reconciles),
    Identity(name='identity:net_assets<=total_assets',
             operands=('net_assets', 'total_assets'),
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
    net_income: int | None = None

    # Income Statement (Prior Year)
    prior_net_sales: int | None = None
    prior_operating_income: int | None = None
    prior_ordinary_income: int | None = None
    prior_net_income: int | None = None

    # Balance Sheet
    total_assets: int | None = None
    net_assets: int | None = None
    total_liabilities: int | None = None

    # Balance Sheet - Debt Details
    short_term_loans_payable: int | None = None
    long_term_loans_payable: int | None = None
    bonds_payable: int | None = None
    current_portion_long_term_loans_payable: int | None = None
    lease_obligations_current: int | None = None
    lease_obligations_noncurrent: int | None = None
    commercial_paper: int | None = None

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


def _coalesce(*values):
    """Return the first non-None value."""
    for v in values:
        if v is not None:
            return v
    return None


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

    # Helper to get DEI values
    def get_dei(key: str) -> str | None:
        return extract_value(csv_files, ELEMENT_MAP.get(key, ''), context_patterns=['FilingDateInstant'])

    # Extract DEI elements
    edinet_code = get_dei('edinet_code')
    company_name = get_dei('company_name')
    security_code = get_dei('security_code')
    accounting_standard = get_dei('accounting_standard')
    is_consolidated_raw = get_dei('is_consolidated')
    is_consolidated = (is_consolidated_raw == 'true') if is_consolidated_raw else None

    # Format ticker
    ticker = None
    if security_code and security_code != '－':
        ticker = f"{security_code.strip()[:4]}.T"

    # Extract period
    fiscal_year_start = parse_date(get_dei('fiscal_year_start'))
    fiscal_year_end = parse_date(get_dei('fiscal_year_end'))

    # Helper for financial extraction
    def get_fin(key: str, period: str) -> int | None:
        element_id = ELEMENT_MAP.get(key, '')
        if not element_id:
            return None
        return extract_financial(csv_files, element_id, period, is_consolidated, IFRS_FALLBACK_MAP)

    def get_revenue_by_suffix(period: str) -> int | None:
        """Consolidated IFRS revenue for custom-namespace filers (e.g. Toyota's
        jpcrp030000-asr_E02144-000:SalesRevenuesIFRS, which no fixed element id
        matches). Matched at the bare (consolidated) context only — the
        *_NonConsolidatedMember rows are deliberately excluded so the parent figure
        can never win here."""
        for canonical in ('SalesRevenuesIFRS', 'TotalNetRevenuesIFRS',
                          'RevenueIFRSSummaryOfBusinessResults'):
            for row in match_element_by_suffix(csv_files, canonical):
                if (row.get('コンテキストID', '') or '') == period:
                    v = coerce_numeric_value(row.get('値', ''))
                    if v:
                        return parse_int(v)
        return None

    # Try summary elements first (J-GAAP then IFRS), then fall back to FS elements
    # FS elements have their own IFRS fallback via IFRS_FALLBACK_MAP in extract_financial()
    net_sales = _coalesce(
        get_fin('net_sales_summary', 'CurrentYearDuration'),
        get_fin('net_sales_ifrs_summary', 'CurrentYearDuration'),
        get_fin('net_sales_usgaap_summary', 'CurrentYearDuration'),
        get_fin('ordinary_revenue_summary', 'CurrentYearDuration'),
        get_fin('operating_revenue1_summary', 'CurrentYearDuration'),
        get_fin('net_sales_broker_fs', 'CurrentYearDuration'),
        get_revenue_by_suffix('CurrentYearDuration'),
        get_fin('operating_revenue_fs', 'CurrentYearDuration'),
        get_fin('net_sales_fs', 'CurrentYearDuration'),
    )
    # IFRS/US-GAAP: try their own operating-profit elements; NEVER fall back to
    # the parent J-GAAP jppfs_cor:OperatingIncome. No current filing is known to
    # tag the parent figure at the bare consolidated context (scan of 2,229
    # IFRS/US-GAAP securities reports, 2026-06), but a filing that did would win
    # the old coalesce — this gate is the defense. Filers with no operating-profit
    # concept (trading houses, US-GAAP TextBlock-only) -> honest None.
    operating_income = _coalesce(
        get_fin('operating_income_ifrs_summary', 'CurrentYearDuration'),
        get_fin('operating_income_ifrs_fs', 'CurrentYearDuration'),
        get_fin('operating_income_usgaap_summary', 'CurrentYearDuration'),
        None if accounting_standard in ('IFRS', 'US GAAP')
        else get_fin('operating_income_fs', 'CurrentYearDuration'),
    )
    ordinary_income = _coalesce(
        get_fin('ordinary_income_summary', 'CurrentYearDuration'),
        get_fin('ordinary_income_usgaap_summary', 'CurrentYearDuration'),
        get_fin('ordinary_income_fs', 'CurrentYearDuration'),
    )
    net_income = _coalesce(
        get_fin('net_income_summary', 'CurrentYearDuration'),
        get_fin('net_income_ifrs_summary', 'CurrentYearDuration'),
        get_fin('net_income_usgaap_summary', 'CurrentYearDuration'),
        get_fin('net_income_fs', 'CurrentYearDuration'),
    )

    # Prior year
    prior_net_sales = _coalesce(
        get_fin('net_sales_summary', 'Prior1YearDuration'),
        get_fin('net_sales_ifrs_summary', 'Prior1YearDuration'),
        get_fin('net_sales_usgaap_summary', 'Prior1YearDuration'),
        get_fin('ordinary_revenue_summary', 'Prior1YearDuration'),
        get_fin('operating_revenue1_summary', 'Prior1YearDuration'),
        get_fin('net_sales_broker_fs', 'Prior1YearDuration'),
        get_revenue_by_suffix('Prior1YearDuration'),
        get_fin('operating_revenue_fs', 'Prior1YearDuration'),
        get_fin('net_sales_fs', 'Prior1YearDuration'),
    )
    prior_operating_income = _coalesce(
        get_fin('operating_income_ifrs_summary', 'Prior1YearDuration'),
        get_fin('operating_income_ifrs_fs', 'Prior1YearDuration'),
        get_fin('operating_income_usgaap_summary', 'Prior1YearDuration'),
        None if accounting_standard in ('IFRS', 'US GAAP')
        else get_fin('operating_income_fs', 'Prior1YearDuration'),
    )
    prior_ordinary_income = _coalesce(
        get_fin('ordinary_income_summary', 'Prior1YearDuration'),
        get_fin('ordinary_income_usgaap_summary', 'Prior1YearDuration'),
        get_fin('ordinary_income_fs', 'Prior1YearDuration'),
    )
    prior_net_income = _coalesce(
        get_fin('net_income_summary', 'Prior1YearDuration'),
        get_fin('net_income_ifrs_summary', 'Prior1YearDuration'),
        get_fin('net_income_usgaap_summary', 'Prior1YearDuration'),
        get_fin('net_income_fs', 'Prior1YearDuration'),
    )

    # Balance sheet
    total_assets = _coalesce(
        get_fin('total_assets_summary', 'CurrentYearInstant'),
        get_fin('total_assets_ifrs_summary', 'CurrentYearInstant'),
        get_fin('total_assets_usgaap_summary', 'CurrentYearInstant'),
        get_fin('total_assets_fs', 'CurrentYearInstant'),
    )
    net_assets = _coalesce(
        get_fin('net_assets_summary', 'CurrentYearInstant'),
        get_fin('net_assets_ifrs_summary', 'CurrentYearInstant'),
        get_fin('net_assets_usgaap_summary', 'CurrentYearInstant'),
        get_fin('net_assets_fs', 'CurrentYearInstant'),
    )
    total_liabilities = get_fin('total_liabilities_fs', 'CurrentYearInstant')

    # Debt details
    short_term_loans_payable = get_fin('short_term_loans_payable', 'CurrentYearInstant')
    long_term_loans_payable = get_fin('long_term_loans_payable', 'CurrentYearInstant')
    bonds_payable = get_fin('bonds_payable', 'CurrentYearInstant')
    current_portion_ltd = get_fin('current_portion_long_term_loans_payable', 'CurrentYearInstant')
    lease_obligations_current = get_fin('lease_obligations_current', 'CurrentYearInstant')
    lease_obligations_noncurrent = get_fin('lease_obligations_noncurrent', 'CurrentYearInstant')
    commercial_paper = get_fin('commercial_paper', 'CurrentYearInstant')

    # Cash flow - Multi-tier fallback:
    # 1. Japan GAAP Summary (jpcrp_cor)
    # 2. IFRS Summary (jpcrp_cor with IFRS suffix)
    # 3. Japan GAAP detailed statement (jppfs_cor)
    # 4. IFRS detailed statement (jpigp_cor)
    operating_cf = _coalesce(
        get_fin('operating_cf_summary', 'CurrentYearDuration'),
        get_fin('operating_cf_ifrs_summary', 'CurrentYearDuration'),
        get_fin('operating_cf_usgaap_summary', 'CurrentYearDuration'),
        get_fin('operating_cf_cfs', 'CurrentYearDuration'),
        get_fin('operating_cf_ifrs', 'CurrentYearDuration'),
    )

    investing_cf = _coalesce(
        get_fin('investing_cf_summary', 'CurrentYearDuration'),
        get_fin('investing_cf_ifrs_summary', 'CurrentYearDuration'),
        get_fin('investing_cf_usgaap_summary', 'CurrentYearDuration'),
        get_fin('investing_cf_cfs', 'CurrentYearDuration'),
        get_fin('investing_cf_ifrs', 'CurrentYearDuration'),
    )

    financing_cf = _coalesce(
        get_fin('financing_cf_summary', 'CurrentYearDuration'),
        get_fin('financing_cf_ifrs_summary', 'CurrentYearDuration'),
        get_fin('financing_cf_usgaap_summary', 'CurrentYearDuration'),
        get_fin('financing_cf_cfs', 'CurrentYearDuration'),
        get_fin('financing_cf_ifrs', 'CurrentYearDuration'),
    )

    # Per-share metrics (try J-GAAP then IFRS summary).
    # coerce_numeric_value() normalizes EDINET null markers ('－' U+FF0D, '−',
    # '-', '') to None — a truthy check alone would let '－' through to
    # Decimal() and crash. Required for both extract_value() calls in the
    # eps waterfall so the `if not eps_str` gate works correctly.
    patterns = get_context_patterns(is_consolidated, 'CurrentYearInstant')
    nav_str = coerce_numeric_value(extract_value(
        csv_files, ELEMENT_MAP['net_assets_per_share'], context_patterns=patterns
    ))
    if not nav_str:
        nav_str = coerce_numeric_value(extract_value(
            csv_files, ELEMENT_MAP['net_assets_per_share_usgaap'], context_patterns=patterns
        ))
    net_assets_per_share = Decimal(nav_str) if nav_str else None

    patterns = get_context_patterns(is_consolidated, 'CurrentYearDuration')
    eps_str = coerce_numeric_value(extract_value(
        csv_files, ELEMENT_MAP['earnings_per_share'], context_patterns=patterns
    ))
    if not eps_str:
        eps_str = coerce_numeric_value(extract_value(
            csv_files, ELEMENT_MAP['earnings_per_share_ifrs'], context_patterns=patterns
        ))
    if not eps_str:
        eps_str = coerce_numeric_value(extract_value(
            csv_files, ELEMENT_MAP['earnings_per_share_usgaap'], context_patterns=patterns
        ))
    earnings_per_share = Decimal(eps_str) if eps_str else None

    # Ratios (try J-GAAP, then IFRS summary, then US-GAAP summary)
    # Note: EquityToAssetRatioUSGAAPSummaryOfBusinessResults IS a genuine ratio
    # (unlike its IFRS taxonomy namesake which is a BPS misnomer).
    patterns = get_context_patterns(is_consolidated, 'CurrentYearInstant')
    provenance = {}
    equity_str = None
    for _key in ('equity_ratio', 'equity_ratio_ifrs', 'equity_ratio_usgaap'):
        equity_str = extract_value(csv_files, ELEMENT_MAP[_key], context_patterns=patterns)
        if equity_str:
            provenance['equity_ratio'] = ELEMENT_MAP[_key]
            break
    equity_ratio = parse_percentage(equity_str)

    patterns = get_context_patterns(is_consolidated, 'CurrentYearDuration')
    roe_str = extract_value(csv_files, ELEMENT_MAP['roe'], context_patterns=patterns)
    if not roe_str:
        roe_str = extract_value(csv_files, ELEMENT_MAP['roe_ifrs'], context_patterns=patterns)
    if not roe_str:
        roe_str = extract_value(csv_files, ELEMENT_MAP['roe_usgaap'], context_patterns=patterns)
    roe = parse_percentage(roe_str)

    # IFRS summary CurrentYear metrics (v0.7.1+).
    # Always extracted; None on non-IFRS rows where the element IDs aren't present.
    # Note: extracted independently of the J-GAAP-first waterfall above, so
    # consumers can distinguish IFRS-summary truth from waterfall-picked values.
    # coerce_numeric_value() handles EDINET null markers ('－' U+FF0D, '−', '-', '')
    # — a truthy check alone would let '－' through to Decimal() and crash.
    ifrs_eps_str = coerce_numeric_value(extract_value(
        csv_files, ELEMENT_MAP['earnings_per_share_ifrs'],
        context_patterns=['CurrentYearDuration'],
    ))
    ifrs_summary_basic_eps = Decimal(ifrs_eps_str) if ifrs_eps_str else None

    ifrs_roe_str = coerce_numeric_value(extract_value(
        csv_files, ELEMENT_MAP['roe_ifrs'],
        context_patterns=['CurrentYearDuration'],
    ))
    ifrs_summary_roe = Decimal(ifrs_roe_str) if ifrs_roe_str else None

    ifrs_bps_str = coerce_numeric_value(extract_value(
        csv_files, ELEMENT_MAP['bps_ifrs'],
        context_patterns=['CurrentYearInstant'],
    ))
    ifrs_summary_bps = Decimal(ifrs_bps_str) if ifrs_bps_str else None

    # Employment
    num_employees = get_fin('num_employees', 'CurrentYearInstant')

    # Balance sheet detail
    cash_and_deposits = get_fin('cash_and_deposits', 'CurrentYearInstant')
    current_assets = get_fin('current_assets', 'CurrentYearInstant')
    noncurrent_assets = get_fin('noncurrent_assets', 'CurrentYearInstant')
    property_plant_equipment = get_fin('property_plant_equipment', 'CurrentYearInstant')
    deferred_tax_assets = get_fin('deferred_tax_assets', 'CurrentYearInstant')
    current_liabilities = get_fin('current_liabilities', 'CurrentYearInstant')
    accounts_payable_other = get_fin('accounts_payable_other', 'CurrentYearInstant')
    retained_earnings = get_fin('retained_earnings', 'CurrentYearInstant')

    # Income detail
    income_before_taxes = get_fin('income_before_taxes', 'CurrentYearDuration')
    non_operating_income = get_fin('non_operating_income', 'CurrentYearDuration')
    non_operating_expenses = get_fin('non_operating_expenses', 'CurrentYearDuration')
    income_taxes = get_fin('income_taxes', 'CurrentYearDuration')

    # Cash flow detail
    depreciation_amortization = get_fin('depreciation_amortization_cfo', 'CurrentYearDuration')

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

        # Identification
        filer_name=company_name or getattr(document, 'filer_name', None),
        filer_name_en=get_dei('company_name_en'),
        filer_edinet_code=edinet_code or getattr(document, 'filer_edinet_code', None),
        ticker=ticker,
        accounting_standard=accounting_standard,
        is_consolidated=is_consolidated,

        # Period
        fiscal_year_start=fiscal_year_start,
        fiscal_year_end=fiscal_year_end,

        # Income Statement (Current)
        net_sales=net_sales,
        operating_income=operating_income,
        ordinary_income=ordinary_income,
        net_income=net_income,

        # Income Statement (Prior)
        prior_net_sales=prior_net_sales,
        prior_operating_income=prior_operating_income,
        prior_ordinary_income=prior_ordinary_income,
        prior_net_income=prior_net_income,

        # Balance Sheet
        total_assets=total_assets,
        net_assets=net_assets,
        total_liabilities=total_liabilities,

        # Balance Sheet - Debt Details
        short_term_loans_payable=short_term_loans_payable,
        long_term_loans_payable=long_term_loans_payable,
        bonds_payable=bonds_payable,
        current_portion_long_term_loans_payable=current_portion_ltd,
        lease_obligations_current=lease_obligations_current,
        lease_obligations_noncurrent=lease_obligations_noncurrent,
        commercial_paper=commercial_paper,

        # Cash Flow
        operating_cash_flow=operating_cf,
        investing_cash_flow=investing_cf,
        financing_cash_flow=financing_cf,

        # Per-Share
        net_assets_per_share=net_assets_per_share,
        earnings_per_share=earnings_per_share,

        # Ratios
        equity_ratio=equity_ratio,
        roe=roe,

        # IFRS summary metrics (v0.7.1+)
        ifrs_summary_basic_eps=ifrs_summary_basic_eps,
        ifrs_summary_roe=ifrs_summary_roe,
        ifrs_summary_bps=ifrs_summary_bps,

        # Employment
        num_employees=num_employees,

        # Balance Sheet Detail
        cash_and_deposits=cash_and_deposits,
        current_assets=current_assets,
        noncurrent_assets=noncurrent_assets,
        property_plant_equipment=property_plant_equipment,
        deferred_tax_assets=deferred_tax_assets,
        current_liabilities=current_liabilities,
        accounts_payable_other=accounts_payable_other,
        retained_earnings=retained_earnings,

        # Income Detail
        income_before_taxes=income_before_taxes,
        non_operating_income=non_operating_income,
        non_operating_expenses=non_operating_expenses,
        income_taxes=income_taxes,

        # Cash Flow Detail
        depreciation_amortization=depreciation_amortization,

        # Segments (v0.7.0+)
        segments=segments,
        segments_text_only=segments_text_only,
        segments_extraction_incomplete=segments_extraction_incomplete,
    )
    apply_validation(report, SECURITIES_BOUNDS, SECURITIES_IDENTITIES,
                     provenance=provenance)
    return report
