"""Эвристики редкости: импорт, лимитированные выпуски, редкие вкусы Monster."""
from __future__ import annotations

import re

# Маркеры импорта (вес 2)
IMPORT_MARKERS = [
    "импорт", "import", "япони", "японск", "japan", "сша", "америк", "usa", "u.s.a",
    "европ", "europe", "герман", "german", "польш", "poland", "коре", "korea",
    "турци", "turkey", "китай", "china", "оаэ", "араб", "англи", "britain", "uk",
    "чехи", "чешск", "испани", "итали", "франц", "france", "тайван", "таиланд", "thai",
]

# Маркеры лимитированных/эксклюзивных выпусков (вес 2)
LIMITED_MARKERS = [
    "лимит", "limited", "эксклюзив", "exclusive", "limited edition",
    "сезон", "seasonal", "season", "редк", "rare", "коллекцион",
    "снят с производства", "discontinued", "спецвыпуск", "special edition",
]

# Слабый сигнал новинки (вес 1)
NOVELTY_MARKERS = ["новинка", "new", "новый вкус"]

# Местное производство (не редкость)
LOCAL_MARKERS = ["сделано в казахстане", "казахстан", "казахстанск", "қазақстан", "kz"]

# Редкие/экзотические вкусы Monster, которые обычно не возят массово в КЗ.
# В обычной линейке ритейла РК стабильно присутствуют Classic, Ultra (white),
# Zero Sugar, Mango Loco, Monarch, иногда Pacific Punch — их в этот список не кладём.
RARE_MONSTER_FLAVORS = [
    "pipeline punch", "ultra fiesta", "ultra sunrise", "ultra paradise",
    "ultra rosa", "ultra violet", "ultra red", "ultra blue", "ultra gold",
    "aussie lemonade", "assault", "khaotic", "nitro", "maxx", "reserve",
    "juiced", "lewis hamilton", "monarch", "mule", "ginger brew",
    "super fuel", "java", "monster energy rio", "pacific pantry",
    "watermelon", "арбуз", "peachy", "персик", "dragon ice tea",
    "doctor's", "doctor s", "energy the doctor",
]

# Бренды и их русские написания
BRAND_PATTERNS = [
    ("Monster", r"monster|монстр"),
    ("Red Bull", r"red\s?bull|ред\s?булл|редбулл"),
    ("Burn", r"\bburn\b|берн"),
    ("Adrenaline Rush", r"adrenaline|адреналин"),
    ("Gorilla", r"gorilla|горилла"),
    ("Flash", r"\bflash\b|флеш"),
    ("Tornado", r"tornado|торнадо"),
    ("E-ON", r"e[\s\-]?on|е[\s\-]?он"),
    ("Dizzy", r"dizzy|диззи"),
    ("Lavina", r"lavina|лавина"),
    ("Gorilla", r"горилла"),
]


def detect_brand(name: str) -> str | None:
    text = (name or "").lower()
    for brand, pattern in BRAND_PATTERNS:
        if re.search(pattern, text):
            return brand
    return None


def _has_any(text: str, markers: list[str]) -> list[str]:
    return [m for m in markers if m in text]


def classify_rarity(name: str) -> tuple[str, list[str]]:
    """Возвращает уровень редкости (ordinary|rare|exclusive) и список меток."""
    text = (name or "").lower()
    tags: list[str] = []
    score = 0

    imported = _has_any(text, IMPORT_MARKERS)
    if imported:
        tags.append("импорт:" + imported[0])
        score += 2

    limited = _has_any(text, LIMITED_MARKERS)
    if limited:
        tags.append("лимит:" + limited[0])
        score += 2

    novelty = _has_any(text, NOVELTY_MARKERS)
    if novelty and not limited:
        tags.append("новинка")
        score += 1

    rare_flavors = [f for f in RARE_MONSTER_FLAVORS if f in text]
    if rare_flavors:
        tags.append("редкий вкус:" + rare_flavors[0])
        score += 1

    if _has_any(text, LOCAL_MARKERS) and score == 0:
        tags.append("местное производство")

    if score >= 3:
        tier = "exclusive"
    elif score >= 1:
        tier = "rare"
    else:
        tier = "ordinary"
    return tier, tags
