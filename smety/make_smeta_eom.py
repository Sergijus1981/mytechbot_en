"""
make_smeta_eom.py v8
Составление сметы по спецификации ЭОМ.
- Бренд проверяется ТОЛЬКО для известных брендов (ДКС, IEK, EKF, КВТ).
- Для остальных (Электрокабель, Северная Аврора, АЛЮР) — ищем аналог.
"""
import re
import sys
import time
import logging
from pathlib import Path

import pandas as pd

from sources import etm, petrovich, spec_dealers

IN_XLSX = Path("spec_materials.xlsx")
OUT_XLSX = Path("smeta_eom_materials.xlsx")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("make_smeta_eom")

SKIP_SECTIONS = {"Электрощитовое оборудование"}

# строгие бренды — только для них проверяем совпадение
STRICT_BRANDS = {
    "дкс", "dkc",
    "iek", "иэк",
    "ekf", "екф",
    "квт", "kvt",
}


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

    if model and str(model).lower() not in ("nan", ""):
        m = str(model).strip()
        if not re.match(r"^(ГОСТ|DIN|ТУ)\s", m, re.IGNORECASE):
            if len(m) >= 3:
                keywords.append(m)

    keywords.extend(normalize_cable(name))

    for m in re.findall(r"\b[A-Za-z]{2,6}-\d{4,}\b", name):
        keywords.append(m.strip())

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
    """
    Возвращает бренд ТОЛЬКО если он из STRICT_BRANDS.
    Для остальных — None (не проверяем бренд, ищем аналог).
    """
    if pd.isna(vendor_raw):
        return None
    v = str(vendor_raw).strip().strip('"').strip("'").strip()
    if not v or v.lower() in ("nan", "none", "null"):
        return None
    if len(v) > 25:
        return None
    v_norm = re.sub(r"[\s\-_\.\(\)\"']", "", v.lower())
    if v_norm not in STRICT_BRANDS:
        return None
    return v


def search_fast(query, keywords, expected_brand=None):
    results = []
    try:
        r = etm.find_best(query, keywords=keywords, expected_brand=expected_brand)
        if r.get("found"):
            results.append({"source": "ЭТМ", **r})
    except Exception as e:
        log.warning("ЭТМ: %s", e)
    return results


def search_full(query, keywords, expected_brand=None):
    results = []

    try:
        r = etm.find_best(query, keywords=keywords, expected_brand=expected_brand)
        if r.get("found"):
            results.append({"source": "ЭТМ", **r})
    except Exception as e:
        log.warning("ЭТМ: %s", e)

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
            return chosen, r["source"], r.get("url", "")
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

        log.info("[%s] %s | %s | %s %s",
                 pos, name[:60], model[:20], qty, unit)

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

        if section in SKIP_SECTIONS:
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

        results = search_fast(name, keywords, expected_brand=expected_brand) if fast \
            else search_full(name, keywords, expected_brand=expected_brand)
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

        rows.append({
            "Позиция": pos, "Раздел": section,
            "Наименование": name, "Тип/марка": model, "Код": code,
            "Завод": vendor_raw if pd.notna(vendor_raw) else "",
            "Ед.": unit, "Кол-во": qty,
            "Цена ед., руб": price,
            "Сумма, руб": round(price * qty, 2) if price else None,
            "Источник": source or "", "Ссылка": url or "",
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