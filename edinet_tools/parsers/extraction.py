"""
ZIP and CSV extraction utilities for EDINET documents.

Handles in-memory extraction of XBRL CSV data from EDINET ZIP files.
"""
import csv
import html
import io
import logging
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, NamedTuple, Optional

from ..utils import parse_strict_tsv
from ._facts import Fact

logger = logging.getLogger(__name__)

# EDINET's fixed XBRL-to-CSV column order. A real EDINET CSV carries this
# exact header row as its first line, but _read_csv_from_zip reads
# positionally (fieldnames=_EDINET_CSV_COLUMNS below) rather than off the
# file's own header text, so the header line itself comes back as an
# ordinary data row (要素ID='要素ID', ...) - callers filter it out by value
# (see categorize_elements's `elem_id == '要素ID'` skip), matching the
# pre-existing behavior this reader has always had.
_EDINET_CSV_COLUMNS = (
    '要素ID', '項目名', 'コンテキストID', '相対年度',
    '連結・個別', '期間・時点', 'ユニットID', '単位', '値',
)


def extract_csv_from_zip(zip_bytes: bytes) -> list[dict[str, Any]]:
    """
    Extract CSV data from EDINET ZIP file bytes.

    Args:
        zip_bytes: Raw bytes of the ZIP file

    Returns:
        List of dicts with 'filename' and 'data' keys.
        Each 'data' is a list of row dicts.
    """
    csv_files = []

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
            for name in zf.namelist():
                # Skip non-CSV files and macOS metadata
                if not name.endswith('.csv'):
                    continue
                if '__MACOSX' in name:
                    continue
                # Skip auditor report files
                if name.split('/')[-1].startswith('jpaud'):
                    continue

                try:
                    csv_data = _read_csv_from_zip(zf, name)
                    if csv_data:
                        csv_files.append({
                            'filename': name.split('/')[-1],
                            'data': csv_data
                        })
                except Exception as e:
                    logger.warning(f"Failed to read CSV {name}: {e}")
                    continue

    except zipfile.BadZipFile as e:
        logger.error(f"Invalid ZIP file: {e}")
        return []
    except Exception as e:
        logger.error(f"Error extracting ZIP: {e}")
        return []

    return csv_files


def _read_csv_from_zip(zf: zipfile.ZipFile, name: str) -> list[dict[str, Any]]:
    """Read a single CSV file from a ZIP archive.

    Row parsing is fail-loud (see utils.parse_strict_tsv): a malformed row
    (unterminated quote, or more fields than the fixed 9-column schema)
    raises csv.Error, which propagates to extract_csv_from_zip's per-file
    try/except - that file is excluded (logged), the rest of the zip's
    files are unaffected. This never silently returns wrong-shaped data.
    """
    raw_bytes = zf.read(name)

    # Try multiple encodings (EDINET uses various encodings). 'utf-8' is
    # tried first - it validates strictly (rejects almost any non-utf-8
    # byte sequence outright), whereas the utf-16 family barely validates
    # anything (most even-length byte strings "succeed", silently decoding
    # to mojibake instead of raising). Found via the 0.8.0 zero-dep smoke
    # test: a real, non-BOM UTF-8-encoded fixture silently mojibaked to a
    # single garbage row under the old utf-16le-first order, pre-dating
    # this task's changes entirely (chardet was never involved here) -
    # latent because every existing zip-based test happened to only ever
    # feed this function utf-16le-encoded content. Real EDINET files are
    # UTF-16-LE with a BOM; the BOM bytes (0xFF 0xFE) are never valid
    # utf-8, so utf-8 fails fast and correctly falls through to
    # 'utf-16le' for those - unaffected by the reorder. 'utf-16le' stays
    # ahead of plain 'utf-16' - it does NOT consume the BOM automatically,
    # hence the manual strip below.
    encodings = ['utf-8', 'utf-16le', 'utf-16', 'shift-jis', 'cp932']
    content = None

    for encoding in encodings:
        try:
            decoded = raw_bytes.decode(encoding)
            # Remove BOM if present
            if decoded.startswith('\ufeff'):
                decoded = decoded[1:]
            content = decoded
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if not content:
        logger.warning(f"Could not decode {name} with any encoding")
        return []

    records = parse_strict_tsv(content.strip(), fieldnames=_EDINET_CSV_COLUMNS)
    for rec in records or []:
        rec['値'] = unescape_entities(rec.get('値'))
    return records or []


