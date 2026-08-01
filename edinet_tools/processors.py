# document_processors.py
import logging
from typing import List, Dict, Any, Optional
from .parser import extract_xbrl_financial_data

logger = logging.getLogger(__name__)

# Define the structure of the output dictionary for document processors
# This structured_data is what will be passed to the LLM tools
StructuredDocumentData = Dict[str, Any]

class BaseDocumentProcessor:
    """Base class for document specific data extraction."""

    def __init__(self, raw_csv_data: List[Dict[str, Any]], doc_id: str, doc_type_code: str, zip_extract_path: str = None):
        """
        Initialize with raw data from CSV files and document metadata.

        Args:
            raw_csv_data: List of dictionaries, each containing 'filename' and 'data' (list of rows/dicts).
            doc_id: EDINET document ID.
            doc_type_code: EDINET document type code.
            zip_extract_path: Path to extracted ZIP contents for XBRL processing.
        """
        self.raw_csv_data = raw_csv_data
        self.doc_id = doc_id
        self.doc_type_code = doc_type_code
        self.zip_extract_path = zip_extract_path
        # Combine all rows from all CSVs for easier querying
        self.all_records = self._combine_raw_data()

    def _combine_raw_data(self) -> List[Dict[str, Any]]:
        """Combine all rows from all CSV files into a single list."""
        combined = []
        for csv_file in self.raw_csv_data:
            # Add filename source to each row for debugging/context if needed
            # for row in csv_file.get('data', []):
            #     row['_source_file'] = csv_file.get('filename')
            combined.extend(csv_file.get('data', []))
        return combined

    def get_value_by_id(self, element_id: str, context_filter: Optional[str] = None) -> Optional[str]:
        """Helper to find a value for a specific element ID, optionally filtered by context."""
        for record in self.all_records:
            if record.get('要素ID') == element_id:
                if context_filter is None or (record.get('コンテキストID') and context_filter in record['コンテキストID']):
                    value = record.get('値')
                    # Clean the text values
                    from .utils import clean_text # Avoid circular import by importing here
                    return clean_text(value)
        return None

    def get_records_by_id(self, element_id: str) -> List[Dict[str, Any]]:
        """Helper to find all records for a specific element ID."""
        return [
            record for record in self.all_records
            if record.get('要素ID') == element_id
        ]

    def get_all_text_blocks(self) -> List[Dict[str, str]]:
        """Extract all generic TextBlock elements."""
        text_blocks = []
        for record in self.all_records:
            element_id = record.get('要素ID')
            value = record.get('値')
            item_name = record.get('項目名', element_id) # Use 項目名 (item name) as title

            if element_id and 'TextBlock' in element_id and value:
                text_blocks.append({
                    'id': element_id,
                    'title': item_name or element_id,  # Ensure title is not None
                    'content': value # Keep original value before cleaning for LLM to process
                })
            # Include report submission reason which may not have "TextBlock" in the ID
            elif element_id and value and (('ReasonForFiling' in element_id) or (item_name and '提出理由' in item_name)):
                 text_blocks.append({
                    'id': element_id,
                    'title': item_name or element_id,  # Ensure title is not None
                    'content': value # Keep original value before cleaning for LLM to process
                })

        return text_blocks

    def process(self) -> Optional[StructuredDocumentData]:
        """
        Process the raw CSV data into a structured dictionary.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement the 'process' method")

    def _get_common_metadata(self) -> Dict[str, Optional[str]]:
         """Extract common metadata available in many filings."""
         from .utils import clean_text # Avoid circular import
         metadata = {}
         id_to_key = {
            'jpdei_cor:EDINETCodeDEI': 'edinet_code',
            'jpdei_cor:FilerNameInJapaneseDEI': 'company_name_ja',
            'jpdei_cor:FilerNameInEnglishDEI': 'company_name_en',
            'jpdei_cor:DocumentTypeDEI': 'document_type',
            'jpcrp-esr_cor:DocumentTitleCoverPage': 'document_title', # Common in some reports
            'jpcrp_cor:DocumentTitle': 'document_title', # Common in others
         }
         for key, element_id in id_to_key.items():
              value = self.get_value_by_id(key)
              if value is not None:
                   metadata[element_id] = clean_text(value)

         # Add doc_id and doc_type_code from the zip filename metadata
         metadata['doc_id'] = self.doc_id
         metadata['doc_type_code'] = self.doc_type_code

         return metadata


class ExtraordinaryReportProcessor(BaseDocumentProcessor):
    """Processor for Extraordinary Reports (doc_type_code '180')."""

    def process(self) -> Optional[StructuredDocumentData]:
        """Extract key data points and text blocks for Extraordinary Reports."""
        logger.debug(f"Processing Extraordinary Report (doc_id: {self.doc_id})")
        structured_data = self._get_common_metadata()

        # Extract specific facts often found in Extraordinary Reports
        key_facts = {}
        # Example: Look for elements related to decisions, resolutions, changes, M&A
        important_element_ids = [
            'jpcrp-esr_cor:ResolutionOfBoardOfDirectorsDescription', # 取締役会決議に関する事項
            'jpcrp-esr_cor:SummaryOfReasonForSubmissionDescription', # 提出理由の概要
            'jpcrp-esr_cor:ContentOfDecisionsDescription', # 決定の内容
            'jpcrp-esr_cor:DateOfResolutionOfBoardOfDirectors', # 取締役会決議日
            'jpcrp-esr_cor:DateOfOccurrence', # 発生日
            'jpcrp-esr_cor:SummaryOfAgreementDescription', # 契約等の概要
            'jpcrp-esr_cor:DetailsOfTransactionPartiesDescription', # 取引相手の概要
            'jpcrp-esr_cor:RationaleForTransactionDescription', # 取引理由
            'jpcrp-esr_cor:ImpactOnBusinessResultsDescription', # 業績に与える影響
        ]
        for element_id in important_element_ids:
            value = self.get_value_by_id(element_id)
            if value is not None:
                # Use a cleaner key name for the fact
                fact_key = element_id.split(':')[-1].replace('Description', '').replace('SummaryOf', '').replace('DetailsOf', '').replace('RationaleFor', '').replace('ImpactOnBusinessResults', 'ImpactOnResults')
                key_facts[fact_key] = value

        structured_data['key_facts'] = key_facts
        structured_data['text_blocks'] = self.get_all_text_blocks() # Include all text blocks as well

        logger.debug(f"Finished processing Extraordinary Report {self.doc_id}. Extracted {len(key_facts)} key facts and {len(structured_data['text_blocks'])} text blocks.")
        return structured_data if structured_data else None


class SemiAnnualReportProcessor(BaseDocumentProcessor):
    """Processor for Semi-Annual Reports (doc_type_code '160')."""

    def process(self) -> Optional[StructuredDocumentData]:
        """Extract key data points, tables, and text blocks for Semi-Annual Reports."""
        logger.debug(f"Processing Semi-Annual Report (doc_id: {self.doc_id})")
        structured_data = self._get_common_metadata()

        # --- Extract XBRL Financial Metrics (Enhanced approach) ---
        xbrl_data = {}
        if self.zip_extract_path:
            try:
                xbrl_data = extract_xbrl_financial_data(self.zip_extract_path)
                logger.debug(f"Extracted XBRL data with {len(xbrl_data.get('financial_metrics', {}))} metrics")
            except Exception as e:
                logger.warning(f"Error extracting XBRL data for {self.doc_id}: {e}")
                xbrl_data = {'has_xbrl_data': False}

        # --- Extract Key Financial Metrics (as key_facts) ---
        # Use XBRL data if available (more accurate), otherwise fallback to CSV approach
        if xbrl_data.get('has_xbrl_data', False) and xbrl_data.get('financial_metrics'):
            # Use enhanced XBRL financial metrics
            key_facts = xbrl_data['financial_metrics'].copy()
            logger.debug(f"Using XBRL financial metrics: {list(key_facts.keys())}")
        else:
            # Fallback to legacy CSV-based approach
            logger.debug("XBRL data not available, using legacy CSV approach")
            key_metrics_map = {
                'jpcrp_cor:OperatingRevenue1SummaryOfBusinessResults': 'OperatingRevenue', # 営業収益
                'jpcrp_cor:OrdinaryIncome': 'OrdinaryIncome', # 経常利益
                'jppfs_cor:ProfitLossAttributableToOwnersOfParent': 'NetIncome', # 親会社株主に帰属する当期純利益
                'jpcrp_cor:BasicEarningsLossPerShareSummaryOfBusinessResults': 'EPS', # 1株当たり当期純利益
                'jpcrp_cor:NetAssetsSummaryOfBusinessResults': 'NetAssets', # 純資産額
                'jpcrp_cor:TotalAssetsSummaryOfBusinessResults': 'TotalAssets', # 総資産額
                'jpcrp_cor:CashAndCashEquivalentsSummaryOfBusinessResults': 'CashAndCashEquivalents', # 現金及び現金同等物
            }
            key_facts = {}
            for xbrl_id, fact_key in key_metrics_map.items():
                current_value = self.get_value_by_id(xbrl_id, context_filter='Current') # Look for Current* contexts
                prior_value = self.get_value_by_id(xbrl_id, context_filter='Prior') # Look for Prior* contexts

                if current_value is not None or prior_value is not None:
                     key_facts[fact_key] = {
                         'current': current_value,
                         'prior': prior_value,
                     }

        # Add XBRL metadata to structured data
        if xbrl_data.get('has_xbrl_data', False):
            structured_data['xbrl_metrics_count'] = xbrl_data.get('metrics_count', 0)
            structured_data['has_enhanced_financials'] = True
        else:
            structured_data['has_enhanced_financials'] = False

        structured_data['key_facts'] = key_facts

        # --- Extract Key Tables (e.g., Financial Statements) ---
        financial_tables_map = {
            'jpigp_cor:CondensedQuarterlyConsolidatedStatementOfFinancialPositionIFRSTextBlock': 'Consolidated Statement of Financial Position',
            'jpigp_cor:CondensedYearToQuarterEndConsolidatedStatementOfProfitOrLossIFRSTextBlock': 'Consolidated Statement of Profit or Loss',
            # Add more table IDs as identified from Semi-Annual reports
        }
        structured_data['financial_tables'] = []
        for xbrl_id, table_title_en in financial_tables_map.items():
             # Find the specific text block containing the table data (often rendered as text)
             table_text_block = self.get_value_by_id(xbrl_id)
             if table_text_block:
                  structured_data['financial_tables'].append({
                       'title_en': table_title_en,
                       'raw_text_content': table_text_block
                  })


        # --- Extract Key Text Blocks (Commentary) ---
        # Define a list of important text block IDs and their English titles
        text_block_elements = [
            ('jpcrp_cor:BusinessResultsOfGroupTextBlock', 'Group Business Results'),
            ('jpcrp_cor:DescriptionOfBusinessTextBlock', 'Description of Business'),
            ('jpcrp_cor:BusinessRisksTextBlock', 'Business Risks'),
            ('jpcrp_cor:ManagementAnalysisOfFinancialPositionOperatingResultsAndCashFlowsTextBlock', 'Management Analysis'),
            ('jpcrp_cor:MajorShareholdersTextBlock', 'Major Shareholders'),
            ('jpigp_cor:NotesSegmentInformationCondensedQuarterlyConsolidatedFinancialStatementsIFRSTextBlock', 'Segment Information Notes'),
            # Add more key text block IDs relevant to semi-annual reports
        ]
        structured_data['text_blocks'] = []
        for xbrl_id, title_en in text_block_elements:
            content = self.get_value_by_id(xbrl_id) # Get the raw text content
            if content:
                structured_data['text_blocks'].append({
                    'id': xbrl_id,
                    'title_en': title_en,
                    'content_jp': content # Keep Japanese content for LLM translation
                })
        # Fallback to include all text blocks if specific ones aren't found (less structured)
        if not structured_data['text_blocks']:
             logger.info(f"Using generic text block extraction for {self.doc_id} (document may be investment trust or non-standard format).")
             structured_data['text_blocks'] = self.get_all_text_blocks()


        logger.debug(f"Finished processing Semi-Annual Report {self.doc_id}. Extracted {len(key_facts)} key facts, {len(structured_data['financial_tables'])} financial tables, and {len(structured_data['text_blocks'])} text blocks.")
        return structured_data if structured_data else None


class SecuritiesReportProcessor(BaseDocumentProcessor):
    """Processor for Securities Reports (doc_type_code '120')."""

    def process(self) -> Optional[StructuredDocumentData]:
        """Extract key data points, tables, and text blocks for Securities Reports."""
        logger.debug(f"Processing Securities Report (doc_id: {self.doc_id})")
        structured_data = self._get_common_metadata()

        # Securities Reports have rich financial data and comprehensive disclosures
        # Extract key financial metrics first
        key_facts = self._extract_financial_metrics()
        
        # Extract business and operational information
        key_facts.update(self._extract_business_facts())
        
        structured_data['key_facts'] = key_facts

        # Extract financial statement tables
        structured_data['financial_tables'] = self._extract_financial_tables()

        # Categorize and extract all text blocks
        structured_data['text_blocks'] = self._categorize_text_blocks()

        logger.debug(f"Finished processing Securities Report {self.doc_id}. Extracted {len(key_facts)} key facts, {len(structured_data['financial_tables'])} financial tables, and {len(structured_data['text_blocks'])} text blocks.")
        return structured_data if structured_data else None

    def _extract_financial_metrics(self) -> Dict[str, Any]:
        """Extract common financial metrics from Securities Reports."""
        financial_metrics = {}
        
        # Common financial metrics across industries
        common_metrics = {
            # Revenue/Income Statement
            'jpcrp_cor:NetSales': 'net_sales',
            'jpcrp_cor:OperatingRevenue1': 'operating_revenue', 
            'jpcrp_cor:OperatingIncome': 'operating_income',
            'jpcrp_cor:OrdinaryIncome': 'ordinary_income',
            'jpcrp_cor:NetIncome': 'net_income',
            'jppfs_cor:ProfitLossAttributableToOwnersOfParent': 'net_income_attributable_to_owners',
            
            # Balance Sheet  
            'jpcrp_cor:TotalAssets': 'total_assets',
            'jpcrp_cor:NetAssets': 'net_assets', 
            'jpcrp_cor:TotalEquity': 'total_equity',
            
            # Per Share Data
            'jpcrp_cor:BasicEarningsLossPerShare': 'earnings_per_share',
            'jpcrp_cor:BookValuePerShare': 'book_value_per_share',
            
            # Cash Flow
            'jpcrp_cor:CashFlowsFromOperatingActivities': 'operating_cash_flow',
            'jpcrp_cor:CashFlowsFromInvestmentActivities': 'investing_cash_flow',
            'jpcrp_cor:CashFlowsFromFinancingActivities': 'financing_cash_flow',
        }
        
        # Extract metrics with current/prior period context if available
        for xbrl_id, metric_key in common_metrics.items():
            current_value = self.get_value_by_id(xbrl_id, context_filter='Current')
            prior_value = self.get_value_by_id(xbrl_id, context_filter='Prior')
            
            # If no context-specific value, try without filter
            if current_value is None and prior_value is None:
                any_value = self.get_value_by_id(xbrl_id)
                if any_value is not None:
                    financial_metrics[metric_key] = any_value
            else:
                if current_value is not None or prior_value is not None:
                    financial_metrics[metric_key] = {
                        'current': current_value,
                        'prior': prior_value
                    }
        
        return financial_metrics

    def _extract_business_facts(self) -> Dict[str, Any]:
        """Extract business and operational facts specific to Securities Reports."""
        business_facts = {}
        
        # Key business information elements
        business_elements = {
            'jpcrp_cor:NumberOfEmployees': 'employee_count',
            'jpcrp_cor:AverageAnnualSalary': 'average_annual_salary', 
            'jpcrp_cor:NumberOfSharesIssuedAndOutstanding': 'shares_outstanding',
            'jpcrp_cor:FiscalYearEnd': 'fiscal_year_end',
            'jpcrp_cor:AccountingStandardsFollowedInPreparationOfFinancialStatements': 'accounting_standards',
        }
        
        for xbrl_id, fact_key in business_elements.items():
            value = self.get_value_by_id(xbrl_id)
            if value is not None:
                business_facts[fact_key] = value
                
        return business_facts

    def _extract_financial_tables(self) -> List[Dict[str, Any]]:
        """Extract structured financial statement tables."""
        financial_tables = []
        
        # Key financial statement table patterns
        table_elements = {
            'jpcrp_cor:ConsolidatedStatementsOfIncome': 'Consolidated Income Statement',
            'jpcrp_cor:ConsolidatedBalanceSheets': 'Consolidated Balance Sheet', 
            'jpcrp_cor:ConsolidatedStatementsOfCashFlows': 'Consolidated Cash Flow Statement',
            'jpcrp_cor:ConsolidatedStatementsOfEquity': 'Consolidated Statement of Equity',
            'jpcrp_cor:SegmentInformation': 'Segment Information',
        }
        
        for xbrl_id, table_title in table_elements.items():
            table_content = self.get_value_by_id(xbrl_id)
            if table_content:
                financial_tables.append({
                    'id': xbrl_id,
                    'title': table_title,
                    'content': table_content
                })
        
        return financial_tables

    def _categorize_text_blocks(self) -> List[Dict[str, Any]]:
        """Categorize and extract all text blocks, ensuring no data loss."""
        all_blocks = self.get_all_text_blocks()
        
        # Add categorization to help with analysis
        for block in all_blocks:
            element_id = block.get('id', '')
            block['category'] = self._categorize_element(element_id)
            
        return all_blocks

    def _categorize_element(self, element_id: str) -> str:
        """Categorize XBRL elements by business area."""
        if not element_id:
            return 'unknown'
            
        # Business area categorization
        if any(keyword in element_id.lower() for keyword in ['business', 'segment', 'product', 'service']):
            return 'business_overview'
        elif any(keyword in element_id.lower() for keyword in ['risk', 'uncertainty', 'contingency']):
            return 'risk_factors'  
        elif any(keyword in element_id.lower() for keyword in ['management', 'analysis', 'md&a', 'financial_position']):
            return 'management_analysis'
        elif any(keyword in element_id.lower() for keyword in ['corporate', 'governance', 'director', 'officer']):
            return 'corporate_governance'
        elif any(keyword in element_id.lower() for keyword in ['shareholder', 'dividend', 'stock']):
            return 'shareholder_information'
        elif any(keyword in element_id.lower() for keyword in ['accounting', 'policy', 'standard', 'method']):
            return 'accounting_information'
        else:
            return 'other'


class InternalControlReportProcessor(BaseDocumentProcessor):
    """Processor for Internal Control Reports (doc_type_code '235')."""

    def process(self) -> Optional[StructuredDocumentData]:
        """Extract key data points and text blocks for Internal Control Reports."""
        logger.debug(f"Processing Internal Control Report (doc_id: {self.doc_id})")
        structured_data = self._get_common_metadata()

        # Internal Control Reports have specific compliance information
        key_facts = {}
        
        # Key internal control elements
        control_elements = {
            'jpcrp_cor:InternalControlAssessmentResult': 'assessment_result',
            'jpcrp_cor:MaterialWeaknessInInternalControl': 'material_weakness',
            'jpcrp_cor:RemediationOfMaterialWeakness': 'remediation_actions',
        }
        
        for xbrl_id, fact_key in control_elements.items():
            value = self.get_value_by_id(xbrl_id)
            if value is not None:
                key_facts[fact_key] = value

        structured_data['key_facts'] = key_facts
        structured_data['financial_tables'] = []  # Internal control reports don't have financial tables
        structured_data['text_blocks'] = self.get_all_text_blocks()

        logger.debug(f"Finished processing Internal Control Report {self.doc_id}. Extracted {len(key_facts)} key facts and {len(structured_data['text_blocks'])} text blocks.")
        return structured_data if structured_data else None


class GenericReportProcessor(BaseDocumentProcessor):
    """Processor for other document types (default)."""

    def process(self) -> Optional[StructuredDocumentData]:
        """Extract common metadata and all text blocks for generic reports."""
        logger.debug(f"Processing Generic Report (doc_id: {self.doc_id}, type: {self.doc_type_code})")
        structured_data = self._get_common_metadata()
        structured_data['key_facts'] = {} # Generic reports might not have standardized facts
        structured_data['financial_tables'] = [] # Or standardized tables

        # For generic reports, primarily extract all text blocks
        structured_data['text_blocks'] = self.get_all_text_blocks()

        logger.debug(f"Finished processing Generic Report {self.doc_id}. Extracted {len(structured_data['text_blocks'])} text blocks.")
        return structured_data if structured_data else None


# Dispatcher Function
def process_raw_csv_data(raw_csv_data: List[Dict[str, Any]], doc_id: str, doc_type_code: str, zip_extract_path: str = None) -> Optional[StructuredDocumentData]:
    """
    Dispatches raw CSV data to the appropriate document processor.

    Args:
        raw_csv_data: List of dictionaries from reading CSV files.
        doc_id: EDINET document ID.
        doc_type_code: EDINET document type code.
        zip_extract_path: Path to extracted ZIP contents for XBRL processing.

    Returns:
        Structured dictionary of the document's data, or None if processing failed.
    """
    processor_map = {
        '180': ExtraordinaryReportProcessor,
        '160': SemiAnnualReportProcessor,
        '120': SecuritiesReportProcessor,
        '235': InternalControlReportProcessor,
        # Add other specific processors here
    }
    default_processor = GenericReportProcessor

    processor_class = processor_map.get(doc_type_code, default_processor)
    logger.debug(f"Using processor {processor_class.__name__} for document type {doc_type_code} (doc_id: {doc_id})")

    try:
        processor = processor_class(raw_csv_data, doc_id, doc_type_code, zip_extract_path)
        return processor.process()
    except Exception as e:
        logger.error(f"Error during processing with {processor_class.__name__} for document {doc_id}: {e}")
        return None
