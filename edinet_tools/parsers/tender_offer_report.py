"""
Parser for Tender Offer Report filings (Doc Type 270/280).

Extracts completion report data from 公開買付報告書 filings.
These are filed by the acquirer after a tender offer closes, reporting
the actual results — shares purchased, final ownership ratios, etc.

Doc 270: Original tender offer report
Doc 280: Amendment to tender offer report
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
    strip_form_label,
)


# XBRL Element ID mappings for Doc 270/280
# Namespace: jptoo-tor_cor (Japanese Public Tender Offer Report)
ELEMENT_MAP = {
    # === DEI Elements ===
    'filer_name': 'jpdei_cor:FilerNameInJapaneseDEI',
    'filer_name_en': 'jpdei_cor:FilerNameInEnglishDEI',
    'filer_edinet_code': 'jpdei_cor:EDINETCodeDEI',
    'security_code': 'jpdei_cor:SecurityCodeDEI',
    'amendment_flag': 'jpdei_cor:AmendmentFlagDEI',

    # === Cover Page ===
    'document_title': 'jptoo-tor_cor:DocumentTitleCoverPage',
    'filing_date': 'jptoo-tor_cor:FilingDateCoverPage',
    'acquirer_name': 'jptoo-tor_cor:FullNameOrNameOfFilerCoverPage',
    'acquirer_address': 'jptoo-tor_cor:ResidentialAddressOrLocationOfFilerCoverPage',
    'contact_phone': 'jptoo-tor_cor:TelephoneNumberCoverPage',
    'contact_name': 'jptoo-tor_cor:NameOfContactPersonCoverPage',

    # === Ownership / Voting Rights (post-purchase results) ===
    'voting_rights_purchased': 'jptoo-tor_cor:NumberOfVotingRightsRepresentedByShareCertificatesEtcAcquiredByPurchaseEtcTextBlock',
    'voting_rights_owned_by_offeror': 'jptoo-tor_cor:NumberOfVotingRightsRepresentedByShareCertificatesEtcOwnedByTenderOfferorAsOfFilingDateA',
    'voting_rights_special_interest': 'jptoo-tor_cor:NumberNumberOfVotingRightsRepresentedByShareCertificatesEtcOwnedBySpecialInterestPartiesG',
    'total_voting_rights': 'jptoo-tor_cor:NumberNumberOfVotingRightsOwnedByAllShareholdersEtcOfSubjectCompanyJ',
    'purchase_ratio': 'jptoo-tor_cor:RatioOfNumberOfVotingRightsRepresentedByShareCertificatesEtcPurchasedAmongNumberOfVotingRightsOwnedByAllShareholdersEtcOfSubjectCompany',
    'holding_ratio_after': 'jptoo-tor_cor:HoldingRatioOfShareCertificatesEtcAfterPurchaseEtc',

    # === Key TextBlock Elements ===
    'target_name': 'jptoo-tor_cor:NameOfSubjectCompanyTextBlock',
    'share_classes_text': 'jptoo-tor_cor:ClassesOfShareCertificatesEtcRelatedToPurchaseEtcTextBlock',
    'shares_acquired_text': 'jptoo-tor_cor:NumberOfShareCertificatesEtcAcquiredByPurchaseEtcTextBlock',
    'result_text': 'jptoo-tor_cor:SuccessOrFailureOfTenderOfferTextBlock',
    'period_text': 'jptoo-tor_cor:TenderOfferPeriodTextBlock',
    'announcement_text': 'jptoo-tor_cor:DateOfOfficialAnnouncementOfTenderOfferAndNameOfNewspaperContainingItTextBlock',
    'settlement_date_text': 'jptoo-tor_cor:DateOfCommencementOfSettlementTextBlock',
}


@dataclass
class TenderOfferResultReport(ParsedReport):
    """
    Parsed Tender Offer Report (Doc 270/280).

    These filings report the outcome of a completed tender offer (TOB /
    公開買付). The acquirer discloses how many shares were purchased, the
    actual ownership ratio achieved, and settlement details.

    Key fields:
        acquirer_name: Name of the entity that made the tender offer
        target_name: Name of the target company
        filing_date: Date the report was filed
        voting_rights_purchased: Voting rights represented by shares purchased
        purchase_ratio: Actual ratio of voting rights purchased to total
        holding_ratio_after: Final ownership ratio after purchase
        is_amendment: Whether this is an amendment (Doc 280)
        result_text: Narrative description of the tender offer result
    """

    # Acquirer identification
    acquirer_name: str | None = None
    acquirer_name_en: str | None = None
    acquirer_edinet_code: str | None = None
    acquirer_address: str | None = None

    # Cover page
    filing_date: date | None = None
    contact_name: str | None = None
    contact_phone: str | None = None

    # Target
    target_name: str | None = None

    # Ownership / voting rights (actual results)
    voting_rights_purchased: int | None = None
    voting_rights_owned_by_offeror: int | None = None
    voting_rights_special_interest: int | None = None
    total_voting_rights: int | None = None
    purchase_ratio: Decimal | None = None
    holding_ratio_after: Decimal | None = None

    # Amendment
    is_amendment: bool = False

    # Key text blocks (Japanese text)
    share_classes_text: str | None = None
    shares_acquired_text: str | None = None
    result_text: str | None = None
    period_text: str | None = None
    announcement_text: str | None = None
    settlement_date_text: str | None = None

    def __repr__(self) -> str:
        name = self.acquirer_name or 'Unknown'
        if len(name) > 25:
            name = name[:22] + '...'
        target = self.target_name or '?'
        if len(target) > 25:
            target = target[:22] + '...'
        amend = ' [AMENDED]' if self.is_amendment else ''
        return f"TenderOfferResultReport(acquirer='{name}', target='{target}'{amend})"


def parse_tender_offer_report(document=None, *, csv_files=None, doc_id=None, doc_type_code=None) -> TenderOfferResultReport:
    """
    Parse a Tender Offer Report filing (Doc 270/280).

    Args:
        document: Document object with fetch() method (optional if csv_files provided)
        csv_files: Pre-extracted CSV data (list of dicts with 'filename' and 'data' keys)
        doc_id: Document ID (required if csv_files provided)
        doc_type_code: Document type code (required if csv_files provided)

    Returns:
        TenderOfferResultReport with extracted fields
    """
    if csv_files is None:
        zip_bytes = document.fetch()
        csv_files = extract_csv_from_zip(zip_bytes)
        doc_id = document.doc_id
        doc_type_code = document.doc_type_code

    if not csv_files:
        return TenderOfferResultReport(
            doc_id=doc_id,
            doc_type_code=doc_type_code,
            source_files=[],
            raw_fields={},
            unmapped_fields={},
            text_blocks={},
        )

    source_files = [f['filename'] for f in csv_files]

    def get(key: str, context: list[str] | None = None) -> str | None:
        return extract_value(csv_files, ELEMENT_MAP.get(key, ''), context_patterns=context)

    # DEI elements
    filer_edinet_code = get('filer_edinet_code', ['FilingDateInstant'])
    filer_name = get('filer_name', ['FilingDateInstant'])
    filer_name_en = get('filer_name_en', ['FilingDateInstant'])
    security_code = get('security_code', ['FilingDateInstant'])
    amendment_flag = get('amendment_flag', ['FilingDateInstant'])

    # Acquirer name from cover page (preferred) or DEI fallback
    acquirer_name = get('acquirer_name') or filer_name
    acquirer_address = get('acquirer_address')
    filing_date = parse_date(get('filing_date'))
    contact_name = get('contact_name')
    contact_phone = get('contact_phone')
    is_amendment = amendment_flag == 'true' if amendment_flag else False

    # Target and results
    target_name = strip_form_label(get('target_name'))
    share_classes_text = get('share_classes_text')
    shares_acquired_text = get('shares_acquired_text')
    voting_rights_purchased = parse_int(get('voting_rights_purchased'))
    voting_rights_owned_by_offeror = parse_int(get('voting_rights_owned_by_offeror'))
    voting_rights_special_interest = parse_int(get('voting_rights_special_interest'))
    total_voting_rights = parse_int(get('total_voting_rights'))
    purchase_ratio = parse_percentage(get('purchase_ratio'))
    holding_ratio_after = parse_percentage(get('holding_ratio_after'))
    result_text = get('result_text')
    period_text = get('period_text')
    announcement_text = get('announcement_text')
    settlement_date_text = get('settlement_date_text')

    raw_fields, text_blocks, unmapped_fields, raw_facts = categorize_elements(csv_files, ELEMENT_MAP)

    return TenderOfferResultReport(
        doc_id=doc_id,
        doc_type_code=doc_type_code,
        source_files=source_files,
        raw_fields=raw_fields,
        unmapped_fields=unmapped_fields,
        text_blocks=text_blocks,
        raw_facts=raw_facts,

        acquirer_name=acquirer_name or getattr(document, 'filer_name', None),
        acquirer_name_en=filer_name_en,
        acquirer_edinet_code=filer_edinet_code or getattr(document, 'filer_edinet_code', None),
        acquirer_address=acquirer_address,

        filing_date=filing_date,
        contact_name=contact_name,
        contact_phone=contact_phone,

        target_name=target_name,

        share_classes_text=share_classes_text,
        shares_acquired_text=shares_acquired_text,
        voting_rights_purchased=voting_rights_purchased,
        voting_rights_owned_by_offeror=voting_rights_owned_by_offeror,
        voting_rights_special_interest=voting_rights_special_interest,
        total_voting_rights=total_voting_rights,
        purchase_ratio=purchase_ratio,
        holding_ratio_after=holding_ratio_after,

        is_amendment=is_amendment,

        result_text=result_text,
        period_text=period_text,
        announcement_text=announcement_text,
        settlement_date_text=settlement_date_text,
    )
