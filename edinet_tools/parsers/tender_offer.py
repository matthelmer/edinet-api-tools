"""
Parser for Tender Offer Registration filings (Doc Type 240/250).

Extracts tender offer (TOB) details from 公開買付届出書 filings.
These are filed when an acquirer launches a public tender offer for
shares of a target company. Key data includes offer price, ownership
ratios, voting rights, and offer terms.

Doc 240: Original tender offer registration
Doc 250: Amendment to tender offer registration
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


# XBRL Element ID mappings for Doc 240/250
# Namespace: jptoo-ton_cor (Japanese Public Tender Offer)
ELEMENT_MAP = {
    # === DEI Elements ===
    'edinet_code': 'jpdei_cor:EDINETCodeDEI',
    'filer_name': 'jpdei_cor:FilerNameInJapaneseDEI',
    'filer_name_en': 'jpdei_cor:FilerNameInEnglishDEI',
    'security_code': 'jpdei_cor:SecurityCodeDEI',
    'amendment_flag': 'jpdei_cor:AmendmentFlagDEI',

    # === Cover Page (structured) ===
    'document_title': 'jptoo-ton_cor:DocumentTitleCoverPage',
    'place_of_filing': 'jptoo-ton_cor:PlaceOfFilingCoverPage',
    'filing_date': 'jptoo-ton_cor:FilingDateCoverPage',
    'acquirer_name': 'jptoo-ton_cor:FullNameOrNameOfFilerOfNotificationCoverPage',
    'acquirer_address': 'jptoo-ton_cor:ResidentialAddressOrLocationOfFilerOfNotificationCoverPage',
    'contact_phone': 'jptoo-ton_cor:TelephoneNumberCoverPage',
    'contact_name': 'jptoo-ton_cor:NameOfContactPersonCoverPage',
    'legal_representative': 'jptoo-ton_cor:NameOfLegalRepresentativeCoverPage',
    'legal_representative_address': 'jptoo-ton_cor:ResidentialAddressOrLocationOfLegalRepresentativeCoverPage',

    # === Ownership / Voting Rights (structured) ===
    'voting_rights_to_purchase': 'jptoo-ton_cor:NumberOfVotingRightsRepresentedByShareCertificatesEtcToBePurchasedA',
    'voting_rights_owned_by_offeror': 'jptoo-ton_cor:NumberNumberOfVotingRightsRepresentedByShareCertificatesEtcOwnedByTenderOfferorD',
    'voting_rights_special_interest': 'jptoo-ton_cor:NumberNumberOfVotingRightsRepresentedByShareCertificatesEtcOwnedBySpecialInterestPartiesG',
    'total_voting_rights': 'jptoo-ton_cor:NumberNumberOfVotingRightsOwnedByAllShareholdersEtcOfSubjectCompanyJ',
    'purchase_ratio': 'jptoo-ton_cor:RatioOfNumberOfVotingRightsRepresentedByShareCertificatesEtcToBePurchasedAmongNumberOfVotingRightsOwnedByAllShareholdersEtcOfSubjectCompany',
    'holding_ratio_after': 'jptoo-ton_cor:HoldingRatioOfShareCertificatesEtcAfterPurchaseEtc',

    # === Base Dates for Voting Rights ===
    'base_date_offeror': 'jptoo-ton_cor:BaseDateNumberOfVotingRightsRepresentedByShareCertificatesEtcOwnedByTenderOfferorD',
    'base_date_special_interest': 'jptoo-ton_cor:BaseDateNumberOfVotingRightsRepresentedByShareCertificatesEtcOwnedBySpecialInterestPartiesG',
    'base_date_total': 'jptoo-ton_cor:BaseDateNumberOfVotingRightsOwnedByAllShareholdersEtcOfSubjectCompanyJ',

    # === Key TextBlock Elements ===
    'target_name': 'jptoo-ton_cor:NameOfSubjectCompanyTextBlock',
    'share_class': 'jptoo-ton_cor:ClassesOfShareCertificatesEtcToAcquireByPurchaseEtcTextBlock',
    'purpose_text': 'jptoo-ton_cor:PurposesOfPurchaseEtcTextBlock',
    'price_text': 'jptoo-ton_cor:PriceOfPurchaseEtcTextBlock',
    'shares_text': 'jptoo-ton_cor:NumberOfShareCertificatesEtcIntendedToPurchaseTextBlock',
    'period_text': 'jptoo-ton_cor:OriginalPeriodAtFilingTextBlock',
    'funding_text': 'jptoo-ton_cor:FundEtcForPurchaseEtcTextBlock',
    'settlement_date_text': 'jptoo-ton_cor:DateOfCommencementOfSettlementTextBlock',
    'acquirer_history_text': 'jptoo-ton_cor:HistoryOfOrganizationTextBlock',
    'major_shareholders_text': 'jptoo-ton_cor:MajorShareholdersInformationAboutSubjectCompanyTextBlock',
    'stock_price_info_text': 'jptoo-ton_cor:InformationAboutStockPricesTextBlock',
}


@dataclass
class TenderOfferReport(ParsedReport):
    """
    Parsed Tender Offer Registration (Doc 240/250).

    These filings disclose public tender offers (TOB / 公開買付) for shares
    of a target company, including the acquirer, offer price, ownership
    ratios, and terms of the offer.

    Key fields:
        acquirer_name: Name of the entity making the tender offer
        target_name: Name of the target company
        filing_date: Date the tender offer was filed
        voting_rights_to_purchase: Voting rights represented by shares to be purchased
        purchase_ratio: Ratio of voting rights being purchased to total
        holding_ratio_after: Expected ownership ratio after purchase
        is_amendment: Whether this is an amendment (Doc 250)
        purpose_text: Purpose of the tender offer (Japanese text)
        price_text: Offer price details (Japanese text)
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
    legal_representative: str | None = None
    legal_representative_address: str | None = None

    # Target
    target_name: str | None = None
    share_class: str | None = None

    # Ownership / voting rights
    voting_rights_to_purchase: int | None = None
    voting_rights_owned_by_offeror: int | None = None
    voting_rights_special_interest: int | None = None
    total_voting_rights: int | None = None
    purchase_ratio: Decimal | None = None
    holding_ratio_after: Decimal | None = None

    # Amendment
    is_amendment: bool = False

    # Key text blocks (Japanese text)
    purpose_text: str | None = None
    price_text: str | None = None
    shares_text: str | None = None
    period_text: str | None = None
    funding_text: str | None = None
    settlement_date_text: str | None = None

    @property
    def acquirer(self):
        """Resolve acquirer to Entity if possible."""
        if self.acquirer_edinet_code:
            from edinet_tools.entity import entity_by_edinet_code
            return entity_by_edinet_code(self.acquirer_edinet_code)
        return None

    def __repr__(self) -> str:
        acquirer = self.acquirer_name or 'Unknown'
        if len(acquirer) > 25:
            acquirer = acquirer[:22] + '...'
        target = self.target_name or '?'
        if len(target) > 25:
            target = target[:22] + '...'
        amend = ' [AMENDED]' if self.is_amendment else ''
        return f"TenderOfferReport(acquirer='{acquirer}', target='{target}'{amend})"


