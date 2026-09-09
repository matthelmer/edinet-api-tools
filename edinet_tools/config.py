# config.py
import os

# edinet-tools reads EDINET_API_KEY from the process environment only. It
# does not load .env files itself — a library shouldn't mutate process env
# as an import side effect. If you keep your key in a .env file, load it in
# YOUR application before importing edinet_tools (e.g. via `python-dotenv`:
# `from dotenv import load_dotenv; load_dotenv()`).
#
# The key is resolved when a request is built, never at import: a key set
# after `import edinet_tools` (notebooks, load_dotenv()-after-import) must
# still be used, and `configure(api_key=...)` must reach the low-level
# fetchers. Nothing here logs — a missing key surfaces as AuthenticationError
# at the point of use, and offline paths (entity lookup, parsing) need no key.


def api_key(override: str | None = None) -> str | None:
    """The EDINET API key to send: explicit override, then `configure()`,
    then the EDINET_API_KEY environment variable, else None."""
    if override:
        return override
    from ._client import _configured_api_key  # lazy: _client imports api imports config
    return _configured_api_key or os.environ.get('EDINET_API_KEY')


# Kept for callers that read it; DO NOT use as a request default — it is a
# snapshot at import time. See api_key().
EDINET_API_KEY = os.environ.get('EDINET_API_KEY')

# One registry of document types: doc_types._DOC_TYPES. This used to be a
# second hand-maintained table that drifted (39 vs 42 codes; 290/310/330
# missing; 370/380 mislabelled) and gated filter_documents (2026-09-09).
from .doc_types import _DOC_TYPES as _REGISTRY

SUPPORTED_DOC_TYPES: dict[str, str] = {code: dt.name_en for code, dt in _REGISTRY.items()}
