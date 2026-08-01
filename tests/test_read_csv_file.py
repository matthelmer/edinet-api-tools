"""Behavior pins for read_csv_file across the pandas->stdlib-csv migration."""
import pytest

from edinet_tools.utils import read_csv_file


def _write(tmp_path, name, text, encoding):
    p = tmp_path / name
    p.write_bytes(text.encode(encoding))
    return str(p)


TSV = '要素ID\tコンテキストID\t値\njpdei_cor:EDINETCodeDEI\tFilingDateInstant\tE01234\njpcrp_cor:NetSales\tCurrentYearDuration\t\n'


class TestReadCsvFile:
    def test_utf16le_bom_edinet_shape(self, tmp_path):
        # EDINET ships UTF-16-LE with BOM; 'utf-16' codec consumes the BOM
        path = _write(tmp_path, 'a.csv', TSV, 'utf-16')
        rows = read_csv_file(path)
        assert rows[0]['要素ID'] == 'jpdei_cor:EDINETCodeDEI'
        assert rows[0]['値'] == 'E01234'

    def test_values_are_strings(self, tmp_path):
        path = _write(tmp_path, 'n.csv', '値\n12345\n', 'utf-8')
        assert read_csv_file(path)[0]['値'] == '12345'

    def test_empty_cell_becomes_none(self, tmp_path):
        path = _write(tmp_path, 'a.csv', TSV, 'utf-16')
        assert read_csv_file(path)[1]['値'] is None

    def test_utf8_fallback(self, tmp_path):
        path = _write(tmp_path, 'b.csv', TSV, 'utf-8')
        rows = read_csv_file(path)
        assert len(rows) == 2

    def test_empty_file_returns_none(self, tmp_path):
        p = tmp_path / 'empty.csv'
        p.write_bytes(b'')
        assert read_csv_file(str(p)) is None

    def test_shape_is_list_of_dicts(self, tmp_path):
        path = _write(tmp_path, 'a.csv', TSV, 'utf-16')
        rows = read_csv_file(path)
        assert isinstance(rows, list) and all(isinstance(r, dict) for r in rows)

    # --- Pandas strict-tokenization parity pins (added after a code-review
    # finding: naive csv.DictReader silently swallows/corrupts malformed input
    # that pandas' C engine rejected outright). Each pin's expected value was
    # verified empirically against the OLD pandas-based implementation
    # (commit 8313c84) before being encoded here - see the pandas-removal
    # report for the verification transcripts.

    def test_malformed_unterminated_quote_returns_none(self, tmp_path):
        # An unterminated quoted field spanning subsequent lines/tabs made
        # pandas' C engine raise ParserError ("EOF inside string") on every
        # encoding, so the old code returned None end-to-end. A naive
        # csv.DictReader raises nothing here and silently absorbs the rest of
        # the file (newlines and tabs included) into one field.
        content = 'A\tB\tC\n"abc\nB\tdef\n'
        path = _write(tmp_path, 'malformed.csv', content, 'utf-8')
        assert read_csv_file(path) is None

    def test_ragged_row_more_fields_than_header_returns_none(self, tmp_path):
        # A data row with MORE fields than the header made pandas raise
        # ParserError ("Expected 3 fields, saw 5") for the whole file, so the
        # old code returned None end-to-end. A naive csv.DictReader instead
        # stows the overflow under a None restkey, silently violating the
        # all-values-are-strings row shape.
        # (Trailing blank line keeps the byte count odd so utf-16le/be don't
        # vacuously "succeed" on a BOM-less reinterpretation of ASCII bytes
        # before reaching the encoding that actually matters here - verified
        # empirically against the old implementation.)
        content = 'A\tB\tC\nx\ty\tz\np\tq\tr\ts\tt\n\n'
        path = _write(tmp_path, 'ragged.csv', content, 'utf-8')
        assert read_csv_file(path) is None

    def test_short_row_fewer_fields_is_padded_not_rejected(self, tmp_path):
        # A row with FEWER fields than the header is NOT an error case:
        # pandas silently padded the missing trailing field with NaN (-> None).
        # The guard added for the ragged-row case above must not over-reject
        # this.
        content = 'A\tB\tC\nx\ty\tz\np\tq\n'
        path = _write(tmp_path, 'short.csv', content, 'utf-8')
        rows = read_csv_file(path)
        assert rows == [
            {'A': 'x', 'B': 'y', 'C': 'z'},
            {'A': 'p', 'B': 'q', 'C': None},
        ]

    def test_legitimately_quoted_field_is_accepted(self, tmp_path):
        # A properly-quoted field containing the delimiter's escape-worthy
        # content (a comma, not the tab delimiter) must still parse cleanly -
        # proving the strict=True guard doesn't over-reject well-formed input.
        # pandas accepted this and unwrapped the quotes.
        content = 'A\tB\tC\n"hello, world"\ty\tz\n'
        path = _write(tmp_path, 'quoted.csv', content, 'utf-8')
        assert read_csv_file(path) == [{'A': 'hello, world', 'B': 'y', 'C': 'z'}]
