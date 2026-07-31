"""
Entity classification for EDINET filers using official FSA data.

Uses two official data sources:
- EdinetcodeDlInfo.csv: All EDINET-registered entities
- FundcodeDlInfo.csv: Investment fund registry

IMPORTANT: Uses official data only. No keyword matching.

FSA serves both English and Japanese variants of these CSVs depending
on which download endpoint produced the file. The schemas are identical
(same column order, same row-by-row data) — only the column headers
and a handful of translatable values differ. The loader resolves columns
by header name (trying both language variants) so it works against either
variant and fails loudly if a column is ever renamed.
"""
from enum import Enum
from pathlib import Path
import csv
import re
import glob


# --- CSV schema resolution ---------------------------------------------------
#
# For each logical field, list the known header names in priority order.
# At load time we find whichever header appears and remember its column
# index. This is robust to the EN/JP format split (FSA serves Japanese
# from the default download endpoint as of 2026-04) and will fail with a
# clear error if FSA ever renames a column entirely.

_EDINET_COLUMN_ALIASES = {
    "edinet_code":      ("EDINET Code",                         "ＥＤＩＮＥＴコード"),
    "submitter_type":   ("Type of Submitter",                   "提出者種別"),
    "listed":           ("Listed company / Unlisted company",   "上場区分"),
    "name_jp":          ("Submitter Name",                      "提出者名"),
    "name_en":          ("Submitter Name（alphabetic）",         "提出者名（英字）"),
    "name_phonetic":    ("Submitter Name（phonetic）",           "提出者名（ヨミ）"),
    "industry":         ("Submitter's industry",                "提出者業種"),
    "securities_code":  ("Securities Identification Code",      "証券コード"),
    "corporate_number": ("Submitter's Japan Corporate Number",  "提出者法人番号"),
}

_FUND_COLUMN_ALIASES = {
    "edinet_code": ("EDINET Code", "ＥＤＩＮＥＴコード"),
}

# Known value synonyms for the listed-status column. The English variant
# writes "Listed company" / "Unlisted company"; the Japanese variant writes
# "上場" / "非上場".
_LISTED_VALUES = frozenset(("Listed company", "上場"))

# JP → EN translation for the industry column. FSA's Japanese CSV uses
# these 39 values; they collapse to 34 distinct English values (5 entity-
# type variants — foreign entity, individual, etc. — all translate to
# "Others" in the English CSV). Extracted from matched EN/JP snapshots.
_INDUSTRY_JP_TO_EN = {
    "その他製品": "Other Products",
    "その他金融業": "Other Financing Business",
    "ガラス・土石製品": "Glass & Ceramics Products",
    "ゴム製品": "Rubber Products",
    "サービス業": "Services",
    "パルプ・紙": "Pulp & Paper",
    "不動産業": "Real Estate",
    "保険業": "Insurance",
    "倉庫・運輸関連": "Warehousing & Harbor Transportation Services",
    "個人（組合発行者を除く）": "Others",
    "個人（非居住者）（組合発行者を除く）": "Others",
    "内国法人・組合（有価証券報告書等の提出義務者以外）": "Others",
    "化学": "Chemicals",
    "医薬品": "Pharmaceutical",
    "卸売業": "Wholesale Trade",
    "外国政府等": "Others",
    "外国法人・組合": "Others",
    "外国法人・組合（有価証券報告書等の提出義務者以外）": "Others",
    "小売業": "Retail Trade",
    "建設業": "Construction",
    "情報・通信業": "Information & Communication",
    "機械": "Machinery",
    "水産・農林業": "Fishery, Agriculture & Forestry",
    "海運業": "Marine Transportation",
    "石油・石炭製品": "Oil & Coal Products",
    "空運業": "Air Transportation",
    "精密機器": "Precision Instruments",
    "繊維製品": "Textiles & Apparels",
    "証券、商品先物取引業": "Securities & Commodity Futures",
    "輸送用機器": "Transportation Equipments",
    "金属製品": "Metal Products",
    "鉄鋼": "Iron & Steel",
    "鉱業": "Mining",
    "銀行業": "Banks",
    "陸運業": "Land Transportation",
    "電気・ガス業": "Electric Power & Gas",
    "電気機器": "Electric Appliances",
    "非鉄金属": "Nonferrous Metals",
    "食料品": "Foods",
}


