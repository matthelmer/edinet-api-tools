# utils.py
import io
import os
import csv
import re
import logging

logger = logging.getLogger(__name__)


# --- The one fail-loud TSV row parser (0.8.0 reader unification) -----------
#
# Both file-path reading (read_csv_file, below) and in-zip-bytes reading
# (parsers.extraction._read_csv_from_zip) parse decoded TSV text through
# this single function, so "what counts as malformed" is defined once.
#
# Contract established during the pandas->stdlib-csv migration and pinned
# by tests/test_read_csv_file.py (do not change without re-reading those
# pins):
#   - strict=True rejects malformed quoting (e.g. an unterminated quoted
#     field swallowing the rest of the file) as csv.Error, the same way
#     pandas' C parser raised ParserError instead of silently absorbing it.
#   - A row with MORE fields than the header/fieldnames raises csv.Error
#     (DictReader's restkey overflow) - pandas raised ParserError
#     ("Expected N fields, saw M") and rejected the whole file for this.
#   - A row with FEWER fields is padded with None, not rejected - pandas
#     silently padded the missing trailing field(s) with NaN -> None.
#   - Empty cells and empty strings both become None (pandas' NaN->None
#     handling).
def parse_strict_tsv(text, *, fieldnames=None):
    """Parse decoded TSV text into a list of row dicts, fail-loud on
    malformed input (see module docstring above for the exact contract).

    fieldnames=None: header-driven off the text's own first line (generic
        CSV/TSV use - read_csv_file's original contract). Returns None if
        the text is headerless/empty, the caller's cue to try the next
        candidate encoding.
    fieldnames=<sequence>: fixed schema; every line - including one that
        happens to equal the header text - is read as an ordinary DATA row.
        This is EDINET's XBRL-to-CSV shape, where the caller (extraction.py)
        filters the header pseudo-row itself downstream by value, not by
        position.

    Raises csv.Error for the two malformed-input shapes above.
    """
    reader = csv.DictReader(io.StringIO(text), delimiter='\t', strict=True, fieldnames=fieldnames)
    if fieldnames is None and not reader.fieldnames:
        return None
    records = []
    for row in reader:
        if None in row:
            raise csv.Error(f"row has more fields than header: {row!r}")
        records.append({k: (v if v not in ('', None) else None) for k, v in row.items()})
    return records


def read_csv_file(file_path):
    """Read a tab-separated CSV file trying multiple encodings."""
    # 'utf-8' is tried before the utf-16 family. utf-8 decoding is strict
    # (rejects almost any non-utf-8 byte sequence outright); utf-16/utf-16le/
    # utf-16be barely validate anything (any even-length byte string mostly
    # "succeeds", producing silently wrong mojibake rather than raising).
    # Before chardet retirement, chardet's own (correct, statistical) guess
    # was tried first and masked this ordering risk. Real EDINET UTF-16-LE
    # BOM files are unaffected: the BOM bytes (0xFF 0xFE) are never valid
    # UTF-8, so utf-8 fails fast and falls through to 'utf-16' either way.
    encodings = ['utf-8', 'utf-16', 'utf-16le', 'utf-16be', 'shift-jis', 'euc-jp', 'iso-8859-1', 'windows-1252']

    for encoding in encodings:
        try:
            with open(file_path, encoding=encoding, newline='') as fh:
                text = fh.read()
            records = parse_strict_tsv(text)
            if records is None:
                # Headerless/empty file: same as pandas' EmptyDataError -> try next encoding
                logger.debug(f"No header row in {os.path.basename(file_path)} with encoding {encoding}")
                continue
            logger.debug(f"Successfully read {os.path.basename(file_path)} with encoding {encoding}")
            return records # Return as list of dictionaries
        except (UnicodeDecodeError, UnicodeError, csv.Error) as e:
            logger.debug(f"Failed to read {os.path.basename(file_path)} with encoding {encoding}: {e}")
            continue
        except Exception as e:
            logger.error(f"An unexpected error occurred reading {os.path.basename(file_path)} with encoding {encoding}: {e}")
            continue

    logger.error(f"Failed to read {file_path}. Unable to determine correct encoding or format.")
    return None


# Text processing
def clean_text(text):
    """Clean and normalize text from disclosures."""
    if text is None:
        return None
    # Ensure it's a string
    text = str(text)
    # replace full-width space with regular space
    text = text.replace('\u3000', ' ')
    # remove excessive whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # replace specific Japanese punctuation with Western equivalents for consistency
    # return text.replace('。', '. ').replace('、', ', ')
    return text

