"""
寵物健康管理 — 自用工具。多寵物：健康日誌(體重/看診/疫苗/驅蟲) + 飲食熱量計算 + 到期提醒推播。

跟 crypto-monitor 的架構差異：這裡不用常駐背景執行緒(Render免費方案的web服務閒置會被停機，
常駐執行緒在免費方案上不可靠)，到期提醒改成一支受token保護的 /api/internal/check-reminders
端點，由外部排程(GitHub Actions cron, 見 .github/workflows/cron.yml)每天呼叫一次觸發。
"""
import logging
import os
from datetime import date, datetime, timedelta

from flask import Flask, jsonify, request, send_from_directory

import db
import diet
import push
import reminders
from scrapers import REGISTRY as PRODUCT_SCRAPERS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pet-care")

app = Flask(__name__, static_folder="static", static_url_path="")

INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN")  # GitHub Actions cron呼叫check-reminders時要帶這個token

# 子紀錄資料表白名單: 表名絕對不能直接接受前端輸入拼SQL, 這裡限制路由的<table>參數只能是這幾個
# 已知字串之一(Flask URL routing比對完全相等, 不在清單裡的值進不來這段程式碼)。
TABLES = {
    "weight_logs": {
        "columns": ["weight_kg", "recorded_at"],
        "required": ["weight_kg", "recorded_at"],
        "order_by": "recorded_at DESC, id DESC",
    },
    "vet_visits": {
        "columns": ["visit_date", "reason", "notes"],
        "required": ["visit_date"],
        "order_by": "visit_date DESC, id DESC",
    },
    "vaccine_records": {
        "columns": ["item_name", "given_date", "next_due_date", "notes"],
        "required": ["item_name", "given_date"],
        "order_by": "given_date DESC, id DESC",
    },
    "deworming_records": {
        "columns": ["item_name", "given_date", "next_due_date", "notes"],
        "required": ["item_name", "given_date"],
        "order_by": "given_date DESC, id DESC",
    },
    "diet_entries": {
        "columns": ["food_name", "amount_grams", "entry_date", "notes"],
        "required": ["food_name", "entry_date"],
        "order_by": "entry_date DESC, id DESC",
    },
    "custom_reminders": {
        "columns": ["title", "due_date", "remind_days_before", "category", "repeat_days"],
        "required": ["title", "due_date"],
        "order_by": "due_date ASC, id ASC",
    },
    "bcs_logs": {
        "columns": ["score", "recorded_at", "notes"],
        "required": ["score", "recorded_at"],
        "order_by": "recorded_at DESC, id DESC",
    },
    "lab_results": {
        "columns": ["test_date", "item_name", "value", "unit", "ref_range", "notes"],
        "required": ["test_date", "item_name"],
        "order_by": "test_date DESC, id DESC",
    },
}


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ============================= 寵物 CRUD =============================
@app.route("/api/pets", methods=["GET"])
def list_pets():
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM pets ORDER BY id").fetchall()
    return jsonify(db.rows_to_dicts(rows))


@app.route("/api/pets", methods=["POST"])
def create_pet():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    species = body.get("species")
    if not name or species not in ("dog", "cat"):
        return jsonify({"ok": False, "error": "name和species(dog/cat)為必填"}), 400
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO pets (name, species, breed, birthday, sex, neutered, microchip_id, weight_goal_kg) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                species,
                body.get("breed"),
                body.get("birthday"),
                body.get("sex", "unknown"),
                1 if body.get("neutered") else 0,
                body.get("microchip_id"),
                body.get("weight_goal_kg"),
            ),
        )
        pet_id = cur.lastrowid
    return jsonify({"ok": True, "id": pet_id})


@app.route("/api/pets/<int:pet_id>", methods=["PUT"])
def update_pet(pet_id):
    body = request.get_json(silent=True) or {}
    fields, values = [], []
    for col in ("name", "species", "breed", "birthday", "sex", "microchip_id", "weight_goal_kg"):
        if col in body:
            fields.append(f"{col} = ?")
            values.append(body[col])
    if "neutered" in body:
        fields.append("neutered = ?")
        values.append(1 if body["neutered"] else 0)
    if not fields:
        return jsonify({"ok": False, "error": "沒有要更新的欄位"}), 400
    values.append(pet_id)
    with db.get_conn() as conn:
        conn.execute(f"UPDATE pets SET {', '.join(fields)} WHERE id = ?", values)
    return jsonify({"ok": True})


@app.route("/api/pets/<int:pet_id>", methods=["DELETE"])
def delete_pet(pet_id):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM pets WHERE id = ?", (pet_id,))
    return jsonify({"ok": True})


