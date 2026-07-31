"""
Tests for edinet_tools.processors module (document processing functionality).

Tests all document processors including the new specialized processors for different
document types, ensuring proper data extraction and no data loss.
"""

import pytest
from unittest.mock import Mock, patch
from edinet_tools.processors import (
    BaseDocumentProcessor,
    ExtraordinaryReportProcessor, 
    SemiAnnualReportProcessor,
    SecuritiesReportProcessor,
    InternalControlReportProcessor,
    GenericReportProcessor,
    process_raw_csv_data
)


class TestBaseDocumentProcessor:
    """Test the base document processor functionality."""
    
    def setup_method(self):
        """Set up test data for base processor."""
        # Mock CSV data with Japanese XBRL structure
        self.mock_csv_data = [
            {
                'filename': 'test_file.csv',
                'data': [
                    {'要素ID': 'jpdei_cor:EDINETCodeDEI', '項目名': 'EDINET Code', '値': 'E02144'},
                    {'要素ID': 'jpdei_cor:FilerNameInJapaneseDEI', '項目名': '会社名', '値': 'テスト株式会社'},
                    {'要素ID': 'jpcrp_cor:BusinessResultsTextBlock', '項目名': 'Business Results', '値': 'Test business content'},
                    {'要素ID': 'jpcrp_cor:NetSales', '項目名': 'Net Sales', 'コンテキストID': 'CurrentYear', '値': '1000000'},
                    {'要素ID': 'jpcrp_cor:NetSales', '項目名': 'Net Sales', 'コンテキストID': 'PriorYear', '値': '900000'},
                ]
            }
        ]
        self.processor = BaseDocumentProcessor(
            self.mock_csv_data, 
            doc_id='TEST001', 
            doc_type_code='120'
        )
    
    def test_initialization(self):
        """Test processor initialization."""
        assert self.processor.doc_id == 'TEST001'
        assert self.processor.doc_type_code == '120'
        assert len(self.processor.all_records) == 5
    
    def test_get_value_by_id(self):
        """Test getting values by element ID."""
        # Test basic value retrieval
        edinet_code = self.processor.get_value_by_id('jpdei_cor:EDINETCodeDEI')
        assert edinet_code == 'E02144'
        
        # Test context filtering
        current_sales = self.processor.get_value_by_id('jpcrp_cor:NetSales', context_filter='Current')
        assert current_sales == '1000000'
        
        prior_sales = self.processor.get_value_by_id('jpcrp_cor:NetSales', context_filter='Prior') 
        assert prior_sales == '900000'
        
        # Test non-existent ID
        missing = self.processor.get_value_by_id('nonexistent:element')
        assert missing is None
    
    def test_get_records_by_id(self):
        """Test getting all records for an element ID."""
        sales_records = self.processor.get_records_by_id('jpcrp_cor:NetSales')
        assert len(sales_records) == 2
        assert sales_records[0]['コンテキストID'] == 'CurrentYear'
        assert sales_records[1]['コンテキストID'] == 'PriorYear'
    
    def test_get_all_text_blocks(self):
        """Test text block extraction."""
        text_blocks = self.processor.get_all_text_blocks()
        assert len(text_blocks) == 1
        
        block = text_blocks[0]
        assert block['id'] == 'jpcrp_cor:BusinessResultsTextBlock'
        assert block['title'] == 'Business Results'
        assert block['content'] == 'Test business content'
    
    def test_get_common_metadata(self):
        """Test common metadata extraction."""
        metadata = self.processor._get_common_metadata()
        
        assert metadata['edinet_code'] == 'E02144'
        assert metadata['company_name_ja'] == 'テスト株式会社'
        assert metadata['doc_id'] == 'TEST001'
        assert metadata['doc_type_code'] == '120'
    
    def test_empty_data_handling(self):
        """Test handling of empty or malformed data."""
        empty_processor = BaseDocumentProcessor([], 'EMPTY001', '999')
        
        assert len(empty_processor.all_records) == 0
        assert empty_processor.get_value_by_id('any:element') is None
        assert empty_processor.get_all_text_blocks() == []
    
    def test_none_value_handling(self):
        """Test handling of None values in data."""
        data_with_nones = [
            {
                'filename': 'test.csv',
                'data': [
                    {'要素ID': None, '項目名': 'Test', '値': 'value'},
                    {'要素ID': 'valid:element', '項目名': None, '値': None},
                    {'要素ID': 'another:element', '項目名': 'Valid Title', '値': 'valid value'},
                ]
            }
        ]
        
        processor = BaseDocumentProcessor(data_with_nones, 'TEST002', '180')
        
        # Should handle None gracefully
        text_blocks = processor.get_all_text_blocks()
        assert len(text_blocks) == 0  # No TextBlocks in this data
        
        # Should handle valid elements
        value = processor.get_value_by_id('another:element')
        assert value == 'valid value'


