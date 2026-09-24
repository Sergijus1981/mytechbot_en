# ============================================================
# regions.py — Аура, 2026-09-24
# Определение региона по тексту PDF
# ============================================================

REGION_MAP = {
    "москва": "msk", "московская": "msk", "дубна": "msk",
    "подольск": "msk", "химки": "msk", "балашиха": "msk",
    "королёв": "msk", "мытищи": "msk", "зеленоград": "msk",
    "санкт-петербург": "spb", "спб": "spb", "петербург": "spb",
    "ленинградская": "spb",
    "новосибирск": "nsk", "красноярск": "kras", "иркутск": "irk",
    "омск": "omsk", "томск": "tomsk", "кемерово": "kem",
    "владивосток": "vvo", "хабаровск": "khv", "якутск": "ykt",
    "краснодар": "krd", "ростов": "rnd", "сочи": "sochi",
    "екатеринбург": "ekb", "челябинск": "chel", "тюмень": "tmn",
    "пермь": "perm", "казань": "kzn", "самара": "sam",
    "нижний новгород": "nn", "воронеж": "vor", "уфа": "ufa",
    "волгоград": "vlg", "саратов": "sar", "тольятти": "tlt",
}

REGION_NAMES = {
    "msk": "Москва",
    "spb": "Санкт-Петербург",
    "nsk": "Новосибирск",
    "vvo": "Владивосток",
    "kras": "Красноярск",
    "irk": "Иркутск",
    "omsk": "Омск",
    "tomsk": "Томск",
    "kem": "Кемерово",
    "khv": "Хабаровск",
    "ykt": "Якутск",
    "krd": "Краснодар",
    "rnd": "Ростов-на-Дону",
    "sochi": "Сочи",
    "ekb": "Екатеринбург",
    "chel": "Челябинск",
    "tmn": "Тюмень",
    "perm": "Пермь",
    "kzn": "Казань",
    "sam": "Самара",
    "nn": "Нижний Новгород",
    "vor": "Воронеж",
    "ufa": "Уфа",
    "vlg": "Волгоград",
    "sar": "Саратов",
    "tlt": "Тольятти",
}

DEFAULT_REGION = "msk"

ETM_CITY = {
    "msk": "moskva", "spb": "sankt-peterburg",
    "nsk": "novosibirsk", "vvo": "vladivostok",
    "ekb": "ekaterinburg", "kzn": "kazan",
    "krd": "krasnodar", "nn": "nizhniy-novgorod",
    "sam": "samara", "chel": "chelyabinsk",
    "rnd": "rostov-na-donu", "perm": "perm",
    "vor": "voronezh", "kras": "krasnoyarsk",
    "ufa": "ufa", "vlg": "volgograd",
    "sar": "saratov", "tlt": "tolyatti",
}


def detect_region(text):
    """Определяет регион по тексту. Приоритет: первое совпадение."""
    if not text:
        return DEFAULT_REGION
    low = text.lower()
    for city, region in REGION_MAP.items():
        if city in low:
            return region
    return DEFAULT_REGION


def region_name(code):
    return REGION_NAMES.get(code, "Москва")


def etm_city(code):
    return ETM_CITY.get(code, "moskva")


if __name__ == "__main__":
    test = "Заказчик: ООО Ядро Фаб Дубна, г. Дубна, Московская область"
    r = detect_region(test)
    print(f"Регион: {r} ({region_name(r)})")
    print(f"ЭТМ город: {etm_city(r)}")


# ============================================================
# ХАБЫ — откуда везём, если нет в регионе
# ============================================================

REGION_HUBS = {
    "vvo": ["khv", "nsk", "msk"],
    "khv": ["vvo", "nsk", "msk"],
    "ykt": ["khv", "nsk", "msk"],
    "nsk": ["kras", "omsk", "msk"],
    "kras": ["irk", "nsk", "msk"],
    "irk": ["kras", "nsk", "msk"],
    "omsk": ["nsk", "tmn", "msk"],
    "tomsk": ["nsk", "kras", "msk"],
    "ekb": ["chel", "tmn", "msk"],
    "chel": ["ekb", "ufa", "msk"],
    "tmn": ["ekb", "chel", "msk"],
    "perm": ["ekb", "ufa", "msk"],
    "ufa": ["chel", "ekb", "msk"],
    "kzn": ["nn", "sam", "msk"],
    "nn": ["kzn", "msk"],
    "sam": ["kzn", "tlt", "msk"],
    "tlt": ["sam", "kzn", "msk"],
    "sar": ["sam", "vlg", "msk"],
    "vlg": ["sar", "rnd", "msk"],
    "vor": ["msk"],
    "krd": ["rnd", "sochi", "msk"],
    "rnd": ["krd", "vlg", "msk"],
    "sochi": ["krd", "rnd", "msk"],
    "spb": ["msk"],
    "msk": [],
}


