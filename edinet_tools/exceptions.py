"""
Custom exceptions for EDINET Tools.

Provides clear, user-friendly error messages for common failure cases.
"""


class EdinetError(Exception):
    """Base exception for EDINET Tools."""
    pass


class APIError(EdinetError):
    """EDINET API related errors."""
    
    def __init__(self, message: str, status_code: int = None, response_text: str = None):
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(message)


class AuthenticationError(APIError):
    """API authentication/authorization errors."""
    
    def __init__(self, message: str = None):
        if not message:
            message = (
                "EDINET API authentication failed. "
                "Please check your API key and ensure it's valid. "
                "Get your API key from: https://disclosure.edinet-fsa.go.jp/"
            )
        super().__init__(message, status_code=401)


class RateLimitError(APIError):
    """API rate limit exceeded errors."""
    
    def __init__(self, message: str = None, retry_after: int = None):
        if not message:
            message = "EDINET API rate limit exceeded. Please wait before making more requests."
            if retry_after:
                message += f" Retry after {retry_after} seconds."
        self.retry_after = retry_after
        super().__init__(message, status_code=429)


class DocumentNotFoundError(EdinetError):
    """Document not found or not accessible."""
    
    def __init__(self, doc_id: str, message: str = None):
        self.doc_id = doc_id
        if not message:
            message = (
                f"Document '{doc_id}' not found or not accessible. "
                f"Please verify the document ID and ensure it's publicly available."
            )
        super().__init__(message)


class CompanyNotFoundError(EdinetError):
    """Company not found in lookup database."""
    
    def __init__(self, identifier: str, suggestions: list = None):
        self.identifier = identifier
        self.suggestions = suggestions or []
        
        message = f"Company '{identifier}' not found."
        
        if self.suggestions:
            message += f" Did you mean: {', '.join(self.suggestions[:3])}?"
        else:
            message += (
                f" Use edinet_tools.search_entities('{identifier}') to search the entity catalog."
            )
            
        super().__init__(message)


class ProcessingError(EdinetError):
    """Document processing and parsing errors."""
    
    def __init__(self, message: str, doc_id: str = None, details: str = None):
        self.doc_id = doc_id
        self.details = details
        
        full_message = f"Processing error: {message}"
        if doc_id:
            full_message += f" (Document: {doc_id})"
        if details:
            full_message += f"\nDetails: {details}"
            
        super().__init__(full_message)


class ConfigurationError(EdinetError):
    """Configuration and setup errors."""
    
    def __init__(self, message: str, fix_suggestion: str = None):
        self.fix_suggestion = fix_suggestion
        
        full_message = message
        if fix_suggestion:
            full_message += f"\nSuggestion: {fix_suggestion}"
            
        super().__init__(full_message)


class ValidationError(EdinetError):
    """Input validation errors."""
    
    def __init__(self, field: str, value: str, expected: str):
        self.field = field
        self.value = value
        self.expected = expected
        
        message = f"Invalid {field}: '{value}'. Expected: {expected}"
        super().__init__(message)


def suggest_companies(query: str, limit: int = 3) -> list:
    """
    Get company suggestions for a failed lookup.
    
    This is used internally by CompanyNotFoundError to provide helpful suggestions.
    """
    try:
        from .data import search_companies
        results = search_companies(query, limit=limit)
        return [f"{r['name_en']} ({r['ticker']})" for r in results]
    except:
        return []