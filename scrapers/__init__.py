"""
每個平台一支 scraper, 統一介面: search(keyword, limit) -> list[dict(external_id, title, url, price, currency)]。
架構照抄 luxury-tracker 專案的 scrapers/ 設計(同一個人維護, 保持兩專案抓取邏輯一致): 每個平台獨立,
一個平台失敗不影響其他平台, SUPPORTED旗標標記目前是否有穩定可用的資料來源。
"""
from . import pchome

REGISTRY = {
    "pchome": pchome,
}