class TestSecuritiesReportProcessor:
    """Test the Securities Report processor (Type 120)."""
    
    def setup_method(self):
        """Set up comprehensive test data for Securities Report."""
        self.mock_csv_data = [
            {
                'filename': 'jpcrp030000-asr-001.csv',
                'data': [
                    # Metadata
                    {'要素ID': 'jpdei_cor:EDINETCodeDEI', '項目名': 'EDINET Code', '値': 'E02144'},
                    {'要素ID': 'jpdei_cor:FilerNameInEnglishDEI', '項目名': 'Company Name EN', '値': 'Test Corporation'},
                    {'要素ID': 'jpdei_cor:DocumentTypeDEI', '項目名': 'Document Type', '値': 'Securities Report'},
                    
                    # Financial metrics
                    {'要素ID': 'jpcrp_cor:NetSales', '項目名': 'Net Sales', 'コンテキストID': 'CurrentYear', '値': '5000000'},
                    {'要素ID': 'jpcrp_cor:NetSales', '項目名': 'Net Sales', 'コンテキストID': 'PriorYear', '値': '4500000'},
                    {'要素ID': 'jpcrp_cor:OperatingIncome', '項目名': 'Operating Income', 'コンテキストID': 'CurrentYear', '値': '500000'},
                    {'要素ID': 'jpcrp_cor:TotalAssets', '項目名': 'Total Assets', '値': '10000000'},
                    {'要素ID': 'jpcrp_cor:BasicEarningsLossPerShare', '項目名': 'EPS', '値': '120.50'},
                    
                    # Business information
                    {'要素ID': 'jpcrp_cor:NumberOfEmployees', '項目名': 'Employee Count', '値': '50000'},
                    {'要素ID': 'jpcrp_cor:AverageAnnualSalary', '項目名': 'Average Salary', '値': '7000000'},
                    
                    # Text blocks
                    {'要素ID': 'jpcrp_cor:ManagementAnalysisOfFinancialPositionOperatingResultsAndCashFlowsTextBlock', 
                     '項目名': 'Management Analysis', '値': 'Management discusses financial position and results...'},
                    {'要素ID': 'jpcrp_cor:RiskFactorsTextBlock', 
                     '項目名': 'Risk Factors', '値': 'Key business risks include market volatility...'},
                    {'要素ID': 'jpcrp_cor:CorporateGovernanceTextBlock',
                     '項目名': 'Corporate Governance', '値': 'Our corporate governance framework...'},
                ]
            }
        ]
        
        self.processor = SecuritiesReportProcessor(
            self.mock_csv_data,
            doc_id='S100TEST1', 
            doc_type_code='120'
        )
    
    def test_process_securities_report(self):
        """Test full processing of Securities Report."""
        result = self.processor.process()
        
        assert result is not None
        assert result['doc_id'] == 'S100TEST1'
        assert result['doc_type_code'] == '120'
        assert result['company_name_en'] == 'Test Corporation'
        
        # Check structure
        assert 'key_facts' in result
        assert 'financial_tables' in result  
        assert 'text_blocks' in result
    
    def test_extract_financial_metrics(self):
        """Test financial metrics extraction."""
        metrics = self.processor._extract_financial_metrics()
        
        # Should extract sales with current/prior
        assert 'net_sales' in metrics
        assert metrics['net_sales']['current'] == '5000000'
        assert metrics['net_sales']['prior'] == '4500000'
        
        # Should extract single values
        assert 'total_assets' in metrics
        assert metrics['total_assets'] == '10000000'
        
        assert 'earnings_per_share' in metrics
        assert metrics['earnings_per_share'] == '120.50'
    
    def test_extract_business_facts(self):
        """Test business facts extraction.""" 
        facts = self.processor._extract_business_facts()
        
        assert 'employee_count' in facts
        assert facts['employee_count'] == '50000'
        
        assert 'average_annual_salary' in facts
        assert facts['average_annual_salary'] == '7000000'
    
    def test_categorize_text_blocks(self):
        """Test text block categorization."""
        blocks = self.processor._categorize_text_blocks()
        
        assert len(blocks) == 3
        
        # Check categories are assigned
        categories = [block['category'] for block in blocks]
        assert 'management_analysis' in categories
        assert 'risk_factors' in categories
        assert 'corporate_governance' in categories
    
    def test_categorize_element(self):
        """Test element categorization logic."""
        # Test various categorization patterns - check actual implementation
        assert self.processor._categorize_element('jpcrp_cor:RiskFactorsTextBlock') == 'risk_factors'  # 'risk' keyword
        assert self.processor._categorize_element('jpcrp_cor:ManagementAnalysisTextBlock') == 'management_analysis'
        assert self.processor._categorize_element('jpcrp_cor:CorporateGovernanceTextBlock') == 'corporate_governance'
        assert self.processor._categorize_element('jpcrp_cor:ShareholderInformationTextBlock') == 'shareholder_information'
        assert self.processor._categorize_element('jpcrp_cor:UnknownElement') == 'other'


