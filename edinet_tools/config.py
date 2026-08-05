# config.py
import os
import logging

# edinet-tools reads EDINET_API_KEY from the process environment only. It
# does not load .env files itself — a library shouldn't mutate process env
# as an import side effect. If you keep your key in a .env file, load it in
# YOUR application before importing edinet_tools (e.g. via `python-dotenv`:
# `from dotenv import load_dotenv; load_dotenv()`).
EDINET_API_KEY = os.environ.get('EDINET_API_KEY')

if not EDINET_API_KEY:
    logging.warning("EDINET_API_KEY not set in .env file.")

# Complete EDINET document types mapping
# Based on official EDINET documentation and API specifications
SUPPORTED_DOC_TYPES = {
    "010": "Securities Notification",
    "020": "Amendment Notification (Securities Notification)",
    "030": "Securities Registration Statement",
    "040": "Amended Securities Registration Statement",
    "050": "Withdrawal Request for Registration",
    "060": "Issuance Registration Notification",
    "070": "Amendment Notification (Issuance Registration Notification)",
    "080": "Issuance Registration Statement",
    "090": "Amended Issuance Registration Statement",
    "100": "Supplementary Issuance Registration Document",
    "110": "Issuance Registration Withdrawal Statement",
    "120": "Securities Report",
    "130": "Securities Report (Amended)",
    "135": "Confirmation Document",
    "136": "Amended Confirmation Document",
    "140": "Quarterly Report",
    "150": "Quarterly Report (Amended)",
    "160": "Semi-Annual Report",
    "170": "Semi-Annual Report (Amended)",
    "180": "Extraordinary Report",
    "190": "Amended Extraordinary Report",
    "200": "Parent Company Status Report",
    "210": "Amended Parent Company Status Report",
    "220": "Treasury Stock Purchase Status Report",
    "230": "Amended Treasury Stock Purchase Status Report",
    "235": "Internal Control Report",
    "236": "Amended Internal Control Report",
    "240": "Tender Offer Registration",
    "250": "Amended Tender Offer Registration Statement",
    "260": "Tender Offer Withdrawal",
    "270": "Tender Offer Report",
    "280": "Amended Tender Offer Report",
    "300": "Amended Statement of Opinion Report",
    "320": "Amended Response to Questions Report",
    "340": "Amended Application for Exemption from Separate Purchase Prohibition",
    "350": "Large Holding Report",
    "360": "Amended Large Shareholding Report",
    "370": "Reference Date Notification",
    "380": "Change Notification",
}
