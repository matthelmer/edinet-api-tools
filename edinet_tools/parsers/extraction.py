"""
ZIP and CSV extraction utilities for EDINET documents.

Handles in-memory extraction of XBRL CSV data from EDINET ZIP files.
"""
import csv
import io
import logging
import re
import unicodedata
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from ._facts import Fact

logger = logging.getLogger(__name__)


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
    """Read a single CSV file from a ZIP archive."""
    raw_bytes = zf.read(name)

    # Try multiple encodings (EDINET uses various encodings)
    encodings = ['utf-16le', 'utf-16', 'utf-8', 'shift-jis', 'cp932']
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

    # Parse tab-separated CSV
    rows = []
    try:
        lines = content.strip().split('\n')
        reader = csv.reader(lines, delimiter='\t')

        for row in reader:
            if len(row) >= 9:
                # Clean up values
                cleaned = [_clean_value(col) for col in row]
                rows.append({
                    '要素ID': cleaned[0],      # element_id
                    '項目名': cleaned[1],      # japanese_label
                    'コンテキストID': cleaned[2],  # context_id
                    '相対年度': cleaned[3],    # relative_year
                    '連結・個別': cleaned[4],   # consolidated_or_individual
                    '期間・時点': cleaned[5],   # period_or_instant
                    'ユニットID': cleaned[6],   # unit_id
                    '単位': cleaned[7],        # unit
                    '値': cleaned[8],          # value
                })
    except Exception as e:
        logger.warning(f"Error parsing CSV {name}: {e}")
        return []

    return rows


def _clean_value(value: str) -> str:
    """Clean a CSV cell value."""
    if not value:
        return ''
    cleaned = value.strip()
    # Remove null bytes and control characters
    cleaned = cleaned.replace('\x00', '').replace('\ufeff', '')
    # Remove quotes
    cleaned = cleaned.strip('"').strip("'").strip()
    return cleaned


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
                            return entry.get('値')
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
                    return value  # Return first match
    return result


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
            value = row.get('値')

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
    columns = ['要素ID', '項目名', 'コンテキストID', '相対年度',
               '連結・個別', '期間・時点', 'ユニットID', '単位', '値']

    for csv_file in csv_files:
        output_path = output_dir / csv_file['filename']
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter='\t')
            writer.writerow(columns)
            for row in csv_file.get('data', []):
                writer.writerow([row.get(col, '') for col in columns])
        written_paths.append(output_path)

    return written_paths


# ---------------------------------------------------------------------------
# Multi-shape value coercion helpers (per spec §3.5)
# ---------------------------------------------------------------------------

# Placeholders EDINET uses for "no value" in numeric contexts.
# After NFKC normalization, U+FF0D (－) becomes '-', and U+2212 (−) becomes '-'.
# So the normalized set is just ('', '-').
_NUMERIC_NULL_PLACEHOLDERS = frozenset({'－', '−', '', '-'})


def coerce_numeric_value(value) -> str | None:
    """Coerce a CSV value to a canonical numeric-string form, or None.

    Per spec §3.5: handles EDINET's varied null-placeholder shapes:
    '－' (U+FF0D full-width minus), '-' (bare ASCII hyphen alone),
    '−' (U+2212 minus sign), '' (empty), whitespace-only. All coerce
    to None.

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

    # After normalization, bare '-' (and its full-width forms, and U+2212 alone)
    # is a null placeholder.  '-1000' is a real negative number and passes through.
    if s in ('-', '−'):
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