class TestInternalControlReportProcessor:
    """Test the Internal Control Report processor (Type 235)."""
    
    def setup_method(self):
        """Set up test data for Internal Control Report."""
        self.mock_csv_data = [
            {
                'filename': 'internal_control.csv',
                'data': [
                    # Metadata
                    {'要素ID': 'jpdei_cor:EDINETCodeDEI', '項目名': 'EDINET Code', '値': 'E02126'},
                    {'要素ID': 'jpdei_cor:FilerNameInEnglishDEI', '項目名': 'Company Name', '値': 'Internal Control Test Co.'},
                    
                    # Internal control specific elements  
                    {'要素ID': 'jpcrp_cor:InternalControlAssessmentResult', '項目名': 'Assessment Result', '値': 'Effective'},
                    {'要素ID': 'jpcrp_cor:MaterialWeaknessInInternalControl', '項目名': 'Material Weakness', '値': 'None identified'},
                    
                    # Text blocks
                    {'要素ID': 'jpcrp_cor:InternalControlFrameworkTextBlock', 
                     '項目名': 'Internal Control Framework', '値': 'Our internal control framework is based on...'},
                    {'要素ID': 'jpcrp_cor:EvaluationScopeTextBlock',
                     '項目名': 'Evaluation Scope', '値': 'The evaluation covered company and subsidiaries...'},
                ]
            }
        ]
        
        self.processor = InternalControlReportProcessor(
            self.mock_csv_data,
            doc_id='S100IC01',
            doc_type_code='235'
        )
    
    def test_process_internal_control_report(self):
        """Test processing of Internal Control Report."""
        result = self.processor.process()
        
        assert result is not None
        assert result['doc_type_code'] == '235'
        assert result['company_name_en'] == 'Internal Control Test Co.'
        
        # Internal control reports should have specific structure
        key_facts = result['key_facts']
        assert 'assessment_result' in key_facts
        assert key_facts['assessment_result'] == 'Effective'
        
        assert 'material_weakness' in key_facts
        assert key_facts['material_weakness'] == 'None identified'
        
        # Should have no financial tables
        assert result['financial_tables'] == []
        
        # Should have text blocks
        assert len(result['text_blocks']) == 2


