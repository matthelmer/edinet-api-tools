"""
Parser for Large Shareholding Reports (Doc Type 350).

Extracts ownership information, filer details, and target company data
from 大量保有報告書 filings.

PROCESSING PHILOSOPHY: Store raw XBRL values faithfully. No interpretation.
- Percentages stored as decimals (0.0967 = 9.67%)
- Text fields stored as-is
- Downstream consumers determine meaning
"""
import re
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date
from typing import Any

from .base import ParsedReport
from .extraction import (
    extract_csv_from_zip,
    extract_value,
    categorize_elements,
    parse_percentage,
    parse_int,
    parse_date,
    unescape_entities,
)


# XBRL Element ID mappings for Doc 350 (Large Holding Reports)
# Validated against jplvh_cor taxonomy
ELEMENT_MAP = {
    # Report Type
    'report_indication': 'jplvh_cor:DocumentTitleCoverPage',

    # Filer Information
    'filer_edinet_code': 'jplvh_cor:EDINETCodeDEI',
    'filer_name_alt1': 'jplvh_cor:Name',
    'filer_name_alt2': 'jplvh_cor:FilerNameInJapaneseDEI',
    'filer_name_en': 'jplvh_cor:FilerNameInEnglishDEI',
    'filer_address': 'jplvh_cor:ResidentialAddressOrAddressOfRegisteredHeadquarter',
    'filer_business': 'jplvh_cor:DescriptionOfBusiness',
    'filer_type': 'jplvh_cor:IndividualOrCorporation',

    # Target Company
    'target_company': 'jplvh_cor:NameOfIssuer',
    'target_ticker': 'jplvh_cor:SecurityCodeOfIssuer',

    # Ownership Data
    'shares_held': 'jplvh_cor:TotalNumberOfStocksEtcHeld',
    'ownership_pct': 'jplvh_cor:HoldingRatioOfShareCertificatesEtc',
    'prior_ownership_pct': 'jplvh_cor:HoldingRatioOfShareCertificatesEtcPerLastReport',
    'shares_outstanding': 'jplvh_cor:TotalNumberOfOutstandingStocksEtc',

    # Purpose & Intent
    'purpose': 'jplvh_cor:PurposeOfHolding',
    'important_proposal': 'jplvh_cor:ActOfMakingImportantProposalEtc',

    # Change Context
    'change_reason': 'jplvh_cor:ReasonForFilingChangeReportCoverPage',

    # Dates
    'filing_date': 'jplvh_cor:FilingDateCoverPage',
    'trigger_date': 'jplvh_cor:DateWhenFilingRequirementAroseCoverPage',
    'base_date': 'jplvh_cor:BaseDate',

    # Funding
    'acquisition_fund_own': 'jplvh_cor:AmountOfOwnFund',
    'acquisition_fund_borrowing': 'jplvh_cor:TotalAmountOfBorrowings',
    'acquisition_fund_other': 'jplvh_cor:TotalAmountFromOtherSources',
    'acquisition_fund_total': 'jplvh_cor:TotalAmountOfFundingForAcquisition',

    # Target Company Detail
    'listed_or_otc': 'jplvh_cor:ListedOrOTC',
}


@dataclass(frozen=True)
class JointHolder:
    """One co-reporter from a Large Holding Report (Doc 350).

    Derived from XBRL FilerLargeVolumeHolder<N>Member axis rows.
    The primary filer is index 1; co-reporters are 2, 3, ..., K.
    Present on both single-filer and joint filings — for single-filer
    reports, joint_holders contains a 1-element list.
    """
    # Stable ordering key — the N in FilerLargeVolumeHolder<N>Member
    holder_number: int

    # Identity
    edinet_code: str | None = None
    name_jp: str | None = None
    name_en: str | None = None
    address: str | None = None

    # Corporate-filer metadata (NULL for individuals)
    representative_name: str | None = None
    representative_title: str | None = None

    # Individual-filer metadata (NULL for corporates)
    workplace_name: str | None = None
    workplace_address: str | None = None

    # Ownership counts (primary clause of §27-23 Para 3)
    shares_held: int | None = None
    warrants_held: int | None = None
    convertible_bonds_held: int | None = None


