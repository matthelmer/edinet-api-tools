#!/usr/bin/env python3
"""
EDINET Tools — Quick Start Demo

Demonstrates entity lookup, document listing, typed parsing,
and doc type registry. Run with an EDINET API key for the full
experience, or without one for entity-only features.

  python demo.py
"""

import os
from datetime import timedelta
import edinet_tools


def _get_recent_docs(max_days_back=5):
    """Get documents from today (JST) or the most recent filing day."""
    today = edinet_tools.today_jst()
    for i in range(max_days_back):
        d = today - timedelta(days=i)
        docs = edinet_tools.documents(d.isoformat())
        if docs:
            if i > 0:
                print(f"  (No filings yet for {today} JST — showing {d})")
            return docs, d
    return [], today


# ── 1. Entity lookup (no API key needed) ──────────────────────────

def entity_lookup():
    """Look up companies by ticker, EDINET code, or name."""
    print("\n--- Entity Lookup ---")

    # By ticker
    mitsubishi = edinet_tools.entity("8058")
    print(f"Ticker 8058: {mitsubishi.name} ({mitsubishi.edinet_code})")

    # By EDINET code
    same = edinet_tools.entity("E02529")
    print(f"Code E02529: {same.name}")

    # By name search
    toyota = edinet_tools.entity("Toyota")
    print(f"Search 'Toyota': {toyota.name} ({toyota.ticker})")

    # Multiple results
    results = edinet_tools.search("trading", limit=3)
    print(f"\nSearch 'trading': {len(results)} results")
    for e in results:
        print(f"  {e.ticker or '----'}: {e.name[:50]}")


# ── 2. Document listing ───────────────────────────────────────────

def list_documents():
    """Fetch the latest day's filings and show a summary."""
    print("\n--- Recent Documents ---")

    docs, filing_date = _get_recent_docs()
    print(f"Found {len(docs)} filings from {filing_date}")

    for doc in docs[:5]:
        print(f"  {doc.doc_id}: {doc.filer_name[:40]} — {doc.doc_type_name}")

    return docs


# ── 3. Typed parsers ─────────────────────────────────────────────

def parse_large_holding(docs):
    """Parse a large holding report (doc 350) — typed fields."""
    print("\n--- Large Holding Report (Doc 350) ---")

    for doc in docs:
        if doc.doc_type_code == "350":
            report = doc.parse()  # → LargeHoldingReport
            print(f"  Parser:    {type(report).__name__}")
            print(f"  Filer:     {report.filer_name}")
            print(f"  Target:    {report.target_company}")
            if report.ownership_pct is not None:
                print(f"  Ownership: {report.ownership_pct}%")
            if report.prior_ownership_pct is not None:
                print(f"  Prior:     {report.prior_ownership_pct}%")
            if report.purpose:
                preview = report.purpose[:120].replace('\n', ' ')
                print(f"  Purpose:   {preview}...")
            return

    print("  No doc 350 found in the last 5 days")


def parse_treasury_stock(docs):
    """Parse a treasury stock report (doc 220) — typed fields."""
    print("\n--- Treasury Stock Report (Doc 220) ---")

    for doc in docs:
        if doc.doc_type_code == "220":
            report = doc.parse()  # → TreasuryStockReport
            print(f"  Parser:    {type(report).__name__}")
            print(f"  Company:   {report.filer_name}")
            if report.filer_name_en:
                print(f"             {report.filer_name_en}")
            print(f"  Ticker:    {report.ticker}")
            print(f"  Filed:     {report.filing_date}")
            print(f"  Period:    {report.reporting_period}")
            print(f"  Board auth:       {bool(report.by_board_meeting)}")
            print(f"  Shareholder auth: {bool(report.by_shareholders_meeting)}")
            return

    print("  No doc 220 found in the last 5 days")


def parse_securities_report(docs):
    """Parse a securities report (doc 120) — rich financial data."""
    print("\n--- Securities Report (Doc 120) ---")

    for doc in docs:
        if doc.doc_type_code == "120":
            report = doc.parse()  # → SecuritiesReport
            print(f"  Parser:       {type(report).__name__}")
            print(f"  Company:      {report.filer_name}")
            print(f"  Ticker:       {report.ticker}")
            print(f"  FY end:       {report.fiscal_year_end}")
            print(f"  Standard:     {report.accounting_standard}")
            print(f"  Consolidated: {report.is_consolidated}")
            if report.net_sales is not None:
                print(f"  Net sales:    ¥{report.net_sales:,}")
            if report.operating_income is not None:
                print(f"  Op. income:   ¥{report.operating_income:,}")
            if report.roe is not None:
                print(f"  ROE:          {report.roe}%")
            if report.equity_ratio is not None:
                print(f"  Equity ratio: {report.equity_ratio}%")
            return

    print("  No doc 120 found in the last 5 days")