class TestExtraordinaryReportProcessor:
    """Test the Extraordinary Report processor (Type 180)."""
    
    def setup_method(self):
        """Set up test data for Extraordinary Report."""
        self.mock_csv_data = [
            {
                'filename': 'extraordinary.csv', 
                'data': [
                    {'要素ID': 'jpdei_cor:EDINETCodeDEI', '項目名': 'EDINET Code', '値': 'E99999'},
                    
                    # Extraordinary report specific elements
                    {'要素ID': 'jpcrp-esr_cor:ResolutionOfBoardOfDirectorsDescription', 
                     '項目名': 'Board Resolution', '値': 'Board resolved to acquire subsidiary...'},
                    {'要素ID': 'jpcrp-esr_cor:DateOfResolutionOfBoardOfDirectors',
                     '項目名': 'Resolution Date', '値': '2025-06-01'},
                    {'要素ID': 'jpcrp-esr_cor:ImpactOnBusinessResultsDescription',
                     '項目名': 'Business Impact', '値': 'Expected to increase revenue by 10%...'},
                     
                    # Text blocks
                    {'要素ID': 'jpcrp_cor:SubmissionReasonTextBlock',
                     '項目名': 'Submission Reason', '値': 'Filing due to material acquisition...'},
                ]
            }
        ]
        
        self.processor = ExtraordinaryReportProcessor(
            self.mock_csv_data,
            doc_id='S100ER01',
            doc_type_code='180'
        )
    
    def test_process_extraordinary_report(self):
        """Test processing of Extraordinary Report."""
        result = self.processor.process()
        
        assert result is not None
        assert result['doc_type_code'] == '180'
        
        # Check key facts extraction - use the actual cleaned key names from processor
        key_facts = result['key_facts']
        assert 'ResolutionOfBoardOfDirectors' in key_facts
        assert 'DateOfResolutionOfBoardOfDirectors' in key_facts
        assert 'ImpactOnResults' in key_facts  # Key gets cleaned to ImpactOnResults
        
        # Check text blocks
        assert len(result['text_blocks']) == 1
        assert result['text_blocks'][0]['title'] == 'Submission Reason'


class TestProcessorDispatcher:
    """Test the processor dispatching functionality."""
    
    def test_process_raw_csv_data_securities_report(self):
        """Test dispatcher selects SecuritiesReportProcessor for type 120."""
        mock_data = [{'filename': 'test.csv', 'data': []}]
        
        with patch('edinet_tools.processors.SecuritiesReportProcessor') as mock_processor_class:
            mock_instance = Mock()
            mock_instance.process.return_value = {'test': 'data'}
            mock_processor_class.return_value = mock_instance
            mock_processor_class.__name__ = 'SecuritiesReportProcessor'  # Fix __name__ attribute
            
            result = process_raw_csv_data(mock_data, 'TEST001', '120')
            
            # Should use SecuritiesReportProcessor
            mock_processor_class.assert_called_once_with(mock_data, 'TEST001', '120', None)
            mock_instance.process.assert_called_once()
            assert result == {'test': 'data'}
    
    def test_process_raw_csv_data_internal_control(self):
        """Test dispatcher selects InternalControlReportProcessor for type 235."""
        mock_data = [{'filename': 'test.csv', 'data': []}]
        
        with patch('edinet_tools.processors.InternalControlReportProcessor') as mock_processor_class:
            mock_instance = Mock()
            mock_instance.process.return_value = {'control': 'data'}
            mock_processor_class.return_value = mock_instance
            mock_processor_class.__name__ = 'InternalControlReportProcessor'  # Fix __name__ attribute
            
            result = process_raw_csv_data(mock_data, 'TEST002', '235')
            
            mock_processor_class.assert_called_once_with(mock_data, 'TEST002', '235', None)
            assert result == {'control': 'data'}
    
    def test_process_raw_csv_data_unknown_type(self):
        """Test dispatcher uses GenericReportProcessor for unknown types."""
        mock_data = [{'filename': 'test.csv', 'data': []}]
        
        with patch('edinet_tools.processors.GenericReportProcessor') as mock_processor_class:
            mock_instance = Mock()
            mock_instance.process.return_value = {'generic': 'data'}
            mock_processor_class.return_value = mock_instance
            mock_processor_class.__name__ = 'GenericReportProcessor'  # Fix __name__ attribute
            
            result = process_raw_csv_data(mock_data, 'TEST003', '999')
            
            mock_processor_class.assert_called_once_with(mock_data, 'TEST003', '999', None)
            assert result == {'generic': 'data'}
    
    def test_process_raw_csv_data_with_exception(self):
        """Test dispatcher handles processor exceptions."""
        mock_data = [{'filename': 'test.csv', 'data': []}]
        
        with patch('edinet_tools.processors.GenericReportProcessor') as mock_processor_class:
            mock_processor_class.side_effect = Exception('Test error')
            mock_processor_class.__name__ = 'GenericReportProcessor'  # Fix __name__ attribute
            
            result = process_raw_csv_data(mock_data, 'TESTERR', '999')
            
            # Should return None on exception
            assert result is None


