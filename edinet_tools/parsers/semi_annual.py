"""
Parser for Semi-Annual Reports (Doc Type 160).

Extracts financial data from 半期報告書 filings.
Supports both corporate and fund reports with IFRS fallback.
"""
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from .base import ParsedReport
from .extraction import (
    Tier,
    resolve_tiers,
    get_dei,
    extract_csv_from_zip,
    categorize_elements,
    parse_date,
)


# XBRL Element ID mappings for Doc 160 (Semi-Annual Reports)
ELEMENT_MAP = {
    # === DEI Elements (Identification) ===
    'edinet_code': 'jpdei_cor:EDINETCodeDEI',
    'fund_code': 'jpdei_cor:FundCodeDEI',
    'filer_name': 'jpdei_cor:FilerNameInJapaneseDEI',
    'fund_name': 'jpdei_cor:FundNameInJapaneseDEI',
    'period_start': 'jpdei_cor:CurrentFiscalYearStartDateDEI',
    'period_end': 'jpdei_cor:CurrentPeriodEndDateDEI',
    'submission_date': 'jpdei_cor:DateOfSubmissionDEI',

    # === Balance Sheet Elements ===
    'assets': 'jppfs_cor:Assets',
    'current_assets': 'jppfs_cor:CurrentAssets',
    'liabilities': 'jppfs_cor:Liabilities',
    'current_liabilities': 'jppfs_cor:CurrentLiabilities',
    'net_assets': 'jppfs_cor:NetAssets',

    # === Income Statement ===
    'operating_income': 'jppfs_cor:OperatingIncome',
    'ordinary_income': 'jppfs_cor:OrdinaryIncome',
    'profit_loss': 'jppfs_cor:ProfitLoss',
}

# IFRS fallback elements
IFRS_FALLBACK_MAP = {
    'jppfs_cor:Assets': 'jpigp_cor:AssetsIFRS',
    'jppfs_cor:CurrentAssets': 'jpigp_cor:CurrentAssetsIFRS',
    'jppfs_cor:Liabilities': 'jpigp_cor:LiabilitiesIFRS',
    'jppfs_cor:CurrentLiabilities': 'jpigp_cor:CurrentLiabilitiesIFRS',
    'jppfs_cor:NetAssets': 'jpigp_cor:EquityIFRS',
    'jppfs_cor:OperatingIncome': 'jpigp_cor:OperatingProfitLossIFRS',
    'jppfs_cor:OrdinaryIncome': 'jpigp_cor:ProfitLossBeforeTaxIFRS',
    'jppfs_cor:ProfitLoss': 'jpigp_cor:ProfitLossIFRS',
}


@dataclass
class SemiAnnualReport(ParsedReport):
    """Parsed Semi-Annual Report (Doc 160)."""

    # Identification
    filer_name: str | None = None
    filer_edinet_code: str | None = None
    fund_code: str | None = None
    fund_name: str | None = None

    # Period
    period_start: date | None = None
    period_end: date | None = None
    filing_date: date | None = None

    # Balance Sheet
    total_assets: int | None = None
    current_assets: int | None = None
    total_liabilities: int | None = None
    current_liabilities: int | None = None
    net_assets: int | None = None

    # Income Statement
    operating_income: int | None = None
    ordinary_income: int | None = None
    profit_loss: int | None = None

    @property
    def filer(self):
        """Resolve filer to Entity via the FSA registry.

        The Entity exposes `entity_type` (an `EntityType` enum: FUND,
        LISTED_COMPANY, UNLISTED_COMPANY, INDIVIDUAL, UNKNOWN), which is
        the authoritative answer to "is this filer a fund or corporation?"
        Use `report.filer.entity_type == EntityType.FUND` instead of any
        XBRL-derived inference — the FSA registry is the source of truth.

        Returns None when filer_edinet_code is not set, or when the entity
        is not in the registry (honest unknown).
        """
        if self.filer_edinet_code:
            from edinet_tools.entity import entity_by_edinet_code
            return entity_by_edinet_code(self.filer_edinet_code)
        return None

    def __repr__(self) -> str:
        filer = self.filer_name or self.fund_name or 'Unknown'
        if len(filer) > 25:
            filer = filer[:22] + '...'
        period = self.period_end.strftime('%Y-%m') if self.period_end else '?'
        return f"SemiAnnualReport(filer='{filer}', period_end={period})"


def _chain(key: str):
    """ELEMENT_MAP[key] plus its IFRS_FALLBACK_MAP fallback as ONE tier's
    element chain."""
    element_id = ELEMENT_MAP[key]
    fallback = IFRS_FALLBACK_MAP.get(element_id)
    if not fallback:
        return element_id
    return (element_id, fallback)


