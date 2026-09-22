import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import diet


def test_compute_rer_basic():
    # 10kg 成犬: 70 * 10^0.75 ≈ 393.6
    assert diet.compute_rer(10) == pytest.approx(393.65, abs=0.1)


def test_compute_rer_rejects_non_positive():
    with pytest.raises(ValueError):
        diet.compute_rer(0)
    with pytest.raises(ValueError):
        diet.compute_rer(-5)


def test_resolve_life_stage_puppy_young():
    assert diet.resolve_life_stage("dog", 2, False) == "puppy_young"


def test_resolve_life_stage_puppy_old():
    assert diet.resolve_life_stage("dog", 8, False) == "puppy_old"


def test_resolve_life_stage_senior():
    assert diet.resolve_life_stage("cat", 100, True) == "senior"


def test_resolve_life_stage_adult_neutered_vs_intact():
    assert diet.resolve_life_stage("dog", 36, True) == "adult_neutered"
    assert diet.resolve_life_stage("dog", 36, False) == "adult_intact"


def test_resolve_life_stage_unknown_age_defaults_to_adult():
    assert diet.resolve_life_stage("cat", None, True) == "adult_neutered"


def test_compute_daily_calories_dog_neutered_adult():
    result = diet.compute_daily_calories("dog", 10, age_months=36, neutered=True)
    assert result["life_stage"] == "adult_neutered"
    assert result["factor"] == 1.6
    assert result["mer_kcal"] == pytest.approx(393.65 * 1.6, abs=0.5)


def test_compute_daily_calories_rejects_bad_species():
    with pytest.raises(ValueError):
        diet.compute_daily_calories("bird", 1)


def test_compute_feeding_amount_grams():
    grams = diet.compute_feeding_amount_grams(mer_kcal=630, food_kcal_per_100g=350)
    assert grams == pytest.approx(180.0)


def test_compute_feeding_amount_grams_rejects_zero_density():
    with pytest.raises(ValueError):
        diet.compute_feeding_amount_grams(500, 0)


def test_split_into_meals_even_division():
    assert diet.split_into_meals(180, 3) == [60.0, 60.0, 60.0]


def test_split_into_meals_last_meal_absorbs_remainder():
    meals = diet.split_into_meals(100, 3)
    assert len(meals) == 3
    assert sum(meals) == pytest.approx(100.0)
    assert meals[0] == meals[1]


def test_split_into_meals_single_meal_is_identity():
    assert diet.split_into_meals(250, 1) == [250.0]


def test_split_into_meals_rejects_non_positive_count():
    with pytest.raises(ValueError):
        diet.split_into_meals(100, 0)
