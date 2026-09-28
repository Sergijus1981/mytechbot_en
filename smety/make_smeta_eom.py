"""
make_smeta_eom.py v12
Составление сметы по спецификации.

НОВОЕ в v12:
- MANUAL_PRICES: добавлены ОЗДС (держатель, пена, трубы, ПВМТ-40, кабель 2×1,5, бокс ЩРВ)
- CUSTOM_ASSEMBLY_KEYWORDS: убран "щрв" (это бокс, не щит)
- MANUAL_PRICES: ЦПИ (БПИ, БВУ, Барьер) — 0.0, запросить у поставщика

НОВОЕ в v11:
- BRAND_ALIASES: Legrand/Schneider/ABB → IEK (аналоги, ушедшие из РФ)
- get_vendor: заменяет бренд на аналог
- search_fast/search_full: fallback без бренда, если с брендом 0
"""
import re
import sys
import time
import logging
from pathlib import Path

import pandas as pd

from sources import etm, petrovich, spec_dealers
import regions as _reg

IN_XLSX = Path("spec_materials.xlsx")
OUT_XLSX = Path("smeta_eom_materials.xlsx")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("make_smeta_eom")


# ===== Бренды для строгой проверки =====
STRICT_BRANDS = {
    "дкс", "dkc",
    "iek", "иэк",
    "ekf", "екф",
    "квт", "kvt",
    "legrand", "леgrand", "ле",
    "abb", "абб",
    "schneider", "шнайдер",
    "neptun", "нептун",
    "argus", "аргус",
    "autora", "аврора",
    "bolid", "болид",
    "rubezh", "рубеж",
    "hikvision", "dahua",
}


# ===== НОВОЕ v11: аналоги брендов, ушедших из РФ =====
BRAND_ALIASES = {
    "legrand": "iek",
    "леgrand": "iek",
    "ле": "iek",
    "schneider": "iek",
    "шнайдер": "iek",
    "abb": "iek",
    "абб": "iek",
}


# ===== Признаки «заказной сборки» =====
SPECIAL_NOTES = {
    "уппв л01": "Аналог: ЦПИ УППВ 1918 М1 исп. У. Требует согласования.",
    "уо л01": "Аналог: ЦПИ УО 1918. Требует согласования.",
    "baо-300": "Уточнить у Ловител.",
    "av-04afd green": "Ориентировочная цена, требует подтверждения у дилера BAS-IP.",
    "av-04afd silver": "Ориентировочная цена, требует подтверждения у дилера BAS-IP.",
    "sp-03 black": "Ориентировочная цена, требует подтверждения у дилера BAS-IP.",
    "av-08fb": "Ориентировочная цена, требует подтверждения у дилера BAS-IP.",
    "aa-14fbst25": "Ориентировочная цена, требует подтверждения у дилера BAS-IP.",
    "am-02": "Ориентировочная цена, требует подтверждения у дилера BAS-IP.",
    "al-sa1": "Ориентировочная цена, требует подтверждения у дилера OMEGA.",
    "al-di": "Ориентировочная цена, требует подтверждения у дилера OMEGA.",
    "al-rb": "Ориентировочная цена, требует подтверждения у дилера OMEGA.",
    "al-co64": "Ориентировочная цена, требует подтверждения у дилера OMEGA.",
    "al-cb": "Ориентировочная цена, требует подтверждения у дилера OMEGA.",
    "al-z8": "Ориентировочная цена, требует подтверждения у дилера OMEGA.",
    "ckat-1200c": "Ориентировочная цена, требует подтверждения у дилера Бастион.",
    "ckat-2400": "Ориентировочная цена, требует подтверждения у дилера Бастион.",
    "dt 1207": "Ориентировочная цена, требует подтверждения у дилера Delta.",
    "dt 1212": "Ориентировочная цена, требует подтверждения у дилера Delta.",
    "sip-t19p": "Ориентировочная цена, требует подтверждения у дилера Yealink.",
    "sip-t46s": "Ориентировочная цена, требует подтверждения у дилера Yealink.",
    "tau-24m.ip-s": "Ориентировочная цена, требует подтверждения у дилера Eitex.",
    "u/utp cat6 zh нг(a)-hf 4x2x0,57": "Ориентировочная цена за метр.",
    "кспэвпнг(a)-hf 2x0,64": "Ориентировочная цена за метр.",
    "ксрэпнг(a)-frhf 2x0,64": "Ориентировочная цена за метр.",
    "кспэвпнг(a)-hf 4x0,64": "Ориентировочная цена за метр.",
}

