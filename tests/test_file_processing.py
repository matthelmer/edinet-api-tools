"""
File Processing Infrastructure Tests - TIER 1 CRITICAL PATH

Tests the file processing pipeline that enables all document extraction:
ZIP handling, encoding detection, CSV parsing, directory processing.
"""

import pytest
import os
import tempfile
import zipfile
import csv
from unittest.mock import Mock, patch, mock_open

from edinet_tools.utils import (
    detect_encoding,
    read_csv_file,
    clean_text,
    process_zip_file,
)


class TestJapaneseEncodingHandling:
    """Test encoding detection and conversion - critical for Japanese documents"""
    
    def setup_method(self):
        """Create test files with different Japanese encodings"""
        self.temp_dir = tempfile.mkdtemp()
        
        # Sample Japanese financial text
        self.japanese_text = '''要素ID\t項目名\tコンテキストID\t値
jpdei_cor:EDINETCodeDEI\tEDINETコード\tFilingDateInstant\tE02144
jpcrp_cor:NetSales\t売上高\tCurrentYear\t1000000000000
jpcrp_cor:CompanyNameTextBlock\t会社名\tFilingDateInstant\tトヨタ自動車株式会社'''

    def teardown_method(self):
        """Clean up test files"""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_utf16_encoding_detection_and_reading(self):
        """UTF-16 is commonly used in EDINET CSV files"""
        utf16_file = os.path.join(self.temp_dir, 'utf16_test.csv')
        
        # Create UTF-16 file (common EDINET format)
        with open(utf16_file, 'w', encoding='utf-16') as f:
            f.write(self.japanese_text)
        
        # Should detect UTF-16
        encoding = detect_encoding(utf16_file)
        assert 'utf-16' in encoding.lower()
        
        # Should read successfully
        records = read_csv_file(utf16_file)
        assert records is not None
        assert len(records) == 3
        
        # Verify Japanese content is preserved
        assert records[0]['要素ID'] == 'jpdei_cor:EDINETCodeDEI'
        assert records[1]['項目名'] == '売上高'
        assert records[2]['値'] == 'トヨタ自動車株式会社'

    def test_utf8_encoding_detection_and_reading(self):
        """UTF-8 handling for processed/converted files"""
        utf8_file = os.path.join(self.temp_dir, 'utf8_test.csv')
        
        with open(utf8_file, 'w', encoding='utf-8') as f:
            f.write(self.japanese_text)
        
        encoding = detect_encoding(utf8_file)
        assert encoding in ['utf-8', 'ascii']  # ASCII detection is acceptable for simple content
        
        records = read_csv_file(utf8_file)
        assert records is not None
        assert records[2]['値'] == 'トヨタ自動車株式会社'

    def test_encoding_fallback_mechanism(self):
        """Test fallback when encoding detection fails"""
        test_file = os.path.join(self.temp_dir, 'fallback_test.csv')
        
        # Create file with complex Japanese content
        complex_text = '''要素ID\t項目名\t値
jpcrp_cor:BusinessResultsTextBlock\t事業の状況\t当第2四半期連結累計期間における業績は、売上高が前年同期比で大幅に増加し、営業利益も改善されました。'''
        
        with open(test_file, 'w', encoding='shift_jis') as f:
            f.write(complex_text)
        
        # Should still read successfully even if detection is imperfect
        records = read_csv_file(test_file)
        assert records is not None
        assert len(records) == 1
        # Complex Japanese business text should be preserved
        assert '第2四半期' in records[0]['値']
        assert '営業利益' in records[0]['値']

    def test_malformed_encoding_graceful_handling(self):
        """Handle files with encoding issues without crashing"""
        bad_file = os.path.join(self.temp_dir, 'bad_encoding.csv')
        
        # Create file with mixed encoding issues
        with open(bad_file, 'wb') as f:
            f.write(b'\xff\xfe')  # UTF-16 BOM
            f.write('normal text,bad\xff\xfe characters'.encode('utf-8', errors='ignore'))
        
        # Graceful-degradation contract: never raises; returns parsed
        # records or None, nothing else.
        records = read_csv_file(bad_file)
        assert records is None or isinstance(records, list)