@dataclass
class LargeHoldingReport(ParsedReport):
    """Parsed Large Shareholding Report (Doc 350)."""

    # Report context
    report_indication: str | None = None
    change_reason: str | None = None

    # Filer (who's reporting)
    filer_name: str | None = None
    filer_name_en: str | None = None
    filer_edinet_code: str | None = None
    filer_address: str | None = None
    filer_type: str | None = None  # "法人" or "個人"
    filer_business: str | None = None

    # Target (company being held)
    target_company: str | None = None
    target_ticker: str | None = None
    listed_or_otc: str | None = None

    # Ownership
    shares_held: int | None = None
    ownership_pct: Decimal | None = None
    prior_ownership_pct: Decimal | None = None
    ownership_change: Decimal | None = None
    shares_outstanding: int | None = None

    # Intent (raw text, no interpretation)
    purpose: str | None = None
    important_proposal: str | None = None

    # Dates
    filing_date: date | None = None
    trigger_date: date | None = None
    base_date: date | None = None

    # Funding
    acquisition_fund_own: int | None = None
    acquisition_fund_borrowing: int | None = None
    acquisition_fund_other: int | None = None
    acquisition_fund_total: int | None = None

    # Joint-filing flag derived from XBRL FilerLargeVolumeHolder<N>Member axis
    # presence in context_ids (v0.7.0+). True when the filing has multiple
    # co-reporters (joint Large Holding Report).
    is_joint_filing: bool = False

    # Joint-holder enumeration (v0.7.1+). Always populated as a list of
    # length >= 1 for valid filings (primary filer = index 1).
    # joint_holder_count mirrors len(joint_holders).
    # is_joint_filing is True when joint_holder_count >= 2.
    joint_holders: list[JointHolder] = field(default_factory=list)
    joint_holder_count: int = 0

    @property
    def filer(self):
        """Resolve filer to Entity if possible."""
        if self.filer_edinet_code:
            from edinet_tools.entity import entity_by_edinet_code
            return entity_by_edinet_code(self.filer_edinet_code)
        return None

    @property
    def target(self):
        """Resolve target to Entity if possible."""
        if self.target_ticker:
            from edinet_tools.entity import entity_by_ticker
            # Strip .T suffix if present for lookup
            ticker = self.target_ticker.replace('.T', '')[:4]
            return entity_by_ticker(ticker)
        return None

    @property
    def ownership_percentage(self) -> float | None:
        """Ownership as a percentage (e.g., 9.67 for 9.67%)."""
        if self.ownership_pct is not None:
            return float(self.ownership_pct * 100)
        return None

    def __repr__(self) -> str:
        filer = self.filer_name or 'Unknown'
        if len(filer) > 20:
            filer = filer[:17] + '...'
        target = self.target_company or 'Unknown'
        if len(target) > 20:
            target = target[:17] + '...'
        if self.ownership_pct is not None:
            pct = f'{float(self.ownership_pct * 100):.2f}%'
        else:
            pct = '?%'
        return f"LargeHoldingReport(filer='{filer}', target='{target}', ownership={pct})"


# Co-reporter axes. Two forms occur in filed Doc 350 XBRL:
#   ...FilerLargeVolumeHolder<N>Member  — primary filer is 1, co-reporters 2..K
#   ...JointHolder<N>Member             — a second axis some filers use for
#                                          共同保有者 (e.g. S100SKDY: 三菱商事 as
#                                          Holder1 + UCC entities as JointHolder1/2)
# Either axis beyond the primary filer marks a joint filing.
_HOLDER_AXIS_RE = re.compile(r'(?:FilerLargeVolumeHolder(\d+)|JointHolder(\d+))Member')
_JOINT_HOLDER_RE = re.compile(r'(?:FilerLargeVolumeHolder(?:[2-9]|\d{2,})|JointHolder\d+)Member')

# Group-total context on a joint filing. Per-holder rows carry the axis
# member suffix; the bare context is the 合計 row. Single-filer filings tag
# only Holder1 and usually omit the bare context.
_TOTAL_CTX = 'FilingDateInstant'
_PRIMARY_SUFFIX = 'FilerLargeVolumeHolder1Member'

