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

# Balance-sheet debt detail (J-GAAP): short_term_loans_payable,
# long_term_loans_payable, bonds_payable, current_portion_long_term_loans_payable
# IFRS reports combined bonds-and-borrowings or borrowings-only lines with no
# clean mapping onto the J-GAAP fields above — two distinct concepts get two
# field names, never coerced onto each other:
report.bonds_and_borrowings_current_ifrs     # 社債及び借入金, current
report.bonds_and_borrowings_noncurrent_ifrs  # 社債及び借入金, non-current
report.borrowings_current_ifrs               # 借入金, current
report.borrowings_noncurrent_ifrs            # 借入金, non-current

# Ownership-basis split (v0.8.0+, see "Ownership basis" below): every
# equity/profit figure that could include non-controlling interests ships
# as an explicit owners-only / total pair, never a single ambiguous field.
report.net_income_owners  # 親会社株主に帰属する当期純利益 — attributable to owners of parent
report.net_income_total   # includes non-controlling interests' share
report.net_assets_total   # 純資産 — includes non-controlling interests
report.net_assets_owners  # equity attributable to owners of parent (always None for J-GAAP — see below)

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

### Ownership basis: owners-only vs. total

Consolidated financial statements sometimes include subsidiaries that
aren't 100% owned — outside investors hold a stake directly in the
subsidiary, not in the parent company. Accounting rules (Japanese GAAP,
IFRS, and US-GAAP alike) call that outside stake a **non-controlling
interest** (NCI; 非支配株主持分, sometimes "minority interest"). Because of
that, a single "net income" or "net assets" figure is ambiguous on its
own — does it include the outside investors' share, or only the piece
that belongs to the parent company's own shareholders?

edinet-tools never picks one silently. Every field where this is
ambiguous ships as an explicit pair:

- **`*_owners`** — attributable to the owners of the parent (親会社株主に帰属する /
  the IFRS and US-GAAP "attributable to [Company]" line). This is
  normally the headline figure in an earnings release, and the number
  EPS is computed from.
- **`*_total`** — includes the non-controlling interests' share too.

The two usually move together, but don't have to: if a subsidiary's
minority shareholders happen to lose money in a period, the parent's
owners-only figure can come out *higher* than the total-including-everyone
figure. That's a real, correctly-filed result, not a bug — so
edinet-tools never assumes `owners <= total` or the reverse. It ships
both numbers exactly as filed and leaves the comparison to you.

#### Fields

| Field | Meaning | Notes |
|---|---|---|
| `net_assets_owners` | Equity attributable to owners of parent | **J-GAAP: always `None`** — Japanese GAAP never files this as a single element. The filed components are `shareholders_equity` + `valuation_translation_adjustments` (below). IFRS and US-GAAP filers populate it directly. |
| `net_assets_total` | Net assets including non-controlling interests (純資産) | Filed for all three standards. |
| `net_income_owners` | Profit attributable to owners of parent (親会社株主に帰属する当期純利益) | Filed for all three standards. |
| `net_income_total` | Profit including non-controlling interests' share | **US-GAAP: structurally `None`** for nearly all filers — no total-basis net-income element exists in that taxonomy tier. |
| `prior_net_income_owners` / `prior_net_income_total` | Same split, prior fiscal year | Same per-standard routing, read from the prior-year XBRL context. |
| `shareholders_equity` | 株主資本 — filed J-GAAP component | J-GAAP only. Never summed into `net_assets_owners` — it's a fact as filed, not a derived aggregate. |
| `valuation_translation_adjustments` | 評価換算差額等 — filed J-GAAP component | J-GAAP only, same rule as above. |
| `non_controlling_interests` | 非支配株主持分 (NCI) | Filed for all three standards; `None` when a filer has no minority-owned subsidiaries. |

If you need an owners-only equity figure for a J-GAAP filer, compute it
yourself from the two filed components
(`shareholders_equity + valuation_translation_adjustments`) — edinet-tools
ships the facts as filed and leaves that arithmetic to you.

#### Migrating from < 0.8.0

`net_assets`, `net_income`, and `prior_net_income` were removed in 0.8.0.
Reading them raises `AttributeError` naming the replacement field(s);
constructing a `SecuritiesReport` with them as keyword arguments raises
`TypeError`. Fix your code from this table:

| Old field | Standard | What the old value actually was | Replacement |
|---|---|---|---|
| `net_assets` | J-GAAP | Always total-basis (incl. NCI) | `net_assets_total` |
| `net_assets` | IFRS / US-GAAP | Owners-basis when the filing tagged it; silently fell back to total-basis otherwise | `net_assets_owners`, falling back to `net_assets_total` for the old fallback behavior |
| `net_income` | J-GAAP / IFRS / US-GAAP | Owners-basis for almost every filer; silently fell back to total-basis for the minority of filers whose owners-basis element was absent | `net_income_owners`, falling back to `net_income_total` for the old fallback behavior (`net_income_total` is `None` for nearly all US-GAAP filers) |
| `prior_net_income` | all | Same mixed routing as `net_income`, prior-year context | `prior_net_income_owners` / `prior_net_income_total`, same fallback pattern |

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
  filing is often internally consistent under a different accounting
  convention than the one being checked — so a mismatch is recorded as a
  flag but no field is altered.

The library never invents a number a document didn't state, and never
suppresses a stated number because it disagrees with a computed one.

```python
report = doc.parse()
for flag in report.extraction_flags:
    print(flag.field, flag.severity, flag.rule, flag.value)
```

### Building your own plausibility checks

Validation above only checks what a value can *structurally* be — never
what's *typical*. edinet-tools deliberately ships no opinion on
plausibility: whether a ratio "looks right" depends on judgment the
library doesn't have, so that judgment stays yours to make, on the typed
fields it hands you as filed. A minimal example, using the
owners/total pair described above:

```python
ratio = abs(report.net_income_owners / report.net_income_total)
low, high = 0.02, 50  # pick a band that fits your use case
if not (low <= ratio <= high):
    review_queue.append((report, ratio))  # your queue, your call
```

Treat a flag from a check like this as a prompt to look, not a verdict.
It's an aggregate screen: a filer whose consolidated net income sits near
zero in a given year can produce a legitimate owners/total ratio in the
hundreds, purely because the denominator is small — both figures are
correctly filed, and the ratio between them is just noisy near zero. A
flagged filing may be exactly what it says. edinet-tools reports what a
filing states; deciding whether a given ratio is worth a second look —
and picking the band that decides that — is a call for the code that
consumes the data, not this library.

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
pytest tests/ -v  # 900+ tests
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