# --- Parsing utilities ---

def parse_percentage(value: Any) -> Optional[Decimal]:
    """
    Parse percentage/ratio value to Decimal.

    EDINET Doc 350 stores ratios as decimals (0.0967 = 9.67%).
    Returns as-is without dividing by 100.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value in ('', '－', '―', '-', '—', 'N/A', 'n/a'):
            return None
        try:
            cleaned = value.replace('%', '').strip()
            return Decimal(cleaned)
        except Exception:
            return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def parse_decimal(value: Any) -> Decimal | None:
    """Decimal from a coerced numeric string; None for null markers and for
    anything Decimal() rejects. Thousands separators are removed first, as
    `parse_int` does, so `1,234.5` reads as 1234.5 rather than None. Only
    finite values are returned. Honest None over a parse that aborts the report."""
    if value is None:
        return None
    s = coerce_numeric_value(str(value))
    if not s:
        return None
    s = s.replace(',', '')
    try:
        d = Decimal(s)
    except ArithmeticError:
        return None
    return d if d.is_finite() else None


def parse_int(value: Any) -> Optional[int]:
    """
    Parse integer, handling Japanese formatting.

    Removes commas and converts to int.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip().replace(',', '').replace('，', '')
        if not value or value in ('－', '―', '-', '—'):
            return None
        try:
            return int(float(value))
        except Exception:
            return None
    try:
        return int(value)
    except Exception:
        return None


def parse_date(value: Any) -> Optional[date]:
    """
    Parse date from various formats.

    Supports: YYYY-MM-DD, YYYY/MM/DD, YYYY年MM月DD日
    """
    if value is None:
        return None
    # Check datetime first (it's a subclass of date)
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value or value in ('－', '―', '-', '—'):
            return None

        # Try standard formats
        for fmt in ('%Y-%m-%d', '%Y/%m/%d'):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue

        # Try Japanese format (2025年11月20日)
        try:
            cleaned = value.replace('年', '-').replace('月', '-').replace('日', '')
            return datetime.strptime(cleaned, '%Y-%m-%d').date()
        except Exception:
            pass

    return None


# EDINET's XBRL-CSV carries raw HTML entity references in some string values
# (`Baillie Gifford &amp; Co`, `日本M&amp;Aセンター`). Only well-formed,
# semicolon-terminated references are decoded: html.unescape alone also
# rewrites legacy no-semicolon forms, which would turn an ordinary '&ETH' or
# '&para' inside a name into 'Ð' / '¶'.
_ENTITY_RE = re.compile(r'&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);')


def unescape_entities(value):
    """Decode well-formed HTML entity references in a string; pass through otherwise."""
    if not isinstance(value, str) or '&' not in value:
        return value
    return _ENTITY_RE.sub(lambda m: html.unescape(m.group(0)), value)


