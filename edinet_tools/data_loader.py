"""
EDINET Company Data Loader

Downloads and processes official EDINET codes from the Japanese government
and integrates with corporate entity translations.
"""

import csv
import io
import os
import urllib.request
import urllib.error
import http.client
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime
import tempfile
import zipfile

logger = logging.getLogger(__name__)

# The FSA serves the EDINET code list as a zip (Edinetcode.zip -> EdinetcodeDlInfo.csv,
# cp932, one metadata line before the header) from the download host. The old
# disclosure2.edinet-fsa.go.jp/weee0020/EDINET_Code_List.csv path 302s to an HTML
# page (probed 2026-09-09); a loader that streamed it wrote HTML into the codes file.
EDINET_CODES_ZIP_URL = "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip"
# Human-facing page for a manual download, when the automatic one fails.
EDINET_CODES_URL = "https://disclosure2.edinet-fsa.go.jp/"

class EdinetDataLoader:
    """Handles downloading and processing official EDINET company data."""
    
    def __init__(self, data_dir: str = None):
        """
        Initialize the data loader.
        
        Args:
            data_dir: Directory to store downloaded data files. 
                     Defaults to package data directory.
        """
        if data_dir is None:
            # Use package data directory
            package_dir = os.path.dirname(__file__)
            self.data_dir = os.path.join(package_dir, 'data')
        else:
            self.data_dir = data_dir
        
        # Ensure data directory exists
        os.makedirs(self.data_dir, exist_ok=True)
        
        self.edinet_codes_file = os.path.join(self.data_dir, 'edinet_codes.csv')
        self.translations_file = os.path.join(self.data_dir, 'corporate_entity_translations.csv')
        self.processed_data_file = os.path.join(self.data_dir, 'processed_companies.csv')
    
    def download_edinet_codes(self, force_update: bool = False) -> bool:
        """
        Download the latest EDINET codes from the official government website.
        
        Args:
            force_update: If True, download even if file already exists
            
        Returns:
            True if download was successful, False otherwise
        """
        if not force_update and os.path.exists(self.edinet_codes_file):
            # Check if file is recent (less than 7 days old)
            file_age = datetime.now().timestamp() - os.path.getmtime(self.edinet_codes_file)
            if file_age < 7 * 24 * 3600:  # 7 days in seconds
                logger.info("EDINET codes file is recent, skipping download")
                return True
        
        logger.info("Downloading EDINET codes from official website...")
        
        try:
            with urllib.request.urlopen(EDINET_CODES_ZIP_URL, timeout=60) as response:
                payload = response.read() if response.status == 200 else b''
        except (OSError, http.client.HTTPException) as e:
            # URLError and TimeoutError are OSErrors; IncompleteRead is an HTTPException.
            logger.warning(f"EDINET code-list download failed: {e}")
            payload = b''

        csv_bytes = self._csv_from_code_list_zip(payload)
        if csv_bytes is None:
            # Never write a non-CSV body: an HTML error page saved as
            # edinet_codes.csv reads as "success" and poisons every lookup.
            logger.warning("EDINET code-list download did not return the expected zip. "
                           "Manual download may be required.")
            logger.info(f"Please download the EDINET codes manually from {EDINET_CODES_URL}")
            logger.info(f"Save as: {self.edinet_codes_file}")
            return False

        # Write beside the target and swap atomically: a failure mid-write must
        # never leave a truncated file where a good one was.
        fd, tmp_path = tempfile.mkstemp(dir=self.data_dir, prefix='.edinet_codes.', suffix='.tmp')
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(csv_bytes)
            os.replace(tmp_path, self.edinet_codes_file)
        except OSError:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
        logger.info(f"Successfully downloaded EDINET codes to {self.edinet_codes_file}")
        return True

    @staticmethod
    def _csv_from_code_list_zip(payload: bytes) -> Optional[bytes]:
        """The single CSV member of the FSA code-list zip, or None when the
        payload is not a zip or carries no CSV (HTML error page, empty body)."""
        if not payload or not zipfile.is_zipfile(io.BytesIO(payload)):
            return None
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            members = [n for n in z.namelist() if n.lower().endswith('.csv')]
            if len(members) != 1:
                logger.warning(f"EDINET code-list zip has {len(members)} CSV members: {z.namelist()}")
                return None
            return z.read(members[0]) or None
    
    def load_translations(self, translation_file: str = None) -> Dict[str, str]:
        """
        Load Japanese to English company name translations.
        
        Args:
            translation_file: Path to translation CSV file
            
        Returns:
            Dictionary mapping Japanese names to English names
        """
        if translation_file is None:
            translation_file = self.translations_file
        
        translations = {}
        
        if not os.path.exists(translation_file):
            logger.warning(f"Translation file not found: {translation_file}")
            return translations
        
        try:
            with open(translation_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header row
                for row in reader:
                    if len(row) >= 2 and row[0] and row[1]:
                        translations[row[0]] = row[1]
            
            logger.info(f"Loaded {len(translations)} translations")
        except Exception as e:
            logger.error(f"Error loading translations: {e}")
        
        return translations
    
    def process_edinet_data(self) -> List[Dict]:
        """
        Process the EDINET codes CSV into a clean company dataset.
        
        Returns:
            List of company dictionaries with standardized fields
        """
        if not os.path.exists(self.edinet_codes_file):
            logger.error("EDINET codes file not found. Run download_edinet_codes() first.")
            return []
        
        # Load translations
        translations = self.load_translations()
        
        companies = []
        
        try:
            # Try Shift-JIS encoding first (common for Japanese government files)
            encodings_to_try = ['shift_jis', 'utf-8', 'cp932', 'euc-jp']
            working_encoding = None
            
            # Header line contains either the English column name "EDINET Code"
            # or the Japanese full-width equivalent "ＥＤＩＮＥＴコード".
            header_markers = ("EDINET Code", "ＥＤＩＮＥＴコード")
            for encoding in encodings_to_try:
                try:
                    with open(self.edinet_codes_file, 'r', encoding=encoding) as f:
                        # Read first few lines to check if encoding works
                        lines = f.readlines()
                        if len(lines) > 1 and any(m in lines[1] for m in header_markers):
                            working_encoding = encoding
                            logger.info(f"Successfully opened EDINET codes file with {encoding} encoding")
                            break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            
            if working_encoding is None:
                logger.error("Could not decode EDINET codes file with any encoding")
                return []
            
            # Now process the file with the working encoding. FSA serves
            # both English and Japanese variants of this CSV; both have
            # identical schema and row order but use different column
            # headers and translated values for a few fields. Resolve
            # columns by header alias via the shared helper in
            # entity_classifier so the loader handles either variant and
            # fails loudly if FSA ever renames a column.
            from .entity_classifier import (
                _EDINET_COLUMN_ALIASES,
                _LISTED_VALUES,
                _resolve_columns,
                translate_industry_to_english,
            )

            with open(self.edinet_codes_file, 'r', encoding=working_encoding) as f:
                reader = csv.reader(f)
                next(reader, None)  # metadata row (date, count)
                header = next(reader, None)
                if header is None:
                    logger.error("EDINET codes file has no header row")
                    return []
                col = _resolve_columns(header, _EDINET_COLUMN_ALIASES)
                max_idx = max(col.values())

                for row in reader:
                    if len(row) <= max_idx:
                        continue

                    edinet_code = row[col["edinet_code"]].strip()
                    name_ja = row[col["name_jp"]].strip()
                    name_en = row[col["name_en"]].strip()
                    securities_code = row[col["securities_code"]].strip()
                    industry_raw = row[col["industry"]].strip()
                    listed_status = row[col["listed"]].strip()

                    # Skip if missing essential data
                    if not edinet_code or not name_ja:
                        continue

                    # Use translation if available and no English name provided
                    if not name_en and name_ja in translations:
                        name_en = translations[name_ja]

                    # Normalize industry to English so downstream search
                    # works the same against either CSV variant.
                    industry_en = translate_industry_to_english(industry_raw)

                    company = {
                        'edinet_code': edinet_code,
                        'ticker': securities_code if securities_code else None,
                        'name_ja': name_ja,
                        'name_en': name_en if name_en else name_ja,  # Fallback to Japanese
                        'industry': industry_en or "",
                        'industry_jp': industry_raw or "",
                        'listed': listed_status in _LISTED_VALUES,
                        'search_text': f"{name_ja} {name_en} {securities_code}".lower()
                    }

                    companies.append(company)
            
            logger.info(f"Processed {len(companies)} companies from EDINET data")
            
            # Save processed data for faster loading
            self._save_processed_data(companies)
            
            return companies
            
        except Exception as e:
            logger.error(f"Error processing EDINET data: {e}")
            return []
    
    def _save_processed_data(self, companies: List[Dict]):
        """Save processed company data to CSV for faster loading."""
        try:
            with open(self.processed_data_file, 'w', encoding='utf-8', newline='') as f:
                if companies:
                    fieldnames = companies[0].keys()
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(companies)
            logger.info(f"Saved processed data to {self.processed_data_file}")
        except Exception as e:
            logger.error(f"Error saving processed data: {e}")
    
    def load_processed_data(self) -> List[Dict]:
        """Load previously processed company data."""
        if not os.path.exists(self.processed_data_file):
            return []
        
        companies = []
        try:
            with open(self.processed_data_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Convert string boolean back to actual boolean
                    row['listed'] = row['listed'].lower() == 'true'
                    companies.append(row)
            
            logger.info(f"Loaded {len(companies)} companies from processed data")
            return companies
        except Exception as e:
            logger.error(f"Error loading processed data: {e}")
            return []
    
    def get_companies(self, force_update: bool = False) -> List[Dict]:
        """
        Get complete company dataset, downloading/processing if needed.
        
        Args:
            force_update: If True, force download and reprocess data
            
        Returns:
            List of company dictionaries
        """
        # Try to load existing processed data first
        if not force_update:
            companies = self.load_processed_data()
            if companies:
                return companies
        
        # Download and process if needed
        if force_update or not os.path.exists(self.edinet_codes_file):
            if not self.download_edinet_codes(force_update=force_update):
                logger.error("Failed to download EDINET codes")
                return []
        
        # Process the data
        return self.process_edinet_data()
    


def get_data_loader() -> EdinetDataLoader:
    """Get the default data loader instance."""
    return EdinetDataLoader()