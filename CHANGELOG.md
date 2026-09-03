# Changelog

## v0.8.2 — 2026-09-03

### Fixed

- **Typed string fields no longer carry raw HTML entity references.** EDINET's XBRL-CSV emits `&amp;` (and occasionally other references) inside string values — `Baillie Gifford &amp; Co`, `日本M&amp;Aセンター`. The joint-holder path of the large-holding parser already decoded these; the top-level fields did not, so `filer_name`, `target_company`, and every other typed string read through `extract_value` came back escaped, and the same filer could resolve to two identities depending on which path produced the name. `extract_value` now decodes well-formed, semicolon-terminated references in every parser. Only well-formed references are touched: a bare `&` in `M&A` or `R&D` is left alone, and legacy no-semicolon forms are deliberately not decoded (`html.unescape` alone would turn `&ETH` inside a name into `Ð`). The fact-bag is unchanged: `raw_fields`, `raw_facts`, `unmapped_fields`, and `text_blocks` keep the filed bytes. New public helper `edinet_tools.parsers.extraction.unescape_entities` for callers that read raw values themselves.

## v0.8.1 — 2026-09-02

### Fixed

- **The client now calls EDINET API v2 on `api.edinet-fsa.go.jp`.** The old `disclosure.edinet-fsa.go.jp` host stopped serving `/api/v2` at the end of August 2026 (it redirects to an HTML error page), so every document-list and document fetch failed with a JSON decode error. `edinet_tools.api.EDINET_API_BASE` carries the host.

### Changed

- **`fetch_document` now raises on EDINET's in-body "no document" answer instead of returning it as bytes.** EDINET reports "no such form for this filing" inside an HTTP 200 response — a 142-byte JSON envelope (`{"metadata": {"status": "404", "message": "Not Found"}}`). The most common case is `type=5` (XBRL-CSV) for a filing that has no XBRL at all: foreign-form filers, parent-company reports, shelf-registration amendments. The low-level function used to hand those bytes back like a document; anyone who saved them got a "zip" that fails much later with `BadZipFile`, far from the cause. It now raises `DocumentNotFoundError` (status 404) or `APIError` (any other status), with no retry — a definitive answer is not a transient failure. `EdinetClient` already raised on this case; the low-level function now matches it, so every caller benefits. This is the per-document twin of the documents-list fix below. Callers that relied on receiving the JSON body as bytes must catch the exception instead.
- **`fetch_documents_list` now raises on EDINET's in-body error answers instead of returning them as data.** EDINET reports failures inside an HTTP 200 body, either as a top-level `StatusCode` (`{"StatusCode": 401, "message": "Access denied due to invalid subscription key..."}`) or as `metadata.status`. Handed back as a dict, a rejected API key is indistinguishable from a day with no filings — an expired key reads as a quiet Saturday, silently, for as long as it takes someone to notice. 0.8.0 closed this at the `EdinetClient` layer; the low-level function kept the old behaviour, so callers that use it directly — a pipeline calling `fetch_documents_list` per date — were still exposed. It now raises `AuthenticationError` (status 401) or `APIError` (any other non-200 status), carrying EDINET's own message, with no retry. A healthy body with zero results is still a legitimate empty day, and a body with no status key at all is not an error. Callers that relied on receiving the error body as a dict must catch the exception instead.
- New public helpers `is_zip_payload(bytes)` and `is_edinet_error_body(bytes)` in `edinet_tools.api`, for callers that handle raw payloads themselves. The client's private sniffers now delegate to them.

## v0.8.0 — 2026-08-10

### Breaking