# ============================= 子紀錄 CRUD (體重/看診/疫苗/驅蟲/飲食/自訂提醒) =============================
@app.route("/api/pets/<int:pet_id>/<table>", methods=["GET"])
def list_records(pet_id, table):
    spec = TABLES.get(table)
    if not spec:
        return jsonify({"ok": False, "error": "未知的紀錄類型"}), 404
    with db.get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE pet_id = ? ORDER BY {spec['order_by']}", (pet_id,)
        ).fetchall()
    return jsonify(db.rows_to_dicts(rows))


@app.route("/api/pets/<int:pet_id>/<table>", methods=["POST"])
def create_record(pet_id, table):
    spec = TABLES.get(table)
    if not spec:
        return jsonify({"ok": False, "error": "未知的紀錄類型"}), 404
    body = request.get_json(silent=True) or {}
    missing = [c for c in spec["required"] if not body.get(c)]
    if missing:
        return jsonify({"ok": False, "error": f"缺少必填欄位: {', '.join(missing)}"}), 400
    cols = [c for c in spec["columns"] if c in body]
    placeholders = ", ".join("?" for _ in cols)
    values = [body[c] for c in cols]
    with db.get_conn() as conn:
        cur = conn.execute(
            f"INSERT INTO {table} (pet_id, {', '.join(cols)}) VALUES (?, {placeholders})",
            [pet_id] + values,
        )
        record_id = cur.lastrowid
    return jsonify({"ok": True, "id": record_id})


@app.route("/api/records/<table>/<int:record_id>", methods=["DELETE"])
def delete_record(table, record_id):
    if table not in TABLES:
        return jsonify({"ok": False, "error": "未知的紀錄類型"}), 404
    with db.get_conn() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
    return jsonify({"ok": True})


# ============================= 飲食熱量計算 =============================
@app.route("/api/pets/<int:pet_id>/diet_calc", methods=["POST"])
def diet_calc(pet_id):
    body = request.get_json(silent=True) or {}
    with db.get_conn() as conn:
        pet = conn.execute("SELECT * FROM pets WHERE id = ?", (pet_id,)).fetchone()
    if not pet:
        return jsonify({"ok": False, "error": "找不到這隻寵物"}), 404

    weight_kg = body.get("weight_kg")
    if weight_kg is None:
        with db.get_conn() as conn:
            latest = conn.execute(
                "SELECT weight_kg FROM weight_logs WHERE pet_id = ? ORDER BY recorded_at DESC, id DESC LIMIT 1",
                (pet_id,),
            ).fetchone()
        if not latest:
            return jsonify({"ok": False, "error": "沒有體重紀錄, 請先輸入weight_kg或新增一筆體重紀錄"}), 400
        weight_kg = latest["weight_kg"]

    age_months = body.get("age_months")
    if age_months is None and pet["birthday"]:
        try:
            born = datetime.strptime(pet["birthday"], "%Y-%m-%d").date()
            today = date.today()
            age_months = (today.year - born.year) * 12 + (today.month - born.month)
        except ValueError:
            age_months = None

    try:
        result = diet.compute_daily_calories(
            species=pet["species"],
            weight_kg=float(weight_kg),
            age_months=age_months,
            neutered=bool(pet["neutered"]),
        )
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    food_kcal_per_100g = body.get("food_kcal_per_100g")
    if food_kcal_per_100g:
        try:
            result["feeding_grams_per_day"] = diet.compute_feeding_amount_grams(
                result["mer_kcal"], float(food_kcal_per_100g)
            )
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        meals_per_day = body.get("meals_per_day")
        if meals_per_day:
            try:
                result["meals_grams"] = diet.split_into_meals(result["feeding_grams_per_day"], int(meals_per_day))
            except ValueError as e:
                return jsonify({"ok": False, "error": str(e)}), 400

    result["weight_kg"] = weight_kg
    if pet["weight_goal_kg"]:
        delta = round(pet["weight_goal_kg"] - float(weight_kg), 2)
        result["weight_goal_kg"] = pet["weight_goal_kg"]
        result["weight_goal_delta_kg"] = delta
    return jsonify({"ok": True, **result})


