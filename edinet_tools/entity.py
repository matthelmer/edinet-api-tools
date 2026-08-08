"""
Entity and Fund classes for EDINET data.

Entity wraps company/individual data from EdinetcodeDlInfo.csv.
Fund wraps investment fund data from FundcodeDlInfo.csv.
"""
import csv
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

from .entity_classifier import EntityClassifier


# Module-level cache for classifier instance
_classifier: EntityClassifier | None = None
# Module-level cache for fund data
_funds: dict[str, dict] | None = None
_funds_by_issuer: dict[str, list[str]] | None = None


def _get_classifier() -> EntityClassifier:
    """Get or create the shared EntityClassifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = EntityClassifier()
    return _classifier


class Entity:
    """
    An EDINET-registered entity (company, fund issuer, individual).

    Wraps data from EdinetcodeDlInfo.csv with convenient accessors.
    """

    def __init__(self, data: dict[str, Any], client: Any = None):
        self._data = data
        self._client = client

    @property
    def edinet_code(self) -> str:
        return self._data.get('edinet_code', '')

    @property
    def name_jp(self) -> str:
        return self._data.get('name_jp', '')

    @property
    def name_en(self) -> str | None:
        return self._data.get('name_en')

    @property
    def name_phonetic(self) -> str | None:
        return self._data.get('name_phonetic')

    @property
    def ticker(self) -> str | None:
        return self._data.get('ticker')

    @property
    def entity_type(self):
        """Fact-shaped entity classification from FSA registry data.

        Returns:
            EntityType enum value: LISTED_COMPANY, UNLISTED_COMPANY, FUND_ISSUER,
            INDIVIDUAL, or UNKNOWN.

        Replaces the deprecated is_listed and is_fund_issuer booleans, which
        collapsed the 5-valued FSA registry classification into 2-valued bools
        and silently coerced unknown cases to False.

        Examples:
            >>> from edinet_tools import EntityType
            >>> entity.entity_type == EntityType.LISTED_COMPANY  # was: entity.is_listed
            >>> entity.entity_type == EntityType.FUND_ISSUER     # was: entity.is_fund_issuer
        """
        classifier = _get_classifier()
        return classifier.get_entity_type(self.edinet_code)

    @property
    def submitter_type(self) -> str | None:
        return self._data.get('submitter_type')

    @property
    def industry(self) -> str | None:
        return self._data.get('industry')

    @property
    def province(self) -> str | None:
        return self._data.get('province')

    @property
    def capital(self) -> int | None:
        return self._data.get('capital')

    @property
    def accounting_period_end(self) -> str | None:
        return self._data.get('accounting_period_end')

    @property
    def corporate_number(self) -> str | None:
        return self._data.get('corporate_number')

    @property
    def name(self) -> str:
        """Primary name (English if available, else Japanese)."""
        return self.name_en or self.name_jp or ''

    @property
    def funds(self) -> list:
        """Funds issued by this entity (empty if not a fund issuer)."""
        # funds_by_issuer is defined later in this module; the fund-issuer
        # check reads _fund_edinet_codes directly to avoid the round-trip.
        classifier = _get_classifier()
        if self.edinet_code not in classifier._fund_edinet_codes:
            return []
        return funds_by_issuer(self.edinet_code)

    def documents(
        self,
        doc_type: str | None = None,
        days: int | None = None,
        days_back: int | None = None,  # Deprecated alias
    ) -> list:
        """
        Get documents filed by this entity.

        Args:
            doc_type: Filter by document type code (e.g., "350")
            days: Number of days to look back (default 30)
            days_back: Deprecated alias for days

        Returns:
            List of Document objects
        """
        from .document import Document
        from ._client import _get_client
        from .timezone import today_jst
        from datetime import timedelta

        # Handle deprecated parameter
        if days_back is not None and days is None:
            days = days_back
        if days is None:
            days = 30

        # Use explicit client if set, otherwise module-level client
        client = self._client if self._client is not None else _get_client()

        # Collect filings from each day (JST so we don't miss today's filings)
        all_filings = []
        today = today_jst()
        for i in range(days):
            check_date = today - timedelta(days=i)
            try:
                filings = client.get_documents_by_date(check_date)
                all_filings.extend(filings)
            except (AttributeError, TypeError) as e:
                # Programming errors should not be silently swallowed
                raise
            except Exception as e:
                # Log API/network errors but continue with other dates
                logger.debug(f"Failed to fetch documents for {check_date}: {e}")
                continue

        # Filter by this entity's EDINET code
        my_filings = [
            f for f in all_filings
            if f.get('edinetCode') == self.edinet_code
        ]

        # Filter by doc type if specified
        if doc_type:
            my_filings = [
                f for f in my_filings
                if f.get('docTypeCode') == doc_type
            ]

        # Convert to Document objects (pass client for fetch())
        return [Document(f, client=client) for f in my_filings]

    def __repr__(self) -> str:
        ticker_part = f", ticker='{self.ticker}'" if self.ticker else ""
        name_part = self.name_en or self.name_jp or ""
        if len(name_part) > 30:
            name_part = name_part[:27] + "..."
        return f"Entity(edinet_code='{self.edinet_code}'{ticker_part}, name='{name_part}')"


def _build_entity_from_classifier(edinet_code: str, classifier: EntityClassifier) -> Entity | None:
    """Build an Entity object from classifier data."""
    if edinet_code not in classifier._edinet_entities:
        return None

    raw = classifier._edinet_entities[edinet_code]
    ticker = classifier.get_securities_code(edinet_code)

    data = {
        'edinet_code': edinet_code,
        'name_jp': raw.get('name_jp', ''),
        'name_en': raw.get('name_en') or None,
        'name_phonetic': raw.get('name_phonetic') or None,
        'ticker': ticker,
        'is_listed': raw.get('is_listed', False),
        'submitter_type': raw.get('submitter_type'),
        'industry': raw.get('industry') or None,
        'corporate_number': raw.get('corporate_number') or None,
    }
    return Entity(data)


def entity_by_edinet_code(edinet_code: str) -> Entity | None:
    """
    Look up an entity by EDINET code.

    Args:
        edinet_code: EDINET code (e.g., "E02144")

    Returns:
        Entity object or None if not found
    """
    classifier = _get_classifier()
    return _build_entity_from_classifier(edinet_code, classifier)


# Shorter alias (v0.2)
def entity_by_code(edinet_code: str) -> Entity | None:
    """
    Look up an entity by EDINET code.

    Alias for entity_by_edinet_code().

    Args:
        edinet_code: EDINET code (e.g., "E02144")

    Returns:
        Entity object or None if not found
    """
    return entity_by_edinet_code(edinet_code)


def entity_by_ticker(ticker: str) -> Entity | None:
    """
    Look up an entity by stock ticker.

    Handles 4-digit numeric (e.g. '7203'), 5-digit numeric with trailing
    zero ('72030'), alphanumeric ('192A', '263A'), and the `.T` suffix
    convention ('7203.T').

    Args:
        ticker: Stock ticker.

    Returns:
        Entity object or None if not found.
    """
    if not ticker:
        return None

    # Strip .T or .t suffix if present (Tokyo Stock Exchange suffix)
    if ticker.upper().endswith('.T'):
        ticker = ticker[:-2]

    classifier = _get_classifier()

    # O(1) lookup via reverse index. The load step indexed both the
    # catalog 5-char form (e.g. '72030', '192A0') and the 4-char form
    # for codes ending in 0.
    edinet_code = classifier._by_securities_code.get(ticker)
    if edinet_code is None:
        # Try the 5-char form with trailing 0 (for cases where caller
        # passed a 4-char form but only the 5-char form was indexed)
        edinet_code = classifier._by_securities_code.get(ticker + '0')
    if edinet_code is None:
        return None
    return _build_entity_from_classifier(edinet_code, classifier)


def entity_by_corporate_number(num: str | None) -> Entity | None:
    """
    Look up an entity by Japan Corporate Number (法人番号).

    The 法人番号 is a 13-digit identifier issued by Japan's National Tax
    Agency. It is globally unique within Japan and never reused, making
    it the canonical disambiguator when name-based resolution is ambiguous.

    Args:
        num: 13-digit Japan Corporate Number, or None.

    Returns:
        Entity object or None if not found / not assigned in catalog.
    """
    if not num or not isinstance(num, str):
        return None

    classifier = _get_classifier()
    edinet_code = classifier._by_corporate_number.get(num)
    if edinet_code is None:
        return None
    return _build_entity_from_classifier(edinet_code, classifier)


def search_entities(query: str, limit: int = 10) -> list[Entity]:
    """
    Search for entities by name.

    Results are ranked by relevance:
    1. Exact name match (highest priority)
    2. Name starts with query
    3. Listed companies over unlisted
    4. Query appears earlier in name

    Names and queries are normalized via normalize_for_matching() before
    comparison — NFKC width-folding, (株)/(有) rewrites, whitespace strip,
    lowercase — so visually-identical strings with different encodings
    match correctly.

    Args:
        query: Search string (matches Japanese or English names)
        limit: Maximum number of results to return

    Returns:
        List of matching Entity objects, sorted by relevance

    Note:
        Also available as search() for brevity.
    """
    if not query or not query.strip():
        return []

    from .normalize import normalize_for_matching

    classifier = _get_classifier()
    q_norm = normalize_for_matching(query)

    # Post-normalize empty guard (e.g., query was all whitespace variants)
    if not q_norm:
        return []

    # Exact-match path (O(1)): hit the reverse index first.
    # Try the whitespace-preserved form first; if that misses, also try the
    # whitespace-collapsed form. This handles the case where the query and
    # catalog use different spacing conventions (common for Japanese
    # individual names: "伊藤 翔太" vs "伊藤翔太").
    exact_codes = classifier._by_normalized_name.get(q_norm, [])
    if not exact_codes:
        q_nows = ''.join(q_norm.split())
        if q_nows and q_nows != q_norm:
            exact_codes = classifier._by_normalized_name.get(q_nows, [])
    if exact_codes:
        # Rank within the exact-match set: listed > unlisted, then name length
        ranked = []
        for code in exact_codes:
            raw = classifier._edinet_entities[code]
            listed_penalty = 0 if raw.get('is_listed') else 500
            name_len = len(raw.get('name_en') or raw.get('name_jp') or '')
            ranked.append((listed_penalty, name_len, code))
        ranked.sort(key=lambda x: (x[0], x[1]))
        results = []
        for _, _, code in ranked[:limit]:
            e = _build_entity_from_classifier(code, classifier)
            if e:
                results.append(e)
        return results

    # Substring-scan fallback (O(N)): use pre-normalized forms on both sides
    matches = []
    for edinet_code, raw in classifier._edinet_entities.items():
        norm_jp = raw.get('_normalized', '')
        norm_en = raw.get('_normalized_en', '')

        if q_norm in norm_jp or q_norm in norm_en:
            score = 1000  # Base score (only reached if not exact — exact was index-handled above)

            # Name starts with query
            if norm_en.startswith(q_norm) or norm_jp.startswith(q_norm):
                score = 100
            else:
                pos_en = norm_en.find(q_norm) if q_norm in norm_en else 999
                pos_jp = norm_jp.find(q_norm) if q_norm in norm_jp else 999
                score = 200 + min(pos_en, pos_jp)

            if not raw.get('is_listed', False):
                score += 500

            name_len = len(raw.get('name_en') or '') or len(raw.get('name_jp') or '') or 999
            matches.append((score, name_len, edinet_code))

    matches.sort(key=lambda x: (x[0], x[1]))

    results = []
    for score, name_len, edinet_code in matches[:limit]:
        e = _build_entity_from_classifier(edinet_code, classifier)
        if e:
            results.append(e)
    return results


# Shorter alias (v0.2)
def search(query: str, limit: int = 10) -> list[Entity]:
    """
    Search for entities by name.

    Alias for search_entities().

    Args:
        query: Search string (matches Japanese or English names)
        limit: Maximum number of results to return

    Returns:
        List of matching Entity objects, sorted by relevance
    """
    return search_entities(query, limit)


def entity(identifier: str) -> Entity | None:
    """
    Smart lookup for an entity by ticker, EDINET code, or name.

    Resolution order:
    1. EDINET code pattern (starts with 'E', 6 characters)
    2. Ticker pattern (4-5 digits, optional .T suffix)
    3. Name search (returns first match)

    Args:
        identifier: Ticker, EDINET code, or company name

    Returns:
        Entity object or None if not found
    """
    if not identifier:
        return None

    # Check for EDINET code pattern
    if re.match(r'^E\d{5}$', identifier):
        return entity_by_edinet_code(identifier)

    # Check for ticker pattern (4-5 digits, optional .T suffix)
    ticker_match = re.match(r'^(\d{4,5})(\.T)?$', identifier, re.IGNORECASE)
    if ticker_match:
        return entity_by_ticker(identifier)

    # Fall back to name search
    results = search_entities(identifier, limit=1)
    return results[0] if results else None


def _load_funds() -> tuple[dict[str, dict], dict[str, list[str]]]:
    """Load and index fund data from FundcodeDlInfo.csv."""
    global _funds, _funds_by_issuer
    if _funds is not None:
        return _funds, _funds_by_issuer

    classifier = _get_classifier()
    _funds = {}
    _funds_by_issuer = {}

    # Read fund CSV
    # Columns: 0=Fund Code, 1=Securities Code, 2=Fund Name, 3=Name Phonetic,
    #          4=Type, 5=Closing Date 1, 6=Closing Date 2, 7=EDINET Code, 8=Issuer Name
    with open(classifier.fund_codes_path, 'r', encoding='cp932', errors='replace') as f:
        reader = csv.reader(f)
        next(reader)  # Skip metadata row
        next(reader)  # Skip header row
        for row in reader:
            if len(row) >= 9:
                fund_code = row[0].strip()
                if fund_code:
                    fund_data = {
                        'fund_code': fund_code,
                        'securities_code': row[1].strip() or None,
                        'name': row[2].strip(),
                        'name_phonetic': row[3].strip() or None,
                        'fund_type': row[4].strip() or None,
                        'accounting_date_1': row[5].strip() or None,
                        'accounting_date_2': row[6].strip() or None,
                        'issuer_edinet_code': row[7].strip(),
                        'issuer_name': row[8].strip(),
                    }
                    _funds[fund_code] = fund_data

                    # Index by issuer
                    issuer_code = fund_data['issuer_edinet_code']
                    if issuer_code:
                        if issuer_code not in _funds_by_issuer:
                            _funds_by_issuer[issuer_code] = []
                        _funds_by_issuer[issuer_code].append(fund_code)

    return _funds, _funds_by_issuer


class Fund:
    """
    An investment fund from EDINET's FundcodeDlInfo.csv.

    Provides access to fund metadata and issuer information.
    """

    def __init__(self, data: dict[str, Any]):
        self._data = data

    @property
    def fund_code(self) -> str:
        return self._data.get('fund_code', '')

    @property
    def securities_code(self) -> str | None:
        return self._data.get('securities_code')

    @property
    def name(self) -> str:
        return self._data.get('name', '')

    @property
    def name_phonetic(self) -> str | None:
        return self._data.get('name_phonetic')

    @property
    def fund_type(self) -> str | None:
        return self._data.get('fund_type')

    @property
    def issuer_edinet_code(self) -> str:
        return self._data.get('issuer_edinet_code', '')

    @property
    def issuer_name(self) -> str:
        return self._data.get('issuer_name', '')

    @property
    def issuer(self) -> Entity | None:
        """The entity (asset management company) that issues this fund."""
        if self.issuer_edinet_code:
            return entity_by_edinet_code(self.issuer_edinet_code)
        return None

    def __repr__(self) -> str:
        name = self.name
        if len(name) > 30:
            name = name[:27] + "..."
        issuer = self.issuer_name
        if len(issuer) > 20:
            issuer = issuer[:17] + "..."
        return f"Fund(code='{self.fund_code}', name='{name}', issuer='{issuer}')"


def fund(identifier: str) -> Fund | None:
    """
    Look up a fund by fund code or name.

    Args:
        identifier: Fund code (e.g., "G01003") or fund name

    Returns:
        Fund object or None if not found
    """
    funds, _ = _load_funds()

    # Try exact fund code lookup first
    if identifier in funds:
        return Fund(funds[identifier])

    # Try name search
    identifier_lower = identifier.lower()
    for fund_code, fund_data in funds.items():
        if identifier_lower in fund_data.get('name', '').lower():
            return Fund(fund_data)

    return None


def funds_by_issuer(edinet_code: str) -> list[Fund]:
    """
    Get all funds issued by a specific entity.

    Args:
        edinet_code: EDINET code of the fund issuer

    Returns:
        List of Fund objects issued by this entity
    """
    funds, by_issuer = _load_funds()
    fund_codes = by_issuer.get(edinet_code, [])
    return [Fund(funds[fc]) for fc in fund_codes]