- **`net_assets`, `net_income`, and `prior_net_income` are removed. Each is replaced by an explicit pair.** A consolidated filing carries two versions of these figures: one for the parent's own shareholders, and one that includes minority (non-controlling) interests. The old single fields silently picked one or the other depending on the accounting standard and the filer's tagging. The new names say which is which.
  - `net_assets_owners` / `net_assets_total`. J-GAAP filers never file an owners-only net assets figure, so `net_assets_owners` is `None` for them.  The filed components ship instead: `shareholders_equity` (株主資本), `valuation_translation_adjustments` (評価換算差額等), and `non_controlling_interests` (非支配株主持分).  Components are never summed into a derived figure.
  - `net_income_owners` / `net_income_total`. `net_income_total` is `None` for nearly all US-GAAP filers because no such element exists in that taxonomy.
  - `prior_net_income_owners` / `prior_net_income_total`, read from the prior-year context.
  - Reading a removed field raises `AttributeError` naming its replacements.  Constructing a report with one raises `TypeError`. See MIGRATING.md.
  - There is deliberately no `owners <= total` rule. Minority shareholders can post a loss, which pushes the owners figure above the total. That is a real filed result, pinned in the test panel (HOYA, fiscal 2026-03).
- **`EntityType.FUND` is renamed `EntityType.FUND_ISSUER`** (value `"fund"` becomes `"fund_issuer"`), and `EntityClassifier.is_fund()` becomes `is_fund_issuer()`.  The classification comes from the fund registry's issuer column.  It means "this entity has issued fund products", not "this entity is a fund".  Trust banks appear there routinely, so the old name invited misreads.  Will likely re-evaluate EntityType usage in future release.

### Added

- **`extraction_flags` on every parsed report.** Typed numeric fields are checked at parse time against structural rules. A value that is impossible under its field's name (a "ratio" of 27,056) is withheld as `None` and flagged; the element mapping is treated as wrong, not the filing. Cross-field identity mismatches are flagged without altering any field. Raw values always remain in `raw_fields`.
- **`StaleDataWarning` on old registry snapshots.** The bundled FSA code lists are a dated snapshot (refreshed 2026-08-08: 11,376 entities, 6,369 fund rows). Loading a snapshot older than a year now warns and points at the path arguments for supplying fresher CSVs. A release-gate test fails if the bundled data ages past the threshold.
- **An IFRS-only last-resort tier for `net_income_total` / `prior_net_income_total`** on `jpcrp_cor:ProfitLossIFRSSummaryOfBusinessResults`, for IFRS filers that tag a total-basis profit but no owners-basis element. It fills only when every earlier tier is `None` and is never read by non-IFRS filers. Full-corpus result: 363 and 361 fills, zero changes to previously populated values.
- New IFRS debt fields (`bonds_and_borrowings` / `borrowings`, current and non-current). IFRS debt is no longer silently absent and is never coerced onto the J-GAAP debt fields.
- Tender-offer registrations flag a stated cover-page filing date more than 30 days after the API submit date. The stated date is never overwritten.

### Fixed