CUSTOM_ASSEMBLY_KEYWORDS = [
    "заказная сборка", "грщ", "шшр", "вру", "впу",
    "главный распределительный", "шкаф шинный",
    "щит силовой", "щит навесной", "2щр", "1щр", "щрк",
    "распределительный щит",
]


# ===== РУЧНЫЕ ЦЕНЫ =====
MANUAL_PRICES = {
    # ===== СКС =====
    "открытая стойка 19": 35000.0,
    "стойка 19": 35000.0,
    "розетка rj45": 300.0,
    "розетка rj-45": 300.0,
    "патч-панель 19": 3500.0,
    "патч-панель": 3500.0,
    "кабельный организатор": 1200.0,
    "патч-корд utp, cat.5e, lszh, 1.0": 250.0,
    # ===== ЗАКАЗНЫЕ ЩИТЫ =====
    "главный распределительный щит": 0.0,
    "грщ7": 0.0,
    "шкаф шинный распределительный": 0.0,
    "шшр": 0.0,
    "вводная панель в полной заводской готовности": 0.0,
    "распределительная панель в полной заводской готовности": 0.0,
    # ===== ЛОТКИ =====
    "лоток перфорированный, сечением 50/50": 350.0,
    "лоток перфорированный, сечением 100/50": 450.0,
    "лоток перфорированный, сечением 200/100": 850.0,
    "лоток перфорированный, сечением 400/100": 1400.0,
    "лоток лестничный, сечением 600/100": 2200.0,
    "крышка с заземлением на лоток осн.100": 500.0,
    "крышка с заземлением на лоток осн.200": 800.0,
    "крышка с заземлением на лоток осн.400": 1400.0,
    # ===== КАБЕЛЬ ППГнг(А)-HF =====
    "ппгнг(а)-hf 1х240": 4544.0,
    "ппгнг(а)-hf 1х185": 2408.0,
    "ппгнг(а)-hf 1х120": 2499.0,
    "ппгнг(а)-hf 1х95": 1987.0,
    "ппгнг(а)-hf 1х70": 1439.0,
    "ппгнг(а)-hf 5х35": 3837.0,
    "ппгнг(а)-hf 5х25": 2810.0,
    "ппгнг(а)-hf 5х16": 1725.0,
    "ппгнг(а)-hf 5х10": 1097.0,
    "ппгнг(а)-hf 5х6": 667.0,
    "ппгнг(а)-hf 5х4": 451.0,
    "ппгнг(а)-hf 5х2,5": 287.0,
    "ппгнг(а)-hf 5х2.5": 287.0,
    "ппгнг(а)-hf 5х1,5": 184.0,
    "ппгнг(а)-hf 5х1.5": 184.0,
    "ппгнг(а)-hf 3х2,5": 164.0,
    "ппгнг(а)-hf 3х2.5": 164.0,
    "ппгнг(а)-hf 3х1,5": 109.0,
    "ппгнг(а)-hf 3х1.5": 109.0,
    "ппгнг(а)-hf 2х1,5": 184.0,
    "ппгнг(а)-hf 2х1.5": 184.0,
    "ппгнг(a)-hf 2х1,5": 184.0,
    "ппгнг(a)-hf 2х1.5": 184.0,
    "ппгнг(a)-hf 2х1,5-0,66": 184.0,
    # ===== ПВМТ-40 =====
    "провод пвмт-40": 250.0,
    "пвмт-40": 250.0,
    "пвмт": 250.0,
    # ===== ОЗДС — ЦПИ =====
    "бпи м1 д-333": 35820.0,
    "базовый блок бпи м1 д-333": 35820.0,
    "базовый блок бпи м1": 35820.0,
    "базовый блок бпи": 35820.0,
    "бву м2 д-333": 5365.0,
    "блок усиления бву м2 д-333": 5365.0,
    "блок усиления бву м2": 5365.0,
    "блок усиления бву": 5365.0,
    "мэ бз м3 д-333": 1770.0,
    "барьер бвэмэ бэ м3 д-333": 1770.0,
    "барьер бвэмэ бэ м3": 1770.0,
    "барьер бвэмэ": 1770.0,
    "барьер бвэ": 1770.0,
    # ===== ОЗДС — материалы =====
    "держатель для жестких и гофрированных труб d=16": 12.0,
    "держатель для жестких и гофрированных труб": 12.0,
    "держатель для жестких труб d=16": 12.0,
    "держатель для гофрированных труб d=16": 12.0,
    "держатель для труб d=16": 12.0,
    "гибкая гофрированная труба": 30.0,
    "труба пвх жесткая гладкая д.16мм": 76.0,
    "труба пвх жесткая гладкая": 76.0,
    "труба стальная d20": 470.0,
    "труба стальная": 470.0,
    "пена монтажная негорючая": 550.0,
    "пена монтажная": 550.0,
    "клей-герметик": 750.0,
    "высокопрочный силиконовый клей-герметик": 750.0,
    "наклейка предупреждающая": 115.0,
    "предупреждающая наклейка": 115.0,
    "саморез 4,5х40": 8.0,
    "саморез 4,5x40": 8.0,
    "саморез 4,5": 8.0,
    "бокс щрв-п": 1500.0,
    "бокс щрв-п-12": 1500.0,
    "щрв-п-12": 1500.0,
    # ===== РАДИОФИКАЦИЯ =====
    "радиорозетка": 350.0,
    "рпв-1": 350.0,
    "кабель ксрпнг(а)-frhf 1х2х0,8": 180.0,
    "ксрпнг(а)-frhf 1х2х0,8": 180.0,
    "кабель ксрпнг(а)-frhf 1х2х1,38": 220.0,
    "ксрпнг(а)-frhf 1х2х1,38": 220.0,
    "кабель ксввнг(а)-ls 1х2х0,8": 120.0,
    "ксввнг(а)-ls 1х2х0,8": 120.0,
    "кабель ксввнг(а)-ls 1х2х1,38": 160.0,
    "ксввнг(а)-ls 1х2х1,38": 160.0,
    "уппв л01": 534360.0,
    "уо л01": 300000.0,
    # ===== ЛВС / Eltex / Бастион / Picocell (2026-09-28) =====
    # ВНИМАНИЕ: ориентировочные цены, требуют подтверждения у дилеров
    "mes2424p": 85000.0,
    "mes2348p": 130000.0,
    "mes5400-24f": 600000.0,
    "mes3300-24f": 250000.0,
    "pm160-220/12": 15000.0,
    "esr-30": 50000.0,
    "wep-200l": 25000.0,
    "fh-sp851tcdl03": 15000.0,
    "e-poe/1": 15000.0,
    "skat-ups 1000 rack": 50000.0,
    "skat-ups 2000 rack": 80000.0,
    "skat-ups 3000 rack": 120000.0,
    "ap-800/2700-10/15": 25000.0,
    "ao-700/2700-4": 8000.0,
    "bs37": 50000.0,
    "profiboost 1800/2100": 80000.0,
    "молния-1": 5000.0,
    "ao-800/2100-3": 6000.0,
    "ao-900/1800/3g-m": 7000.0,
    "тау 918": 10000.0,
    # ===== СС1 / BAS-IP / OMEGA / Бастион / Yealink (2026-09-28) =====
    # ВНИМАНИЕ: ориентировочные цены, требуют подтверждения у дилеров
    # BAS-IP
    "av-04afd green": 25000.0,
    "av-04afd silver": 25000.0,
    "sp-03 black": 15000.0,
    "av-08fb": 35000.0,
    "aa-14fbst25": 8000.0,
    "am-02": 20000.0,
    # OMEGA
    "al-sa1": 20000.0,
    "al-di": 4000.0,
    "al-rb": 4000.0,
    "al-co64": 350000.0,
    "al-cb": 2500.0,
    "al-z8": 15000.0,
    # Бастион
    "ckat-1200c": 45000.0,
    "ckat-2400": 85000.0,
    # Delta
    "dt 1207": 1500.0,
    "dt 1212": 2500.0,
    # Yealink
    "sip-t19p": 7000.0,
    "sip-t46s": 25000.0,
    # Eitex
    "tau-24m.ip-s": 35000.0,
    # Паритет
    "u/utp cat6 zh нг(a)-hf 4x2x0,57": 57.0,
    "u/utp cat6 zh нг(a)-hf 4x2x0.57": 57.0,
    "кспэвпнг(a)-hf 2x0,64": 180.0,
    "кспэвпнг(a)-hf 2x0.64": 180.0,
    "ксрэпнг(a)-frhf 2x0,64": 250.0,
    "ксрэпнг(a)-frhf 2x0.64": 250.0,
    "кспэвпнг(a)-hf 4x0,64": 350.0,
    "кспэвпнг(a)-hf 4x0.64": 350.0,
        # ===== СВН / Hikvision / Seagate / Acer / Logitech (2026-09-28) =====
    "ds-2cd7a26g0/p-izhs": 70000.0,
    "автоматизированное рабочее место оператора": 150000.0,
    "ds-2cd7a26g0": 70000.0,
    "ids-2cd7a26g0-izhs": 66000.0,
    "ids-2cd7a26g0": 66000.0,
    "ds-2cd3726gt-izs": 36500.0,
    "ds-2cd3726gt": 36500.0,
    "ds-8664ni-i8": 146000.0,
    "ds-a806245": 480000.0,
    "st6000dm003": 21000.0,
    "st6000dm004": 35000.0,
    "df24n1s": 13000.0,
    "d421e": 7000.0,
    "mk220": 2000.0,
    "e-poe/1": 4800.0,
    "sb1-2-8р8с-c6-wh2": 800.0,
    "hikcentral access control": 3500.0,
    "hikcentral-p-anpr-1ch": 15000.0,
    "ds-1260zj": 900.0,
    "ds-1280zj-s": 1700.0,
    "cp660": 4000.0,
    "pp6u-1m/g": 135.0,
    # ===== Parsec =====
        # ===== СКУД (2026-09-28) =====
    "индукционная петля": 5000.0,
    "parsecnet 3": 150000.0,
    "parsecnet 3 (pro)": 150000.0,
    "esmart reader oem": 14000.0,
    "esmart reader серии oem": 14000.0,
    "esmart® reader серии oem": 14000.0,
    "nc-8000": 39576,
    "pr-x18": 23400,
    "er1602": 21500,
    "st-lr321": 60002,
    "sma2": 34750,
    "st-rb002pd": 2146,
}


