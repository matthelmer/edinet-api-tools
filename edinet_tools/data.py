"""
Company data and lookup functionality for EDINET Tools.

Provides ticker symbol to EDINET code mapping and company search capabilities
using official EDINET codes from the Japanese government.
"""

from typing import Dict, List, Optional, Any
import logging
from .data_loader import get_data_loader
from .normalize import normalize_for_matching
import difflib

logger = logging.getLogger(__name__)

# This will be populated from official EDINET data
_company_data_cache = None



class CompanyLookup:
    """Company lookup and search functionality using official EDINET data."""
    
    def __init__(self, force_update: bool = False):
        self.data_loader = get_data_loader()
        self._load_company_data(force_update)
        
        # Create lookup maps
        self._build_lookup_maps()
        
        # Create name search indexes
        self._build_search_indexes()
    
    def _load_company_data(self, force_update: bool = False):
        """Load company data from official EDINET sources."""
        global _company_data_cache
        
        if _company_data_cache is None or force_update:
            try:
                # Load companies from official EDINET data
                _company_data_cache = self.data_loader.get_companies(force_update=force_update)
                logger.info(f"Loaded {len(_company_data_cache)} companies from EDINET data")
            except Exception as e:
                logger.error(f"Failed to load EDINET data: {e}")
                # Fallback to minimal dataset
                _company_data_cache = self._get_fallback_companies()
                logger.warning(f"Using fallback dataset with {len(_company_data_cache)} companies")
        
        self.companies = _company_data_cache
    
    def _get_fallback_companies(self) -> List[Dict]:
        """Fallback to minimal hardcoded dataset if EDINET data fails."""
        return [
            {
                'edinet_code': 'E02144',
                'ticker': '7203',
                'name_ja': 'トヨタ自動車株式会社',
                'name_en': 'Toyota Motor Corporation',
                'industry': 'Automobiles',
                'listed': True,
                'search_text': 'トヨタ自動車株式会社 toyota motor corporation 7203'
            },
            {
                'edinet_code': 'E02218',
                'ticker': '6758',
                'name_ja': 'ソニーグループ株式会社',
                'name_en': 'Sony Group Corporation',
                'industry': 'Electronics',
                'listed': True,
                'search_text': 'ソニーグループ株式会社 sony group corporation 6758'
            },
            {
                'edinet_code': 'E04425',
                'ticker': '9984',
                'name_ja': 'ソフトバンクグループ株式会社',
                'name_en': 'SoftBank Group Corp',
                'industry': 'Telecommunications',
                'listed': True,
                'search_text': 'ソフトバンクグループ株式会社 softbank group corp 9984'
            },
            {
                'edinet_code': 'E01959',
                'ticker': '6861',
                'name_ja': '株式会社キーエンス',
                'name_en': 'Keyence Corporation',
                'industry': 'Electronic Equipment',
                'listed': True,
                'search_text': '株式会社キーエンス keyence corporation 6861'
            },
            {
                'edinet_code': 'E03492',
                'ticker': '8306',
                'name_ja': '株式会社三菱ＵＦＪフィナンシャル・グループ',
                'name_en': 'Mitsubishi UFJ Financial Group',
                'industry': 'Banking',
                'listed': True,
                'search_text': '株式会社三菱ＵＦＪフィナンシャル・グループ mitsubishi ufj financial group 8306'
            }
        ]
    
    def _build_lookup_maps(self):
        """Build ticker and EDINET lookup maps."""
        self.ticker_to_edinet_map = {}
        self.edinet_to_ticker_map = {}
        self.edinet_to_company = {}
        
        for company in self.companies:
            edinet_code = company['edinet_code']
            ticker = company.get('ticker', '').strip()
            
            if ticker:
                # Store the original ticker
                self.ticker_to_edinet_map[ticker] = edinet_code
                self.edinet_to_ticker_map[edinet_code] = ticker
                
                # Also store common variations for easier lookup
                if ticker.endswith('0') and len(ticker) == 5:
                    # If it's a 5-digit ticker ending in 0, also map the 4-digit version
                    short_ticker = ticker[:-1]
                    if short_ticker not in self.ticker_to_edinet_map:
                        self.ticker_to_edinet_map[short_ticker] = edinet_code
                elif len(ticker) == 4:
                    # If it's a 4-digit ticker, also map the 5-digit version
                    long_ticker = ticker + '0'
                    if long_ticker not in self.ticker_to_edinet_map:
                        self.ticker_to_edinet_map[long_ticker] = edinet_code
            
            self.edinet_to_company[edinet_code] = company
    
    def _build_search_indexes(self):
        """Build search indexes for company names.

        Index keys are normalized via normalize_for_matching (NFKC
        width-folding + (株)/(有) rewrites + lowercase) so full-width /
        half-width variants of visually identical names share one key.
        Queries are normalized the same way at lookup time.
        """
        self.name_to_edinet = {}

        for company in self.companies:
            edinet_code = company['edinet_code']

            # Add Japanese name variations
            name_ja = company.get('name_ja', '')
            if name_ja:
                self.name_to_edinet[normalize_for_matching(name_ja)] = edinet_code
                # Remove common suffixes for easier search
                for suffix in ['株式会社', '(株)', 'カ)', 'カブシキガイシャ']:
                    clean_name = normalize_for_matching(name_ja.replace(suffix, ''))
                    if clean_name:
                        self.name_to_edinet[clean_name] = edinet_code

            # Add English name variations
            name_en = company.get('name_en', '')
            if name_en:
                self.name_to_edinet[normalize_for_matching(name_en)] = edinet_code
                # Remove common suffixes
                for suffix in [' corporation', ' corp', ' ltd', ' limited', ' inc', ' co']:
                    clean_name = normalize_for_matching(name_en.lower().replace(suffix, ''))
                    if clean_name:
                        self.name_to_edinet[clean_name] = edinet_code
    
    def ticker_to_edinet(self, ticker: str) -> Optional[str]:
        """Convert ticker symbol to EDINET code."""
        # Handle both with and without .T suffix and whitespace
        clean_ticker = ticker.strip().replace('.T', '').replace('.JP', '')
        
        # Try exact match first
        result = self.ticker_to_edinet_map.get(clean_ticker)
        if result:
            return result
        
        # Try with trailing zero (EDINET format: 7203 -> 72030)
        padded_ticker = clean_ticker + '0'
        result = self.ticker_to_edinet_map.get(padded_ticker)
        if result:
            return result
        
        # Try without trailing zero (if input was already padded)
        if clean_ticker.endswith('0') and len(clean_ticker) == 5:
            unpadded_ticker = clean_ticker[:-1]
            result = self.ticker_to_edinet_map.get(unpadded_ticker)
            if result:
                return result
        
        return None
    
    def edinet_to_ticker_code(self, edinet_code: str) -> Optional[str]:
        """Convert EDINET code to ticker symbol."""
        return self.edinet_to_ticker_map.get(edinet_code)
    
    def resolve_company_identifier(self, identifier: str) -> Optional[str]:
        """
        Resolve various company identifiers to EDINET code.
        
        Accepts:
        - Ticker symbols (7203, 7203.T)
        - EDINET codes (E02144)
        - Company names (Toyota, トヨタ)
        
        Returns EDINET code or None if not found.
        """
        identifier = identifier.strip()
        
        # Already an EDINET code
        if identifier.startswith('E') and len(identifier) == 6:
            return identifier
        
        # Try ticker lookup
        edinet_code = self.ticker_to_edinet(identifier)
        if edinet_code:
            return edinet_code
        
        # Try name lookup (index keys are normalize_for_matching-normalized)
        edinet_code = self.name_to_edinet.get(normalize_for_matching(identifier))
        if edinet_code:
            return edinet_code

        return None
    
    def search_companies(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search companies by name or ticker using fuzzy matching.
        
        Args:
            query: Search term
            limit: Maximum number of results
            
        Returns:
            List of matching company information
        """
        # Width-fold + lowercase both sides (NFKC): full-width queries
        # (ＱＰＳ, ＫＥＹＥＮＣＥ — what Japanese IMEs naturally produce)
        # must match ASCII search_text and vice versa.
        query = normalize_for_matching(query)

        # Return empty list for empty queries
        if not query:
            return []

        matches = []

        for company in self.companies:
            score = 0

            # Exact ticker match
            if query == company.get('ticker', ''):
                score = 100

            # Check search text for fuzzy matching
            search_text = normalize_for_matching(company.get('search_text', ''))
            
            # Exact substring match
            if query in search_text:
                score = 90
            
            # Fuzzy matching using difflib for partial matches
            if score == 0:
                # Split search text into words and check each
                words = search_text.split()
                for word in words:
                    # Check if query is similar to any word
                    similarity = difflib.SequenceMatcher(None, query, word).ratio()
                    if similarity > 0.6:  # 60% similarity threshold
                        score = max(score, int(similarity * 80))
            
            # Industry/category match. Match against both English and
            # Japanese forms so users can search in either language
            # regardless of which CSV variant produced the cache.
            industry_en = company.get('industry', '').lower()
            industry_jp = company.get('industry_jp', '').lower()
            if (query in industry_en) or (industry_jp and query in industry_jp):
                score = max(score, 50)
            
            if score > 0:
                match = {
                    'edinet_code': company['edinet_code'],
                    'ticker': company.get('ticker'),
                    'name_ja': company.get('name_ja'),
                    'name_en': company.get('name_en'),
                    'industry': company.get('industry'),
                    'listed': company.get('listed'),
                    'match_score': score
                }
                matches.append(match)
        
        # Sort by match score and limit results
        matches.sort(key=lambda x: x['match_score'], reverse=True)
        return matches[:limit]
    
    def get_company_info(self, edinet_code: str) -> Optional[Dict[str, Any]]:
        """Get company information by EDINET code."""
        return self.edinet_to_company.get(edinet_code)
    
    def get_supported_companies(self) -> List[Dict[str, Any]]:
        """Get list of all supported companies."""
        return sorted(self.companies, key=lambda x: x.get('ticker', '') or x['edinet_code'])
    
    def update_data(self, force_update: bool = True):
        """Update company data from official EDINET sources."""
        global _company_data_cache
        _company_data_cache = None
        self._load_company_data(force_update=force_update)
        self._build_lookup_maps()
        self._build_search_indexes()
        logger.info("Company data updated successfully")


# Global instance for package use (will be initialized on first access)
_company_lookup = None

def _get_company_lookup():
    """Get or create the global company lookup instance."""
    global _company_lookup
    if _company_lookup is None:
        _company_lookup = CompanyLookup()
    return _company_lookup

# Convenience functions
def ticker_to_edinet(ticker: str) -> Optional[str]:
    """Convert ticker symbol to EDINET code."""
    return _get_company_lookup().ticker_to_edinet(ticker)

def resolve_company(identifier: str) -> Optional[str]:
    """Resolve company identifier to EDINET code.""" 
    return _get_company_lookup().resolve_company_identifier(identifier)

def search_companies(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search companies by name or ticker."""
    return _get_company_lookup().search_companies(query, limit)

def get_company_info(edinet_code: str) -> Optional[Dict[str, Any]]:
    """Get company information by EDINET code."""
    return _get_company_lookup().get_company_info(edinet_code)

def get_supported_companies() -> List[Dict[str, Any]]:
    """Get list of all supported companies."""
    return _get_company_lookup().get_supported_companies()

def update_company_data(force_update: bool = True):
    """Update company data from official EDINET sources."""
    return _get_company_lookup().update_data(force_update=force_update)