class TestGenericReportProcessor:
    """Test the Generic Report processor (fallback)."""

    def test_generic_processor_basic_functionality(self):
        """Test generic processor handles any document type."""
        mock_data = [
            {
                'filename': 'generic.csv',
                'data': [
                    {'要素ID': 'jpdei_cor:EDINETCodeDEI', '項目名': 'EDINET Code', '値': 'E12345'},
                    {'要素ID': 'jpcrp_cor:SomeTextBlock', '項目名': 'Some Text Block', '値': 'Generic content'},
                ]
            }
        ]

        processor = GenericReportProcessor(mock_data, 'GENERIC01', '999')
        result = processor.process()

        assert result is not None
        assert result['doc_type_code'] == '999'
        assert result['edinet_code'] == 'E12345'

        # Generic processor should have empty key facts and financial tables
        assert result['key_facts'] == {}
        assert result['financial_tables'] == []

        # Should extract text blocks
        assert len(result['text_blocks']) == 1


class TestDispatcherEndToEndRealShape:
    """End-to-end dispatcher tests with NO mocks — assert on real processor output.

    AUDIT NOTE (false-confidence-test, 2026-05-22): TestProcessorDispatcher
    above mocks the processor classes and asserts on the mock's stub
    return ({'test': 'data'}). That asserts on what the mock returned, NOT on
    what real code emits. Invisible to drift if the real processor signature
    or output shape changes — the mock will just keep returning {'test': 'data'}
    forever.

    These complementary tests run the REAL processor for each dispatched type
    with a minimal-but-valid input, and assert on the real output shape (keys
    the real .process() method emits). If a processor's contract drifts, these
    tests catch it.

    The dispatcher-with-mock tests are retained because the dispatcher's job
    IS routing — testing it with mocks is reasonable for that specific
    behavior. But the dispatcher's CONTRACT also requires the dispatched
    processor's return-shape promise to hold, which only real-shape tests can
    verify.
    """

    def _minimal_csv_data(self, edinet_code='E12345'):
        return [
            {
                'filename': 'minimal.csv',
                'data': [
                    {'要素ID': 'jpdei_cor:EDINETCodeDEI', '項目名': 'EDINETコード', '値': edinet_code},
                    {'要素ID': 'jpdei_cor:FilerNameInJapaneseDEI', '項目名': '会社名', '値': 'テスト株式会社'},
                ]
            }
        ]

    def test_dispatch_120_real_returns_securities_report_shape(self):
        """Doc 120 dispatch hits SecuritiesReportProcessor; result has real shape."""
        result = process_raw_csv_data(self._minimal_csv_data(), 'S100R120', '120')
        assert result is not None
        # Real SecuritiesReportProcessor contract:
        assert result['doc_id'] == 'S100R120'
        assert result['doc_type_code'] == '120'
        assert result['edinet_code'] == 'E12345'
        assert 'key_facts' in result
        assert 'financial_tables' in result
        assert 'text_blocks' in result
        # SecuritiesReportProcessor emits key_facts AS A DICT (not stub
        # {'test': 'data'}), financial_tables AS A LIST. Drift catcher:
        assert isinstance(result['key_facts'], dict)
        assert isinstance(result['financial_tables'], list)
        assert isinstance(result['text_blocks'], list)

    def test_dispatch_180_real_returns_extraordinary_report_shape(self):
        """Doc 180 dispatch hits ExtraordinaryReportProcessor; result has real shape."""
        data = self._minimal_csv_data()
        # Add a 180-specific element so we have something for key_facts:
        data[0]['data'].append({
            '要素ID': 'jpcrp-esr_cor:DateOfResolutionOfBoardOfDirectors',
            '項目名': '取締役会決議日', '値': '2025-04-01'
        })
        result = process_raw_csv_data(data, 'S100R180', '180')
        assert result is not None
        assert result['doc_type_code'] == '180'
        # ExtraordinaryReportProcessor.process() emits cleaned key:
        assert 'DateOfResolutionOfBoardOfDirectors' in result['key_facts']
        assert result['key_facts']['DateOfResolutionOfBoardOfDirectors'] == '2025-04-01'
        # text_blocks must be a list (real contract)
        assert isinstance(result['text_blocks'], list)

    def test_dispatch_235_real_returns_internal_control_shape(self):
        """Doc 235 dispatch hits InternalControlReportProcessor; result has real shape."""
        data = self._minimal_csv_data()
        data[0]['data'].append({
            '要素ID': 'jpcrp_cor:InternalControlAssessmentResult',
            '項目名': '評価結果', '値': '有効'
        })
        result = process_raw_csv_data(data, 'S100R235', '235')
        assert result is not None
        assert result['doc_type_code'] == '235'
        # InternalControlReportProcessor.process() emits 'assessment_result' key:
        assert 'assessment_result' in result['key_facts']
        assert result['key_facts']['assessment_result'] == '有効'
        # Internal control reports must emit financial_tables == [] (per
        # the real processor contract — "Internal control reports don't have
        # financial tables"):
        assert result['financial_tables'] == []

    def test_dispatch_unknown_type_real_returns_generic_shape(self):
        """Unknown doc-type-code falls through to GenericReportProcessor."""
        result = process_raw_csv_data(self._minimal_csv_data(), 'S100R999', '999')
        assert result is not None
        assert result['doc_type_code'] == '999'
        # Generic emits empty key_facts and empty financial_tables (real contract):
        assert result['key_facts'] == {}
        assert result['financial_tables'] == []

    def test_dispatch_160_real_returns_semi_annual_shape(self):
        """Doc 160 dispatch hits SemiAnnualReportProcessor with real shape."""
        data = self._minimal_csv_data()
        data[0]['data'].append({
            '要素ID': 'jpcrp_cor:OrdinaryIncome', '項目名': '経常利益',
            'コンテキストID': 'CurrentYTDDuration', '値': '500000'
        })
        result = process_raw_csv_data(data, 'S100R160', '160')
        assert result is not None
        assert result['doc_type_code'] == '160'
        # SemiAnnualReportProcessor emits 'OrdinaryIncome' as a cleaned key with
        # current/prior shape:
        assert 'OrdinaryIncome' in result['key_facts']
        assert result['key_facts']['OrdinaryIncome']['current'] == '500000'
        # has_enhanced_financials should be False (no zip_extract_path):
        assert result['has_enhanced_financials'] is False