# Values EDINET uses for "nothing to report" in free-text intent fields.
_BLANK_MARKS = frozenset({'', '－', '-', '―', '—', '該当事項なし', '該当なし', '無', 'なし'})


def _first_value(csv_files: list, element_id: str, ctx_ok) -> str | None:
    """First 値 for element_id whose context satisfies ctx_ok, decoded."""
    for csv_file in csv_files or []:
        for row in csv_file.get('data', []) or []:
            if row.get('要素ID') != element_id:
                continue
            if ctx_ok(row.get('コンテキストID', '') or ''):
                v = row.get('値')
                return unescape_entities(v) if v is not None else None
    return None


def _group_value(csv_files: list, key: str) -> str | None:
    """A holding figure at GROUP grain: the bare total context first, then the
    primary filer's own row (the only row a single-filer filing carries), then
    positional first-match for legacy un-axised filings.

    Before 0.8.4 `ownership_pct`/`shares_held` took the LAST match and
    `prior_ownership_pct` the FIRST — i.e. group total vs holder 1's prior on
    every joint filing (375 of 400 sampled prod filings since 2024 disagreed
    with the filed total-context prior).
    """
    element_id = ELEMENT_MAP[key]
    return (
        _first_value(csv_files, element_id, lambda c: c == _TOTAL_CTX)
        or _first_value(csv_files, element_id, lambda c: c.endswith(_PRIMARY_SUFFIX))
        or extract_value(csv_files, element_id)
    )


def _any_holder_value(csv_files: list, key: str) -> str | None:
    """A per-holder intent field read at GROUP grain: the first co-reporter
    that states something wins; if every holder is blank, the first row's
    blank marker is returned as filed (never invented)."""
    element_id = ELEMENT_MAP[key]
    first = None
    for csv_file in csv_files or []:
        for row in csv_file.get('data', []) or []:
            if row.get('要素ID') != element_id:
                continue
            v = row.get('値')
            v = unescape_entities(v) if v is not None else None
            if first is None:
                first = v
            if (v or '').strip() not in _BLANK_MARKS:
                return v
    return first


def _detect_joint_filing(csv_files: list) -> bool:
    """Return True when context_ids carry a co-reporter axis beyond the primary.

    Real EDINET Doc 350 filings carry per-co-reporter axis members like
    `FilingDateInstant_jplvh030000-lvh_E23615-000FilerLargeVolumeHolder1Member`
    for the primary filer and `...FilerLargeVolumeHolder2Member`,
    `...3Member`, etc. — or `...JointHolder<N>Member` — for additional
    co-reporters. Only Holder1Member present = single filer.

    (Note: the form-schema extension namespace prefix `jplvh030000-lvh_E#####-000`
    varies per filer; the load-bearing discriminator is the member-name
    pattern, not the axis-namespace prefix.)
    """
    for csv_file in csv_files or []:
        for row in csv_file.get('data', []) or []:
            ctx = row.get('コンテキストID', '') or ''
            if _JOINT_HOLDER_RE.search(ctx):
                return True
    return False


# Field label (項目名) → (attribute, type)
_HOLDER_FIELD_MAP: dict[str, tuple[str, type]] = {
    'EDINETコード、大量保有DEI': ('edinet_code', str),
    '氏名又は名称（日本語表記）、大量保有DEI': ('name_jp', str),
    '氏名又は名称': ('name_jp', str),  # fallback for older filings
    '氏名又は名称（英語表記）、大量保有DEI': ('name_en', str),
    '住所又は本店所在地': ('address', str),
    '代表者氏名': ('representative_name', str),
    '代表者役職': ('representative_title', str),
    '勤務先名称': ('workplace_name', str),
    '勤務先住所': ('workplace_address', str),
    '株券又は投資証券等、法第27条の23第3項本文': ('shares_held', int),
    '新株予約権証券又は新投資口予約権証券等、法第27条の23第3項本文': ('warrants_held', int),
    '新株予約権付社債券、法第27条の23第3項本文': ('convertible_bonds_held', int),
}