# Per-field tier tables (v0.8.0 stage-5 migration) — STRUCTURAL migration
# only. These resolve with period=None: context-BLIND, first match in file
# order, exactly the legacy behavior. That blindness is a known defect
# (a Prior2 or parent-context row earlier in the file wins over the
# current period); the ratified semi-annual context fix will replace
# period=None with real period/consolidation discipline as its own
# separately-predicted change — do NOT "fix" it in passing here.
_FIELD_TIERS = {
    'total_assets': (Tier(_chain('assets')),),
    'current_assets': (Tier(_chain('current_assets')),),
    'total_liabilities': (Tier(_chain('liabilities')),),
    'current_liabilities': (Tier(_chain('current_liabilities')),),
    'net_assets': (Tier(_chain('net_assets')),),
    'operating_income': (Tier(_chain('operating_income')),),
    'ordinary_income': (Tier(_chain('ordinary_income')),),
    'profit_loss': (Tier(_chain('profit_loss')),),
}


def _extract_financial(csv_files: list, element_id: str) -> Optional[int]:
    """Legacy-shaped helper (kept for tests/back-compat): one primary
    element with its IFRS fallback, resolved context-blind through the
    tier core — identical semantics to the pre-tier implementation,
    including the null-marker normalization that lets the IFRS fallback
    fire when the primary carries '－'."""
    fallback = IFRS_FALLBACK_MAP.get(element_id)
    chain = (element_id, fallback) if fallback else element_id
    hit = resolve_tiers(csv_files, (Tier(chain),), standard=None,
                        period=None, is_consolidated=None)
    return hit.value if hit else None


def parse_semi_annual_report(document=None, *, csv_files=None, doc_id=None, doc_type_code=None) -> SemiAnnualReport:
    """
    Parse a Semi-Annual Report document.

    Args:
        document: Document object with fetch() method (optional if csv_files provided)
        csv_files: Pre-extracted CSV data (list of dicts with 'filename' and 'data' keys)
        doc_id: Document ID (required if csv_files provided)
        doc_type_code: Document type code (required if csv_files provided)

    Returns:
        SemiAnnualReport with extracted fields
    """
    if csv_files is None:
        zip_bytes = document.fetch()
        csv_files = extract_csv_from_zip(zip_bytes)
        doc_id = document.doc_id
        doc_type_code = document.doc_type_code

    if not csv_files:
        return SemiAnnualReport(
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
    filer_name = get_dei(csv_files, ELEMENT_MAP, 'filer_name')
    fund_code = get_dei(csv_files, ELEMENT_MAP, 'fund_code')
    fund_name = get_dei(csv_files, ELEMENT_MAP, 'fund_name')

    # Extract period
    period_start = parse_date(get_dei(csv_files, ELEMENT_MAP, 'period_start'))
    period_end = parse_date(get_dei(csv_files, ELEMENT_MAP, 'period_end'))
    filing_date = parse_date(get_dei(csv_files, ELEMENT_MAP, 'submission_date')) or period_end

    # Financial data from the tier tables — context-blind compatibility
    # path (period=None); see the _FIELD_TIERS comment.
    def fin(name):
        hit = resolve_tiers(csv_files, _FIELD_TIERS[name], standard=None,
                            period=None, is_consolidated=None)
        return hit.value if hit else None

    total_assets = fin('total_assets')
    current_assets = fin('current_assets')
    total_liabilities = fin('total_liabilities')
    current_liabilities = fin('current_liabilities')
    net_assets = fin('net_assets')
    operating_income = fin('operating_income')
    ordinary_income = fin('ordinary_income')
    profit_loss = fin('profit_loss')

    # Categorize all elements
    raw_fields, text_blocks, unmapped_fields, raw_facts = categorize_elements(csv_files, ELEMENT_MAP)

    return SemiAnnualReport(
        doc_id=doc_id,
        doc_type_code=doc_type_code,
        source_files=source_files,
        raw_fields=raw_fields,
        unmapped_fields=unmapped_fields,
        text_blocks=text_blocks,
        raw_facts=raw_facts,

        # Identification
        filer_name=filer_name or getattr(document, 'filer_name', None),
        filer_edinet_code=edinet_code or getattr(document, 'filer_edinet_code', None),
        fund_code=fund_code,
        fund_name=fund_name,

        # Period
        period_start=period_start,
        period_end=period_end,
        filing_date=filing_date,

        # Balance Sheet
        total_assets=total_assets,
        current_assets=current_assets,
        total_liabilities=total_liabilities,
        current_liabilities=current_liabilities,
        net_assets=net_assets,

        # Income Statement
        operating_income=operating_income,
        ordinary_income=ordinary_income,
        profit_loss=profit_loss,
    )
