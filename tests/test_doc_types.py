"""Tests for DocType registry."""
import pytest
from edinet_tools.doc_types import DocType, doc_type, list_doc_types


class TestDocType:
    """Test DocType registry."""

    def test_doc_type_lookup(self):
        """Look up doc type by code."""
        dt = doc_type("350")
        assert dt is not None
        assert dt.code == "350"
        assert dt.name_en == "Large Shareholding Report"
        assert dt.name_jp == "大量保有報告書"

    def test_common_doc_types_defined(self):
        """All common doc types are defined."""
        for code in ["120", "140", "160", "180", "220", "240", "350"]:
            dt = doc_type(code)
            assert dt is not None
            assert dt.name_en is not None

    def test_unknown_doc_type_returns_none(self):
        """Unknown doc type returns None."""
        assert doc_type("999") is None

    def test_list_doc_types(self):
        """list_doc_types returns all defined types."""
        types = list_doc_types()
        assert len(types) >= 5
        assert all(isinstance(t, DocType) for t in types)

    def test_doc_type_has_all_attributes(self):
        """DocType has expected attributes."""
        dt = doc_type("120")
        assert hasattr(dt, 'code')
        assert hasattr(dt, 'name_en')
        assert hasattr(dt, 'name_jp')
        assert hasattr(dt, 'description')

    def test_doc_type_repr(self):
        """DocType repr is informative."""
        dt = doc_type("350")
        repr_str = repr(dt)
        assert "350" in repr_str

    def test_amendment_doc_types(self):
        """Amendment doc types are defined."""
        # 130 is Securities Report Amendment
        dt = doc_type("130")
        assert dt is not None
        assert "Amendment" in dt.name_en or "訂正" in dt.name_jp


# 書類種別コード per the FSA's EDINET API仕様書 (Version 2, 参考資料 4-1; the
# copy at disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/download/ESE140206.pdf,
# updated 2026-06-03). name_jp is the filed name, verbatim.
OFFICIAL_NAME_JP = {
    '010': '有価証券通知書', '020': '変更通知書（有価証券通知書）', '030': '有価証券届出書',
    '040': '訂正有価証券届出書', '050': '届出の取下げ願い', '060': '発行登録通知書',
    '070': '変更通知書（発行登録通知書）', '080': '発行登録書', '090': '訂正発行登録書',
    '100': '発行登録追補書類', '110': '発行登録取下届出書', '120': '有価証券報告書',
    '130': '訂正有価証券報告書', '135': '確認書', '136': '訂正確認書', '140': '四半期報告書',
    '150': '訂正四半期報告書', '160': '半期報告書', '170': '訂正半期報告書', '180': '臨時報告書',
    '190': '訂正臨時報告書', '200': '親会社等状況報告書', '210': '訂正親会社等状況報告書',
    '220': '自己株券買付状況報告書', '230': '訂正自己株券買付状況報告書', '235': '内部統制報告書',
    '236': '訂正内部統制報告書', '240': '公開買付届出書', '250': '訂正公開買付届出書',
    '260': '公開買付撤回届出書', '270': '公開買付報告書', '280': '訂正公開買付報告書',
    '290': '意見表明報告書', '300': '訂正意見表明報告書', '310': '対質問回答報告書',
    '320': '訂正対質問回答報告書', '330': '別途買付け禁止の特例を受けるための申出書',
    '340': '訂正別途買付け禁止の特例を受けるための申出書', '350': '大量保有報告書',
    '360': '訂正大量保有報告書', '370': '基準日の届出書', '380': '変更の届出書',
}


class TestRegistryMatchesTheSpec:
    def test_every_code_in_the_spec_is_registered_and_nothing_else(self):
        assert {dt.code for dt in list_doc_types()} == set(OFFICIAL_NAME_JP)

    @pytest.mark.parametrize('code,name_jp', sorted(OFFICIAL_NAME_JP.items()))
    def test_name_jp_is_the_filed_name(self, code, name_jp):
        assert doc_type(code).name_jp == name_jp

    def test_370_and_380_are_not_large_shareholding_change_reports(self):
        """変更報告書 (the 5% change report) is filed under 350, not 370; 370 is the
        record-date notification and 380 the change notification. The 0.8.4
        draft registry had them backwards."""
        assert '変更報告書' not in doc_type('370').name_jp
        assert 'Shareholding' not in doc_type('370').name_en
        assert 'Shareholding' not in doc_type('380').name_en
        assert 'Shelf' not in doc_type('070').name_en