# Japanese null markers used in Doc 350 holder rows.
# Superset of extraction.py's `_NUMERIC_NULL_PLACEHOLDERS` for the dash family;
# adds 'ー' (katakana prolonged sound), 'なし', '該当なし' which appear in
# narrative fields like 代表者氏名 when the filer is an individual.
# Kept local rather than imported to avoid coupling Doc 350 holder semantics
# to the broader numeric-null path.
_NULL_VALUES = {'－', '-', '', 'ー', 'なし', '―', '該当なし'}


def _normalize_holder_value(raw: str, typ: type):
    """Normalize a raw XBRL value to typed Python or None."""
    if raw is None or str(raw).strip() in _NULL_VALUES:
        return None
    if typ is int:
        try:
            return int(float(str(raw).replace(',', '').strip()))
        except (ValueError, TypeError):
            return None
    # EDINET emits raw HTML entity references in some filer names (&amp; etc.).
    return unescape_entities(str(raw).strip())


def _extract_joint_holders(csv_files: list) -> list[JointHolder]:
    """Extract per-holder rows from XBRL substrate.

    Buckets rows by `FilerLargeVolumeHolder<N>Member` axis, extracts
    typed fields by `項目名` label, returns list sorted by N ascending.

    For single-filer reports, returns a 1-element list (the primary filer
    at N=1). For joint reports (K>=2 co-reporters), returns K elements.
    For corrupt or partial XBRL, returns what's parseable; missing fields
    are None.
    """
    # Bucket key: (axis, N). Axis 0 = FilerLargeVolumeHolder (primary is N=1),
    # axis 1 = JointHolder. Holders are emitted in that order and renumbered
    # 1..K so holder_number stays a dense ordering key across both axes.
    by_holder: dict[tuple[int, int], dict] = {}
    for csv_file in csv_files or []:
        for row in csv_file.get('data', []) or []:
            ctx = row.get('コンテキストID', '') or ''
            m = _HOLDER_AXIS_RE.search(ctx)
            if not m:
                continue
            key = (0, int(m.group(1))) if m.group(1) is not None else (1, int(m.group(2)))
            field_label = row.get('項目名', '') or ''
            if field_label not in _HOLDER_FIELD_MAP:
                continue
            attr, typ = _HOLDER_FIELD_MAP[field_label]
            value = _normalize_holder_value(row.get('値', ''), typ)
            holder_dict = by_holder.setdefault(key, {})
            # First-wins per (holder, attr) to avoid the fallback
            # '氏名又は名称' label overwriting '氏名又は名称（日本語表記）、大量保有DEI'
            # when both appear in a transitional filing. In practice these labels
            # are mutually exclusive by filing vintage; the guard is defensive.
            if attr not in holder_dict or holder_dict[attr] is None:
                holder_dict[attr] = value
    return [JointHolder(holder_number=i, **by_holder[k])
            for i, k in enumerate(sorted(by_holder.keys()), start=1)]