def extract_value(
    csv_files: list,
    element_id: str,
    get_last: bool = False,
    context_patterns: Optional[list[str]] = None
) -> Optional[str]:
    """
    Extract value from csv_files by XBRL element ID.

    Args:
        csv_files: List of dicts with 'filename' and 'data' keys
        element_id: XBRL element ID to search for
        get_last: If True, return last occurrence (useful for totals in joint filings)
        context_patterns: List of context IDs to try in order (e.g., ['CurrentYearDuration'])
                         If None, returns first match regardless of context.
                         Uses exact matching to prevent e.g. 'CurrentYearDuration' from
                         matching 'CurrentYearDuration_NonConsolidatedMember'.
    """
    # If context patterns specified, try each in priority order
    if context_patterns:
        for pattern in context_patterns:
            for csv_file in csv_files:
                data = csv_file.get('data', [])
                for entry in data:
                    if entry.get('要素ID') == element_id:
                        context = entry.get('コンテキストID', '')
                        if context == pattern:
                            return unescape_entities(entry.get('値'))
        return None

    # No context patterns - return first (or last) match
    result = None
    for csv_file in csv_files:
        data = csv_file.get('data', [])
        for entry in data:
            if entry.get('要素ID') == element_id:
                value = entry.get('値')
                if get_last:
                    result = value  # Keep updating to get last
                else:
                    return unescape_entities(value)  # Return first match
    return unescape_entities(result)


def get_context_patterns(is_consolidated: bool, period: str) -> list[str]:
    """
    Build context patterns in priority order for financial data extraction.

    EDINET convention: bare context (e.g., 'CurrentYearDuration') = consolidated data.
    Non-consolidated data uses '_NonConsolidatedMember' suffix.
    There is NO '_ConsolidatedMember' suffix in real EDINET data.

    Args:
        is_consolidated: Whether the filer prepares consolidated statements
        period: Period identifier (e.g., 'CurrentYearDuration', 'CurrentQuarterInstant')

    Returns:
        List of context patterns to try in priority order
    """
    if is_consolidated:
        # Strict consolidated: a missing consolidated value must fall through to the
        # next ELEMENT/tier in the caller's waterfall, NOT silently borrow the
        # non-consolidated (parent) value of THIS element. Borrowing the parent here
        # is the root cause of IFRS/US-GAAP revenue reading the parent figure
        # (e.g. Toyota ¥18T parent vs ¥48T consolidated). When no consolidated value
        # exists for a metric, the typed field is honestly None — the parent value
        # is still preserved in the fact-bag (raw_fields / raw_facts), not lost.
        return [period]
    else:
        return [
            f"{period}_NonConsolidatedMember",   # Non-consolidated (preferred)
            period,                              # Fallback to bare context
        ]


def extract_financial(
    csv_files: list,
    element_id: str,
    period: str,
    is_consolidated: bool,
    ifrs_fallback_map: Optional[dict[str, str | list[str]]] = None
) -> Optional[int]:
    """
    Extract financial value with context preference and optional IFRS fallback.

    Tries to extract a financial value using context patterns appropriate for
    the filer's consolidation status. If not found and an IFRS fallback map
    is provided, tries the IFRS equivalent element.

    Args:
        csv_files: List of dicts with 'filename' and 'data' keys
        element_id: XBRL element ID to extract (e.g., 'jppfs_cor:NetSales')
        period: Period identifier (e.g., 'CurrentYearDuration')
        is_consolidated: Whether the filer prepares consolidated statements
        ifrs_fallback_map: Optional dict mapping JGAAP element IDs to IFRS equivalents

    Returns:
        Parsed integer value, or None if not found
    """
    patterns = get_context_patterns(is_consolidated, period)

    # Try each context level with both primary and IFRS fallback before
    # falling through to the next context level. This prevents non-consolidated
    # J-GAAP data from leaking into results for consolidated IFRS filers.
    #
    # coerce_numeric_value() normalizes EDINET null markers ('－' / '-' / '−' / '')
    # to None before the truthy check. Without it, IFRS reporters that emit
    # J-GAAP elements with '－' would truthy-pass the primary-element check,
    # parse_int('－') would return None, and the IFRS fallback would NEVER
    # fire — silently masking valid IFRS values with None.
    for pattern in patterns:
        # Try primary element at this context level
        value_str = coerce_numeric_value(
            extract_value(csv_files, element_id, context_patterns=[pattern])
        )
        if value_str:
            return parse_int(value_str)

        # Try IFRS fallback(s) at the same context level
        if ifrs_fallback_map:
            fallbacks = ifrs_fallback_map.get(element_id)
            if fallbacks:
                # Support both single string and list of fallbacks
                if isinstance(fallbacks, str):
                    fallbacks = [fallbacks]
                for ifrs_element in fallbacks:
                    value_str = coerce_numeric_value(
                        extract_value(csv_files, ifrs_element, context_patterns=[pattern])
                    )
                    if value_str:
                        return parse_int(value_str)

    return None


