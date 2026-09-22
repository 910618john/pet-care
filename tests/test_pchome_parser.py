import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers import pchome

# 精簡過的真實回應片段(2026/09實際打PChome search API存下來的格式, 見開發時探測紀錄)
SAMPLE_RESPONSE = {
    "totalRows": 2414,
    "prods": [
        {"Id": "DXBG71-A900GMRM9", "name": "經典系列 狗飼料 13.6kg", "price": 1875, "originPrice": 1875},
        {"Id": "DXBG7R-A900HHBIV", "name": "另一款飼料", "price": 1030, "originPrice": 1200},
        {"Id": "MISSING-PRICE", "name": "缺價格商品"},
        {"Id": "", "name": "缺id商品", "price": 500},
    ],
}


def test_parse_response_extracts_valid_products():
    results = pchome.parse_response(SAMPLE_RESPONSE)
    assert len(results) == 2  # 缺price/缺id的兩筆要被跳過
    first = results[0]
    assert first["external_id"] == "DXBG71-A900GMRM9"
    assert first["price"] == 1875.0
    assert first["currency"] == "TWD"
    assert first["url"] == "https://24h.pchome.com.tw/prod/DXBG71-A900GMRM9"


def test_parse_response_respects_limit():
    results = pchome.parse_response(SAMPLE_RESPONSE, limit=1)
    assert len(results) == 1


def test_parse_response_empty_prods_returns_empty_list():
    assert pchome.parse_response({"prods": []}) == []


def test_parse_response_missing_prods_key_returns_empty_list():
    assert pchome.parse_response({}) == []
