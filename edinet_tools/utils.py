# utils.py
import os
import pandas as pd
import re
import chardet
import tempfile
import zipfile
import logging
from typing import Dict, Any, Optional

from .processors import process_raw_csv_data

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
            # Use low_memory=False to avoid DtypeWarning on mixed types
            df = pd.read_csv(file_path, encoding=encoding, sep='\t', dtype=str, low_memory=False)
            logger.debug(f"Successfully read {os.path.basename(file_path)} with encoding {encoding}")
            # Replace NaN with None to handle missing values consistently
            df = df.replace({float('nan'): None, '': None})
            return df.to_dict(orient='records') # Return as list of dictionaries
        except (UnicodeDecodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as e:
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


# ZIP file processing
def process_zip_file(path_to_zip_file: str, doc_id: str, doc_type_code: str) -> Optional[Dict[str, Any]]:
    """
    Extract CSVs from a ZIP file, read them, and process into structured data
    using the appropriate document processor.

    :param path_to_zip_file: Path to the downloaded ZIP file.
    :param doc_id: EDINET document ID.
    :param doc_type_code: EDINET document type code.
    :return: Structured dictionary of the document's data, or None if processing failed.
    """
    raw_csv_data = []
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                with zipfile.ZipFile(path_to_zip_file, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                logger.debug(f"Extracted {os.path.basename(path_to_zip_file)} to {temp_dir}")
            except zipfile.BadZipFile as e:
                logger.error(f"Bad ZIP file: {path_to_zip_file}. Error: {e}")
                return None
            except Exception as e:
                logger.error(f"Error extracting {os.path.basename(path_to_zip_file)}: {e}")
                return None

            # Find and read all CSV files within the extracted structure
            csv_file_paths = []
            for root, dirs, files in os.walk(temp_dir):
                 # Exclude __MACOSX directory if present
                 if '__MACOSX' in dirs:
                     dirs.remove('__MACOSX')
                 for file in files:
                     if file.endswith('.csv'):
                         csv_file_paths.append(os.path.join(root, file))

            if not csv_file_paths:
                logger.warning(f"No CSV files found in extracted zip: {os.path.basename(path_to_zip_file)}")
                return None

            for file_path in csv_file_paths:
                # Skip auditor report files (start with 'jpaud')
                if os.path.basename(file_path).startswith('jpaud'):
                     logger.debug(f"Skipping auditor report file: {os.path.basename(file_path)}")
                     continue

                csv_records = read_csv_file(file_path)
                if csv_records is not None:
                    raw_csv_data.append({
                        'filename': os.path.basename(file_path),
                        'data': csv_records
                    })

            if not raw_csv_data:
                 logger.warning(f"No valid data extracted from CSVs in {os.path.basename(path_to_zip_file)}")
                 return None

            # Dispatch raw data to appropriate document processor
            structured_data = process_raw_csv_data(raw_csv_data, doc_id, doc_type_code, temp_dir)

            if structured_data:
                 logger.info(f"Successfully processed structured data for {os.path.basename(path_to_zip_file)}")
                 return structured_data
            else:
                 logger.warning(f"Document processor returned no data for {os.path.basename(path_to_zip_file)}")
                 return None

    except Exception as e:
        logger.error(f"Critical error processing zip file {path_to_zip_file}: {e}")
        # traceback.print_exc() # Uncomment for detailed traceback during debugging
        return None


