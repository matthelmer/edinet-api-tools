"""
File Processing Infrastructure Tests - TIER 1 CRITICAL PATH

Tests the file processing pipeline that enables all document extraction:
encoding fallback, CSV parsing, directory processing.
"""

import os
import tempfile

from edinet_tools.utils import (
    read_csv_file,
    clean_text,
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

        # Should read successfully (encoding tried via the fixed candidate
        # list, 'utf-16' first -- no chardet detection step since 0.8.0)
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