@app.route("/api/food_presets")
def food_presets():
    species = request.args.get("species")
    with db.get_conn() as conn:
        if species:
            rows = conn.execute(
                "SELECT * FROM food_presets WHERE species = ? ORDER BY brand, product_name", (species,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM food_presets ORDER BY brand, product_name").fetchall()
    return jsonify(db.rows_to_dicts(rows))


# ============================= 病史時間線 =============================
TIMELINE_SOURCES = [
    ("weight_logs", "recorded_at", "weight", lambda r: f"體重紀錄：{r['weight_kg']}kg"),
    ("vet_visits", "visit_date", "vet_visit", lambda r: f"看診：{r.get('reason') or '(未填原因)'}"),
    ("vaccine_records", "given_date", "vaccine", lambda r: f"疫苗：{r['item_name']}"),
    ("deworming_records", "given_date", "deworming", lambda r: f"驅蟲：{r['item_name']}"),
    ("bcs_logs", "recorded_at", "bcs", lambda r: f"體態評分：{r['score']}/9"),
    ("lab_results", "test_date", "lab", lambda r: f"檢驗：{r['item_name']} = {r.get('value')} {r.get('unit') or ''}".strip()),
]


@app.route("/api/pets/<int:pet_id>/timeline")
def pet_timeline(pet_id):
    events = []
    with db.get_conn() as conn:
        for table, date_col, kind, summarize in TIMELINE_SOURCES:
            rows = conn.execute(f"SELECT * FROM {table} WHERE pet_id = ?", (pet_id,)).fetchall()
            for r in rows:
                r = dict(r)
                events.append({"date": r[date_col], "type": kind, "summary": summarize(r), "id": r["id"]})
    events.sort(key=lambda e: e["date"], reverse=True)
    return jsonify(events)


# ============================= 花費記錄 =============================
EXPENSE_CATEGORIES = ("飼料", "零食", "看診", "疫苗驅蟲", "美容", "保健品", "用品", "其他")


@app.route("/api/expenses", methods=["GET"])
def list_expenses():
    month = request.args.get("month")  # "YYYY-MM", 不帶就回全部
    with db.get_conn() as conn:
        if month:
            rows = conn.execute(
                "SELECT e.*, p.name AS pet_name FROM expenses e LEFT JOIN pets p ON p.id = e.pet_id "
                "WHERE substr(e.expense_date, 1, 7) = ? ORDER BY e.expense_date DESC, e.id DESC",
                (month,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT e.*, p.name AS pet_name FROM expenses e LEFT JOIN pets p ON p.id = e.pet_id "
                "ORDER BY e.expense_date DESC, e.id DESC"
            ).fetchall()
    return jsonify(db.rows_to_dicts(rows))


@app.route("/api/expenses", methods=["POST"])
def create_expense():
    body = request.get_json(silent=True) or {}
    category = body.get("category")
    amount = body.get("amount")
    expense_date = body.get("expense_date")
    if category not in EXPENSE_CATEGORIES or not amount or not expense_date:
        return jsonify({"ok": False, "error": f"category(需為{'/'.join(EXPENSE_CATEGORIES)})/amount/expense_date為必填"}), 400
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO expenses (pet_id, category, amount, expense_date, notes) VALUES (?, ?, ?, ?, ?)",
            (body.get("pet_id"), category, float(amount), expense_date, body.get("notes")),
        )
        expense_id = cur.lastrowid
    return jsonify({"ok": True, "id": expense_id})


@app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    return jsonify({"ok": True})


@app.route("/api/expenses/summary")
def expenses_summary():
    """近months個月(含當月)每月總花費, 由舊到新排序, 給趨勢圖用。"""
    months = int(request.args.get("months", 6))
    today = date.today()
    month_keys = []
    y, m = today.year, today.month
    for _ in range(months):
        month_keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    month_keys.reverse()
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT substr(expense_date, 1, 7) AS month, SUM(amount) AS total FROM expenses GROUP BY month"
        ).fetchall()
    totals = {r["month"]: r["total"] for r in rows}
    return jsonify([{"month": mk, "total": totals.get(mk, 0)} for mk in month_keys])


# ============================= 寵物狀態總覽 (跨所有寵物的健康快照) =============================
@app.route("/api/pets/status")
def pets_status():
    with db.get_conn() as conn:
        pets = db.rows_to_dicts(conn.execute("SELECT * FROM pets ORDER BY id").fetchall())
        weight_rows = conn.execute(
            "SELECT pet_id, weight_kg, recorded_at FROM weight_logs ORDER BY pet_id, recorded_at DESC, id DESC"
        ).fetchall()
        bcs_rows = conn.execute(
            "SELECT pet_id, score, recorded_at FROM bcs_logs ORDER BY pet_id, recorded_at DESC, id DESC"
        ).fetchall()
        vaccine_records = db.rows_to_dicts(conn.execute("SELECT * FROM vaccine_records").fetchall())
        deworming_records = db.rows_to_dicts(conn.execute("SELECT * FROM deworming_records").fetchall())
        custom_reminders = db.rows_to_dicts(conn.execute("SELECT * FROM custom_reminders").fetchall())

    latest_weight, latest_bcs = {}, {}
    for r in weight_rows:
        latest_weight.setdefault(r["pet_id"], {"weight_kg": r["weight_kg"], "recorded_at": r["recorded_at"]})
    for r in bcs_rows:
        latest_bcs.setdefault(r["pet_id"], {"score": r["score"], "recorded_at": r["recorded_at"]})

    # notified_keys給空set: 這裡要的是「現在算下來有幾件事到期」的即時快照, 不受背景排程是否已經推播過影響
    due = reminders.collect_due_reminders(pets, vaccine_records, deworming_records, custom_reminders, date.today(), set())
    due_count_by_pet = {}
    for item in due:
        due_count_by_pet[item["pet_id"]] = due_count_by_pet.get(item["pet_id"], 0) + 1

    result = []
    for pet in pets:
        result.append({
            **pet,
            "latest_weight": latest_weight.get(pet["id"]),
            "latest_bcs": latest_bcs.get(pet["id"]),
            "due_reminders": due_count_by_pet.get(pet["id"], 0),
        })
    return jsonify(result)


# ============================= 到期提醒 (由GitHub Actions cron觸發) =============================
@app.route("/api/internal/check-reminders", methods=["GET", "POST"])
def check_reminders():
    token = request.args.get("token") or (request.get_json(silent=True) or {}).get("token")
    if not INTERNAL_TOKEN or token != INTERNAL_TOKEN:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    with db.get_conn() as conn:
        pets = db.rows_to_dicts(conn.execute("SELECT id, name FROM pets").fetchall())
        vaccine_records = db.rows_to_dicts(conn.execute("SELECT * FROM vaccine_records").fetchall())
        deworming_records = db.rows_to_dicts(conn.execute("SELECT * FROM deworming_records").fetchall())
        custom_reminders = db.rows_to_dicts(conn.execute("SELECT * FROM custom_reminders").fetchall())
        notified_keys = {r["reminder_key"] for r in conn.execute("SELECT reminder_key FROM notified_reminders")}

    due = reminders.collect_due_reminders(
        pets, vaccine_records, deworming_records, custom_reminders, date.today(), notified_keys
    )

    for item in due:
        push.send_notification(title=item["title"], body=f"到期日: {item['due_date']}", url="/")
        with db.get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO notified_reminders (reminder_key, title, pet_id, due_date) VALUES (?, ?, ?, ?)",
                (item["key"], item["title"], item["pet_id"], item["due_date"]),
            )
            # 只有custom_reminders支援自動週期重複——疫苗/驅蟲的下次到期日是獸醫另外決定的實際回診結果,
            # 不是固定間隔, 用程式自動猜下一次日期反而容易誤導使用者, 所以那兩種還是要使用者自己新增下一筆
            if item["kind"] == "custom" and item.get("repeat_days"):
                due_date = datetime.strptime(item["due_date"], "%Y-%m-%d").date()
                next_due = (due_date + timedelta(days=item["repeat_days"])).isoformat()
                row = conn.execute("SELECT * FROM custom_reminders WHERE id = ?", (item["record_id"],)).fetchone()
                if row:
                    conn.execute(
                        "INSERT INTO custom_reminders (pet_id, title, due_date, remind_days_before, category, repeat_days) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (row["pet_id"], row["title"], next_due, row["remind_days_before"], row["category"], row["repeat_days"]),
                    )
    log.info(f"提醒檢查完成, 共送出{len(due)}則推播")
    return jsonify({"ok": True, "notified": due})