def parse_tender_offer(document=None, *, csv_files=None, doc_id=None, doc_type_code=None) -> TenderOfferReport:
    """
    Parse a Tender Offer Registration filing.

    Args:
        document: Document object with fetch() method (optional if csv_files provided)
        csv_files: Pre-extracted CSV data (list of dicts with 'filename' and 'data' keys)
        doc_id: Document ID (required if csv_files provided)
        doc_type_code: Document type code (required if csv_files provided)

    Returns:
        TenderOfferReport with extracted fields
    """
    if csv_files is None:
        zip_bytes = document.fetch()
        csv_files = extract_csv_from_zip(zip_bytes)
        doc_id = document.doc_id
        doc_type_code = document.doc_type_code

    if not csv_files:
        return TenderOfferReport(
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

    # Acquirer name from cover page (preferred) or DEI fallback
    acquirer_name = get('acquirer_name') or filer_name
    acquirer_address = get('acquirer_address')

    # Filing date
    filing_date = parse_date(get('filing_date'))

    # Submit date (from API metadata, if available)
    submitted = None
    if document is not None and getattr(document, 'filing_datetime', None):
        submitted = document.filing_datetime.date()

    # Contact / legal representative
    contact_name = get('contact_name')
    contact_phone = get('contact_phone')
    legal_representative = get('legal_representative')
    legal_representative_address = get('legal_representative_address')

    # Amendment flag
    is_amendment = amendment_flag == 'true' if amendment_flag else False

    # Target company info (TextBlock elements)
    target_name = strip_form_label(get('target_name'))
    share_class = get('share_class')

    # Ownership / voting rights (structured numeric fields)
    voting_rights_to_purchase = parse_int(get('voting_rights_to_purchase'))
    voting_rights_owned_by_offeror = parse_int(get('voting_rights_owned_by_offeror'))
    voting_rights_special_interest = parse_int(get('voting_rights_special_interest'))
    total_voting_rights = parse_int(get('total_voting_rights'))
    purchase_ratio = parse_percentage(get('purchase_ratio'))
    holding_ratio_after = parse_percentage(get('holding_ratio_after'))

    # Key text blocks
    purpose_text = get('purpose_text')
    price_text = get('price_text')
    shares_text = get('shares_text')
    period_text = get('period_text')
    funding_text = get('funding_text')
    settlement_date_text = get('settlement_date_text')

    # Categorize all elements
    raw_fields, text_blocks, unmapped_fields, raw_facts = categorize_elements(csv_files, ELEMENT_MAP)

    report = TenderOfferReport(
        doc_id=doc_id,
        doc_type_code=doc_type_code,
        source_files=source_files,
        raw_fields=raw_fields,
        unmapped_fields=unmapped_fields,
        text_blocks=text_blocks,
        raw_facts=raw_facts,

        # Acquirer identification
        acquirer_name=acquirer_name or getattr(document, 'filer_name', None),
        acquirer_name_en=filer_name_en,
        acquirer_edinet_code=edinet_code or getattr(document, 'filer_edinet_code', None),
        acquirer_address=acquirer_address,

        # Cover page
        filing_date=filing_date,
        contact_name=contact_name,
        contact_phone=contact_phone,
        legal_representative=legal_representative,
        legal_representative_address=legal_representative_address,

        # Target
        target_name=target_name,
        share_class=share_class,

        # Ownership
        voting_rights_to_purchase=voting_rights_to_purchase,
        voting_rights_owned_by_offeror=voting_rights_owned_by_offeror,
        voting_rights_special_interest=voting_rights_special_interest,
        total_voting_rights=total_voting_rights,
        purchase_ratio=purchase_ratio,
        holding_ratio_after=holding_ratio_after,

        # Amendment
        is_amendment=is_amendment,

        # Text blocks
        purpose_text=purpose_text,
        price_text=price_text,
        shares_text=shares_text,
        period_text=period_text,
        funding_text=funding_text,
        settlement_date_text=settlement_date_text,
    )

    from .validation import check_filing_date_sanity
    sanity_flag = check_filing_date_sanity(filing_date, submitted)
    if sanity_flag:
        report.extraction_flags.append(sanity_flag)
    return report