def is_custom_assembly(name):
    if not name:
        return False
    n = name.lower()
    return any(w in n for w in CUSTOM_ASSEMBLY_KEYWORDS)


def normalize_cable(name):
    m = re.search(
        r"(ППГнг\s*\(?[АA]?\)?\s*-?\s*HF)\s*(\d+)\s*[хx]\s*(\d+)[,.]?(\d*)",
        name, re.IGNORECASE
    )
    if not m:
        return []
    mark = re.sub(r"\s+", "", m.group(1))
    cores = m.group(2)
    sec_int = m.group(3)
    sec_dec = m.group(4) or ""
    section = f"{sec_int}.{sec_dec}" if sec_dec else sec_int
    section_ru = f"{sec_int},{sec_dec}" if sec_dec else sec_int

    return [
        f"{mark} {cores}х{section}",
        f"{mark} {cores}х{section_ru}",
        f"{mark} {cores}х{section}ок",
    ]


def extract_keywords(name, model, code):
    keywords = []

    if code and str(code).lower() not in ("nan", ""):
        c_clean = re.sub(r"\s+", "", str(code).strip())
        if len(c_clean) >= 3:
            keywords.append(c_clean)

    model_str = ""
    if model and str(model).lower() not in ("nan", ""):
        m = str(model).strip()
        if not re.match(r"^(ГОСТ|DIN|ТУ)\s", m, re.IGNORECASE):
            if len(m) >= 3:
                model_str = m
                keywords.append(m)

    keywords.extend(normalize_cable(name))

    for m in re.findall(r"\b[A-Za-z]{2,6}-\d{4,}\b", name):
        keywords.append(m.strip())

    name_lower = name.lower()
    type_words = [
        ("розетка", "розетка"), ("выключатель", "выключатель"),
        ("переключатель", "переключатель"), ("светильник", "светильник"),
        ("люстра", "люстра"), ("датчик", "датчик"),
        ("контроллер", "контроллер"), ("извещатель", "извещатель"),
        ("оповещатель", "оповещатель"), ("табло", "табло"),
        ("сирена", "сирена"), ("прибор", "прибор"),
        ("панель", "панель"), ("блок", "блок"),
        ("кабель", "кабель"), ("провод", "провод"),
        ("автомат", "автомат"), ("счетчик", "счетчик"),
        ("трансформатор", "трансформатор"), ("ограничитель", "ограничитель"),
        ("лючок", "лючок"), ("лента", "лента"), ("муфта", "муфта"),
        ("щит", "щит"), ("шкаф", "шкаф"), ("труба", "труба"),
        ("лоток", "лоток"), ("короб", "короб"), ("коробка", "коробка"),
        ("наконечник", "наконечник"), ("полоса", "полоса"),
        ("уголок", "уголок"), ("шпилька", "шпилька"),
        ("болт", "болт"), ("гайка", "гайка"), ("шайба", "шайба"),
        ("саморез", "саморез"), ("дюбель", "дюбель"),
        ("пена", "пена"), ("кожух", "кожух"), ("скоба", "скоба"),
        ("аккумулятор", "аккумулятор"), ("батарея", "батарея"),
        ("держатель", "держатель"),
    ]
    device_type = None
    for tw, canonical in type_words:
        if tw in name_lower:
            device_type = canonical
            break

    extras = []
    for e in ["IP44", "IP22", "IP20", "IP31", "IP54", "IP56", "IP67"]:
        if e.lower() in name_lower:
            extras.append(e)
    for e in ["трехфазная", "проходной", "двухклавишный", "одноклавишный",
              "влагостойкая", "двойная", "TV", "интернет", "напольный",
              "огнестойкий", "силовой", "низкотоксичный",
              "радиоканальный", "адресный", "дымовой", "тепловой",
              "ручной", "звуковой", "речевой", "световой"]:
        if e.lower() in name_lower:
            extras.append(e)

    if device_type:
        combined = device_type
        if model_str:
            combined += " " + model_str
        if extras:
            combined += " " + " ".join(extras[:2])
        full_name = name.strip()[:60]
        if full_name and full_name.lower() != combined.lower():
            keywords.insert(0, full_name)
        keywords.insert(1, combined)

    seen = set()
    out = []
    for k in keywords:
        kl = k.lower().replace("-", "").replace(" ", "")
        if kl in seen or len(kl) < 3:
            continue
        seen.add(kl)
        out.append(k)
    return out[:6]