def _resolve_columns(header: list[str], aliases: dict[str, tuple]) -> dict[str, int]:
    """Map each logical field to its column index in ``header``.

    For each (field, alias-tuple) pair, scan the header for the first
    alias that appears and record its index. Raises ValueError naming the
    missing field if none of a field's aliases are found — so FSA schema
    changes fail loudly rather than silently returning wrong data.
    """
    positions: dict[str, int] = {}
    for field, alias_tuple in aliases.items():
        for alias in alias_tuple:
            if alias in header:
                positions[field] = header.index(alias)
                break
        else:
            raise ValueError(
                f"No column found for {field!r} in CSV header. "
                f"Tried aliases {alias_tuple!r}. Got header: {header!r}. "
                f"FSA may have changed the schema — update _EDINET_COLUMN_ALIASES."
            )
    return positions


def translate_industry_to_english(value: str | None) -> str | None:
    """Translate a Japanese industry value to its English equivalent.

    Returns the input unchanged if it's already English (or any unknown
    value). Useful for downstream code that normalizes industry strings
    without caring which CSV variant the underlying data came from.
    """
    if value is None:
        return None
    return _INDUSTRY_JP_TO_EN.get(value, value)


class EntityType(Enum):
    """Classification of EDINET-registered entities."""
    FUND = "fund"
    LISTED_COMPANY = "listed_company"
    UNLISTED_COMPANY = "unlisted_company"
    INDIVIDUAL = "individual"
    UNKNOWN = "unknown"


