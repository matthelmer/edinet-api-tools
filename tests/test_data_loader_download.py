"""The FSA code list is served as a zip (`Edinetcode.zip` → `EdinetcodeDlInfo.csv`,
cp932, one metadata line before the header) from `disclosure2dl.edinet-fsa.go.jp`.
The old `disclosure2.edinet-fsa.go.jp/weee0020/EDINET_Code_List.csv` path now 302s
to an HTML page (probed 2026-09-09); before 0.8.4 the loader would have written
that HTML into `edinet_codes.csv` and reported success."""
import io
import zipfile
from unittest.mock import patch

import pytest

from edinet_tools import data_loader
from edinet_tools.data_loader import EdinetDataLoader

CSV = ('ダウンロード実行日,2026年09月09日現在,件数,1件\n'
       'ＥＤＩＮＥＴコード,提出者種別,上場区分,連結の有無,資本金,決算日,提出者名,提出者名（英字）,提出者名（ヨミ）,所在地,提出者業種,証券コード,提出者法人番号\n'
       '"E00004","内国法人・組合","上場","有","1491","5月31日","カネコ種苗株式会社","KANEKO SEEDS CO., LTD.","カネコシュビョウ","群馬県","水産・農林業","13760","6070001000998"\n')


class _Resp(io.BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('EdinetcodeDlInfo.csv', CSV.encode('cp932'))
    return buf.getvalue()


def test_download_unpacks_the_code_list_zip(tmp_path):
    loader = EdinetDataLoader(data_dir=str(tmp_path))
    with patch.object(data_loader.urllib.request, 'urlopen', return_value=_Resp(_zip_bytes())) as m:
        assert loader.download_edinet_codes(force_update=True) is True
    assert m.call_args[0][0] == data_loader.EDINET_CODES_ZIP_URL
    assert 'disclosure2dl.edinet-fsa.go.jp' in data_loader.EDINET_CODES_ZIP_URL
    saved = tmp_path.joinpath('edinet_codes.csv').read_bytes()
    assert saved == CSV.encode('cp932')
    # The parser downstream reads exactly this shape.
    companies = loader.process_edinet_data()
    assert [c['edinet_code'] for c in companies] == ['E00004']


def test_download_refuses_a_non_zip_payload_and_writes_nothing(tmp_path):
    loader = EdinetDataLoader(data_dir=str(tmp_path))
    html = b'<!DOCTYPE html><html><body>EDINET</body></html>'
    with patch.object(data_loader.urllib.request, 'urlopen', return_value=_Resp(html)):
        assert loader.download_edinet_codes(force_update=True) is False
    assert not tmp_path.joinpath('edinet_codes.csv').exists()


def test_download_refuses_a_zip_without_a_csv_member(tmp_path):
    loader = EdinetDataLoader(data_dir=str(tmp_path))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('readme.txt', 'nope')
    with patch.object(data_loader.urllib.request, 'urlopen', return_value=_Resp(buf.getvalue())):
        assert loader.download_edinet_codes(force_update=True) is False
    assert not tmp_path.joinpath('edinet_codes.csv').exists()