def get_vendor(vendor_raw):
    """Возвращает бренд из STRICT_BRANDS, заменяя на аналог через BRAND_ALIASES."""
    if pd.isna(vendor_raw):
        return None
    v = str(vendor_raw).strip().strip('"').strip("'").strip()
    if not v or v.lower() in ("nan", "none", "null"):
        return None
    if len(v) > 30:
        return None
    v_norm = re.sub(r"[\s\-_\.\(\)\"']", "", v.lower())
    if v_norm not in STRICT_BRANDS:
        return None
    return BRAND_ALIASES.get(v_norm, v)


def _get_region():
    try:
        import parse_spec
        return getattr(parse_spec, "CURRENT_REGION", "msk")
    except Exception:
        return "msk"


def search_with_hubs(query, keywords, expected_brand=None, item_type="прочее"):
    """
    Ищет цену по цепочке хабов:
    1. MANUAL_PRICES (приоритет)
    2. Регион объекта
    3. Ближний хаб → средний → Москва
    """
    import regions as _reg

    # === 1. MANUAL_PRICES ===
    _mk = None
    _all = (str(query) + " " + str(keywords)).lower()
    for _k in MANUAL_PRICES:
        if _k in _all:
            _mk = _k
            break
    if _mk:
        _p = MANUAL_PRICES[_mk]
        if _p == 0.0:
            return {"found": False, "reason": "заказная сборка"}
        return {
            "found": True,
            "source": "Ручная",
            "name": str(query) + " (ручная цена)",
            "price": MANUAL_PRICES[_mk],
            "url": "",
            "region_used": "msk",
            "coef": 1.00,
            "note": SPECIAL_NOTES.get(_mk, "проверенная цена"),
            "manual_key": _mk,
        }

    # === 2. Регион объекта ===
    region_obj = _get_region()
    hubs = _reg.get_hubs_for_region(region_obj)

    r = etm.find_best(query, keywords=keywords, expected_brand=expected_brand, min_price=100, region=region_obj)
    if r.get("found"):
        r["region_used"] = region_obj
        r["coef"] = 1.00
        r["note"] = "местный"
        return r

    # === 3. Хабы ===
    for hub in hubs:
        if hub == region_obj:
            continue
        r = etm.find_best(query, keywords=keywords, expected_brand=expected_brand, min_price=100, region=hub)
        if r.get("found"):
            coef = _reg.get_hub_coef(hub, region_obj, item_type)
            r["price"] = round(r["price"] * coef, 2)
            r["region_used"] = hub
            r["coef"] = coef
            r["source"] = "ЭТМ"
            r["note"] = _reg.region_name(hub) + " + доставка (×" + str(coef) + ")"
            return r

    return {"found": False}