def parse_large_holding(document=None, *, csv_files=None, doc_id=None, doc_type_code=None) -> LargeHoldingReport:
    """
    Parse a Large Shareholding Report document.

    Args:
        document: Document object with fetch() method (optional if csv_files provided)
        csv_files: Pre-extracted CSV data (list of dicts with 'filename' and 'data' keys)
        doc_id: Document ID (required if csv_files provided)
        doc_type_code: Document type code (required if csv_files provided)

    Returns:
        LargeHoldingReport with extracted fields
    """
    # Fetch and extract CSV data (unless pre-extracted)
    if csv_files is None:
        zip_bytes = document.fetch()
        csv_files = extract_csv_from_zip(zip_bytes)
        doc_id = document.doc_id
        doc_type_code = document.doc_type_code


    if not csv_files:
        # Return minimal report if extraction failed
        return LargeHoldingReport(
            doc_id=doc_id,
            doc_type_code=doc_type_code,
            source_files=[],
            raw_fields={},
            unmapped_fields={},
            text_blocks={},
        )

    # Get source filenames
    source_files = [f['filename'] for f in csv_files]

    # Extract values using element map
    def get(key: str, last: bool = False) -> str | None:
        return extract_value(csv_files, ELEMENT_MAP.get(key, ''), get_last=last)

    # Filer name (try multiple element IDs)
    filer_name = get('filer_name_alt1') or get('filer_name_alt2') or getattr(document, 'filer_name', None)

    # Target ticker (normalize to 4-digit + .T format)
    target_ticker_raw = get('target_ticker')
    target_ticker = None
    if target_ticker_raw:
        ticker_digits = target_ticker_raw.strip()[:4]
        target_ticker = f"{ticker_digits}.T"

    # Holding figures at GROUP grain: explicit total-context selection (0.8.4).
    # On a joint filing these are the 合計 row; on a single-filer filing the
    # primary holder's row. Per-holder figures stay on joint_holders.
    ownership_pct = parse_percentage(_group_value(csv_files, 'ownership_pct'))
    prior_ownership_pct = parse_percentage(_group_value(csv_files, 'prior_ownership_pct'))

    # Calculate ownership change
    ownership_change = None
    if ownership_pct is not None and prior_ownership_pct is not None:
        ownership_change = ownership_pct - prior_ownership_pct

    # Dates
    filing_date = parse_date(get('filing_date'))
    filing_datetime = getattr(document, 'filing_datetime', None)
    if not filing_date and filing_datetime:
        filing_date = filing_datetime.date()

    # Categorize all elements
    raw_fields, text_blocks, unmapped_fields, raw_facts = categorize_elements(csv_files, ELEMENT_MAP)

    # Detect joint filing via FilerLargeVolumeHolder<N>Member axis presence
    # in context_ids (N >= 2; primary filer is always Holder1Member).
    is_joint_filing = _detect_joint_filing(csv_files)
    joint_holders_list = _extract_joint_holders(csv_files)

    return LargeHoldingReport(
        doc_id=doc_id,
        doc_type_code=doc_type_code,
        source_files=source_files,
        raw_fields=raw_fields,
        unmapped_fields=unmapped_fields,
        text_blocks=text_blocks,
        raw_facts=raw_facts,

        # Report context
        report_indication=get('report_indication'),
        change_reason=get('change_reason'),

        # Filer
        filer_name=filer_name,
        filer_name_en=get('filer_name_en'),
        filer_edinet_code=get('filer_edinet_code') or getattr(document, 'filer_edinet_code', None),
        filer_address=get('filer_address'),
        filer_type=get('filer_type'),
        filer_business=get('filer_business'),

        # Target
        target_company=get('target_company'),
        target_ticker=target_ticker,
        listed_or_otc=get('listed_or_otc'),

        # Ownership
        shares_held=parse_int(_group_value(csv_files, 'shares_held')),
        ownership_pct=ownership_pct,
        prior_ownership_pct=prior_ownership_pct,
        ownership_change=ownership_change,
        shares_outstanding=parse_int(get('shares_outstanding')),

        # Purpose & Intent. `purpose` is per-holder with no group row; the
        # primary filer's is reported here (co-reporters' on joint_holders).
        # `important_proposal` is read across co-reporters: the first holder
        # that states an act wins (0.8.4; ~2% of joint filings differ by holder).
        purpose=get('purpose'),
        important_proposal=_any_holder_value(csv_files, 'important_proposal'),

        # Dates
        filing_date=filing_date,
        trigger_date=parse_date(get('trigger_date')),
        base_date=parse_date(get('base_date')),

        # Funding
        acquisition_fund_own=parse_int(get('acquisition_fund_own')),
        acquisition_fund_borrowing=parse_int(get('acquisition_fund_borrowing')),
        acquisition_fund_other=parse_int(get('acquisition_fund_other')),
        acquisition_fund_total=parse_int(get('acquisition_fund_total')),

        # Joint-filing flag (FilerLargeVolumeHolder<N>Member axis presence, N >= 2)
        is_joint_filing=is_joint_filing,
        joint_holders=joint_holders_list,
        joint_holder_count=len(joint_holders_list),
    )
