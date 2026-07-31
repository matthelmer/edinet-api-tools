# edinet-tools

[![PyPI](https://img.shields.io/pypi/v/edinet-tools)](https://pypi.org/project/edinet-tools/)
[![Downloads](https://static.pepy.tech/badge/edinet-tools)](https://pepy.tech/project/edinet-tools)
[![Tests](https://github.com/matthelmer/edinet-tools/actions/workflows/test.yml/badge.svg)](https://github.com/matthelmer/edinet-tools/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Python library for Japan's [EDINET](https://disclosure2.edinet-fsa.go.jp/) disclosure system — the official source for securities reports, shareholding notices, tender offers, and other regulatory filings from listed Japanese companies.

```python
import edinet_tools

toyota = edinet_tools.entity("7203")
docs = toyota.documents(days=30)
report = docs[0].parse()  # → SecuritiesReport, LargeHoldingReport, etc.
```

## Install

```bash
pip install edinet-tools
```

Requires Python 3.10+. No heavy dependencies — just `pandas`, `python-dateutil`, `chardet`, and `python-dotenv`.

## Design

edinet-tools has three layers:

1. **API client** — fetch document listings and download filings in any format (XBRL, PDF, HTML)
2. **Typed parsers** — every EDINET document type routes to a named Python dataclass with structured fields
3. **Full capture** — elements not yet mapped to typed fields are preserved in `raw_fields`, `unmapped_fields`, `text_blocks`, and `raw_facts` (the full XBRL fact set), so you can explore what's available and nothing is silently dropped

Each parser maps known XBRL elements to typed Python fields (dates, decimals, strings). As EDINET evolves or new elements become useful, adding a field is one line in the element map and one line on the dataclass.

Typed fields favor honest `None` over plausible-but-wrong values. Financial figures are selected per accounting standard (J-GAAP, IFRS, US GAAP), and a consolidated filer never silently inherits parent-company figures. Element mappings are pinned by tests against real, unedited filings and cross-checked against issuers' own earnings releases. When a filing doesn't contain a concept, the field is `None`, and the raw data is still in the fact-bag.

## EDINET Document Types

EDINET defines 42 document types spanning corporate disclosure, capital markets activity, and governance reporting. edinet-tools provides typed parsers for all of them.

| Code | Family | Description |
|------|--------|-------------|
| 120, 130 | Securities Reports | Annual reports — financials, governance, business overview (J-GAAP / IFRS / US GAAP) |
| 140, 150 | Quarterly Reports | Quarterly financials (abolished April 2024) |
| 160, 170 | Semi-Annual Reports | Semi-annual reports, primarily investment funds |
| 180, 190 | Extraordinary Reports | Material events — M&A, management changes, restructuring |
| 220, 230 | Treasury Stock | Share buyback authorization and execution status |
| 235, 236 | Internal Control | J-SOX evaluation results — internal control effectiveness |
| 135, 136 | Confirmation Documents | CEO/CFO attestation (primarily PDF) |
| 200, 210 | Parent Company Reports | Parent-subsidiary relationships |
| 350, 360 | Large Shareholding | 5%+ ownership filings — filer, target, ownership percentage |
| 370, 380 | Shareholding Changes | Position changes for large holders |
| 240, 250 | Tender Offer Registration | Public tender offer filings |
| 260 | Tender Offer Withdrawal | Withdrawal of tender offers |
| 270, 280 | Tender Offer Reports | Tender offer completion — outcome, final holdings |
| 290, 300 | Statement of Opinion | Target company's board opinion on a tender offer |
| 310, 320 | Response to Questions | Regulatory Q&A during tender offer process |
| 330, 340 | Exemption Application | Exemption from separate purchase prohibition |
| 030, 040 | Securities Registration | New securities registration statements (primarily funds) |
| 010, 020 | Securities Notification | Securities issuance notifications |
| 050 | Registration Withdrawal | Withdrawal of securities registration |
| 070, 080, 090 | Shelf Registration | Shelf registration for future bond/equity issuance |
| 060 | Issuance Notification | Issuance registration notifications |
| 100 | Issuance Supplementary | Supplementary shelf registration drawdown documents |
| 110 | Issuance Withdrawal | Withdrawal of issuance registration |

Amendments (even-numbered codes like 130, 150, 190) route to the same parser as their base type and set `is_amendment = True`.

```python
from edinet_tools import supported_doc_types, doc_type

supported_doc_types()  # All 42 codes with typed parsers

dt = doc_type("235")
print(dt.name_en)  # "Internal Control Report"
print(dt.name_jp)  # "内部統制報告書"
```

## Usage

### Entity Lookup

```python
import edinet_tools

toyota = edinet_tools.entity("7203")      # By ticker (digit or alphanumeric)
toyota = edinet_tools.entity("Toyota")    # By name search
toyota = edinet_tools.entity("E02144")    # By EDINET code
print(toyota.name, toyota.edinet_code)    # TOYOTA MOTOR CORPORATION E02144

# Look up by Japan Corporate Number (法人番号)
toyota = edinet_tools.entity_by_corporate_number("1180301018771")

# Name search handles full-width/half-width, gaiji (㈱), and middle-dot variants
mufg = edinet_tools.search("三菱UFJ銀行")  # matches the catalog's ＵＦＪ form too

banks = edinet_tools.search("bank", limit=5)
```

### Fetching Documents

```python
# All filings for a date (requires EDINET_API_KEY)
docs = edinet_tools.documents("2026-01-20")

# Filter by company and type
earnings = toyota.documents(doc_type="120", days=365)
```

### Parsing

```python
report = doc.parse()

# Securities Report — consolidated financials (J-GAAP, IFRS, US-GAAP)
report.net_sales
report.operating_cash_flow
report.roe
report.accounting_standard  # "Japan GAAP", "IFRS", or "US GAAP"
report.segments             # list[SegmentRow] — per-segment metrics

# Large Shareholding Report
report.filer_name
report.target_company
report.ownership_pct

# Tender Offer
report.acquirer_name
report.target_name
report.holding_ratio_after

# Any report
report.fields()     # List available typed fields
report.to_dict()    # Export as dictionary
report.raw_fields   # All XBRL elements by element ID
report.text_blocks  # Narrative text block content
```

### Validation

Typed numeric fields are checked at parse time against structural rules —
what a value can possibly be, never what is typical. Findings land in
`report.extraction_flags`:

- **Bounds withhold.** A value that is structurally impossible under its
  field's name (e.g. a "ratio" of 27,056) means the element mapping is wrong,
  not the filing. The typed field is set to `None` and a flag records the
  field, source element, value, and rule. The raw value always remains in
  `raw_fields`.
- **Identities annotate.** Cross-field accounting checks (e.g. equity ratio
  vs net assets / total assets) cannot tell which operand is wrong — and the
  filing is often internally consistent under a different grain — so a
  mismatch is recorded as a flag but no field is altered.

The library never invents a number a document didn't state, and never
suppresses a stated number because it disagrees with a computed one.

```python
report = doc.parse()
for flag in report.extraction_flags:
    print(flag.field, flag.severity, flag.rule, flag.value)
```

### Download Formats

```python
from edinet_tools.api import fetch_document

csv_zip = fetch_document("S100ABC")            # XBRL CSV (default)
pdf = fetch_document("S100ABC", type=2)        # PDF
html_zip = fetch_document("S100ABC", type=1)   # HTML documents
```

## Configuration

Get a free API key from [EDINET](https://disclosure2.edinet-fsa.go.jp/) ([video walkthrough](https://youtu.be/2ao-CZS-BtQ?t=63)):

```bash
export EDINET_API_KEY=your_key_here
```

Or use a `.env` file. Entity lookup and parsing work without an API key — only document fetching requires one.

## Testing

```bash
pytest tests/ -v  # 830+ tests
```

## Links

- [Changelog](CHANGELOG.md)
- [PyPI](https://pypi.org/project/edinet-tools/)
- [GitHub](https://github.com/matthelmer/edinet-tools)
- [EDINET](https://disclosure2.edinet-fsa.go.jp/)

## License

MIT

---

*Independent project. Not affiliated with Japan's Financial Services Agency. Verify data independently before making financial decisions.*
