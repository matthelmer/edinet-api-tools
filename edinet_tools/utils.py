# utils.py
import os
import csv
import re
import chardet
import logging

logger = logging.getLogger(__name__)


# Encoding and file reading
def detect_encoding(file_path):
    """Detect encoding of a file."""
    try:
        with open(file_path, 'rb') as file:
            raw_data = file.read(1024) # Read only first 1024 bytes for speed
        result = chardet.detect(raw_data)
        logger.debug(f"Detected encoding {result['encoding']} with confidence {result['confidence']} for {os.path.basename(file_path)}")
        return result['encoding']
    except IOError as e:
        logger.error(f"Error detecting encoding for {file_path}: {e}")
        return None


def read_csv_file(file_path):
    """Read a tab-separated CSV file trying multiple encodings."""
    detected_encoding = detect_encoding(file_path)

    # Prioritize detected encoding, then common ones for EDINET, then broad set
    encodings = [detected_encoding] if detected_encoding else []
    encodings.extend(['utf-16', 'utf-16le', 'utf-16be', 'utf-8', 'shift-jis', 'euc-jp', 'iso-8859-1', 'windows-1252'])

    # Remove duplicates while preserving order
    for encoding in list(dict.fromkeys(encodings)):
        if not encoding: continue
        try:
            with open(file_path, encoding=encoding, newline='') as fh:
                # strict=True rejects malformed quoting (e.g. an unterminated quoted
                # field swallowing the rest of the file) as csv.Error, the same way
                # pandas' C parser raised ParserError instead of silently absorbing it.
                reader = csv.DictReader(fh, delimiter='\t', strict=True)
                if not reader.fieldnames:
                    # Headerless/empty file: same as pandas' EmptyDataError -> try next encoding
                    logger.debug(f"No header row in {os.path.basename(file_path)} with encoding {encoding}")
                    continue
                records = []
                for row in reader:
                    if None in row:
                        # Row has MORE fields than the header; DictReader stows the
                        # overflow under a None key (restkey). pandas raised
                        # ParserError ("Expected N fields, saw M") and rejected the
                        # whole file for this - mirror that by failing this encoding
                        # attempt entirely rather than returning a corrupted row shape.
                        raise csv.Error(
                            f"row has more fields than header {reader.fieldnames!r}: {row!r}"
                        )
                    # Empty cells and empty strings both become None, matching pandas' NaN->None handling
                    records.append({k: (v if v not in ('', None) else None) for k, v in row.items()})
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

