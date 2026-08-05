"""
Parser for Quarterly Reports (Doc Type 140).

Extracts quarterly financial data from 四半期報告書 filings.

IMPORTANT: Income statement data is year-to-date cumulative, not quarterly-only.
- Q1 report: First 3 months of fiscal year
- Q2 report: First 6 months (cumulative)
- Q3 report: First 9 months (cumulative)
"""
from dataclasses import dataclass
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
    get_context_patterns,
    parse_percentage,
    parse_date,
    coerce_numeric_value,
)


# XBRL Element ID mappings for Doc 140 (Quarterly Reports)
ELEMENT_MAP = {
    # === DEI Elements (Identification) ===
    'edinet_code': 'jpdei_cor:EDINETCodeDEI',
    'security_code': 'jpdei_cor:SecurityCodeDEI',
    'company_name': 'jpdei_cor:FilerNameInJapaneseDEI',
    'fiscal_year_end': 'jpdei_cor:CurrentFiscalYearEndDateDEI',
    'filing_date': 'jpcrp_cor:FilingDateCoverPage',
    'is_consolidated': 'jpdei_cor:WhetherConsolidatedFinancialStatementsArePreparedDEI',

    # === Income Statement Elements (YTD Cumulative) ===
    'net_sales': 'jppfs_cor:NetSales',
    'operating_income': 'jppfs_cor:OperatingIncome',
    'ordinary_income': 'jppfs_cor:OrdinaryIncome',
    'net_income': 'jppfs_cor:ProfitLossAttributableToOwnersOfParent',

    # === Balance Sheet Elements (Point-in-Time) ===
    'total_assets': 'jppfs_cor:Assets',
    'net_assets': 'jppfs_cor:NetAssets',
    'total_liabilities': 'jppfs_cor:Liabilities',

    # === Cash Flow Elements (YTD Cumulative) ===
    'operating_cf': 'jpcrp_cor:NetCashProvidedByUsedInOperatingActivitiesSummaryOfBusinessResults',
    'investing_cf': 'jpcrp_cor:NetCashProvidedByUsedInInvestingActivitiesSummaryOfBusinessResults',
    'financing_cf': 'jpcrp_cor:NetCashProvidedByUsedInFinancingActivitiesSummaryOfBusinessResults',

    # === Per Share Metrics ===
    'eps_basic': 'jpcrp_cor:BasicEarningsLossPerShareSummaryOfBusinessResults',

    # === Key Ratios ===
    'equity_ratio': 'jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResults',
}

# IFRS fallback elements
IFRS_FALLBACK_MAP = {
    'jppfs_cor:NetSales': 'jpigp_cor:RevenueIFRS',
    'jppfs_cor:OperatingIncome': 'jpigp_cor:OperatingProfitLossIFRS',
    'jppfs_cor:ProfitLossAttributableToOwnersOfParent': 'jpigp_cor:ProfitLossAttributableToOwnersOfParentIFRS',
    'jppfs_cor:Assets': 'jpigp_cor:AssetsIFRS',
    'jppfs_cor:NetAssets': 'jpigp_cor:EquityIFRS',
    'jppfs_cor:Liabilities': 'jpigp_cor:LiabilitiesIFRS',
}


def _chain(key: str):
    """ELEMENT_MAP[key] plus its IFRS_FALLBACK_MAP fallback as ONE tier's
    element chain (extract_financial's primary-plus-fallback, declarative)."""
    element_id = ELEMENT_MAP[key]
    fallback = IFRS_FALLBACK_MAP.get(element_id)
    if not fallback:
        return element_id
    return (element_id, fallback)