def categorize_elements(
    csv_files: list,
    element_map: Optional[dict[str, str]] = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[Fact]]:
    """
    Categorize all elements from csv_files into four buckets.

    Args:
        csv_files: List of dicts with 'filename' and 'data' keys
        element_map: Dict of field_name -> element_id for mapped fields.
                     Defaults to empty dict if not provided.

    Returns:
        Tuple of (raw_fields, text_blocks, unmapped_fields, raw_facts):
        - raw_fields: ALL elements by element_id (last-wins, nothing lost)
        - text_blocks: TextBlock elements
        - unmapped_fields: Elements not in element_map (excluding TextBlocks)
        - raw_facts: Every (element_id, context_id, value, unit_id) triple
    """
    # Build reverse map: element_id -> field_name
    mapped_element_ids = set(element_map.values()) if element_map else set()

    raw_fields: dict[str, Any] = {}
    text_blocks: dict[str, Any] = {}
    unmapped_fields: dict[str, Any] = {}
    raw_facts: list[Fact] = []

    for csv_file in csv_files or []:
        for row in csv_file.get('data', []):
            elem_id = row.get('要素ID', '')
            value = unescape_entities(row.get('値'))

            if not elem_id or value is None:
                continue

            # Skip header row
            if elem_id == '要素ID':
                continue

            # Store in raw_fields (everything, last-wins)
            raw_fields[elem_id] = value

            # Collect every triple for raw_facts
            context_id = row.get('コンテキストID', '')
            unit_id = row.get('ユニットID', '') or None
            raw_facts.append(Fact(
                element_id=elem_id,
                context_id=context_id,
                value=value,
                unit_id=unit_id,
            ))

            # Categorize
            if 'TextBlock' in elem_id:
                # TextBlock element
                key = elem_id.split(':')[-1] if ':' in elem_id else elem_id
                text_blocks[key] = value
            elif elem_id not in mapped_element_ids:
                # Unmapped element
                key = elem_id.split(':')[-1] if ':' in elem_id else elem_id
                unmapped_fields[key] = value

    return raw_fields, text_blocks, unmapped_fields, raw_facts


def match_element_by_suffix(
    csv_files: list,
    canonical_name: str,
    industry_suffixes: tuple = (),
) -> list:
    """Find CSV rows whose element_id ends with the canonical name or an industry-suffixed variant.

    Per spec §3.5: handles per-filer custom-element namespaces
    (jpcrp030000-asr_<EDINET>-000:NetSales) + industry suffixes
    (NetSalesINS, NetSalesBNK).

    Args:
        csv_files: List of dicts with 'filename' + 'data' keys (the shape
            returned by extract_csv_from_zip).
        canonical_name: The base element name to match against (e.g., 'NetSales').
        industry_suffixes: Optional tuple of industry suffixes to also accept
            (e.g., ('INS', 'BNK') for insurance + bank variants).

    Returns:
        List of CSV row dicts (full rows, not just element_ids) whose element_id
        ends with the canonical name or any of the suffixed variants.
    """
    accepted_endings = [canonical_name] + [
        canonical_name + suffix for suffix in industry_suffixes
    ]
    results = []

    for csv_file in csv_files or []:
        for row in csv_file.get('data', []) or []:
            elem_id = row.get('要素ID', '') or ''
            if not elem_id or elem_id == '要素ID':
                continue
            # Match against the local-name portion (after the colon, if present)
            local_name = elem_id.split(':')[-1] if ':' in elem_id else elem_id
            if local_name in accepted_endings:
                results.append(row)

    return results