def search_fast(query, keywords, expected_brand=None):
    results = []
    try:
        r = etm.find_best(query, keywords=keywords, expected_brand=expected_brand, min_price=100, region=_get_region())
        if r.get("found"):
            results.append({"source": "ЭТМ", **r})
    except Exception as e:
        log.warning("ЭТМ: %s", e)

    if not results and expected_brand:
        try:
            log.info("    → fallback без бренда")
            r = etm.find_best(query, keywords=keywords, expected_brand=None, min_price=100, region=_get_region())
            if r.get("found"):
                results.append({"source": "ЭТМ", **r})
        except Exception as e:
            log.warning("ЭТМ (fallback): %s", e)

    return results


def search_full(query, keywords, expected_brand=None):
    results = []

    try:
        r = etm.find_best(query, keywords=keywords, expected_brand=expected_brand, min_price=100, region=_get_region())
        if r.get("found"):
            results.append({"source": "ЭТМ", **r})
    except Exception as e:
        log.warning("ЭТМ: %s", e)

    if not results and expected_brand:
        try:
            log.info("    → fallback без бренда")
            r = etm.find_best(query, keywords=keywords, expected_brand=None, min_price=100, region=_get_region())
            if r.get("found"):
                results.append({"source": "ЭТМ", **r})
        except Exception as e:
            log.warning("ЭТМ (fallback): %s", e)

    try:
        r = petrovich.find_best(query, keywords=keywords)
        if r.get("found"):
            results.append({"source": "Петрович", **r})
    except Exception as e:
        log.warning("Петрович: %s", e)

    try:
        spec_query = keywords[0] if keywords else query
        res = spec_dealers.find_prices(spec_query, keywords=keywords)
        for r in res[:1]:
            results.append({
                "source": r.get("dealer", "Дилер"),
                "name": r.get("name", ""),
                "price": r.get("price"),
                "url": r.get("url", ""),
            })
    except Exception as e:
        log.warning("spec_dealers: %s", e)

    return results


