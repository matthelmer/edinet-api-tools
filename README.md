# edinet-tools

[![PyPI](https://img.shields.io/pypi/v/edinet-tools)](https://pypi.org/project/edinet-tools/)
[![Tests](https://github.com/matthelmer/edinet-tools/actions/workflows/test.yml/badge.svg)](https://github.com/matthelmer/edinet-tools/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Python library for Japan's [EDINET](https://disclosure2.edinet-fsa.go.jp/) disclosure system — the official source for securities reports, shareholding notices, tender offers, and other regulatory filings from listed Japanese companies.

EDINET covers 42 document types, and the same financial concept is tagged under a different XBRL element depending on the filer's accounting standard (J-GAAP, IFRS, US-GAAP). This library maps that into one typed Python field per concept.

If you need one company's latest filing once, the [EDINET web UI](https://disclosure2.edinet-fsa.go.jp/) is faster than writing code for it — this library is for programmatic or repeated access. Looking for same-day earnings announcements instead of regulatory filings? That's [TDNET](https://www.release.tdnet.info/), not EDINET.

> **Upgrading from an earlier version?** 0.8.0 removes three financial-statement fields (replaced with owners/total pairs), `EdinetClient`, and a handful of long-deprecated shims. See [MIGRATING.md](https://github.com/matthelmer/edinet-tools/blob/main/MIGRATING.md).

```python
import edinet_tools

toyota = edinet_tools.entity("7203")
docs = toyota.documents(days=30)   # requires EDINET_API_KEY — see Configuration
report = docs[0].parse()  # → SecuritiesReport, LargeHoldingReport, etc.
```

## Install

```bash
pip install edinet-tools
```

Requires Python 3.10+. Zero runtime dependencies — standard library only. (Through 0.7.x it pulled in pandas, numpy, python-dateutil, chardet, and python-dotenv: roughly 109MB of `site-packages`, almost all of it pandas and numpy.)

## Design

edinet-tools has three layers:

1. **API client** — fetch document listings and download filings in any format (XBRL, PDF, HTML)
2. **Typed parsers** — every EDINET document type routes to a named Python dataclass with structured fields
3. **Full capture** — elements not yet mapped to typed fields are preserved in `raw_fields`, `unmapped_fields`, `text_blocks`, and `raw_facts` (the full XBRL fact set), so you can explore what's available and nothing is silently dropped

Each parser maps known XBRL elements to typed Python fields (dates, decimals, strings). As EDINET evolves or new elements become useful, adding a field is one line in the element map and one line on the dataclass.

Typed fields favor honest `None` over plausible-but-wrong values. Financial figures are selected per accounting standard (J-GAAP, IFRS, US GAAP), and a consolidated filer never silently inherits parent-company figures. When a filing doesn't contain a concept, the field is `None`, and the raw data is still in the fact-bag.

## Verification

- **Full-corpus migration proof.** 0.8.0 rewrote the internals of the securities, quarterly, and semi-annual parsers. Old and new were run against all 176,460 filings in an archived corpus and compared field by field: the only differences were on the pre-registered set of filings touched by the one intentional data-quality fix shipped alongside it (below).
- **Golden-fixture panel, cross-checked to the yen.** Eight companies — Toyota, ITOCHU, HOYA, Kansai Paint, Shimamura, Horii Food Service, Shiga Bank, Komatsu — spanning J-GAAP, IFRS, and US-GAAP, mega-cap and small-cap, with and without non-controlling interests, pin every extracted figure against the issuer's own published results.
- **Cross-field identity check, at corpus scale.** `equity_ratio` recomputed from the same filing's own `total_assets` and owners-equity figures agrees with the ratio the filer stated, within ±0.02, in 30,338 of 30,340 evaluable J-GAAP filings and 77 of 77 evaluable US-GAAP filings. The two J-GAAP exceptions are filer-side reporting outliers, not extraction defects.
- **What that check caught.** Run against IFRS filings, it exposed a systematic defect of this library's own: filings that present both an IFRS and a legacy J-GAAP highlights table were served the J-GAAP figures. That is fixed in 0.8.0, and the post-fix re-run leaves two outliers, both filer-side (see CHANGELOG).

Full methodology and the pre-registered pass/fail criteria are in [CHANGELOG.md](CHANGELOG.md).

## EDINET Document Types

EDINET defines 42 document types spanning corporate disclosure, capital markets activity, and governance reporting. edinet-tools provides typed parsers for all of them. Verified against EDINET's own document-type catalog as of 2026-08-06 — EDINET adds and retires document types over time (Doc 140 quarterly reports, for example, were abolished in April 2024).

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
# On a joint filing, ownership_pct is the CO-FILERS' GROUP total — not the
# named filer's own stake. Roughly half of all 5%+ filings are joint, so
# summing ownership_pct across filers double-counts badly.
report.ownership_pct
report.is_joint_filing      # True when 2+ filers report together
report.joint_holders        # list[JointHolder], one per co-reporter, holder_number 1..N
report.joint_holder_count

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

A consolidated filer's subsidiaries aren't always 100% owned, so a single
"net income" or "net assets" figure is ambiguous — does it include the
outside (non-controlling) investors' share, or only the parent company's
own shareholders' piece? edinet-tools never picks one silently: every
field where this is ambiguous ships as an explicit `*_owners` / `*_total`
pair, both exactly as filed. Full explanation, including the
`owners <= total` non-assumption and why it matters:
[docs/ownership-basis.md](https://github.com/matthelmer/edinet-tools/blob/main/docs/ownership-basis.md).

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

Upgrading from before 0.8.0? `net_assets`, `net_income`, and
`prior_net_income` were removed — see [MIGRATING.md](https://github.com/matthelmer/edinet-tools/blob/main/MIGRATING.md) for the
full field-by-field replacement table.

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

## Known limitations

### What returns `None`, and why

| Field / situation | Returns `None` when | Why |
|---|---|---|
| `net_assets_owners` (J-GAAP filers) | Always | Japanese GAAP never files a single owners-only net-assets element. The filed components (`shareholders_equity`, `valuation_translation_adjustments`) ship instead — see "Ownership basis" above. |
| `net_income_total` (US-GAAP filers) | Nearly always | No total-basis net-income element exists in the US-GAAP summary taxonomy tier. |
| `operating_income` | The filer's own accounting standard has no operating-profit subtotal (e.g. some IFRS trading houses) | Selected per accounting standard; never falls back to a different standard's, or the parent company's, figure. |
| Any typed field | The filing doesn't tag the concept at all | The library never invents a number a document didn't state. The raw element set is still there in `raw_fields` / `raw_facts`. |
| Any numeric field | A structural-bounds check fails (e.g. a "ratio" of 27,056) | The element mapping is treated as wrong for this filing, not the filing itself. Recorded in `extraction_flags`; the raw value stays in `raw_fields`. |

### Tried and rejected

- **`EquityToAssetRatioIFRSSummaryOfBusinessResults` looked like the IFRS equity-ratio element by name. It isn't.** Despite the name, it carries per-share equity in yen, not a ratio. Fixed in 0.7.1 — the per-share value now feeds `ifrs_summary_bps`, and `equity_ratio` reads the actual ratio element.
- **Financial-sector revenue and bank/insurer profit elements are deliberately not mapped onto `operating_income`.** Banks and insurers don't report a general-corporate operating-profit subtotal; `net_sales` reads their revenue concept (経常収益) via its own tier, but forcing that revenue concept, or a bank's profit line, into `operating_income` would compare unlike things and produce a plausible-looking wrong number. These filers correctly return `operating_income = None`.
- **There is deliberately no `owners <= total` rule anywhere in the library.** A subsidiary's minority shareholders can themselves post a loss in a period, which pushes the parent's owners-only figure above the total-including-non-controlling-interests figure — a real, correctly-filed result, not a bug. HOYA is the pinned real-filing counterexample in the test fixture panel: for fiscal year 2026-03, `net_income_owners` (¥253,085M) exceeds `net_income_total` (¥251,451M) because non-controlling interests' own share of profit was negative that period.

## Configuration

Get a free API key from [EDINET](https://disclosure2.edinet-fsa.go.jp/) ([video walkthrough](https://youtu.be/2ao-CZS-BtQ?t=63)):

```bash
export EDINET_API_KEY=your_key_here
```

edinet-tools reads `EDINET_API_KEY` from the process environment only — it does not load `.env` files itself. Use `python-dotenv` in YOUR app if you like:

```python
from dotenv import load_dotenv
load_dotenv()

import edinet_tools  # EDINET_API_KEY is now set
```

Entity lookup and parsing work without an API key — only document fetching requires one.

## Testing

```bash
pytest tests/ -v
```

The suite runs offline against committed real-filing fixtures — no API key
and no network needed; the handful of live API-contract tests skip without
a key.

## Links

- [Changelog](CHANGELOG.md)
- [PyPI](https://pypi.org/project/edinet-tools/)
- [GitHub](https://github.com/matthelmer/edinet-tools)
- [EDINET](https://disclosure2.edinet-fsa.go.jp/)

## License

MIT

---

*Independent project. Not affiliated with Japan's Financial Services Agency. Verify data independently before making financial decisions.*