# ---------------------------------------------------------------------------
# Declarative tier resolution (v0.8.0)
#
# `Tier` + `resolve_tiers` replace the per-parser waterfall idioms
# (_coalesce over extract_financial calls, per-share/ratio element loops,
# custom-namespace suffix hatches) with per-field tier tables. The resolver
# COMPOSES the primitives above — extract_value / get_context_patterns /
# match_element_by_suffix / coerce_numeric_value — it introduces no new
# row-iteration logic. Every semantic here reproduces a behavior the
# migrated parsers already had; the migration was proven by full-corpus
# old-vs-new equivalence, so treat any semantic change as a mapping change
# (census + prediction first).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Tier:
    """One step of a declarative extraction waterfall.

    element_id: a single XBRL element id, or a tuple resolved as ONE tier —
        in 'financial' mode the chain is tried pattern-major (context level
        outer, element inner), which is exactly extract_financial's
        primary-plus-fallbacks semantics. For suffix_match tiers these are
        canonical local names, tried canonical-major.
    standards: whitelist — the tier applies only when the filing's
        accounting standard is in the tuple; None applies to every standard.
        A missing (None) standard matches ONLY standards=None tiers.
    exclude_standards: blacklist — the 0.7.1 operating-income gate's shape
        ("IFRS/US-GAAP filers NEVER fall back to the parent J-GAAP
        element"). A whitelist cannot express "every standard except these,
        unknown/missing included", so the gate keeps its blacklist form.
    suffix_match: resolve via match_element_by_suffix at the BARE period
        context only — the custom-namespace hatch contract (a parent
        _NonConsolidatedMember figure can never win a suffix tier).
    last_resort: consulted only after every non-last_resort tier resolved
        to None, regardless of the tier's position in the table (it stays
        in the table so the tier data documents itself).
    """
    element_id: str | tuple
    standards: Optional[tuple] = None
    exclude_standards: Optional[tuple] = None
    suffix_match: bool = False
    last_resort: bool = False

    @property
    def elements(self) -> tuple:
        if isinstance(self.element_id, tuple):
            return self.element_id
        return (self.element_id,)


class TierHit(NamedTuple):
    """A resolved tier: the value (int in 'financial' mode, str in 'string'
    mode) plus the winning element id — free per-field provenance."""
    value: Any
    element_id: str


def _tier_in_scope(tier: Tier, standard: Optional[str]) -> bool:
    if tier.standards is not None and standard not in tier.standards:
        return False
    if tier.exclude_standards is not None and standard in tier.exclude_standards:
        return False
    return True


def _resolve_suffix_tier(csv_files, tier, period):
    """The securities.py hatch scan, verbatim semantics: canonical-major,
    bare-period context only, null-marker rows skipped mid-scan, first
    coerce-truthy value string wins."""
    for canonical in tier.elements:
        for row in match_element_by_suffix(csv_files, canonical):
            if (row.get('コンテキストID', '') or '') == period:
                v = coerce_numeric_value(row.get('値', ''))
                if v:
                    return v, (row.get('要素ID', '') or canonical)
    return None, None


def _resolve_financial_tier(csv_files, tier, patterns):
    """extract_financial's within-call semantics: context level outer,
    element chain inner, first coerce-truthy string commits the tier."""
    for pattern in patterns:
        context_patterns = [pattern] if pattern is not None else None
        for elem in tier.elements:
            s = coerce_numeric_value(
                extract_value(csv_files, elem, context_patterns=context_patterns))
            if s:
                return s, elem
    return None, None


