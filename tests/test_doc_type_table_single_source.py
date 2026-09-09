"""There is one registry of EDINET document types: `doc_types._DOC_TYPES`.
`config.SUPPORTED_DOC_TYPES` was a second, hand-maintained copy that had
drifted — 39 entries against 42, missing 290 / 310 / 330 (tender-offer
opinion, Q&A, exemption) while listing their amendment codes, and mislabelling
370 / 380. `filter_documents` gated on the stale copy, so a date-range harvest
silently dropped three filing types the package ships typed parsers for
(found 2026-09-09)."""
from edinet_tools import DOCUMENT_TYPES
from edinet_tools.api import filter_documents
from edinet_tools.doc_types import _DOC_TYPES
from edinet_tools.parsers import supported_doc_types


def test_document_types_is_derived_from_the_doc_type_registry():
    assert DOCUMENT_TYPES == {code: dt.name_en for code, dt in _DOC_TYPES.items()}
    assert set(DOCUMENT_TYPES) == set(supported_doc_types())
    assert len(DOCUMENT_TYPES) == 42


def test_filter_documents_keeps_every_registered_doc_type():
    docs = [{'docID': f'S{c}', 'docTypeCode': c, 'filerName': 'x', 'secCode': '12340'}
            for c in _DOC_TYPES]
    kept = {d['docTypeCode'] for d in filter_documents(docs)}
    assert kept == set(_DOC_TYPES)
    for c in ('290', '310', '330'):
        assert c in kept


def test_filter_documents_still_drops_unregistered_codes():
    docs = [{'docID': 'S999', 'docTypeCode': '999', 'filerName': 'x', 'secCode': '12340'}]
    assert filter_documents(docs) == []