@app.route("/api/reminders/history")
def reminders_history():
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT nr.*, p.name AS pet_name FROM notified_reminders nr "
            "LEFT JOIN pets p ON p.id = nr.pet_id ORDER BY nr.notified_at DESC LIMIT 200"
        ).fetchall()
    return jsonify(db.rows_to_dicts(rows))


# ============================= 推播訂閱 =============================
@app.route("/api/push/vapid_public_key")
def push_vapid_public_key():
    key = push.get_public_key()
    if not key:
        return jsonify({"ok": False, "error": "VAPID金鑰尚未就緒"}), 503
    return jsonify({"ok": True, "publicKey": key})


@app.route("/api/push/subscribe", methods=["POST"])
def push_subscribe():
    sub = request.get_json(silent=True) or {}
    if not sub.get("endpoint") or not sub.get("keys"):
        return jsonify({"ok": False, "error": "訂閱資料格式不對"}), 400
    push.add_subscription(sub)
    return jsonify({"ok": True})


@app.route("/api/push/unsubscribe", methods=["POST"])
def push_unsubscribe():
    body = request.get_json(silent=True) or {}
    endpoint = body.get("endpoint")
    if endpoint:
        push.remove_subscription(endpoint)
    return jsonify({"ok": True})


# ============================= 寵物用品比價 (零食/飼料/保健品/用品) =============================
@app.route("/api/products", methods=["GET"])
def list_products():
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    return jsonify(db.rows_to_dicts(rows))


