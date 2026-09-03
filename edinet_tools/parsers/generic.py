"""
Raw parser for document types without dedicated parsers.

Returns a RawReport containing all XBRL data for exploration.
Use raw_fields dict to discover available elements, then consider
creating a typed parser if you need structured access repeatedly.
"""
from dataclasses import dataclass
from typing import Any

from .base import ParsedReport
from .extraction import unescape_entities, extract_csv_from_zip, extract_value


# Common DEI elements found across most document types
COMMON_DEI_ELEMENTS = {
    'edinet_code': 'jpdei_cor:EDINETCodeDEI',
    'filer_name': 'jpdei_cor:FilerNameInJapaneseDEI',
    'filer_name_en': 'jpdei_cor:FilerNameInEnglishDEI',
    'security_code': 'jpdei_cor:SecurityCodeDEI',
    'fund_code': 'jpdei_cor:FundCodeDEI',
}


@dataclass
class RawReport(ParsedReport):
    """
    Raw parsed report for unknown document types.

    Use this to explore XBRL data from document types without dedicated parsers.

    Key attributes:
        raw_fields: Dict of all XBRL elements (element_id -> value).
                    This is your exploration surface for unknown doc types.
        text_blocks: Dict of TextBlock elements (useful for narrative content).
        unmapped_fields: Always empty for RawReport. This field exists in typed
                        parsers to show elements not mapped to named attributes,
                        but RawReport has no such mapping - use raw_fields instead.

    Example:
        report = doc.parse()  # Returns RawReport for unknown types
        print(list(report.raw_fields.keys())[:10])  # See available elements
        print(report.raw_fields.get('jpdei_cor:FilerNameInJapaneseDEI'))
    """
    filer_name: str | None = None
    filer_name_en: str | None = None
    filer_edinet_code: str | None = None
    ticker: str | None = None
    doc_description: str | None = None

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
        return f"RawReport(doc_id='{self.doc_id}', type={self.doc_type_code}, filer='{filer}')"


# Backwards compatibility alias
GenericReport = RawReport


def parse_raw(document) -> RawReport:
    """
    Parse a document without type-specific field mapping.

    Extracts all XBRL elements into raw_fields for exploration.
    Used automatically by parse() for document types without
    dedicated parsers (120, 140, 160, 180, 350).

    Args:
        document: Document object with fetch() method

    Returns:
        RawReport with raw_fields containing all XBRL elements
    """
    zip_bytes = document.fetch()
    csv_files = extract_csv_from_zip(zip_bytes)

    if not csv_files:
        return RawReport(
            doc_id=document.doc_id,
            doc_type_code=document.doc_type_code,
            filer_name=getattr(document, 'filer_name', None),
            filer_edinet_code=getattr(document, 'filer_edinet_code', None),
            doc_description=getattr(document, 'doc_description', None),
            source_files=[],
            raw_fields={},
            unmapped_fields={},
            text_blocks={},
        )

    source_files = [f['filename'] for f in csv_files]

    # Extract common DEI elements
    def get_dei(key: str) -> str | None:
        return extract_value(csv_files, COMMON_DEI_ELEMENTS.get(key, ''), context_patterns=['FilingDateInstant'])

    edinet_code = get_dei('edinet_code')
    filer_name = get_dei('filer_name')
    filer_name_en = get_dei('filer_name_en')
    security_code = get_dei('security_code')

    # Format ticker
    ticker = None
    if security_code and security_code != '－':
        ticker = f"{security_code.strip()[:4]}.T"

    # Collect ALL elements into raw_fields
    raw_fields: dict[str, Any] = {}
    text_blocks: dict[str, Any] = {}

    for csv_file in csv_files:
        for row in csv_file.get('data', []):
            elem_id = row.get('要素ID', '')
            value = unescape_entities(row.get('値'))

            if not elem_id or value is None:
                continue

            # Store everything in raw_fields
            raw_fields[elem_id] = value

            # Also categorize text blocks
            if 'TextBlock' in elem_id:
                key = elem_id.split(':')[-1] if ':' in elem_id else elem_id
                text_blocks[key] = value

    return RawReport(
        doc_id=document.doc_id,
        doc_type_code=document.doc_type_code,
        source_files=source_files,
        raw_fields=raw_fields,
        unmapped_fields={},  # Empty - concept only applies to typed parsers
        text_blocks=text_blocks,

        filer_name=filer_name or getattr(document, 'filer_name', None),
        filer_name_en=filer_name_en,
        filer_edinet_code=edinet_code or getattr(document, 'filer_edinet_code', None),
        ticker=ticker,
        doc_description=getattr(document, 'doc_description', None),
    )


# Backwards compatibility alias
parse_generic = parse_raw
