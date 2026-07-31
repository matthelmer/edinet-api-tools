"""
Parser for Treasury Stock Purchase Status Reports (Doc Type 220/230).

Extracts buyback activity details from 自己株券買付状況報告書 filings.
Companies file these to report on treasury stock acquisition programs,
including share counts, authorization details, and disposal/holding status.

Doc 220: Original report
Doc 230: Amendment to treasury stock report
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from .base import ParsedReport
from .extraction import (
    extract_csv_from_zip,
    extract_value,
    categorize_elements,
    parse_date,
    parse_int,
    parse_percentage,
)


# XBRL Element ID mappings for Doc 220/230
# Namespace: jpcrp-sbr_cor (Japanese Corporate Reporting - Standard Business Report)
ELEMENT_MAP = {
    # === DEI Elements ===
    'edinet_code': 'jpdei_cor:EDINETCodeDEI',
    'filer_name': 'jpdei_cor:FilerNameInJapaneseDEI',
    'filer_name_en': 'jpdei_cor:FilerNameInEnglishDEI',
    'security_code': 'jpdei_cor:SecurityCodeDEI',
    'amendment_flag': 'jpdei_cor:AmendmentFlagDEI',

    # === Cover Page ===
    'document_title': 'jpcrp-sbr_cor:DocumentTitleCoverPage',
    'filing_date': 'jpcrp-sbr_cor:FilingDateCoverPage',
    'company_name': 'jpcrp-sbr_cor:CompanyNameCoverPage',
    'company_name_en': 'jpcrp-sbr_cor:CompanyNameInEnglishCoverPage',
    'company_address': 'jpcrp-sbr_cor:AddressOfRegisteredHeadquarterCoverPage',
    'representative_name': 'jpcrp-sbr_cor:TitleAndNameOfRepresentativeCoverPage',
    'reporting_period': 'jpcrp-sbr_cor:ReportingPeriodCoverPage',

    # === Treasury Stock Content ===
    'classes_of_shares': 'jpcrp-sbr_cor:ClassesOfSharesTextBlock',
    'by_shareholders_meeting': 'jpcrp-sbr_cor:AcquisitionsByResolutionOfShareholdersMeetingTextBlock',
    'by_board_meeting': 'jpcrp-sbr_cor:AcquisitionsByResolutionOfBoardOfDirectorsMeetingTextBlock',

    # === Disposal / Holding ===
    'disposals_text': 'jpcrp-sbr_cor:DisposalsOfTreasurySharesTextBlock',
    'holding_text': 'jpcrp-sbr_cor:HoldingOfTreasurySharesTextBlock',
}


@dataclass
class TreasuryStockReport(ParsedReport):
    """
    Parsed Treasury Stock Purchase Status Report (Doc 220/230).

    These reports disclose company share buyback activity including
    acquisition authorizations, shares acquired, and treasury holdings.

    Key fields:
        filer_name: Company filing the report
        filing_date: Date of filing
        is_amendment: Whether this is an amendment (Doc 230)
        by_shareholders_meeting: Buyback authorization from shareholders meeting (Japanese text)
        by_board_meeting: Buyback authorization from board meeting (Japanese text)
        disposal_holding_text: Status of treasury stock disposal/holding (Japanese text)
        reporting_period: The period this report covers

    Note: Share counts and ratios are typically found in text_blocks or
    unmapped_fields as they are embedded in TextBlock elements rather
    than structured XBRL numeric fields.
    """

    # Identification
    filer_name: str | None = None
    filer_name_en: str | None = None
    filer_edinet_code: str | None = None
    ticker: str | None = None

    # Cover page
    document_title: str | None = None
    filing_date: date | None = None
    representative: str | None = None
    address: str | None = None
    reporting_period: str | None = None

    # Amendment
    is_amendment: bool = False

    # Authorization content (Japanese text)
    by_shareholders_meeting: str | None = None
    by_board_meeting: str | None = None

    # Disposal / holding status (Japanese text)
    disposal_holding_text: str | None = None

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
        amend = ' [AMENDED]' if self.is_amendment else ''
        return f"TreasuryStockReport(filer='{filer}'{amend})"


def parse_treasury_stock_report(document=None, *, csv_files=None, doc_id=None, doc_type_code=None) -> TreasuryStockReport:
    """
    Parse a Treasury Stock Purchase Status Report.

    Args:
        document: Document object with fetch() method (optional if csv_files provided)
        csv_files: Pre-extracted CSV data (list of dicts with 'filename' and 'data' keys)
        doc_id: Document ID (required if csv_files provided)
        doc_type_code: Document type code (required if csv_files provided)

    Returns:
        TreasuryStockReport with extracted fields
    """
    if csv_files is None:
        zip_bytes = document.fetch()
        csv_files = extract_csv_from_zip(zip_bytes)
        doc_id = document.doc_id
        doc_type_code = document.doc_type_code

    if not csv_files:
        return TreasuryStockReport(
            doc_id=doc_id,
            doc_type_code=doc_type_code,
            source_files=[],
            raw_fields={},
            unmapped_fields={},
            text_blocks={},
        )

    source_files = [f['filename'] for f in csv_files]

    # Helper to get value
    def get(key: str, context: list[str] | None = None) -> str | None:
        return extract_value(csv_files, ELEMENT_MAP.get(key, ''), context_patterns=context)

    # Extract DEI elements with context filtering
    edinet_code = get('edinet_code', ['FilingDateInstant'])
    filer_name = get('filer_name', ['FilingDateInstant'])
    filer_name_en = get('filer_name_en', ['FilingDateInstant'])
    security_code = get('security_code', ['FilingDateInstant'])
    amendment_flag = get('amendment_flag', ['FilingDateInstant'])

    # Fallback filer name from cover page
    if not filer_name:
        filer_name = get('company_name')
    if not filer_name_en:
        filer_name_en = get('company_name_en')

    # Format ticker
    ticker = None
    if security_code and security_code != '－':
        ticker = f"{security_code.strip()[:4]}.T"

    # Filing date
    filing_date = parse_date(get('filing_date'))

    # Cover page details
    document_title = get('document_title') or '自己株券買付状況報告書'
    representative = get('representative_name')
    address = get('company_address')
    reporting_period = get('reporting_period')

    # Amendment flag
    is_amendment = amendment_flag == 'true' if amendment_flag else False

    # Authorization text blocks
    by_shareholders_meeting = get('by_shareholders_meeting')
    by_board_meeting = get('by_board_meeting')

    # Disposal/holding - combine two text blocks
    disposals_text = get('disposals_text')
    holding_text = get('holding_text')
    disposal_holding_text = '\n'.join(filter(None, [disposals_text, holding_text])) or None

    # Categorize all elements
    raw_fields, text_blocks, unmapped_fields, raw_facts = categorize_elements(csv_files, ELEMENT_MAP)

    return TreasuryStockReport(
        doc_id=doc_id,
        doc_type_code=doc_type_code,
        source_files=source_files,
        raw_fields=raw_fields,
        unmapped_fields=unmapped_fields,
        text_blocks=text_blocks,
        raw_facts=raw_facts,

        # Identification
        filer_name=filer_name or getattr(document, 'filer_name', None),
        filer_name_en=filer_name_en,
        filer_edinet_code=edinet_code or getattr(document, 'filer_edinet_code', None),
        ticker=ticker,

        # Cover page
        document_title=document_title,
        filing_date=filing_date,
        representative=representative,
        address=address,
        reporting_period=reporting_period,

        # Amendment
        is_amendment=is_amendment,

        # Content
        by_shareholders_meeting=by_shareholders_meeting,
        by_board_meeting=by_board_meeting,
        disposal_holding_text=disposal_holding_text,
    )