@app.route("/api/products", methods=["POST"])
def create_product():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    category = body.get("category")
    keyword = (body.get("keyword") or "").strip()
    if not name or category not in ("零食", "飼料", "保健品", "用品") or not keyword:
        return jsonify({"ok": False, "error": "name/category(零食/飼料/保健品/用品)/keyword為必填"}), 400
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO products (name, category, keyword) VALUES (?, ?, ?)", (name, category, keyword)
        )
        product_id = cur.lastrowid
    return jsonify({"ok": True, "id": product_id})


@app.route("/api/products/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    return jsonify({"ok": True})


@app.route("/api/products/<int:product_id>/price_history")
def product_price_history(product_id):
    with db.get_conn() as conn:
        rows = conn.execute(
            """
            SELECT pl.platform, pl.external_id, pl.title, pl.url, ps.price, ps.scraped_at
            FROM product_price_snapshots ps
            JOIN product_listings pl ON pl.id = ps.listing_id
            WHERE pl.product_id = ?
            ORDER BY ps.scraped_at ASC
            """,
            (product_id,),
        ).fetchall()
    return jsonify(db.rows_to_dicts(rows))


@app.route("/api/products/<int:product_id>/listings")
def product_listings(product_id):
    with db.get_conn() as conn:
        rows = conn.execute(
            """
            SELECT pl.id, pl.platform, pl.title, pl.url, pl.last_seen_at, ps.price
            FROM product_listings pl
            JOIN product_price_snapshots ps ON ps.id = (
                SELECT id FROM product_price_snapshots WHERE listing_id = pl.id ORDER BY scraped_at DESC LIMIT 1
            )
            WHERE pl.product_id = ?
            ORDER BY pl.last_seen_at DESC
            """,
            (product_id,),
        ).fetchall()
    return jsonify(db.rows_to_dicts(rows))


@app.route("/api/platforms")
def list_platforms():
    return jsonify([{"platform": name, "supported": mod.SUPPORTED} for name, mod in PRODUCT_SCRAPERS.items()])


def _scrape_product_platform(conn, product, platform, mod):
    listings = mod.search(product["keyword"])  # 失敗直接丟例外, 呼叫端try/except處理
    for listing in listings:
        conn.execute(
            """
            INSERT INTO product_listings (product_id, platform, external_id, title, url, last_seen_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(platform, external_id) DO UPDATE SET
                title = excluded.title, url = excluded.url, last_seen_at = datetime('now')
            """,
            (product["id"], platform, listing["external_id"], listing["title"], listing["url"]),
        )
        listing_id = conn.execute(
            "SELECT id FROM product_listings WHERE platform = ? AND external_id = ?",
            (platform, listing["external_id"]),
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO product_price_snapshots (listing_id, price) VALUES (?, ?)",
            (listing_id, listing["price"]),
        )
    return len(listings)


@app.route("/api/internal/run-product-scrape", methods=["GET", "POST"])
def run_product_scrape():
    token = request.args.get("token") or (request.get_json(silent=True) or {}).get("token")
    if not INTERNAL_TOKEN or token != INTERNAL_TOKEN:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    with db.get_conn() as conn:
        products = db.rows_to_dicts(conn.execute("SELECT * FROM products").fetchall())

    summary = []
    for product in products:
        for platform, mod in PRODUCT_SCRAPERS.items():
            if not mod.SUPPORTED:
                continue
            entry = {"product_id": product["id"], "platform": platform, "ok": False, "listings_found": 0, "error": None}
            try:
                with db.get_conn() as conn:
                    entry["listings_found"] = _scrape_product_platform(conn, product, platform, mod)
                entry["ok"] = True
            except Exception as e:
                entry["error"] = str(e)
                log.warning(f"[{platform}] 抓取商品「{product['name']}」失敗: {e}")
            summary.append(entry)

    log.info(f"商品排程抓取完成, 共{len(summary)}筆(平台x商品)")
    return jsonify({"ok": True, "results": summary})


db.init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=True)
