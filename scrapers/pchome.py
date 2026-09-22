"""
PChome 24h購物 關鍵字搜尋。開發luxury-tracker時實測過(2026/09): 搜尋API
`ecshweb.pchome.com.tw/search/v3.3/all/results` 直接回傳乾淨的JSON(name/price/Id),
不需要處理JS渲染或反爬蟲, 是這次比價功能目前唯一驗證過穩定可用的平台。

同時測過的momo(`apisearch.momoshop.com.tw`)直接403、Yahoo奇摩購物是SPA(初始HTML沒有資料,
跟Yahoo奇摩拍賣同一套技術棧), 兩者都先不支援, 之後有需要再評估無頭瀏覽器。
"""
import logging

import requests

from .base import HEADERS, TIMEOUT

log = logging.getLogger("pet-care")

PLATFORM = "pchome"
SUPPORTED = True

SEARCH_URL = "https://ecshweb.pchome.com.tw/search/v3.3/all/results"
PRODUCT_URL = "https://24h.pchome.com.tw/prod/{id}"


def parse_response(data, limit=30):
    """純函式(不碰網路), 從search API回傳的JSON抽取商品清單, 方便用存好的資料測試。"""
    results = []
    for prod in data.get("prods", []):
        price = prod.get("price")
        prod_id = prod.get("Id")
        name = prod.get("name")
        if not (price and prod_id and name):
            continue  # 缺欄位的商品跳過, 不要整批搜尋因為一筆資料不完整就掛掉
        results.append({
            "external_id": prod_id,
            "title": name,
            "url": PRODUCT_URL.format(id=prod_id),
            "price": float(price),
            "currency": "TWD",
        })
        if len(results) >= limit:
            break
    return results


def search(keyword, limit=30):
    resp = requests.get(
        SEARCH_URL,
        params={"q": keyword, "page": 1, "sort": "sale/dc"},
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    results = parse_response(resp.json(), limit=limit)
    if not results:
        log.warning(f"[pchome] 關鍵字「{keyword}」沒有抓到任何商品, 可能是搜尋無結果或API改版")
    return results