def pick_price(results):
    if not results:
        return None, None, None
    prices = sorted([r["price"] for r in results if r.get("price")])
    if not prices:
        return None, None, None
    if len(prices) == 1:
        chosen = prices[0]
    elif len(prices) == 2:
        chosen = prices[0]
    else:
        chosen = prices[1]
    for r in results:
        if abs(r["price"] - chosen) < 0.01:
            return chosen, r.get("source", ""), r.get("url", "")
    return chosen, results[0]["source"], results[0].get("url", "")


def main():
    fast = "--fast" in sys.argv
    limit = None
    for i, arg in enumerate(sys.argv):
        if arg.startswith("--limit"):
            try:
                limit = int(arg.split("=")[1]) if "=" in arg else int(sys.argv[i + 1])
            except (IndexError, ValueError):
                pass

    if not IN_XLSX.exists():
        log.error("Нет файла: %s", IN_XLSX)
        return

    log.info("Читаю: %s", IN_XLSX)
    df = pd.read_excel(IN_XLSX, dtype={"Позиция": str, "Код": str})
    log.info("Позиций в спецификации: %d", len(df))
    log.info("Режим: %s", "FAST (только ЭТМ)" if fast else "FULL (все источники)")
    if limit:
        df = df.head(limit)
        log.info("Ограничение: первые %d позиций", limit)

    rows = []
    found = 0
    total_sum = 0.0

    for i, r in df.iterrows():
        pos = str(r["Позиция"])
        name = str(r["Наименование"])
        model = str(r["Тип/марка"]) if pd.notna(r["Тип/марка"]) else ""
        code = str(r["Код"]) if pd.notna(r["Код"]) else ""
        unit = str(r["Ед."]) if pd.notna(r["Ед."]) else ""
        qty = r["Кол-во"] if pd.notna(r["Кол-во"]) else None
        section = r["Раздел"] if pd.notna(r["Раздел"]) else ""
        vendor_raw = r["Завод"]
        expected_brand = get_vendor(vendor_raw)

        log.info("[%s] %s | %s | %s %s", pos, name[:60], model[:20], qty, unit)

        if qty is None or not unit:
            log.info("    → пропуск (нет кол-ва или ед.)")
            rows.append({
                "Позиция": pos, "Раздел": section,
                "Наименование": name, "Тип/марка": model, "Код": code,
                "Завод": vendor_raw if pd.notna(vendor_raw) else "",
                "Ед.": unit, "Кол-во": qty,
                "Цена ед., руб": None, "Сумма, руб": None,
                "Источник": "", "Ссылка": "", "Статус": "заголовок раздела",
            })
            continue

        if is_custom_assembly(name):
            log.info("    → заказная сборка, пропуск")
            rows.append({
                "Позиция": pos, "Раздел": section,
                "Наименование": name, "Тип/марка": model, "Код": code,
                "Завод": vendor_raw if pd.notna(vendor_raw) else "",
                "Ед.": unit, "Кол-во": qty,
                "Цена ед., руб": None, "Сумма, руб": None,
                "Источник": "", "Ссылка": "", "Статус": "заказная сборка",
            })
            continue

        keywords = extract_keywords(name, model, code)
        if keywords:
            log.info("    ключи: %s", keywords)

        if expected_brand:
            log.info("    бренд (строго): %s", expected_brand)

        _item_type = _reg.detect_item_type(name)
        _r = search_with_hubs(name, keywords, expected_brand=expected_brand, item_type=_item_type)
        results = [_r] if _r.get("found") else []
        log.info("    найдено: %d", len(results))

        price, source, url = pick_price(results)
        if price:
            found += 1
            total_sum += price * qty
            log.info("    цена: %s ₽ (%s)", price, source)
            status = "ok"
        else:
            log.info("    цена: не найдено")
            status = "нет цены"

        _r_region = ""
        _r_coef = 1.00
        _r_note = ""
        if results and isinstance(results[0], dict):
            _r_region = results[0].get("region_used", "")
            _r_coef = results[0].get("coef", 1.00)
            _r_note = results[0].get("note", "")

        rows.append({
            "Позиция": pos, "Раздел": section,
            "Наименование": name, "Тип/марка": model, "Код": code,
            "Завод": vendor_raw if pd.notna(vendor_raw) else "",
            "Ед.": unit, "Кол-во": qty,
            "Цена ед., руб": price,
            "Сумма, руб": round(price * qty, 2) if price else None,
            "Источник": source or "",
            "Регион цены": _reg.region_name(_r_region) if _r_region else "",
            "Коэф.": _r_coef,
            "Примечание": _r_note,
            "Ссылка": url or "",
            "Статус": status,
        })

        time.sleep(0.3)

    rows.append({
        "Позиция": "", "Раздел": "ИТОГО", "Наименование": "",
        "Тип/марка": "", "Код": "", "Завод": "", "Ед.": "", "Кол-во": "",
        "Цена ед., руб": "", "Сумма, руб": round(total_sum, 2),
        "Источник": "", "Ссылка": "", "Статус": "",
    })

    out = pd.DataFrame(rows)
    out.to_excel(OUT_XLSX, index=False)
    log.info("Сохранено: %s", OUT_XLSX.resolve())
    log.info("Найдено цен: %d", found)
    log.info("Итого материалов: %.2f руб", total_sum)


if __name__ == "__main__":
    main()