# ============================================================
# КОЭФФИЦИЕНТЫ ЛОГИСТИКИ (от хаба к региону объекта)
# ============================================================

HUB_TO_REGION_COEF = {
    ("khv", "vvo"): 1.03,
    ("nsk", "vvo"): 1.06,
    ("msk", "vvo"): 1.10,
    ("vvo", "khv"): 1.03,
    ("nsk", "khv"): 1.07,
    ("msk", "khv"): 1.12,
    ("khv", "ykt"): 1.08,
    ("nsk", "ykt"): 1.12,
    ("msk", "ykt"): 1.20,
    ("kras", "nsk"): 1.02,
    ("omsk", "nsk"): 1.02,
    ("msk", "nsk"): 1.05,
    ("irk", "kras"): 1.03,
    ("nsk", "kras"): 1.03,
    ("msk", "kras"): 1.07,
    ("kras", "irk"): 1.03,
    ("nsk", "irk"): 1.05,
    ("msk", "irk"): 1.08,
    ("nsk", "omsk"): 1.02,
    ("tmn", "omsk"): 1.04,
    ("msk", "omsk"): 1.06,
    ("nsk", "tomsk"): 1.02,
    ("kras", "tomsk"): 1.04,
    ("msk", "tomsk"): 1.06,
    ("chel", "ekb"): 1.01,
    ("tmn", "ekb"): 1.02,
    ("msk", "ekb"): 1.03,
    ("ekb", "chel"): 1.01,
    ("ufa", "chel"): 1.02,
    ("msk", "chel"): 1.03,
    ("ekb", "tmn"): 1.02,
    ("chel", "tmn"): 1.02,
    ("msk", "tmn"): 1.04,
    ("ekb", "perm"): 1.02,
    ("ufa", "perm"): 1.02,
    ("msk", "perm"): 1.04,
    ("chel", "ufa"): 1.02,
    ("ekb", "ufa"): 1.02,
    ("msk", "ufa"): 1.03,
    ("nn", "kzn"): 1.01,
    ("sam", "kzn"): 1.02,
    ("msk", "kzn"): 1.03,
    ("kzn", "nn"): 1.01,
    ("msk", "nn"): 1.02,
    ("kzn", "sam"): 1.02,
    ("tlt", "sam"): 1.01,
    ("msk", "sam"): 1.03,
    ("sam", "tlt"): 1.01,
    ("kzn", "tlt"): 1.02,
    ("msk", "tlt"): 1.03,
    ("sam", "sar"): 1.02,
    ("vlg", "sar"): 1.02,
    ("msk", "sar"): 1.03,
    ("sar", "vlg"): 1.02,
    ("rnd", "vlg"): 1.02,
    ("msk", "vlg"): 1.03,
    ("msk", "vor"): 1.02,
    ("rnd", "krd"): 1.02,
    ("sochi", "krd"): 1.02,
    ("msk", "krd"): 1.04,
    ("krd", "rnd"): 1.02,
    ("vlg", "rnd"): 1.02,
    ("msk", "rnd"): 1.03,
    ("krd", "sochi"): 1.02,
    ("rnd", "sochi"): 1.02,
    ("msk", "sochi"): 1.05,
    ("msk", "spb"): 1.01,
}


# ============================================================
# МНОЖИТЕЛЬ ПО ТИПУ ТОВАРА
# ============================================================

TYPE_MULT = {
    "кабель": 1.00,
    "лоток": 1.05,
    "щит": 1.03,
    "крепёж": 1.08,
    "прочее": 1.10,
}


def get_hub_coef(from_hub, to_region, item_type="прочее"):
    """Коэффициент логистики: от хаба к региону."""
    if from_hub == to_region:
        return 1.00
    base = HUB_TO_REGION_COEF.get((from_hub, to_region), 1.15)
    type_mult = TYPE_MULT.get(item_type, 1.10)
    return round(base * type_mult, 3)


def get_hubs_for_region(region):
    """Список хабов для региона (ближний → Москва)."""
    if region == "msk":
        return ["msk"]
    return REGION_HUBS.get(region, ["msk"])


def detect_item_type(name):
    """Определяет тип товара по названию."""
    if not name:
        return "прочее"
    n = name.lower()
    if any(w in n for w in ["кабель", "ппг", "ввг", "вбш", "провод", "пугв"]):
        return "кабель"
    if any(w in n for w in ["лоток", "лотк", "угол", "крышка", "переходник", "ответвитель"]):
        return "лоток"
    if any(w in n for w in ["щит", "шкаф", "грщ", "вру", "шшр", "панель"]):
        return "щит"
    if any(w in n for w in ["болт", "гайка", "шайба", "винт", "шпильк", "хомут", "саморез", "дюбель", "крепление"]):
        return "крепёж"
    return "прочее"