def parse_internal_control(docs):
    """Parse an internal control report (doc 235) — J-SOX compliance."""
    print("\n--- Internal Control Report (Doc 235) ---")

    for doc in docs:
        if doc.doc_type_code in ("235", "236"):
            report = doc.parse()  # → InternalControlReport
            print(f"  Parser:    {type(report).__name__}")
            print(f"  Company:   {report.company_name or report.filer_name}")
            print(f"  Filed:     {report.filing_date}")
            if report.representative:
                print(f"  Signed by: {report.representative}")
            if report.cfo:
                print(f"  CFO:       {report.cfo}")
            if report.evaluation_result_text:
                preview = report.evaluation_result_text[:120].replace('\n', ' ')
                print(f"  Evaluation: {preview}...")
            print(f"  Amendment: {report.is_amendment}")
            return

    print("  No doc 235/236 found in the last 5 days")


# ── 4. Doc type registry ─────────────────────────────────────────

def doc_type_registry():
    """Browse the document type registry."""
    print("\n--- Doc Type Registry ---")

    all_types = edinet_tools.doc_types()
    print(f"{len(all_types)} document types registered\n")

    for dt in sorted(all_types, key=lambda t: t.code):
        print(f"  {dt.code}: {dt.name_en} ({dt.name_jp})")


# ── 5. supported_doc_types() — what has a typed parser ───────────

def show_supported_doc_types():
    """Show which doc types have typed parsers (not a generic fallback)."""
    print("\n--- Typed Parser Coverage ---")

    codes = edinet_tools.supported_doc_types()
    print(f"{len(codes)} doc types have typed parsers:\n")

    # Print in groups of 8 for readability
    for i in range(0, len(codes), 8):
        row = codes[i:i + 8]
        print("  " + "  ".join(row))

    print()
    # Highlight a few notable ones
    highlights = {
        "120": "Annual Securities Report",
        "235": "Internal Control Report (J-SOX)",
        "240": "Tender Offer Registration",
        "350": "Large Shareholding Report (>5%)",
    }
    print("Notable types:")
    for code, label in highlights.items():
        print(f"  {code}: {label}")


# ── 6. doc_type() — metadata for any code (even without a parser) ─

def show_doc_type_metadata():
    """Look up metadata for doc types, including those without typed parsers."""
    print("\n--- Doc Type Metadata Lookup ---")

    # Type 200 has metadata but no typed parser — falls back to RawReport
    dt = edinet_tools.doc_type("200")
    print(f"Code 200: {dt.name_en}")
    print(f"  Japanese: {dt.name_jp}")
    print(f"  Description: {dt.description}")

    from edinet_tools.parsers import supported_doc_types
    has_parser = "200" in supported_doc_types()
    print(f"  Has typed parser: {has_parser}  (falls back to RawReport)")

    print()

    # Type 235 has both metadata AND a typed parser
    dt2 = edinet_tools.doc_type("235")
    print(f"Code 235: {dt2.name_en}")
    print(f"  Japanese: {dt2.name_jp}")
    print(f"  Description: {dt2.description}")
    has_parser2 = "235" in supported_doc_types()
    print(f"  Has typed parser: {has_parser2}")


# ── 7. PDF download via fetch_document(type=2) ────────────────────

def show_pdf_download():
    """Show how to download PDF versions using the low-level API."""
    print("\n--- PDF Download (Low-Level API) ---")
    print("  The high-level doc.fetch() always returns the XBRL/CSV ZIP.")
    print("  For PDF, use the low-level fetch_document() with type=2:\n")
    print("    from edinet_tools.api import fetch_document")
    print()
    print("    doc_id = 'S100ABC123'")
    print()
    print("    # type=5 (default): XBRL-to-CSV ZIP — what parsers use")
    print("    xbrl_bytes = fetch_document(doc_id, type=5)")
    print()
    print("    # type=2: PDF version of the filing")
    print("    pdf_bytes  = fetch_document(doc_id, type=2)")
    print("    with open('filing.pdf', 'wb') as f:")
    print("        f.write(pdf_bytes)")
    print()
    print("    # type=1: HTML ZIP (full document with HTML + attachments)")
    print("    html_zip   = fetch_document(doc_id, type=1)")
    print()
    print("  Type reference:")
    print("    1 = HTML ZIP (PublicDoc, AuditDoc)")
    print("    2 = PDF")
    print("    3 = Attachment ZIP (AttachDoc)")
    print("    4 = English documents ZIP (EnglishDoc)")
    print("    5 = XBRL-to-CSV ZIP (default, used by parsers)")


# ── 8. Shelf registration parser (Doc 080) — static example ──────