class TestProcessorWithRealisticNoiseFixture:
    """Run processors against a realistic 20+ row CSV with all known noise patterns.

    AUDIT NOTE (false-confidence-test, 2026-05-22): the per-processor
    setup_method fixtures above are 4-13 rows of pristine inputs. Real EDINET
    filings carry far more noise: dimensional Member contexts, '－' nulls,
    namespace variations (jpcrp_cor / jppfs_cor / jpigp_cor), TextBlock rows
    mixed with metric rows, duplicate-id rows distinguished only by context.

    The segments bug (fixed 2026-04-28) was invisible to clean fixtures
    precisely because the per-segment Member rows that confused the parser
    were absent from the test data.

    This fixture is 25 rows with the noise patterns deliberately included.
    """

    def _build_realistic_securities_data(self):
        return [
            {
                'filename': 'jpcrp030000-asr-001.csv',
                'data': [
                    {'要素ID': 'jpdei_cor:EDINETCodeDEI', '項目名': 'EDINETコード', '値': 'E54321'},
                    {'要素ID': 'jpdei_cor:FilerNameInJapaneseDEI', '項目名': '会社名', '値': '株式会社ノイズ試験'},
                    {'要素ID': 'jpdei_cor:FilerNameInEnglishDEI', '項目名': 'Name EN', '値': 'Noise Test Inc.'},
                    # Headline metrics first (these should win get_value_by_id):
                    {'要素ID': 'jpcrp_cor:NetSales', '項目名': '売上高',
                     'コンテキストID': 'CurrentYearDuration', '値': '8000000000'},
                    {'要素ID': 'jpcrp_cor:NetSales', '項目名': '売上高',
                     'コンテキストID': 'Prior1YearDuration', '値': '7200000000'},
                    {'要素ID': 'jpcrp_cor:OperatingIncome', '項目名': '営業利益',
                     'コンテキストID': 'CurrentYearDuration', '値': '800000000'},
                    {'要素ID': 'jpcrp_cor:TotalAssets', '項目名': '総資産',
                     'コンテキストID': 'CurrentYearInstant', '値': '20000000000'},
                    # Dimensional Member contexts (the segments-bug shape):
                    {'要素ID': 'jpcrp_cor:NetSales', '項目名': '売上高',
                     'コンテキストID': 'CurrentYearDuration_jpcrp030000-asr_E54321-000SegmentAMember',
                     '値': '5000000000'},
                    {'要素ID': 'jpcrp_cor:NetSales', '項目名': '売上高',
                     'コンテキストID': 'CurrentYearDuration_jpcrp030000-asr_E54321-000SegmentBMember',
                     '値': '3000000000'},
                    # '－' EDINET null marker rows:
                    {'要素ID': 'jpcrp_cor:DividendPerShare', '項目名': '配当',
                     'コンテキストID': 'CurrentYearDuration', '値': '－'},
                    {'要素ID': 'jpcrp_cor:OrdinaryIncome', '項目名': '経常利益',
                     'コンテキストID': 'Prior1YearDuration', '値': '－'},
                    # Namespace variants:
                    {'要素ID': 'jppfs_cor:ProfitLossAttributableToOwnersOfParent',
                     '項目名': '当期純利益', 'コンテキストID': 'CurrentYearDuration', '値': '600000000'},
                    {'要素ID': 'jpigp_cor:RevenueIFRS', '項目名': '売上収益(IFRS)',
                     'コンテキストID': 'CurrentYearDuration', '値': '8100000000'},
                    # Business facts:
                    {'要素ID': 'jpcrp_cor:NumberOfEmployees', '項目名': '従業員数', '値': '12000'},
                    {'要素ID': 'jpcrp_cor:AverageAnnualSalary', '項目名': '平均給与', '値': '6800000'},
                    {'要素ID': 'jpcrp_cor:NumberOfSharesIssuedAndOutstanding',
                     '項目名': '発行済株式数', '値': '50000000'},
                    # TextBlock rows mixed in:
                    {'要素ID': 'jpcrp_cor:ManagementAnalysisOfFinancialPositionOperatingResultsAndCashFlowsTextBlock',
                     '項目名': 'MD&A', '値': '当連結会計年度の業績について報告します。売上高は前年比増加しました。'},
                    {'要素ID': 'jpcrp_cor:RiskFactorsTextBlock', '項目名': 'リスク要因',
                     '値': '当社事業に係る主要なリスクは以下の通りです。'},
                    {'要素ID': 'jpcrp_cor:CorporateGovernanceTextBlock', '項目名': 'ガバナンス',
                     '値': '当社のコーポレートガバナンス体制について。'},
                    {'要素ID': 'jpcrp_cor:ShareholderInformationTextBlock', '項目名': '株主情報',
                     '値': '当社の主要株主は以下の通りです。'},
                    # NonConsolidatedMember disambiguator:
                    {'要素ID': 'jpcrp_cor:BookValuePerShare', '項目名': '1株当たり純資産',
                     'コンテキストID': 'CurrentYearInstant_NonConsolidatedMember', '値': '400.00'},
                    # Orphan/None rows:
                    {'要素ID': None, '項目名': 'orphan', '値': 'no-id-row'},
                    {'要素ID': 'jpcrp_cor:SomeUnmappedTextBlock', '項目名': 'unmapped',
                     '値': None},  # None value should be filtered from text_blocks
                    {'要素ID': 'jpcrp_cor:UnmappedFactNotInProcessorMap',
                     '項目名': '何か', '値': 'ignored-by-processor'},
                    {'要素ID': 'jpcrp_cor:AccountingStandardsFollowedInPreparationOfFinancialStatements',
                     '項目名': '会計基準', '値': 'IFRS'},
                ]
            }
        ]

    def test_securities_processor_handles_realistic_noise(self):
        """SecuritiesReportProcessor extracts cleanly from 20+ row noisy fixture."""
        data = self._build_realistic_securities_data()
        assert len(data[0]['data']) >= 20, "fixture must have ≥20 rows"

        processor = SecuritiesReportProcessor(data, 'S100NOISE1', '120')
        result = processor.process()

        # Metadata robustness:
        assert result['edinet_code'] == 'E54321'
        assert result['company_name_ja'] == '株式会社ノイズ試験'
        assert result['company_name_en'] == 'Noise Test Inc.'

        # Financial metrics: headline values should win (first-match-on-Current).
        # NOTE: The processor's get_value_by_id does a linear scan and returns
        # the FIRST row whose 要素ID matches AND context contains the filter.
        # The headline 'CurrentYearDuration' row precedes the Member-suffixed
        # rows in this fixture, so 5000000000 (SegmentA) should NOT overwrite
        # the 8000000000 headline.
        kf = result['key_facts']
        assert kf['net_sales']['current'] == '8000000000', (
            f"headline NetSales overwritten by segment row — net_sales={kf.get('net_sales')}"
        )
        assert kf['net_sales']['prior'] == '7200000000'
        assert kf['operating_income']['current'] == '800000000'
        assert kf['total_assets']['current'] == '20000000000'
        assert kf['net_income_attributable_to_owners']['current'] == '600000000'
        assert kf['employee_count'] == '12000'
        assert kf['average_annual_salary'] == '6800000'
        assert kf['shares_outstanding'] == '50000000'
        assert kf['accounting_standards'] == 'IFRS'

        # Text blocks: only rows with non-None 値 should appear; None-valued
        # SomeUnmappedTextBlock must be filtered out.
        text_blocks = result['text_blocks']
        tb_ids = [tb['id'] for tb in text_blocks]
        assert 'jpcrp_cor:ManagementAnalysisOfFinancialPositionOperatingResultsAndCashFlowsTextBlock' in tb_ids
        assert 'jpcrp_cor:RiskFactorsTextBlock' in tb_ids
        assert 'jpcrp_cor:CorporateGovernanceTextBlock' in tb_ids
        # Critical drift catch: None-valued TextBlock row must NOT appear.
        assert 'jpcrp_cor:SomeUnmappedTextBlock' not in tb_ids, (
            'None-valued TextBlock row leaked into output — get_all_text_blocks '
            'should filter `if element_id and ... and value`'
        )

        # Categorization assigned for each block:
        for tb in text_blocks:
            assert 'category' in tb and tb['category'] in {
                'business_overview', 'risk_factors', 'management_analysis',
                'corporate_governance', 'shareholder_information',
                'accounting_information', 'other', 'unknown'
            }


        
        print("✅ Basic processor validation passed!")