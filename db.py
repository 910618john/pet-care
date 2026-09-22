"""
SQLite 資料層。用標準函式庫 sqlite3, 不上 ORM(單檔案、schema簡單, ORM只會增加不必要的複雜度)。

DB_PATH 預設寫在程式碼同一個資料夾(本機開發用)。Render免費方案沒有掛Disk,
每次重新部署/重啟都會回到全新的空DB, 這是計畫階段跟使用者確認過的取捨(先求免費，
之後真的需要資料long-term保留再加Render Disk, 設DB_PATH環境變數指到掛載路徑即可)。
"""
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "pet_care.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS pets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    species TEXT NOT NULL CHECK(species IN ('dog', 'cat')),
    breed TEXT,
    birthday TEXT,
    sex TEXT CHECK(sex IN ('m', 'f', 'unknown')) DEFAULT 'unknown',
    neutered INTEGER NOT NULL DEFAULT 0,
    weight_goal_kg REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS weight_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    weight_kg REAL NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vet_visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    visit_date TEXT NOT NULL,
    reason TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS vaccine_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    item_name TEXT NOT NULL,
    given_date TEXT NOT NULL,
    next_due_date TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS deworming_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    item_name TEXT NOT NULL,
    given_date TEXT NOT NULL,
    next_due_date TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS diet_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    food_name TEXT NOT NULL,
    amount_grams REAL,
    entry_date TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS bcs_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 9),
    recorded_at TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS lab_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    test_date TEXT NOT NULL,
    item_name TEXT NOT NULL,
    value REAL,
    unit TEXT,
    ref_range TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS custom_reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id INTEGER NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    due_date TEXT NOT NULL,
    remind_days_before INTEGER NOT NULL DEFAULT 3,
    category TEXT NOT NULL DEFAULT 'other',
    repeat_days INTEGER
);

-- 記錄「哪個提醒實例已經推播過」, key是「來源類型:紀錄id:到期日」組成的字串。
-- 到期日一變(使用者改了下次到期日)key就跟著變, 等於視為新的提醒實例, 不會被舊紀錄擋住。
-- title/pet_id/due_date是推播當下存的快照, 不是外鍵參照——之後原始紀錄被刪除或改掉,
-- 歷史紀錄頁還是要能顯示「當初推播的是什麼」, 不能因為原始紀錄消失就顯示不出來。
CREATE TABLE IF NOT EXISTS notified_reminders (
    reminder_key TEXT PRIMARY KEY,
    title TEXT,
    pet_id INTEGER,
    due_date TEXT,
    notified_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL UNIQUE,
    keys_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS food_presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand TEXT NOT NULL,
    product_name TEXT NOT NULL,
    species TEXT NOT NULL CHECK(species IN ('dog', 'cat')),
    kcal_per_100g REAL NOT NULL
);

-- 比價追蹤的商品(零食/飼料/保健品/用品), 不綁定特定寵物 — 同一包飼料可能家裡好幾隻都在吃。
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('零食', '飼料', '保健品', '用品')),
    keyword TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS product_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT,
    url TEXT,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(platform, external_id)
);

CREATE TABLE IF NOT EXISTS product_price_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES product_listings(id) ON DELETE CASCADE,
    price REAL NOT NULL,
    scraped_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# 常見台灣市場飼料品牌熱量密度(kcal/100g), 抓包裝上常見公開標示值當起點, 個別批次/口味會有差異,
# 只當飲食計算機的「快速帶入」選項, 使用者永遠可以自己覆蓋掉這個數字。
FOOD_PRESETS_SEED = [
    ("Royal Canin 皇家", "腸胃保健處方 成犬", "dog", 337),
    ("Royal Canin 皇家", "室內成貓", "cat", 374),
    ("Hill's 希爾思", "i/d 腸胃保健 成犬", "dog", 378),
    ("Hill's 希爾思", "c/d 泌尿道保健 成貓", "cat", 368),
    ("Orijen 渴望", "六種魚 成犬", "dog", 405),
    ("Orijen 渴望", "六種魚 成貓", "cat", 400),
    ("Acana 愛肯拿", "無穀野性草原 成犬", "dog", 366),
    ("Acana 愛肯拿", "野性極橙 成貓", "cat", 391),
    ("Nutro 美士", "全犬種成犬", "dog", 350),
    ("Nutro 美士", "室內成貓", "cat", 385),
    ("ProNature Holistic 大地", "田園糙米蔬果 成犬", "dog", 335),
    ("ProNature Holistic 大地", "田園糙米蔬果 成貓", "cat", 355),
    ("K9 Natural", "生食淋醬牛肉 成犬", "dog", 175),
    ("Ziwi Peak 巔峰", "風乾牛肉 成犬", "dog", 460),
    ("Ziwi Peak 巔峰", "風乾牛肉 成貓", "cat", 460),
    ("Instinct 本能", "無穀雞肉 成犬", "dog", 400),
    ("Instinct 本能", "無穀雞肉 成貓", "cat", 410),
    ("Now Fresh 諾大", "無穀火雞 成犬", "dog", 358),
    ("Taste of the Wild", "無穀野牛 成犬", "dog", 370),
    ("愛肯拿 幼犬", "太平洋鮭魚 幼犬", "dog", 411),
]


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _seed_food_presets(conn)


def _seed_food_presets(conn):
    """只在表是空的時候seed一次, 不然每次啟動都重插入或者使用者刪掉的品項又跑回來。"""
    count = conn.execute("SELECT COUNT(*) FROM food_presets").fetchone()[0]
    if count > 0:
        return
    conn.executemany(
        "INSERT INTO food_presets (brand, product_name, species, kcal_per_100g) VALUES (?, ?, ?, ?)",
        FOOD_PRESETS_SEED,
    )


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def rows_to_dicts(rows):
    return [dict(r) for r in rows]
