"""Financial-sector filers (8699 HS Holdings: securities) report revenue as
OperatingRevenue (営業収益), not NetSales. Without the mapping, net_sales is
NULL or a tiny sub-line and operating_income > net_sales (impossible margin).
"""
from edinet_tools.parsers.securities import parse_securities_report
from tests.conftest import load_securities_fixture

def _parse(name):
    cf = load_securities_fixture(name)
    return parse_securities_report(csv_files=cf, doc_id='TEST', doc_type_code='120')


def test_financial_filer_net_sales_from_operating_revenue():
    r = _parse('hsholdings_fy_revenue')
    assert r.net_sales == 37766000000
    assert r.prior_net_sales == 49597000000
    # impossible-margin gone
    assert r.operating_income is None or r.operating_income <= r.net_sales


# Securities brokers tag their top-line revenue as 営業収益 (operating revenue)
# via broker-ordinance elements distinct from the generic NetSales/OrdinaryIncome
# summary tiers: jpcrp_cor:OperatingRevenue1SummaryOfBusinessResults (summary
# table) and jppfs_cor:OperatingRevenueSEC (FS-level fallback). Both carry the
# GROSS top-line figure — 純営業収益 (NetOperatingRevenueSEC, after financial
# expenses) and 金融収益 (FinancialRevenueORSEC, a component) are deliberately
# NOT mapped here. Values pinned below are IR-verified against each broker's
# own published 決算短信 (financial results announcement) to the yen.

def test_broker_consolidated_operating_revenue_summary_feeds_net_sales():
    # Consolidated broker (summary + FS elements agree at the bare context).
    r = _parse('broker_jgaap_a')
    assert r.net_sales == 1467983000000
    assert r.prior_net_sales == 1372014000000


def test_broker_nonconsolidated_operating_revenue_summary_feeds_net_sales():
    # Non-consolidated-only broker (WhetherConsolidatedFinancialStatementsArePreparedDEI
    # = false); the _NonConsolidatedMember context must be picked up.
    r = _parse('broker_jgaap_b')
    assert r.net_sales == 52660000000
    assert r.prior_net_sales == 39204000000


def test_broker_operating_revenue_fs_fallback_feeds_net_sales():
    r = _parse('broker_jgaap_c')
    assert r.net_sales == 95595000000
    assert r.prior_net_sales == 81936000000