- **A rejected API key now raises `AuthenticationError` instead of returning an empty document list.** EDINET reports auth failures inside an HTTP 200 body, which the client used to read as a day with no filings.
- **IFRS-transition filings were served J-GAAP figures on `equity_ratio`, `total_assets`, and `net_assets_total`.** Companies moving to IFRS sometimes file both an IFRS and a legacy J-GAAP highlights table in one document, and the parser tried the J-GAAP elements first regardless of the filing's own standard. IFRS filings now read IFRS elements first. The identity check below flagged 138 filings; every one was hand-checked against its raw CSV, confirming 136 as this defect (101 distinct filers) and 2 as filer-side quirks. A full-corpus re-parse confirmed the fix changes exactly the predicted 222-filing set and nothing else.
- **Semi-annual reports (Doc 160/170) read the wrong period.** EDINET lists the prior period's row before the current period's, and the parser took the first match, so financial fields systematically carried the prior period's value. The parser now resolves the filing's own current-period context and never borrows a parent-only figure for a consolidated filer. New fields `accounting_standard` and `is_consolidated` are read from DEI. Applies to all 16 financial fields; roughly 17,000 of the 18,484 corpus rows change at least one column, and 40 rows recover fee or profit figures the old read missed entirely (3 verified against the filer's own printed totals).
- **Tender-offer results (Doc 270/280): two voting-rights fields remapped, two retired.** `total_voting_rights` and `voting_rights_special_interest` were mapped to the registration filing's element letters and never filled; remapped to the results-side elements (473 and 298 fills across 610 filings). `voting_rights_purchased` and `purchase_ratio` have no backing element at all and now return `None` rather than a derived guess.
- **A non-BOM UTF-8 CSV could silently decode as UTF-16 mojibake.** The reader tried `utf-16le` before `utf-8`. It now tries `utf-8` first, which rejects wrong bytes outright. Real EDINET files (UTF-16-LE with a BOM) are unaffected.
- **Company search now matches across character widths.** Full-width Latin and digit queries (ＫＥＹＥＮＣＥ, what a Japanese IME naturally produces) returned nothing from `search_companies` and `resolve_company_identifier`. Queries and index keys are now width-normalized.
- Securities brokers' operating revenue (営業収益) now populates `net_sales`.
- IFRS filers tagging operating profit under custom namespaces now populate `operating_income`. Bank and insurer profit lines are deliberately not mapped; they are different concepts.
- IFRS and US-GAAP filers now populate net assets per share.
- Filings that disclose only a single combined equity line now populate `net_assets_total` instead of `None`; `net_assets_owners` correctly stays `None`.
- The 【対象者名】 form label is stripped from tender-offer target names.
- The company-not-found error now suggests `search_entities()`, a function that exists.

### Known gaps (deferred)

- **Quarterly reports (Doc 140/150) still lack the per-standard element gate**: an IFRS or US-GAAP quarterly filer can read a J-GAAP element ahead of its own standard's where both exist. No quarterly value changed in 0.8.0 (the full-corpus re-parse shows zero quarterly diffs). Scheduled for 0.9.0.

### Removed

- **All runtime dependencies. The package now uses the standard library only.**
  - pandas, and transitively numpy (suggested by Ben Allen). TSV parsing uses the stdlib `csv` module. Both TSV readers now share one fail-loud core: an unterminated quote or an over-long row raises `csv.Error` instead of being silently absorbed; short rows are padded with `None`.
  - python-dateutil. The one call site now uses stdlib date arithmetic, verified against the old implementation across leap-year boundaries.
  - python-dotenv. The package no longer loads `.env` files on import; `EDINET_API_KEY` is read from the environment only. Call `load_dotenv()` yourself before importing if you keep the key in a `.env` file.
  - chardet. The readers try a fixed encoding order instead of a statistical guess. This retirement surfaced the UTF-8 ordering bug fixed above.
- **The legacy `EdinetClient` class**, deprecated since 0.2.0. Use the module-level functions: `configure()`, `documents()`, `entity.documents()`, and `doc.fetch()` / `doc.parse()`.
- **The deprecated boolean shims** from the 0.6.1 fact-shaped transition: `Entity.is_listed`, `Entity.is_fund_issuer`, `EntityClassifier.is_listed()`, `TreasuryStockReport.has_board_authorization` / `has_shareholder_authorization`, and `utils.process_zip_directory()`.
- **The legacy `processors.py` / `parser.py` pipeline** and `utils.process_zip_file`. An exposure audit found it reachable only from itself and its own tests. Dead code, removed outright.
- **The dead `[analysis]` install extra.** The analysis module was removed in 0.4.1. Importing without an LLM key no longer logs a spurious warning.

### Tests

- **Full-corpus equivalence proof.** Every stored filing with cached CSVs (176,460 documents) was parsed with the old and the new parser and diffed. The only differences are the pre-registered set belonging to the IFRS-transition fix above. Quarterly and semi-annual: zero diffs.
- **Full-corpus identity check.** `equity_ratio` recomputed from each filing's own figures matches the filer's stated ratio within ±0.02 in 30,338 of 30,340 J-GAAP filings, 2,302 of 2,304 IFRS filings, and 77 of 77 US-GAAP filings. The six exceptions are filer-side reporting quirks, not extraction defects. This is the check that found the IFRS-transition defect.
- **Eight-company golden-fixture panel** (Toyota, ITOCHU, HOYA, Kansai Paint, Shimamura, Horii Food Service, Shiga Bank, Komatsu): all three standards, mega-cap to small-cap, with and without minority interests, every figure pinned to the yen against the issuer's own published results.
- Test count: 836 at the 0.7.1 close, 1,001 at release. New fixture panels cover every fix above; the removed legacy pipeline took its dedicated test files with it.

## v0.7.1 — 2026-06-12

Correctness release for the securities report parser. Income-statement fields are now selected per accounting standard, several element mappings pointed at XBRL ids that don't exist in real filings, and banks, insurers, and securities firms now get real revenue figures.

### Fixed

- **`operating_income` is now selected per accounting standard.** Previously every filer was read through the J-GAAP element first, so IFRS and US-GAAP companies could pick up a parent-company figure. Each standard now reads its own operating-profit elements, including `OperatingIncomeLossUSGAAPSummaryOfBusinessResults` (v0.7.0 wrongly claimed no US-GAAP element exists; Sony and others tag it). Filers whose statements have no operating-profit subtotal, like IFRS trading houses, return `None` instead of a wrong number. Applies to current and prior year.
- **IFRS `equity_ratio` was storing equity per share, in yen.** The element it read (`EquityToAssetRatioIFRSSummaryOfBusinessResults`) is named misleadingly; its real meaning is per-share equity. `equity_ratio` now reads the actual ratio element. The per-share value still feeds `ifrs_summary_bps`.
- **IFRS `current_liabilities` was always `None`.** It was mapped to an element that doesn't exist in real filings; the real one is `TotalCurrentLiabilitiesIFRS`. Also added the missing deferred-tax-assets and depreciation fallbacks.
- **The J-GAAP cash-flow fallback tier never fired.** All three element ids were wrong. Replaced with the real `jppfs_cor:NetCashProvidedByUsedIn*Activities` elements.

### Added

- **Revenue for financial-sector filers.** Banks and insurers report 経常収益 and securities firms 営業収益 rather than net sales. `net_sales` now reads those elements when the standard ones are absent. Previously these filers returned `None` or picked up a small sub-business line. Known gap: securities firms that tag only `OperatingRevenueSEC`-style variants still return `None`; mapping planned.
- **US-GAAP balance sheet and cash flows.** Total assets, equity, equity ratio, book value per share, and the three cash-flow figures now populate for US-GAAP filers, via the `...USGAAPSummaryOfBusinessResults` elements.

### Tests

- Five new golden fixtures from real, unedited filings (Itochu, Toyota Tsusho, HS Holdings, MUFG, Canon), pinned to exact values. Test count: 798 → 832.
- Output cross-checked against the issuers' own earnings releases for 20 filings across J-GAAP, IFRS, and US GAAP. Every populated figure matched to the yen.

### Note for existing databases

Parser fixes apply on re-parse. Rows extracted with earlier versions keep their old values. Re-extract IFRS, US-GAAP, and financial-sector filings — and make sure your update path writes `None` over old values rather than skipping them, since some fields are now correctly `None`.

## v0.7.0 — 2026-05-29

Segment-information parsing, a consolidated-revenue data-quality fix for IFRS/US-GAAP filers, registry-based filer classification, and the fact-shaped API transition (`Entity.entity_type`).

### Added

- **`SegmentRow` + `parse_segments_from_csv()`** — per-segment metrics from annual securities reports. Anchored-union discriminator (anchor on segment-name suffixes; admit aggregation rows only when they carry a segment-exclusive element), plus a no-anchor path that recovers industry/sector-named segments by seeding from segment-specific aggregation rows. Zero over-extraction across the broad-sample harness.
- **`SecuritiesReport` fields**: `segments`, `segments_text_only` (segment data in HTML text-blocks, not CSV), `segments_extraction_incomplete` (aggregation rows present but no segments extracted — honest miss flag).
- **US-GAAP summary income-statement elements** mapped (revenue, profit-before-tax, net income, EPS, ROE) — US-GAAP filers previously extracted as `None`. No operating-income line in the US-GAAP summary, so `operating_income` is honestly `None`.
- **`LargeHoldingReport.is_joint_filing`** — derived from `FilerLargeVolumeHolder<N>Member` axis presence (N ≥ 2), not hardcoded `False`.
- **`Fact` + `ParsedReport.raw_facts`** — typed access to the full XBRL fact set, alongside `raw_fields` / `text_blocks` / `unmapped_fields`.
- **`extract_dimensional()`** — axis-context primitive with member-name cleaning; substrate for segments and future schedule-table parsers.
- **`Entity.entity_type`** (`EntityType` enum) — fact-shaped FSA-registry classification; replaces the deprecated `is_listed` / `is_fund_issuer` booleans.
- **`extract_csv_to_disk()` + `Document.save_extracted_csvs()`** — disk-output helpers complementing in-memory `extract_csv_from_zip()`.

### Fixed

- **Consolidated revenue for IFRS / US-GAAP filers** — `net_sales` (and other income-statement metrics) returned the non-consolidated **parent** figure (e.g. ¥18T parent vs ¥48T consolidated). Now a consolidated filer never substitutes the parent value: a missing consolidated value falls through to the next element/tier or to honest `None` (parent stays in the fact-bag). With IFRS/US-GAAP/custom-namespace revenue elements mapped, the full cohort reads consolidated. Pinned by real-filing golden fixtures.
- **Holder names HTML-unescaped** — `_normalize_holder_value` applies `html.unescape`, so Doc 350 filer names with `&amp;` etc. are clean text.
- **`ExtraordinaryReport` / `SemiAnnualReport` filer classification** — `is_fund` returned `True` for ~all recent corporate filings (EDINET `'－'` placeholders broke the DEI heuristic). Now classified via the FSA registry (`report.filer.entity_type`); parsers expose `filer_edinet_code` as a fact.
- **`TreasuryStockReport` authorization flags** — `has_board_authorization` / `has_shareholder_authorization` no longer return `True` for empty/whitespace text blocks.
- **`QuarterlyReport.is_consolidated` and `SecuritiesReport.is_consolidated`** now return `None` when the `WhetherConsolidatedFinancialStatementsArePreparedDEI` element is missing, rather than silently defaulting to `True`. Honest unknowns over silent-failure-as-default.
- **`extract_dimensional()` member names** are stripped of per-filer extension namespace prefixes (e.g., `E03847-000DomesticLifeInsuranceReportableSegments` → `DomesticLifeInsuranceReportableSegments`), matching `segments.py`'s `_clean_member_name()`. Avoids requiring every consumer to re-implement the cleaning.

### Deprecated

The deprecations below all emit `DeprecationWarning`. They will be removed in a future major release; consumers should migrate to the fact-shaped equivalents.

- **`Entity.is_listed`** — use `entity.entity_type == EntityType.LISTED_COMPANY`.
- **`Entity.is_fund_issuer`** — use `entity.entity_type == EntityType.FUND`.
- **`EntityClassifier.is_listed(edinet_code)`** — use `classifier.get_entity_type(code) == EntityType.LISTED_COMPANY`.
- **`TreasuryStockReport.has_board_authorization`** — use `bool(parsed.by_board_meeting and parsed.by_board_meeting.strip())` directly.
- **`TreasuryStockReport.has_shareholder_authorization`** — use `bool(parsed.by_shareholders_meeting and parsed.by_shareholders_meeting.strip())` directly.
- **`utils.process_zip_directory()`** — use `extract_csv_from_zip()` for in-memory CSV extraction or `extract_csv_to_disk()` for disk output (both in `edinet_tools.parsers.extraction`).
- **All public methods on `EdinetClient`** (`get_documents_by_date`, `get_recent_filings`, `get_company_filings`, `search_companies`, `download_filing_raw`, `download_filing`, `download_filings_batch`, `extract_filing_data`) — use the module-level functions and `Document` / `Entity` classes instead. Migration paths are named in each method's `DeprecationWarning` message.

### Removed

- **`ExtraordinaryReport.is_fund` / `SemiAnnualReport.is_fund`** and the intermediate `filer_namespace` field — replaced by registry-based classification via `report.filer.entity_type`.
- **`parsers.namespace_helpers`** (`infer_filer_type()`) — namespace inference conflated the shared `jppfs_cor:` taxonomy with corporate-only signal; parsers now expose facts, consumers classify via the FSA registry.
- **`parser.extract_mtp_targets()`** — dead code, zero callers.

### Tests

- Audit-closure remediation across routing / processor / API test families (real-ZIP body-execution assertions, dead-fixture removal).
- Real-EDINET golden fixtures per failure class (segments incl. no-anchor, consolidated-revenue, blast-radius characterization).
- Test count: 612 → 798.

## v0.6.0 — 2026-05-12

### Added

- `normalize_for_matching(s)` — public name-matching helper. NFKC normalization, `(株)` → `株式会社` / `(有)` → `有限会社` rewrites, katakana / Latin middle-dot stripping (`・` U+30FB, `·` U+00B7), whitespace collapse (runs folded to a single ASCII space; whitespace preserved between words so `Toyota` doesn't match `Toyo Tanso`), lowercase. Idempotent.
- `entity_by_corporate_number(num)` — O(1) lookup by 13-digit 法人番号 (Japan Corporate Number).
- `Entity.name_phonetic` and `Entity.corporate_number` now populated for classifier-path entities. Sourced from the `Submitter Name (phonetic)` and `Submitter's Japan Corporate Number` columns of `EdinetcodeDlInfo.csv`.
- GitHub Actions CI workflow (`.github/workflows/test.yml`) — multi-Python test matrix on push and pull_request.

### Changed

- `search_entities()` — O(1) exact-match via reverse index; substring-fallback path uses pre-normalized forms on both sides. Visually-identical strings with different Unicode encodings (full-width vs half-width Latin, `（` vs `(`, `㈱` vs `株式会社`, middle-dot variants like `モルガン・スタンレー` vs `モルガンスタンレー`) now resolve to the same entity.
- `search_entities()` bidirectional whitespace handling — when a query like `山田太郎` doesn't exact-match, falls back to the whitespace-collapsed catalog form, recovering names where the catalog stores them with internal spaces (`山田 太郎`). Particularly relevant for Japanese individual-filer names.
- `entity_by_ticker()` — O(N) scan replaced with O(1) reverse-index lookup. Now also handles alphanumeric tickers (`192A`, `263A`, `275A`-class).

### Not changed

- Public API signatures and return shapes — drop-in upgrade for existing callers.

### Known limitations (documented as xfail tests)

- Punctuation / symbol / abbreviation variance (`Co Ltd` ↔ `Co., Ltd.`, `&` ↔ `and`, `Inc` ↔ `Incorporated`).
- Queries with trailing parentheticals longer than the catalog name (e.g. `(信託口)` trust-account suffixes) — downstream consumers needing this should pre-strip before calling `search_entities`.
- Trust banks (`日本マスタートラスト信託銀行` etc.) are not in the EDINET catalog at all — they exist in the 法人番号 corporate registry only. v0.7.0+ may add a `法人番号公表サイト` ingestion layer to cover them.

## v0.5.1

- More robust EN/JP catalog loader — resolves columns by header alias, accepts both Japanese and English variants of FSA's `EdinetcodeDlInfo.csv` and `FundcodeDlInfo.csv`, fails loudly on schema renames.
- Fund-precedence fix in `EntityClassifier` — listed-company status now wins over fund-registry membership (Credit Saison, JAFCO etc. no longer misclassified as funds).
- Industry translation — `industry` field normalized to English regardless of CSV variant; raw Japanese preserved separately. New `translate_industry_to_english()` public helper.
- `scripts/refresh_csvs.py` — downloads fresh CSVs from FSA.
- CSVs refreshed.

## v0.5.0

Typed parsers for all 42 EDINET document types.

## v0.4.3

Add `fetch_and_parse` API. Expose `industry` field on `Entity`.