def resolve_tiers(
    csv_files: list,
    tiers,
    *,
    standard: Optional[str],
    period: Optional[str],
    is_consolidated: Optional[bool],
    mode: str = 'financial',
    coerce: bool = True,
) -> Optional[TierHit]:
    """Resolve a per-field tier table to a TierHit, or None (honest absence).

    Two modes, each reproducing one pre-existing waterfall idiom exactly:

    - 'financial' (ints): the get_fin/_coalesce idiom. Per tier:
      pattern-major over the element chain, null markers skip WITHIN the
      tier; a coerce-truthy string that fails parse_int commits the tier
      but advances the WATERFALL (matching a get_fin returning None into
      _coalesce). `coerce` is ignored (always on — extract_financial's
      contract).
    - 'string' (raw value strings; caller parses): the per-share/ratio
      idioms. Per tier: ONE extract_value call per element over the FULL
      pattern list (extract_value short-circuits on the first pattern with
      any row — a marker at the preferred context is returned, not
      pattern-fallen-through). coerce=True reproduces the eps/nav
      null-marker tier-advance; coerce=False reproduces the legacy
      equity-ratio/roe first-non-empty-raw-string-stops behavior (the
      caller's parse_percentage turns markers into None).

    period=None resolves context-blind (extract_value with no context
    patterns — first match in file order), preserving the semi-annual
    parser's legacy semantics until its ratified context fix lands.
    Suffix tiers require a concrete period.

    standard/period/is_consolidated are keyword-only so call sites read as
    data, matching the tier tables they resolve.
    """
    if mode not in ('financial', 'string'):
        raise ValueError(f"unknown mode: {mode!r}")
    if period is not None:
        patterns = get_context_patterns(is_consolidated, period)
    else:
        patterns = [None]

    ordered = [t for t in tiers if not t.last_resort] + \
              [t for t in tiers if t.last_resort]

    for tier in ordered:
        if not _tier_in_scope(tier, standard):
            continue

        if tier.suffix_match:
            if period is None:
                raise ValueError('suffix_match tiers require a concrete period')
            s, elem = _resolve_suffix_tier(csv_files, tier, period)
            if s is None:
                continue
            if mode == 'financial':
                v = parse_int(s)
                if v is None:
                    continue  # parse failure advances the waterfall
                return TierHit(v, elem)
            return TierHit(s, elem)

        if mode == 'financial':
            s, elem = _resolve_financial_tier(csv_files, tier, patterns)
            if s is None:
                continue
            v = parse_int(s)
            if v is None:
                continue  # parse failure advances the waterfall
            return TierHit(v, elem)

        # string mode
        for elem in tier.elements:
            s = extract_value(
                csv_files, elem,
                context_patterns=patterns if period is not None else None)
            candidate = coerce_numeric_value(s) if coerce else s
            if candidate:
                return TierHit(candidate, elem)

    return None


def get_dei(csv_files: list, element_map: dict, key: str) -> Optional[str]:
    """Shared DEI reader: identification facts are filed once, at the
    FilingDateInstant context. Returns None for unknown keys (the parsers'
    pre-existing lenient contract)."""
    return extract_value(csv_files, element_map.get(key, ''),
                         context_patterns=['FilingDateInstant'])