class EntityClassifier:
    """
    Classify EDINET entities using official FSA data.

    Data sources:
    - EdinetcodeDlInfo.csv: All EDINET-registered entities (11,000+ entities)
    - FundcodeDlInfo.csv: Investment fund registry (6,000+ funds, ~300 unique issuers)

    IMPORTANT: Uses official data only. No keyword matching.

    Usage:
        classifier = EntityClassifier()
        classifier.get_entity_type('E00001')  # -> EntityType.LISTED_COMPANY
        classifier.is_fund('E12345')          # -> True
        classifier.is_known('E99999')         # -> False (stale data indicator)
    """

    def __init__(self, edinet_codes_path: str = None, fund_codes_path: str = None):
        """
        Initialize classifier with data files.

        Args:
            edinet_codes_path: Path to EdinetcodeDlInfo CSV (auto-detected if None)
            fund_codes_path: Path to FundcodeDlInfo CSV (auto-detected if None)
        """
        self.edinet_codes_path = edinet_codes_path or self._find_latest_file('EdinetcodeDlInfo')
        self.fund_codes_path = fund_codes_path or self._find_latest_file('FundcodeDlInfo')

        if not self.edinet_codes_path:
            raise FileNotFoundError("No EdinetcodeDlInfo CSV found in data directory")
        if not self.fund_codes_path:
            raise FileNotFoundError("No FundcodeDlInfo CSV found in data directory")

        # Extract dates from filenames for version tracking
        self.edinet_codes_date = self._extract_date(self.edinet_codes_path)
        self.fund_codes_date = self._extract_date(self.fund_codes_path)

        self._load_data()

    def _find_latest_file(self, prefix: str) -> str | None:
        """Find the latest dated file matching prefix in data directory."""
        data_dir = Path(__file__).parent / 'data'
        pattern = str(data_dir / f'{prefix}*.csv')
        matches = glob.glob(pattern)

        if not matches:
            return None

        # Sort by filename (dated files will sort chronologically)
        matches.sort(reverse=True)
        return matches[0]

    def _extract_date(self, path: str) -> str:
        """Extract date from filename like 'EdinetcodeDlInfo_20251205.csv'."""
        match = re.search(r'_(\d{8})\.csv$', str(path))
        if match:
            d = match.group(1)
            return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        return "unknown"

    def _load_data(self):
        """Load and index both CSV files."""
        from .normalize import normalize_for_matching

        self._fund_edinet_codes = set()
        self._edinet_entities = {}  # edinet_code -> entity info

        # Reverse indexes for O(1) lookups (v0.6.0)
        self._by_normalized_name = {}      # normalized name -> list[edinet_code]
        self._by_securities_code = {}      # securities_code -> edinet_code
        self._by_corporate_number = {}     # 法人番号 -> edinet_code

        # Load fund codes (Shift-JIS encoded). We only need the issuer's
        # EDINET code from this file, but we still resolve it by header so
        # that a schema change surfaces immediately instead of silently
        # indexing the wrong column.
        with open(self.fund_codes_path, 'r', encoding='cp932', errors='replace') as f:
            reader = csv.reader(f)
            next(reader, None)  # metadata row (download date, count)
            header = next(reader, None)
            if header is None:
                raise ValueError(f"Empty fund codes file: {self.fund_codes_path}")
            fund_col = _resolve_columns(header, _FUND_COLUMN_ALIASES)
            idx_edinet = fund_col["edinet_code"]
            for row in reader:
                if len(row) <= idx_edinet:
                    continue
                edinet_code = row[idx_edinet].strip()
                if edinet_code.startswith('E'):
                    self._fund_edinet_codes.add(edinet_code)

        # Load EDINET codes (Shift-JIS encoded). Resolve every column by
        # header alias so the loader handles both EN and JP CSV variants.
        with open(self.edinet_codes_path, 'r', encoding='cp932', errors='replace') as f:
            reader = csv.reader(f)
            next(reader, None)  # metadata row
            header = next(reader, None)
            if header is None:
                raise ValueError(f"Empty EDINET codes file: {self.edinet_codes_path}")
            col = _resolve_columns(header, _EDINET_COLUMN_ALIASES)
            max_idx = max(col.values())
            for row in reader:
                if len(row) <= max_idx:
                    continue
                edinet_code = row[col["edinet_code"]].strip()
                if not edinet_code.startswith('E'):
                    continue

                name_jp = row[col["name_jp"]].strip() or None
                name_en = row[col["name_en"]].strip() or None
                name_phonetic = row[col["name_phonetic"]].strip() or None
                securities_code = row[col["securities_code"]].strip() or None
                corporate_number = row[col["corporate_number"]].strip() or None
                industry_raw = row[col["industry"]].strip() or None

                # Pre-compute normalized forms for substring-scan fallback
                normalized_jp = normalize_for_matching(name_jp)
                normalized_en = normalize_for_matching(name_en)

                self._edinet_entities[edinet_code] = {
                    'submitter_type': row[col["submitter_type"]].strip(),
                    'is_listed': row[col["listed"]].strip() in _LISTED_VALUES,
                    'name_jp': name_jp,
                    'name_en': name_en,
                    'name_phonetic': name_phonetic,
                    # Industry values may be Japanese or English depending
                    # on CSV variant. Normalize `industry` to English for
                    # stable downstream behavior (backward compatible with
                    # the 0.5.0 shape) and preserve the raw Japanese value
                    # separately.
                    'industry': translate_industry_to_english(industry_raw),
                    'industry_jp': industry_raw,
                    'securities_code': securities_code,
                    'corporate_number': corporate_number,
                    '_normalized': normalized_jp,    # primary
                    '_normalized_en': normalized_en, # fallback for EN-only queries
                }

                # Build reverse indexes — index each name under BOTH its
                # whitespace-preserved form and its whitespace-collapsed form.
                # This recovers individual names like "伊藤翔太" vs "伊藤 翔太"
                # without false-positives in the substring-fallback scan
                # (which uses the whitespace-preserved form on both sides).
                seen_keys = set()
                for n in (normalized_jp, normalized_en):
                    if not n or n in seen_keys:
                        continue
                    seen_keys.add(n)
                    self._by_normalized_name.setdefault(n, []).append(edinet_code)
                    n_nows = ''.join(n.split())  # whitespace-collapsed form
                    if n_nows and n_nows != n and n_nows not in seen_keys:
                        seen_keys.add(n_nows)
                        self._by_normalized_name.setdefault(n_nows, []).append(edinet_code)
                if securities_code:
                    self._by_securities_code[securities_code] = edinet_code
                    # Also index the 4-digit form (strip trailing 0 for 5-digit-ending-in-0 codes)
                    if len(securities_code) == 5 and securities_code.endswith('0'):
                        self._by_securities_code[securities_code[:4]] = edinet_code
                if corporate_number:
                    self._by_corporate_number[corporate_number] = edinet_code

    def get_entity_type(self, edinet_code: str) -> EntityType:
        """
        Determine entity type from official data.

        Args:
            edinet_code: EDINET code (e.g., 'E00001')

        Returns:
            EntityType classification

        Note:
            Some listed companies (e.g. Credit Saison E03041, JAFCO E04806)
            also appear in the fund registry because they have issued fund
            products. For investors they are listed equities, not funds, so
            listed-company status from the EDINET registry takes precedence
            over fund-registry membership.
        """
        if not edinet_code:
            return EntityType.UNKNOWN

        entity = self._edinet_entities.get(edinet_code)

        # Listed status from the EDINET registry wins, even if the entity
        # also appears in the fund registry.
        if entity and entity['is_listed']:
            return EntityType.LISTED_COMPANY

        # Fund registry takes precedence over unlisted classification.
        if edinet_code in self._fund_edinet_codes:
            return EntityType.FUND

        if not entity:
            return EntityType.UNKNOWN

        # Check submitter type for individuals
        # Japanese: '個人' means individual
        if '個人' in entity['submitter_type']:
            return EntityType.INDIVIDUAL

        return EntityType.UNLISTED_COMPANY

    def is_fund(self, edinet_code: str) -> bool:
        """Check if entity is an investment fund issuer."""
        return edinet_code in self._fund_edinet_codes

    def is_known(self, edinet_code: str) -> bool:
        """
        Check if entity exists in our data.

        Returns False for unknown codes, which indicates either:
        - Stale reference data (need to update CSVs)
        - Invalid EDINET code
        """
        return edinet_code in self._edinet_entities or edinet_code in self._fund_edinet_codes

    def get_securities_code(self, edinet_code: str) -> str | None:
        """
        Get 4-digit securities code for listed companies.

        Args:
            edinet_code: EDINET code

        Returns:
            4-digit securities code (e.g., '7203' for Toyota) or None
        """
        entity = self._edinet_entities.get(edinet_code)
        if entity and entity.get('securities_code'):
            code = entity['securities_code']
            # Convert 5-digit (12340) to 4-digit (1234)
            if len(code) == 5 and code.endswith('0'):
                return code[:4]
            return code if code else None
        return None

    def get_entity_name(self, edinet_code: str, prefer_english: bool = True) -> str | None:
        """
        Get entity name.

        Args:
            edinet_code: EDINET code
            prefer_english: If True, return English name if available

        Returns:
            Entity name or None
        """
        entity = self._edinet_entities.get(edinet_code)
        if not entity:
            return None

        if prefer_english and entity.get('name_en'):
            return entity['name_en']
        return entity.get('name_jp')

    @property
    def data_version(self) -> dict:
        """Return data file versions for staleness tracking."""
        return {
            'edinet_codes': self.edinet_codes_date,
            'fund_codes': self.fund_codes_date
        }

    @property
    def stats(self) -> dict:
        """Return statistics about loaded data."""
        listed = sum(1 for e in self._edinet_entities.values() if e['is_listed'])
        return {
            'total_entities': len(self._edinet_entities),
            'listed_companies': listed,
            'unlisted_entities': len(self._edinet_entities) - listed,
            'fund_issuers': len(self._fund_edinet_codes)
        }

    def __repr__(self) -> str:
        return (
            f"EntityClassifier("
            f"entities={len(self._edinet_entities)}, "
            f"funds={len(self._fund_edinet_codes)}, "
            f"version={self.data_version})"
        )
