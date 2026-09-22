import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db


def test_food_presets_seed_has_entries():
    assert len(db.FOOD_PRESETS_SEED) >= 10


def test_food_presets_seed_species_valid():
    for brand, product_name, species, kcal in db.FOOD_PRESETS_SEED:
        assert species in ("dog", "cat")
        assert kcal > 0
        assert brand and product_name


def test_seed_food_presets_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    with db.get_conn() as conn:
        first_count = conn.execute("SELECT COUNT(*) FROM food_presets").fetchone()[0]
    db.init_db()  # 模擬重啟, 種子資料不應該重複插入
    with db.get_conn() as conn:
        second_count = conn.execute("SELECT COUNT(*) FROM food_presets").fetchone()[0]
    assert first_count == len(db.FOOD_PRESETS_SEED)
    assert second_count == first_count
