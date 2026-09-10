"""
DocType registry for EDINET document types.

Provides metadata about document types including English/Japanese names
and descriptions. Every doc type code a user might encounter is registered
here, even those without typed parsers.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class DocType:
    """
    EDINET document type metadata.

    Attributes:
        code: Document type code (e.g., "350")
        name_en: English name
        name_jp: Japanese name
        description: Brief description of the document type
    """
    code: str
    name_en: str
    name_jp: str
    description: str = ""

    def __repr__(self) -> str:
        return f"DocType(code='{self.code}', name='{self.name_en}')"


# Registry of all known EDINET document types.
# Organized by family: securities notification/registration (010-110),
# periodic reports (120-210), treasury/internal control (220-236),
# tender offer (240-340), large shareholding (350-380).
_DOC_TYPES: dict[str, DocType] = {

    # === Securities Notification (有価証券通知書) family (010-020) ===
    "010": DocType(
        code="010",
        name_en="Securities Notification",
        name_jp="有価証券通知書",
        description="Notification for new securities issuance",
    ),
    "020": DocType(
        code="020",
        name_en="Securities Notification Amendment",
        name_jp="変更通知書（有価証券通知書）",
        description="Amendment to securities notification",
    ),

    # === Securities Registration Statement (有価証券届出書) family (030-050) ===
    "030": DocType(
        code="030",
        name_en="Securities Registration Statement",
        name_jp="有価証券届出書",
        description="Registration statement for new securities issuance",
    ),
    "040": DocType(
        code="040",
        name_en="Securities Registration Statement Amendment",
        name_jp="訂正有価証券届出書",
        description="Amendment to securities registration statement",
    ),
    "050": DocType(
        code="050",
        name_en="Securities Registration Withdrawal",
        name_jp="届出の取下げ願い",
        description="Withdrawal of securities registration statement",
    ),

    # === Issuance Registration / Shelf Registration (発行登録書) family (060-110) ===
    "060": DocType(
        code="060",
        name_en="Issuance Registration Notification",
        name_jp="発行登録通知書",
        description="Notification of issuance registration",
    ),
    "070": DocType(
        code="070",
        name_en="Amendment Notification (Issuance Registration Notification)",
        name_jp="変更通知書（発行登録通知書）",
        description="Change notification for an issuance registration notification",
    ),
    "080": DocType(
        code="080",
        name_en="Issuance Registration Statement",
        name_jp="発行登録書",
        description="Issuance (shelf) registration statement",
    ),
    "090": DocType(
        code="090",
        name_en="Issuance Registration Statement Amendment",
        name_jp="訂正発行登録書",
        description="Amendment to issuance registration statement",
    ),
    "100": DocType(
        code="100",
        name_en="Supplementary Issuance Registration Document",
        name_jp="発行登録追補書類",
        description="Supplementary document for shelf registration drawdown",
    ),
    "110": DocType(
        code="110",
        name_en="Issuance Registration Withdrawal",
        name_jp="発行登録取下届出書",
        description="Withdrawal of issuance registration",
    ),

    # === Periodic Reports (有価証券報告書 / 四半期報告書 etc.) family (120-210) ===
    "120": DocType(
        code="120",
        name_en="Securities Report",
        name_jp="有価証券報告書",
        description="Annual securities report filed by listed companies",
    ),
    "130": DocType(
        code="130",
        name_en="Securities Report Amendment",
        name_jp="訂正有価証券報告書",
        description="Amendment to annual securities report",
    ),
    "135": DocType(
        code="135",
        name_en="Confirmation Document",
        name_jp="確認書",
        description="CEO/CFO confirmation document accompanying annual report",
    ),
    "136": DocType(
        code="136",
        name_en="Confirmation Document Amendment",
        name_jp="訂正確認書",
        description="Amendment to confirmation document",
    ),
    "140": DocType(
        code="140",
        name_en="Quarterly Report",
        name_jp="四半期報告書",
        description="Quarterly financial report (Q1, Q2, Q3); abolished April 2024",
    ),
    "150": DocType(
        code="150",
        name_en="Quarterly Report Amendment",
        name_jp="訂正四半期報告書",
        description="Amendment to quarterly report",
    ),
    "160": DocType(
        code="160",
        name_en="Semi-Annual Report",
        name_jp="半期報告書",
        description="Semi-annual report (primarily for investment funds)",
    ),
    "170": DocType(
        code="170",
        name_en="Semi-Annual Report Amendment",
        name_jp="訂正半期報告書",
        description="Amendment to semi-annual report",
    ),
    "180": DocType(
        code="180",
        name_en="Extraordinary Report",
        name_jp="臨時報告書",
        description="Report on material events (M&A, management changes, etc.)",
    ),
    "190": DocType(
        code="190",
        name_en="Extraordinary Report Amendment",
        name_jp="訂正臨時報告書",
        description="Amendment to extraordinary report",
    ),
    "200": DocType(
        code="200",
        name_en="Parent Company Status Report",
        name_jp="親会社等状況報告書",
        description="Report on parent company status",
    ),
    "210": DocType(
        code="210",
        name_en="Parent Company Status Report Amendment",
        name_jp="訂正親会社等状況報告書",
        description="Amendment to parent company status report",
    ),

    # === Treasury Stock / Internal Control (自己株 / 内部統制) family (220-236) ===
    "220": DocType(
        code="220",
        name_en="Treasury Stock Report",
        name_jp="自己株券買付状況報告書",
        description="Report on treasury stock (share buyback) acquisition status",
    ),
    "230": DocType(
        code="230",
        name_en="Treasury Stock Report Amendment",
        name_jp="訂正自己株券買付状況報告書",
        description="Amendment to treasury stock report",
    ),
    "235": DocType(
        code="235",
        name_en="Internal Control Report",
        name_jp="内部統制報告書",
        description="Internal control report (J-SOX)",
    ),
    "236": DocType(
        code="236",
        name_en="Internal Control Report Amendment",
        name_jp="訂正内部統制報告書",
        description="Amendment to internal control report",
    ),

    # === Tender Offer (公開買付) family (240-340) ===
    "240": DocType(
        code="240",
        name_en="Tender Offer Registration",
        name_jp="公開買付届出書",
        description="Registration for tender offer (TOB)",
    ),
    "250": DocType(
        code="250",
        name_en="Tender Offer Registration Amendment",
        name_jp="訂正公開買付届出書",
        description="Amendment to tender offer registration",
    ),
    "260": DocType(
        code="260",
        name_en="Tender Offer Withdrawal",
        name_jp="公開買付撤回届出書",
        description="Withdrawal of tender offer",
    ),
    "270": DocType(
        code="270",
        name_en="Tender Offer Report",
        name_jp="公開買付報告書",
        description="Report on completion of tender offer",
    ),
    "280": DocType(
        code="280",
        name_en="Tender Offer Report Amendment",
        name_jp="訂正公開買付報告書",
        description="Amendment to tender offer completion report",
    ),
    "290": DocType(
        code="290",
        name_en="Statement of Opinion Report",
        name_jp="意見表明報告書",
        description="Target company's statement of opinion on a tender offer",
    ),
    "300": DocType(
        code="300",
        name_en="Statement of Opinion Report Amendment",
        name_jp="訂正意見表明報告書",
        description="Amendment to statement of opinion report",
    ),
    "310": DocType(
        code="310",
        name_en="Response to Questions Report",
        name_jp="対質問回答報告書",
        description="Target company's response to acquirer's questions",
    ),
    "320": DocType(
        code="320",
        name_en="Response to Questions Report Amendment",
        name_jp="訂正対質問回答報告書",
        description="Amendment to response to questions report",
    ),
    "330": DocType(
        code="330",
        name_en="Exemption Application",
        name_jp="別途買付け禁止の特例を受けるための申出書",
        description="Application for exemption from separate purchase prohibition",
    ),
    "340": DocType(
        code="340",
        name_en="Exemption Application Amendment",
        name_jp="訂正別途買付け禁止の特例を受けるための申出書",
        description="Amendment to exemption application",
    ),

    # === Large Shareholding Reports (大量保有報告書) family (350-380) ===
    "350": DocType(
        code="350",
        name_en="Large Shareholding Report",
        name_jp="大量保有報告書",
        description="Report when ownership exceeds 5% of a listed company",
    ),
    "360": DocType(
        code="360",
        name_en="Large Shareholding Report Amendment",
        name_jp="訂正大量保有報告書",
        description="Amendment to large shareholding report",
    ),
    "370": DocType(
        code="370",
        name_en="Reference Date Notification",
        name_jp="基準日の届出書",
        description="Notification of a reference (record) date under the large shareholding rules",
    ),
    "380": DocType(
        code="380",
        name_en="Change Notification",
        name_jp="変更の届出書",
        description="Notification of a change to a reference date notification",
    ),
}


def doc_type(code: str) -> DocType | None:
    """
    Look up a document type by code.

    Args:
        code: Document type code (e.g., "350")

    Returns:
        DocType object or None if not found
    """
    return _DOC_TYPES.get(code)


def list_doc_types() -> list[DocType]:
    """
    Get all registered document types.

    Returns:
        List of all DocType objects
    """
    return list(_DOC_TYPES.values())


# Shorter alias (v0.2)
def doc_types() -> list[DocType]:
    """
    Get all registered document types.

    Alias for list_doc_types().

    Returns:
        List of all DocType objects
    """
    return list_doc_types()
