"""
每日建議熱量計算, 用獸醫營養學常見的 RER/MER 公式(純函式, 不碰資料庫, 方便測試):

RER(靜止能量需求, kcal/day) = 70 * 體重(kg) ^ 0.75  — 這是體重2~45kg左右通用的標準公式,
  極端體重(<2kg或>45kg)用這個公式會失準, 但一般家庭寵物狗貓都落在這個範圍內, 先不特別處理。

MER(維持能量需求) = RER * 生活型態係數, 係數依物種/年齡/絕育狀態決定, 抓業界常見的區間中位數:
  來源: 這組係數是獸醫營養學教科書(如WSAVA全球營養委員會指引)常見的通用區間, 個體差異大,
  只能當「起點」, 實際餵食量要搭配體態評分(BCS)持續調整, 不是精確處方——這點要在前端UI上明講,
  避免使用者誤以為是精準醫囑。
"""

LIFE_STAGE_FACTORS = {
    ("dog", "puppy_young"): 3.0,   # 4個月以下幼犬
    ("dog", "puppy_old"): 2.0,     # 4~12個月幼犬
    ("dog", "adult_neutered"): 1.6,
    ("dog", "adult_intact"): 1.8,
    ("dog", "senior"): 1.4,
    ("cat", "puppy_young"): 3.0,   # 4個月以下幼貓, 跟幼犬同一套區間, 業界常見做法
    ("cat", "puppy_old"): 2.5,     # 4~12個月幼貓
    ("cat", "adult_neutered"): 1.2,
    ("cat", "adult_intact"): 1.4,
    ("cat", "senior"): 1.1,
}


def resolve_life_stage(species, age_months, neutered):
    """依月齡+絕育狀態決定要套哪一組係數。age_months為None(不知道生日)時當一般成犬貓成年處理,
    這是保守起點(幼年期熱量需求明顯較高, 沒有月齡資訊時寧可低估也不要亂猜幼年期)。"""
    if age_months is not None and age_months < 4:
        return "puppy_young"
    if age_months is not None and age_months < 12:
        return "puppy_old"
    if age_months is not None and age_months >= 84:  # 7歲以上一般視為熟齡犬貓
        return "senior"
    return "adult_neutered" if neutered else "adult_intact"


def compute_rer(weight_kg):
    if weight_kg is None or weight_kg <= 0:
        raise ValueError("體重必須是正數")
    return 70 * (weight_kg ** 0.75)


def compute_daily_calories(species, weight_kg, age_months=None, neutered=False):
    """回傳 dict: rer / mer(建議每日總熱量kcal) / life_stage(套用的係數分類)"""
    if species not in ("dog", "cat"):
        raise ValueError("species必須是dog或cat")
    life_stage = resolve_life_stage(species, age_months, neutered)
    rer = compute_rer(weight_kg)
    factor = LIFE_STAGE_FACTORS[(species, life_stage)]
    mer = rer * factor
    return {
        "rer_kcal": round(rer, 1),
        "mer_kcal": round(mer, 1),
        "life_stage": life_stage,
        "factor": factor,
    }


def compute_feeding_amount_grams(mer_kcal, food_kcal_per_100g):
    """依飼料的「每100g熱量(kcal)」換算建議每日餵食公克數。food_kcal_per_100g通常印在飼料包裝上。"""
    if not food_kcal_per_100g or food_kcal_per_100g <= 0:
        raise ValueError("飼料熱量密度必須是正數")
    return round(mer_kcal / food_kcal_per_100g * 100, 1)


def split_into_meals(total_grams, meals_per_day):
    """把每日總餵食量平均分成meals_per_day餐, 除不盡的餘數由最後一餐吸收(公克數不會因為四捨五入
    分餐而讓每天加總跟總量對不起來, 使用者才不會覺得「怎麼分餐後總量不一樣」)。"""
    if not meals_per_day or meals_per_day <= 0:
        raise ValueError("每日餐數必須是正整數")
    meals_per_day = int(meals_per_day)
    base = round(total_grams / meals_per_day, 1)
    meals = [base] * (meals_per_day - 1)
    last = round(total_grams - base * (meals_per_day - 1), 1)
    meals.append(last)
    return meals