# Per-field tier tables (v0.8.0 stage-5 migration). Single-tier waterfalls:
# each field is one primary element with at most one IFRS fallback, exactly
# the pre-migration extract_financial calls. Deliberately NO per-standard
# gate here — the quarterly gate (and the 0.7.1-class leak it would close)
# is a deferred, separately-predicted change, not migration drift.
# Income-statement + cash-flow tables serve both the CurrentYTDDuration and
# Prior1YTDDuration reads; balance-sheet tables read CurrentQuarterInstant.
_YTD_TIERS = {
    'revenue_ytd': (Tier(_chain('net_sales')),),
    'operating_profit_ytd': (Tier(_chain('operating_income')),),
    'ordinary_profit_ytd': (Tier(_chain('ordinary_income')),),
    'net_income_ytd': (Tier(_chain('net_income')),),
}
_CF_TIERS = {
    'operating_cash_flow_ytd': (Tier(_chain('operating_cf')),),
    'investing_cash_flow_ytd': (Tier(_chain('investing_cf')),),
    'financing_cash_flow_ytd': (Tier(_chain('financing_cf')),),
}
_INSTANT_TIERS = {
    'total_assets': (Tier(_chain('total_assets')),),
    'net_assets': (Tier(_chain('net_assets')),),
    'total_liabilities': (Tier(_chain('total_liabilities')),),
}


@dataclass
class QuarterlyReport(ParsedReport):
    """Parsed Quarterly Report (Doc 140)."""

    # Identification
    filer_name: str | None = None
    filer_edinet_code: str | None = None
    ticker: str | None = None
    is_consolidated: bool | None = None

    # Period
    fiscal_year_end: date | None = None
    quarter_number: int | None = None  # 1, 2, or 3
    filing_date: date | None = None

    # Income Statement (Current YTD)
    revenue_ytd: int | None = None
    operating_profit_ytd: int | None = None
    ordinary_profit_ytd: int | None = None
    net_income_ytd: int | None = None

    # Income Statement (Prior Year YTD)
    prior_revenue_ytd: int | None = None
    prior_operating_profit_ytd: int | None = None
    prior_ordinary_profit_ytd: int | None = None
    prior_net_income_ytd: int | None = None

    # Balance Sheet
    total_assets: int | None = None
    net_assets: int | None = None
    total_liabilities: int | None = None

    # Cash Flow
    operating_cash_flow_ytd: int | None = None
    investing_cash_flow_ytd: int | None = None
    financing_cash_flow_ytd: int | None = None

    # Per-Share
    eps_basic_ytd: Decimal | None = None

    # Ratios
    equity_ratio: Decimal | None = None

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
        q = f"Q{self.quarter_number}" if self.quarter_number else 'Q?'
        fy = self.fiscal_year_end.year if self.fiscal_year_end else '?'
        return f"QuarterlyReport(filer='{filer}', {q} FY{fy})"


def _derive_quarter_number(filing_date: date, fiscal_year_end: date) -> Optional[int]:
    """
    Derive quarter number (1, 2, or 3) from filing date and fiscal year end.

    Japanese companies typically file quarterly reports 45 days after quarter end.
    For a March fiscal year end (common in Japan):
        - Q1 (Apr-Jun): Filed Jul-Aug, 3-5 months from FY start
        - Q2 (Jul-Sep): Filed Oct-Nov, 6-8 months from FY start
        - Q3 (Oct-Dec): Filed Jan-Feb, 9-11 months from FY start

    Returns None if filing date doesn't match expected quarterly timing
    (e.g., annual reports filed after fiscal year end).
    """
    from dateutil.relativedelta import relativedelta

    # Calculate fiscal year start (day after prior year end)
    fiscal_year_start = fiscal_year_end - relativedelta(years=1) + relativedelta(days=1)

    # Calculate months from fiscal year start to filing date
    months_from_start = (filing_date.year - fiscal_year_start.year) * 12 + \
                       (filing_date.month - fiscal_year_start.month)

    # Map to quarter (filing typically happens 1-2 months after quarter end)
    if 3 <= months_from_start <= 5:
        return 1
    elif 6 <= months_from_start <= 8:
        return 2
    elif 9 <= months_from_start <= 11:
        return 3
    else:
        return None


