"""
core/matcher.py
Утилиты для сравнения строк и приведения единиц.
"""
import re

# карта похожих букв (русская/английская)
HOMOGLYPHS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
    "х": "x", "у": "y", "к": "k", "м": "m", "т": "t",
    "в": "b", "н": "h",
    "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C",
    "Х": "X", "У": "Y", "К": "K", "М": "M", "Т": "T",
    "В": "B", "Н": "H",
})


def normalize(s):
    """Приводит строку к сравнимому виду."""
    if not s:
        return ""
    s = s.translate(HOMOGLYPHS)
    s = s.lower()
    s = re.sub(r"[\s\-_/\\.,()]+", "", s)
    return s


def keyword_match(name, keywords):
    """
    Проверяет, что все ключевые слова есть в названии.
    Игнорирует регистр, дефисы, homoglyphs.
    """
    if not keywords:
        return True
    n = normalize(name)
    for k in keywords:
        if normalize(k) not in n:
            return False
    return True


# ---------- приведение единиц ----------

# паттерны "N м", "N шт.", "L=NNN", "L3000 - 3 м", "бухта 100 м", "305 м"
UNIT_PATTERNS = [
    r"(\d{1,5})\s*м\b",           # 305 м
    r"(\d{1,5})\s*шт\b",          # 100 шт
    r"L\s*=?\s*(\d{2,5})",        # L3000 или L=3000
    r"(\d{1,5})\s*метр",          # 100 метров
    r"бухт[аы]?\s*(\d{1,5})",     # бухта 100
    r"уп\.?\s*(\d{1,5})",         # уп. 100
]


def detect_multiplier(name, unit_akt):
    """
    Ищет множитель в названии найденного товара.
    Возвращает int (множитель) или 1.
    """
    if not name:
        return 1

    # для мм → м: L3000 значит 3 м
    m = re.search(r"L\s*=?\s*(\d{3,5})", name)
    if m and unit_akt in ("м", "м.", "пог.м"):
        mm = int(m.group(1))
        # если это мм (L3000 = 3000 мм = 3 м)
        if mm >= 100:
            return max(1, mm // 1000)
        return mm

    # "N м" для кабеля, трубы
    if unit_akt in ("м", "м.", "пог.м"):
        for pat in [r"(\d{2,5})\s*м\b", r"(\d{2,5})\s*метр"]:
            m = re.search(pat, name)
            if m:
                n = int(m.group(1))
                if n >= 2:
                    return n

    # "N шт" для коробок, шпилек
    if unit_akt.startswith("шт"):
        for pat in [r"(\d{2,4})\s*шт", r"уп\.?\s*(\d{2,4})"]:
            m = re.search(pat, name)
            if m:
                n = int(m.group(1))
                if n >= 2:
                    return n

    # бухта N
    m = re.search(r"бухт[аы]?\s*(\d{2,5})", name)
    if m:
        n = int(m.group(1))
        if n >= 2:
            return n

    return 1


def adjust_price(price, name, unit_akt):
    """
    Приводит цену к базовой единице (за 1 м или за 1 шт).
    Возвращает (приведённая_цена, множитель).
    """
    if not price:
        return price, 1
    mult = detect_multiplier(name, unit_akt)
    return round(price / mult, 2), mult


# ---------- сборные позиции ----------

COLLECTIVE_MARKERS = [
    "расходные", "расходный", "крепежные материалы", "крепежные и",
    "мобилизация", "организация площадки", "предварительные затраты",
    "прочие", "прочее", "разные", "комплекс работ", "монтажные работы",
    "пусконаладка", "пусконаладочные",
]


def is_collective(name):
    """Проверяет, что это сборная позиция, а не конкретный товар."""
    n = (name or "").lower()
    return any(m in n for m in COLLECTIVE_MARKERS)