def extract_csv_to_disk(zip_bytes: bytes, output_dir) -> list:
    """
    Extract CSV files from an EDINET ZIP and write them to disk.

    Preserves the 9-column EDINET CSV shape (要素ID, 項目名, コンテキストID,
    相対年度, 連結・個別, 期間・時点, ユニットID, 単位, 値) as utf-8 TSV.

    This is the modular disk-output helper, complementing the in-memory
    extract_csv_from_zip() for callers who want raw CSV files on disk
    for debugging, archival, memory-constrained processing, or out-of-band
    consumption.

    Args:
        zip_bytes: Raw bytes of the EDINET ZIP file
        output_dir: Directory where CSV files will be written. Created
                   recursively if it does not exist. Accepts str or Path.

    Returns:
        List of Path objects, one per CSV file written. Empty list if
        the ZIP contains no CSV files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_files = extract_csv_from_zip(zip_bytes)
    written_paths = []

    for csv_file in csv_files:
        output_path = output_dir / csv_file['filename']
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter='\t')
            writer.writerow(_EDINET_CSV_COLUMNS)
            for row in csv_file.get('data', []):
                writer.writerow([row.get(col, '') for col in _EDINET_CSV_COLUMNS])
        written_paths.append(output_path)

    return written_paths


# ---------------------------------------------------------------------------
# Multi-shape value coercion helpers (per spec §3.5)
# ---------------------------------------------------------------------------

# Placeholders EDINET uses for "no value" in numeric contexts.
# NFKC folds U+FF0D (－) to '-' but leaves U+2212 (−), U+2015 (―) and
# U+2014 (—) unchanged, so the set carries every member explicitly and
# coerce_numeric_value checks membership AFTER normalization.
# '―'/'—' added v0.8.0 (stage-5 B5): both appear in real filings and were
# already nulled by the quarterly eps marker tuple and parse_int/parse_date
# — extending the shared set is what makes replacing those local tuples
# with coerce_numeric_value behavior-preserving.
_NUMERIC_NULL_PLACEHOLDERS = frozenset({'－', '−', '', '-', '―', '—'})


def coerce_numeric_value(value) -> str | None:
    """Coerce a CSV value to a canonical numeric-string form, or None.

    Per spec §3.5: handles EDINET's varied null-placeholder shapes:
    '－' (U+FF0D full-width minus), '-' (bare ASCII hyphen alone),
    '−' (U+2212 minus sign), '―' (U+2015 horizontal bar), '—' (U+2014
    em dash), '' (empty), whitespace-only. All coerce to None.

    Full-width digits ('１', '２', ...) and full-width comma ('，') are
    normalized to half-width equivalents via NFKC.

    Negative numbers ('-1000') pass through correctly — they are NOT
    placeholders because they have digits attached.

    Args:
        value: The raw string value from a CSV cell (may be None).

    Returns:
        Normalized numeric string, or None if value is a null-placeholder.
    """
    if value is None:
        return None

    s = str(value).strip()
    if not s:
        return None

    # NFKC normalizes full-width digits/punctuation to half-width.
    # e.g. '１０００' -> '1000', '１，０００' -> '1,000', '－' (U+FF0D) -> '-'
    # Note: U+2212 (−, mathematical minus) is NOT changed by NFKC, so handle it
    # explicitly alongside the bare ASCII '-' placeholder check below.
    s = unicodedata.normalize('NFKC', s)

    # After normalization, a bare dash-family character alone is a null
    # placeholder ('-' from NFKC-folded '－', plus the unfolded '−'/'―'/'—').
    # '-1000' is a real negative number and passes through.
    if s in _NUMERIC_NULL_PLACEHOLDERS:
        return None

    # Empty string after normalization (shouldn't happen after strip, but be safe)
    if not s:
        return None

    return s


def coerce_int(value) -> int | None:
    """Coerce a CSV value to int, or None for placeholders.

    Wraps coerce_numeric_value() and adds int() conversion (with comma stripping).

    Args:
        value: The raw string value from a CSV cell (may be None).

    Returns:
        Integer, or None if value is a null-placeholder or non-numeric.
    """
    normalized = coerce_numeric_value(value)
    if normalized is None:
        return None
    # Strip comma separators (e.g. '1,000,000' -> '1000000')
    cleaned = normalized.replace(',', '')
    try:
        return int(cleaned)
    except ValueError:
        return None


# Leading EDINET form-section label on target-company names in the
# tender-offer document family: '１【対象者名】...' / '（１）【対象者名】...'.
_FORM_LABEL_RE = re.compile(r'^\s*[0-9０-９()（）．.]*\s*【対象者名】\s*')


def strip_form_label(value: Optional[str]) -> Optional[str]:
    """Strip the leading 【対象者名】 form label from a target-company name.
    Idempotent; None passes through."""
    if value is None:
        return None
    return _FORM_LABEL_RE.sub('', value).strip()