class TestZipFileProcessing:
    """Test ZIP file extraction and processing - critical for EDINET document downloads"""
    
    def setup_method(self):
        """Create test ZIP files with realistic EDINET structure"""
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Clean up test files"""
        import shutil  
        shutil.rmtree(self.temp_dir)

    def test_zip_with_japanese_filenames(self):
        """EDINET ZIP files may contain Japanese filenames"""
        zip_path = os.path.join(self.temp_dir, 'S100TEST1-160-テスト会社.zip')
        
        # Create ZIP with Japanese filename inside
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            csv_content = '''要素ID\t項目名\t値
jpdei_cor:EDINETCodeDEI\tEDINETコード\tE02144
jpcrp_cor:NetSales\t売上高\t5000000000'''
            zf.writestr('財務データ.csv', csv_content.encode('utf-8'))
        
        with patch('edinet_tools.utils.process_raw_csv_data') as mock_process:
            mock_process.return_value = {'doc_id': 'S100TEST1', 'success': True}
            
            result = process_zip_file(zip_path, 'S100TEST1', '160')
            
            assert result is not None
            assert result['success'] is True
            mock_process.assert_called_once()
            
            # Verify CSV data was extracted
            call_args = mock_process.call_args[0]
            raw_csv_data = call_args[0]
            assert len(raw_csv_data) == 1
            assert raw_csv_data[0]['filename'] == '財務データ.csv'

    def test_zip_with_multiple_csv_files(self):
        """EDINET documents often contain multiple CSV files"""
        zip_path = os.path.join(self.temp_dir, 'S100MULTI-180-MultiCSV.zip')
        
        with zipfile.ZipFile(zip_path, 'w') as zf:
            # Main financial data
            main_csv = '''要素ID\t項目名\t値
jpdei_cor:EDINETCodeDEI\tEDINETコード\tE02144'''
            zf.writestr('main_data.csv', main_csv.encode('utf-8'))
            
            # Additional details
            details_csv = '''要素ID\t項目名\t値
jpcrp_cor:BusinessResultsTextBlock\t事業結果\t業績は順調に推移しています'''
            zf.writestr('details.csv', details_csv.encode('utf-8'))
            
            # Auditor report (should be skipped)
            audit_csv = '''audit_field\taudit_value
auditor_opinion\tUnqualified'''
            zf.writestr('jpaud_audit.csv', audit_csv.encode('utf-8'))
        
        with patch('edinet_tools.utils.process_raw_csv_data') as mock_process:
            mock_process.return_value = {'doc_id': 'S100MULTI', 'csv_count': 2}
            
            result = process_zip_file(zip_path, 'S100MULTI', '180')
            
            assert result is not None
            mock_process.assert_called_once()
            
            # Should have extracted 2 CSV files (excluding auditor file)
            call_args = mock_process.call_args[0]
            raw_csv_data = call_args[0]
            assert len(raw_csv_data) == 2
            
            # Verify auditor file was excluded
            filenames = [data['filename'] for data in raw_csv_data]
            assert 'jpaud_audit.csv' not in filenames
            assert 'main_data.csv' in filenames
            assert 'details.csv' in filenames

    def test_corrupted_zip_file_handling(self):
        """Handle corrupted ZIP files gracefully"""
        bad_zip = os.path.join(self.temp_dir, 'corrupted.zip')
        
        # Create invalid ZIP file
        with open(bad_zip, 'w') as f:
            f.write('This is not a ZIP file')
        
        result = process_zip_file(bad_zip, 'S100BAD', '160')
        
        # Should return None, not crash
        assert result is None

    def test_empty_zip_file_handling(self):
        """Handle ZIP files with no CSV content"""
        empty_zip = os.path.join(self.temp_dir, 'empty.zip')

        with zipfile.ZipFile(empty_zip, 'w') as zf:
            zf.writestr('readme.txt', 'No CSV files here')

        result = process_zip_file(empty_zip, 'S100EMPTY', '160')

        # Should return None when no CSV files found
        assert result is None

    def test_zip_end_to_end_doc_180_real_processing(self):
        """End-to-end ZIP processing for Doc 180 with NO mocks.

        AUDIT NOTE (false-confidence-test, 2026-05-22): the
        `test_zip_with_japanese_filenames` and `test_zip_with_multiple_csv_files`
        tests above patch `edinet_tools.utils.process_raw_csv_data` and assert
        on the mock's stub return value. That validates only the ZIP-walking
        and CSV-collection layer — the downstream processing contract is
        never exercised, so a real-shape drift in process_raw_csv_data would
        be invisible to those tests.

        This test runs the FULL pipeline end-to-end with a real Doc 180 fixture
        (small required-fields footprint) and asserts on the REAL
        ExtraordinaryReportProcessor output shape. If the processor's contract
        drifts or the dispatcher misroutes, this fires.

        Why Doc 180: small required-fields footprint, fast, and demonstrates
        the namespace-prefixed jpcrp-esr_cor elements survive the ZIP →
        CSV → processor round-trip without corruption.
        """
        zip_path = os.path.join(self.temp_dir, 'S100E2E18-180-EndToEnd.zip')

        # Real-shape Doc 180 CSV content (tab-separated, UTF-16 LE BOM — the
        # actual EDINET file format).
        # Build the tab-separated content that real EDINET CSVs use:
        rows = [
            ('要素ID', '項目名', 'コンテキストID', '値'),
            ('jpdei_cor:EDINETCodeDEI', 'EDINETコード', 'FilingDateInstant', 'E99999'),
            ('jpdei_cor:FilerNameInJapaneseDEI', '会社名', 'FilingDateInstant', 'エンドツーエンド株式会社'),
            ('jpcrp-esr_cor:ResolutionOfBoardOfDirectorsDescription', '取締役会決議',
             'CurrentYearInstant', '2025年8月1日開催の取締役会において、A社の全株式取得を決議。'),
            ('jpcrp-esr_cor:DateOfResolutionOfBoardOfDirectors', '取締役会決議日',
             'CurrentYearInstant', '2025-08-01'),
            ('jpcrp-esr_cor:ImpactOnBusinessResultsDescription', '業績への影響',
             'CurrentYearInstant', '当連結会計年度の業績に与える影響は軽微である。'),
            ('jpcrp_cor:SubmissionReasonTextBlock', '提出理由',
             'CurrentYearInstant', '子会社取得のため臨時報告書を提出する。'),
        ]
        csv_content = '\n'.join('\t'.join(r) for r in rows)

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Use UTF-16 LE encoding which is what EDINET actually uses for
            # CSV files. This also exercises the encoding-detection code
            # path in read_csv_file.
            zf.writestr('jpcrp-esr-001_E99999-000.csv',
                        csv_content.encode('utf-16'))
            # Auditor file that must be filtered:
            zf.writestr('jpaud_audit_E99999.csv',
                        'audit_field\taudit_value\nopinion\tunqualified\n'.encode('utf-16'))

        # NO mocks — real end-to-end:
        result = process_zip_file(zip_path, 'S100E2E18', '180')

        assert result is not None, (
            'process_zip_file returned None — real end-to-end pipeline broke'
        )
        # Real ExtraordinaryReportProcessor contract:
        assert result['doc_id'] == 'S100E2E18'
        assert result['doc_type_code'] == '180'
        assert result['edinet_code'] == 'E99999'
        assert result['company_name_ja'] == 'エンドツーエンド株式会社'
        # key_facts is a dict (not a mock stub {'test': 'data'}):
        assert isinstance(result['key_facts'], dict)
        # Cleaned key names from the real processor's cleaning rule:
        kf = result['key_facts']
        assert 'ResolutionOfBoardOfDirectors' in kf
        assert '取締役会' in kf['ResolutionOfBoardOfDirectors']
        assert kf['DateOfResolutionOfBoardOfDirectors'] == '2025-08-01'
        assert 'ImpactOnResults' in kf  # cleaned: ImpactOnBusinessResults → ImpactOnResults
        # text_blocks list (not a stub):
        assert isinstance(result['text_blocks'], list)
        tb_ids = [tb['id'] for tb in result['text_blocks']]
        assert 'jpcrp_cor:SubmissionReasonTextBlock' in tb_ids

    def test_zip_end_to_end_doc_220_treasury_real_processing(self):
        """End-to-end ZIP processing for Doc 220 (treasury stock) — falls through
        to GenericReportProcessor.

        Doc 220 has no dedicated processor in the dispatcher map, so it should
        route to GenericReportProcessor. This test pins the dispatcher's
        fallback behavior with a real ZIP → real processing call chain.
        """
        zip_path = os.path.join(self.temp_dir, 'S100E2E22-220-Treasury.zip')

        rows = [
            ('要素ID', '項目名', 'コンテキストID', '値'),
            ('jpdei_cor:EDINETCodeDEI', 'EDINETコード', 'FilingDateInstant', 'E22220'),
            ('jpdei_cor:FilerNameInJapaneseDEI', '会社名', 'FilingDateInstant', 'トレジャリー株式会社'),
            ('jpcrp_cor:TreasuryStockAcquisitionTextBlock', '自己株式取得',
             'CurrentYearInstant', '当社は本日、自己株式の取得を決議いたしました。'),
        ]
        csv_content = '\n'.join('\t'.join(r) for r in rows)
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('treasury.csv', csv_content.encode('utf-16'))

        result = process_zip_file(zip_path, 'S100E2E22', '220')
        assert result is not None
        # Generic fallback contract:
        assert result['doc_id'] == 'S100E2E22'
        assert result['doc_type_code'] == '220'
        assert result['edinet_code'] == 'E22220'
        # GenericReportProcessor emits empty key_facts + empty financial_tables:
        assert result['key_facts'] == {}
        assert result['financial_tables'] == []
        # But text_blocks should be populated:
        tb_ids = [tb['id'] for tb in result['text_blocks']]
        assert 'jpcrp_cor:TreasuryStockAcquisitionTextBlock' in tb_ids


class TestTextProcessing:
    """Test Japanese text cleaning and normalization"""
    
    def test_japanese_fullwidth_space_normalization(self):
        """Convert Japanese full-width spaces to regular spaces"""
        text_with_fullwidth = 'トヨタ　自動車　株式会社'
        cleaned = clean_text(text_with_fullwidth)
        assert cleaned == 'トヨタ 自動車 株式会社'
    
    def test_japanese_business_text_cleaning(self):
        """Clean Japanese business text while preserving meaning"""
        messy_japanese = '''  
        売上高は前年同期比で　15％増加し、
        
        営業利益も　　改善されました。  
        '''
        
        cleaned = clean_text(messy_japanese)
        
        # Should preserve all Japanese characters
        assert '売上高' in cleaned
        assert '前年同期比' in cleaned
        assert '15％増加' in cleaned
        assert '営業利益' in cleaned
        assert '改善' in cleaned
        
        # Should normalize spacing
        assert '　　' not in cleaned  # No double full-width spaces
        assert cleaned.strip() == cleaned  # No leading/trailing whitespace
        
    def test_mixed_japanese_english_text_cleaning(self):
        """Handle mixed Japanese-English content properly"""
        mixed_text = '  TOYOTA MOTOR CORPORATION　トヨタ自動車株式会社  \t\n  '
        cleaned = clean_text(mixed_text)
        
        assert cleaned == 'TOYOTA MOTOR CORPORATION トヨタ自動車株式会社'
        
    def test_none_and_empty_text_handling(self):
        """Handle None and empty text inputs gracefully"""
        assert clean_text(None) is None
        assert clean_text('') == ''
        assert clean_text('   \t\n   ') == ''