def show_shelf_registration_parser():
    """Show the ShelfRegistrationReport parser using mock data."""
    print("\n--- Shelf Registration Parser (Doc 080) — Static Example ---")
    print("  Parser: ShelfRegistrationReport")
    print("  Filed when a company registers a shelf of securities")
    print("  it may issue over a defined future period.\n")
    print("  Key fields:")
    print("    shelf_registration_number  Unique identifier for the registration")
    print("    planned_period             Issuance window (Japanese text)")
    print("    security_types             Types of securities registered")
    print("    filing_date                Date of registration")
    print("    filer_edinet_code          EDINET code of the issuer")
    print()

    # Show what a parsed result looks like using the parser directly with mock CSV
    from edinet_tools.parsers.shelf_registration import (
        parse_shelf_registration,
        ShelfRegistrationReport,
        ELEMENT_MAP,
    )
    from edinet_tools.parsers.extraction import extract_csv_from_zip
    import io
    import zipfile

    # Build a minimal mock CSV (tab-separated, UTF-16LE as EDINET uses)
    rows = [
        f"{ELEMENT_MAP['filer_name']}\tlabel\tFilingDateInstant\t0\t連結\t期間\t\t\t東急不動産ホールディングス株式会社",
        f"{ELEMENT_MAP['filer_edinet_code']}\tlabel\tFilingDateInstant\t0\t連結\t期間\t\t\tE03063",
        f"{ELEMENT_MAP['shelf_registration_number']}\tlabel\tFilingDateInstant\t0\t連結\t期間\t\t\t第1号",
        f"{ELEMENT_MAP['filing_date']}\tlabel\tFilingDateInstant\t0\t連結\t期間\t\t\t2024-04-01",
        f"{ELEMENT_MAP['planned_period']}\tlabel\tFilingDateInstant\t0\t連結\t期間\t\t\t2024年4月1日から2026年3月31日まで",
        f"{ELEMENT_MAP['security_types']}\tlabel\tFilingDateInstant\t0\t連結\t期間\t\t\t社債券",
    ]
    content = '\n'.join(rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('XBRL_TO_CSV/test.csv', content.encode('utf-16le'))

    csv_files = extract_csv_from_zip(buf.getvalue())
    report = parse_shelf_registration(
        csv_files=csv_files,
        doc_id='S100MOCK1',
        doc_type_code='080',
    )

    print(f"  Result: {repr(report)}")
    print(f"    filer_name:                {report.filer_name}")
    print(f"    filer_edinet_code:         {report.filer_edinet_code}")
    print(f"    shelf_registration_number: {report.shelf_registration_number}")
    print(f"    filing_date:               {report.filing_date}")
    print(f"    planned_period:            {report.planned_period}")
    print(f"    security_types:            {report.security_types}")
    print(f"    is_amendment:              {report.is_amendment}")


# ── Main ──────────────────────────────────────────────────────────

def main():
    has_api_key = bool(os.getenv('EDINET_API_KEY'))

    print("EDINET Tools Quick Start")
    print("=" * 40)

    # Entity lookup and doc type features work without an API key
    entity_lookup()
    show_supported_doc_types()
    show_doc_type_metadata()
    show_pdf_download()
    show_shelf_registration_parser()

    # Doc type registry (all registered codes)
    print("\n--- Full Doc Type Registry ---")
    all_types = edinet_tools.doc_types()
    print(f"{len(all_types)} document types registered:")
    for dt in sorted(all_types, key=lambda t: t.code):
        print(f"  {dt.code}: {dt.name_en} ({dt.name_jp})")

    if not has_api_key:
        print("\n" + "-" * 40)
        print("Set EDINET_API_KEY for document features.")
        print("Get a free key: https://disclosure.edinet-fsa.go.jp/")
    else:
        docs = list_documents()
        if docs:
            parse_large_holding(docs)
            parse_treasury_stock(docs)
            parse_securities_report(docs)
            parse_internal_control(docs)

    print("\n" + "=" * 40)
    print("Getting Started:\n")
    print("  pip install edinet-tools\n")
    print("  import edinet_tools\n")
    print("  # Look up any company")
    print('  company = edinet_tools.entity("7203")')
    print(f"  # → {edinet_tools.entity('7203').name}\n")
    print("  # Show all doc types with typed parsers")
    print("  edinet_tools.supported_doc_types()")
    print(f"  # → {edinet_tools.supported_doc_types()[:4]} ...\n")
    print("  # Look up metadata for any doc type code")
    print('  edinet_tools.doc_type("235")')
    print("  # → DocType(code='235', name='Internal Control Report')\n")
    print("  # Get filings for a date")
    print('  docs = edinet_tools.documents("2026-01-20")\n')
    print("  # Parse → typed report object")
    print("  report = docs[0].parse()")
    print("  # → SecuritiesReport, LargeHoldingReport, InternalControlReport, etc.\n")
    print("  GitHub: https://github.com/matthelmer/edinet-tools")


if __name__ == "__main__":
    main()