def parse_quarterly_report(document=None, *, csv_files=None, doc_id=None, doc_type_code=None) -> QuarterlyReport:
    """
    Parse a Quarterly Report document.

    Args:
        document: Document object with fetch() method (optional if csv_files provided)
        csv_files: Pre-extracted CSV data (list of dicts with 'filename' and 'data' keys)
        doc_id: Document ID (required if csv_files provided)
        doc_type_code: Document type code (required if csv_files provided)

    Returns:
        QuarterlyReport with extracted fields
    """
    if csv_files is None:
        zip_bytes = document.fetch()
        csv_files = extract_csv_from_zip(zip_bytes)
        doc_id = document.doc_id
        doc_type_code = document.doc_type_code

    if not csv_files:
        return QuarterlyReport(
            doc_id=doc_id,
            doc_type_code=doc_type_code,
            source_files=[],
            raw_fields={},
            unmapped_fields={},
            text_blocks={},
        )

    source_files = [f['filename'] for f in csv_files]

    # Extract DEI elements
    edinet_code = get_dei(csv_files, ELEMENT_MAP, 'edinet_code')
    company_name = get_dei(csv_files, ELEMENT_MAP, 'company_name')
    security_code = get_dei(csv_files, ELEMENT_MAP, 'security_code')
    is_consolidated_raw = get_dei(csv_files, ELEMENT_MAP, 'is_consolidated')
    is_consolidated = (is_consolidated_raw == 'true') if is_consolidated_raw else None

    # Format ticker
    ticker = None
    if security_code and security_code != '－':
        ticker = f"{security_code.strip()[:4]}.T"

    # Extract period
    fiscal_year_end = parse_date(get_dei(csv_files, ELEMENT_MAP, 'fiscal_year_end'))
    filing_date_str = extract_value(csv_files, ELEMENT_MAP['filing_date'])
    filing_date = parse_date(filing_date_str)

    # Derive quarter number
    quarter_number = None
    if filing_date and fiscal_year_end:
        quarter_number = _derive_quarter_number(filing_date, fiscal_year_end)

    # Financials from the tier tables. Standard is intentionally None-ish
    # here: quarterly tiers carry no standards scoping (no gate — see the
    # table comment), so nothing consults it.
    def fin(tiers, period):
        hit = resolve_tiers(csv_files, tiers, standard=None, period=period,
                            is_consolidated=is_consolidated)
        return hit.value if hit else None

    fields = {}
    for name, tiers in _YTD_TIERS.items():
        fields[name] = fin(tiers, 'CurrentYTDDuration')
        fields[f'prior_{name}'] = fin(tiers, 'Prior1YTDDuration')
    for name, tiers in _CF_TIERS.items():
        fields[name] = fin(tiers, 'CurrentYTDDuration')
    for name, tiers in _INSTANT_TIERS.items():
        fields[name] = fin(tiers, 'CurrentQuarterInstant')

    # Per-share metrics. coerce_numeric_value nulls the full dash-family
    # marker set (incl. '―'/'—' — the local tuple this replaced); the
    # guarded Decimal keeps the legacy silent-None on non-numeric strings.
    patterns = get_context_patterns(is_consolidated, 'CurrentYTDDuration')
    eps_str = coerce_numeric_value(extract_value(
        csv_files, ELEMENT_MAP['eps_basic'], context_patterns=patterns))
    eps_basic = None
    if eps_str:
        try:
            eps_basic = Decimal(eps_str)
        except ArithmeticError:
            eps_basic = None

    # Ratios
    patterns = get_context_patterns(is_consolidated, 'CurrentQuarterInstant')
    equity_str = extract_value(csv_files, ELEMENT_MAP['equity_ratio'], context_patterns=patterns)
    equity_ratio = parse_percentage(equity_str)

    # Categorize all elements
    raw_fields, text_blocks, unmapped_fields, raw_facts = categorize_elements(csv_files, ELEMENT_MAP)

    return QuarterlyReport(
        doc_id=doc_id,
        doc_type_code=doc_type_code,
        source_files=source_files,
        raw_fields=raw_fields,
        unmapped_fields=unmapped_fields,
        text_blocks=text_blocks,
        raw_facts=raw_facts,

        # Identification
        filer_name=company_name or getattr(document, 'filer_name', None),
        filer_edinet_code=edinet_code or getattr(document, 'filer_edinet_code', None),
        ticker=ticker,
        is_consolidated=is_consolidated,

        # Period
        fiscal_year_end=fiscal_year_end,
        quarter_number=quarter_number,
        filing_date=filing_date,

        # Financials (tier tables): income statement current + prior YTD,
        # balance sheet, cash flow
        **fields,

        # Per-Share
        eps_basic_ytd=eps_basic,

        # Ratios
        equity_ratio=equity_ratio,
    )
