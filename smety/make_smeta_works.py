"""
make_smeta_works.py v9
Расчёт работ по спецификации.
- Захардкоженные цены (кабели, лотки, щиты, муфты) — для ЭОМ 2.3
- НОВОЕ: WORKS_PRICES — расценки по ключевым словам для любых позиций
- Монтаж розеток, выключателей, светильников, извещателей, оповещателей
"""
import re
from prices_aps import get_montage_price as aps_montage, get_pnr_price as aps_pnr, get_cable_price as aps_cable
from prices_skud import get_skud_price as skud_price, get_turniket_price as turniket_price, get_barrier_price as barrier_price, get_video_price as video_price, get_cable_price as skud_cable
import logging
from pathlib import Path

import pandas as pd

IN_XLSX = Path("smeta_eom_materials.xlsx")
OUT_XLSX = Path("smeta_eom_full.xlsx")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("make_smeta_works")


MARKUP_MATERIALS = 0.20
MARKUP_WORKS = 0.15

COEF_HEIGHT = 1.0  # высота (от 3 м) — не учтено
COEF_ACTIVE = 1.0  # стеснённые условия — не учтено
COEF_NIGHT = 1.0  # ночь — не учтено
COEF_TOTAL = COEF_HEIGHT * COEF_ACTIVE * COEF_NIGHT

VAT = 0.20
COEF_TURNS = 0.07
FEE_CABLE_TERMINATION = 150_000


# ===== Захардкоженные цены (для ЭОМ 2.3) =====
CABLE_PRICES = {
    "1х240": 585, "1х185": 530, "1х120": 530, "1х95": 530, "1х70": 365,
    "5х35": 255, "5х25": 255, "5х16": 190, "5х10": 127, "5х6": 127,
    "5х4": 127, "5х2,5": 127, "5х1,5": 110,
    "3х2,5": 110, "3х1,5": 110,
}

TRAY_PRICES = {
    "50/50": 265.65, "100/50": 265.65,
    "200/100": 1143.45, "400/100": 1143.45,
    "600/100": 1279.74,
}

PANEL_PRICES = {
    "ГРЩ7": 30000, "ШШР": 30000,
    "2ЩР11": 6000,
    "2ЩРК1": 4500, "2ЩРК2": 4500, "2ЩРК3": 4500,
    "2ЩРВ2": 4500, "2ЩРВ3": 4500, "2ЩРВ4": 4500,
    "2ЩРВ5": 4500, "2ЩРВ6": 4500, "2ЩРВ7": 4500,
    "1ЩРВ8": 4500,
}

COUPLING_PRICES = {
    "150/240": 2500, "70/120": 2000, "35/50": 1500,
}

PULL_PRICE = 70


# ===== НОВОЕ: расценки по ключевым словам =====
def normalize_key(name):
    """Нормализует название работы → ключ для базы."""
    import re
    n = str(name).lower()
    n = re.sub(r"[\s\-_.,\(\)\"']", "", n)
    return n


def find_in_db(work_name, region):
    """
    Ищет цену работы в prices_works.db по региону.
    Возвращает (price, unit, source) или None.
    """
    import sqlite3
    try:
        conn = sqlite3.connect("prices_works.db")
        cur = conn.cursor()
        key = normalize_key(work_name)
        # 1. Точное совпадение
        cur.execute("""
            SELECT price, unit, source FROM prices
            WHERE work_key = ? AND region = ?
            LIMIT 1
        """, (key, region))
        row = cur.fetchone()
        if row:
            conn.close()
            return row
        # 2. По подстроке (длинные ключи — приоритет)
        cur.execute("""
            SELECT price, unit, source FROM prices
            WHERE ? LIKE '%' || work_key || '%' AND region = ?
            ORDER BY LENGTH(work_key) DESC
            LIMIT 1
        """, (key, region))
        row = cur.fetchone()
        conn.close()
        return row
    except Exception:
        return None


WORKS_PRICES = [
    # ===== КАБЕЛЬ (вторая с конца) =====
    ("5х240", 640, "Прокладка кабеля 5х240"),
    ("5х185", 220, "Прокладка кабеля 5х185"),
    ("5х150", 480, "Прокладка кабеля 5х150"),
    ("5х120", 480, "Прокладка кабеля 5х120"),
    ("5х95", 400, "Прокладка кабеля 5х95"),
    ("5х50", 320, "Прокладка кабеля 5х50"),
    ("5х35", 220, "Прокладка кабеля 5х35"),
    ("5х25", 135, "Прокладка кабеля 5х25"),
    ("5х16", 190, "Прокладка кабеля 5х16"),
    ("5х10", 150, "Прокладка кабеля 5х10"),
    ("5х6", 80, "Прокладка кабеля 5х6"),
    ("5х4", 150, "Прокладка кабеля 5х4"),
    ("5х2,5", 100, "Прокладка кабеля 5х2,5"),
    ("5х1,5", 100, "Прокладка кабеля 5х1,5"),
    ("3х2,5", 90, "Прокладка кабеля 3х2,5"),
    ("3х1,5", 70, "Прокладка кабеля 3х1,5"),
    # ===== ЛОТКИ =====
    ("лоток 600/100", 894, "Монтаж лотка 600/100"),
    ("лоток 400/100", 480, "Монтаж лотка 400/100"),
    ("лоток 200/100", 320, "Монтаж лотка 200/100"),
    ("лоток 100/50", 280, "Монтаж лотка 100/50"),
    ("лоток 50/50", 190, "Монтаж лотка 50/50"),
    ("крышка лотка 400", 65, "Установка крышки 400"),
    ("крышка лотка 200", 65, "Установка крышки 200"),
    ("угол лотка 400", 120, "Угол лотка 400"),
    ("угол лотка 200", 95, "Угол лотка 200"),
    ("кронштейн лотка 400", 95, "Кронштейн 400"),
    ("кронштейн лотка 200", 75, "Кронштейн 200"),
    # ===== МУФТЫ =====
    ("муфта 240", 5755, "Монтаж концевой муфты 240"),
    ("муфта 150", 4755, "Монтаж концевой муфты 150"),
    ("муфта 95", 3755, "Монтаж концевой муфты 95"),
    # ===== ЩИТЫ =====
    ("главный распределительный", 300000, "Монтаж ГРЩ (с ПНР)"),
    ("грщ", 300000, "Монтаж ГРЩ (с ПНР)"),
    ("шкаф шинный", 150000, "Монтаж ШШР"),
    ("шшр", 150000, "Монтаж ШШР"),
    ("вру", 250000, "Монтаж ВРУ"),
    ("щит силовой", 10000, "Монтаж щита силового"),
    ("щит навесной", 10000, "Монтаж щита навесного"),
    ("щр", 10000, "Монтаж щита распределительного"),
    # ===== РОЗЕТКИ, ВЫКЛЮЧАТЕЛИ =====
    ("розетк", 288, "Монтаж розетки"),
    ("выключател", 265, "Монтаж выключателя"),
    # ===== СВЕТИЛЬНИКИ =====
    ("светильник", 1250, "Монтаж светильника"),
    ("люстра", 2500, "Монтаж люстры"),
    # ===== ПРОЧЕЕ =====
    ("труба", 55, "Прокладка трубы"),
    ("кабель", 150, "Прокладка кабеля"),
    ("шпилька", 55, "Монтаж шпильки"),
    ("болт", 5, "Монтаж болта"),
]

def find_work_price(name):
    """Ищет расценку по ключевому слову в наименовании."""
    if not name:
        return None, None
    n = name.lower()

    # === 1. АПС / СОУЭ ===
    p = aps_montage(name)
    if p:
        return p, "АПС: монтаж"
    p = aps_pnr(name)
    if p:
        return p, "АПС: ПНР"

    # === 2. СКУД ===
    p = skud_price(name)
    if p:
        return p, "СКУД: монтаж"
    p = turniket_price(name)
    if p:
        return p, "СКУД: турникет"
    p = barrier_price(name)
    if p:
        return p, "СКУД: шлагбаум"
    p = video_price(name)
    if p:
        return p, "СКУД: видео"

    # === 3. WORKS_PRICES (приоритет для ЭОМ) ===
    for key, price, work_name in WORKS_PRICES:
        if key in n:
            return price, work_name

    # === 4. БАЗА prices_works.db (fallback) ===
    try:
        import parse_spec
        region = getattr(parse_spec, "CURRENT_REGION", "msk")
    except Exception:
        region = "msk"
    db = find_in_db(name, region)
    if db:
        price, unit, source = db
        return price, f"{source} ({region})"

    return None, None


def parse_cable_section(name):
    m = re.search(r"(\d+)\s*[хx]\s*(\d+)(?:[,.](\d+))?", name)
    if not m:
        return None
    cores = m.group(1)
    sec = m.group(2) + ("," + m.group(3) if m.group(3) else "")
    return f"{cores}х{sec}"


def parse_tray_section(name):
    m = re.search(r"(\d+)\s*/\s*(\d+)", name)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return None


def calc_works(df):
    works = []
    used_pos = set()

    # 1. Захардкоженные работы (приоритет)
    for _, r in df.iterrows():
        pos = str(r["Позиция"])
        name = str(r["Наименование"])
        model = str(r["Тип/марка"]) if pd.notna(r["Тип/марка"]) else ""
        qty = r["Кол-во"] if pd.notna(r["Кол-во"]) else None
        section = r["Раздел"] if pd.notna(r["Раздел"]) else ""

        if qty is None:
            continue

        added = False

        if section == "Кабельная продукция" and name.startswith("ППГ"):
            sec = parse_cable_section(name)
            if sec and sec in CABLE_PRICES:
                rate = CABLE_PRICES[sec]
                works.append({
                    "Позиция": pos, "Работа": f"Прокладка кабеля {sec}",
                    "Ед.": "м", "Объём": qty,
                    "Расценка, руб": rate, "Сумма, руб": round(rate * qty, 2),
                })
                used_pos.add(pos)
                added = True

        elif section == "Кабеленесущая продукция" and "лоток" in name.lower():
            sec = parse_tray_section(name)
            if sec and sec in TRAY_PRICES:
                rate = TRAY_PRICES[sec]
                works.append({
                    "Позиция": pos, "Работа": f"Монтаж лотка {sec}",
                    "Ед.": "м", "Объём": qty,
                    "Расценка, руб": rate, "Сумма, руб": round(rate * qty, 2),
                })
                used_pos.add(pos)
                added = True

        elif section == "Щитовое оборудование":
            m = model.strip()
            if m in PANEL_PRICES:
                rate = PANEL_PRICES[m]
                works.append({
                    "Позиция": pos, "Работа": f"Монтаж щита {m}",
                    "Ед.": "шт", "Объём": qty,
                    "Расценка, руб": rate, "Сумма, руб": round(rate * qty, 2),
                })
                used_pos.add(pos)
                added = True

        elif "муфта кабельная" in name.lower():
            for key, rate in COUPLING_PRICES.items():
                if key in name:
                    works.append({
                        "Позиция": pos, "Работа": f"Монтаж муфты {key}",
                        "Ед.": "шт", "Объём": qty,
                        "Расценка, руб": rate, "Сумма, руб": round(rate * qty, 2),
                    })
                    used_pos.add(pos)
                    added = True
                    break

        # Если не добавили захардкоженное — пробуем WORKS_PRICES
        if not added:
            rate, work_name = find_work_price(name)
            if rate and work_name:
                works.append({
                    "Позиция": pos, "Работа": work_name,
                    "Ед.": r["Ед."] if pd.notna(r["Ед."]) else "шт",
                    "Объём": qty,
                    "Расценка, руб": rate, "Сумма, руб": round(rate * qty, 2),
                })

    return works


def main():
    if not IN_XLSX.exists():
        log.error("Нет файла: %s", IN_XLSX)
        return

    log.info("Читаю: %s", IN_XLSX)
    df = pd.read_excel(IN_XLSX, dtype={"Позиция": str, "Код": str})
    log.info("Позиций: %d", len(df))

    df_no_total = df[df["Раздел"] != "ИТОГО"]
    if "Сумма, руб" in df_no_total.columns:
        m = pd.to_numeric(df_no_total["Сумма, руб"], errors="coerce").fillna(0)
        materials_total = float(m.sum())
    else:
        materials_total = 0.0

    log.info("Материалы (без наценки): %.2f руб", materials_total)

    works = calc_works(df_no_total)
    log.info("Найдено работ: %d", len(works))
    works_base = sum(w["Сумма, руб"] for w in works)
    log.info("Работы (база): %.2f руб", works_base)

    works_with_coef = works_base * COEF_TOTAL
    turns_amount = works_with_coef * COEF_TURNS
    works_with_turns = works_with_coef + turns_amount
    works_with_termination = works_with_turns + FEE_CABLE_TERMINATION
    works_markup = works_with_termination * MARKUP_WORKS
    works_total = works_with_termination + works_markup

    materials_markup = materials_total * MARKUP_MATERIALS
    materials_with_markup = materials_total + materials_markup

    subtotal = materials_with_markup + works_total
    vat_amount = subtotal * VAT
    grand_total = subtotal + vat_amount

    log.info("Материалы с наценкой: %.2f", materials_with_markup)
    log.info("Работы с наценкой: %.2f", works_total)
    log.info("Подытог: %.2f", subtotal)
    log.info("НДС 20%%: %.2f", vat_amount)
    log.info("=== ВСЕГО С НДС: %.2f ===", grand_total)

    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        materials_rows = []
        for _, r in df.iterrows():
            materials_rows.append({
                "Позиция": r["Позиция"], "Раздел": r["Раздел"],
                "Наименование": r["Наименование"], "Ед.": r["Ед."],
                "Кол-во": r["Кол-во"],
                "Цена ед., руб": r["Цена ед., руб"] if "Цена ед., руб" in r else "",
                "Сумма, руб": r["Сумма, руб"] if "Сумма, руб" in r else "",
                "Источник": r.get("Источник", ""),
                "Статус": r.get("Статус", ""),
            })
        materials_rows.append({
            "Позиция": "", "Раздел": "ИТОГО материалы (без наценки)",
            "Наименование": "", "Ед.": "", "Кол-во": "",
            "Цена ед., руб": "", "Сумма, руб": round(materials_total, 2),
            "Источник": "", "Статус": "",
        })
        materials_rows.append({
            "Позиция": "", "Раздел": "Наценка на материалы 20%",
            "Наименование": "", "Ед.": "", "Кол-во": "",
            "Цена ед., руб": "", "Сумма, руб": round(materials_markup, 2),
            "Источник": "", "Статус": "",
        })
        materials_rows.append({
            "Позиция": "", "Раздел": "ИТОГО материалы с наценкой",
            "Наименование": "", "Ед.": "", "Кол-во": "",
            "Цена ед., руб": "", "Сумма, руб": round(materials_with_markup, 2),
            "Источник": "", "Статус": "",
        })
        pd.DataFrame(materials_rows).to_excel(writer, sheet_name="Материалы", index=False)

        works_rows = list(works)
        works_rows.append({
            "Позиция": "", "Работа": "ИТОГО работы (база)",
            "Ед.": "", "Объём": "", "Расценка, руб": "",
            "Сумма, руб": round(works_base, 2),
        })
        works_rows.append({
            "Позиция": "", "Работа": f"× Коэффициент условий ({COEF_TOTAL:.3f})",
            "Ед.": "", "Объём": "", "Расценка, руб": "",
            "Сумма, руб": round(works_with_coef, 2),
        })
        works_rows.append({
            "Позиция": "", "Работа": f"+ Повороты ({int(COEF_TURNS*100)}%)",
            "Ед.": "", "Объём": "", "Расценка, руб": "",
            "Сумма, руб": round(works_with_turns, 2),
        })
        works_rows.append({
            "Позиция": "", "Работа": "+ Оконечка кабелей (укрупнённо)",
            "Ед.": "", "Объём": "", "Расценка, руб": "",
            "Сумма, руб": round(works_with_termination, 2),
        })
        works_rows.append({
            "Позиция": "", "Работа": "Наценка на работы 15%",
            "Ед.": "", "Объём": "", "Расценка, руб": "",
            "Сумма, руб": round(works_markup, 2),
        })
        works_rows.append({
            "Позиция": "", "Работа": "ИТОГО работы с наценкой",
            "Ед.": "", "Объём": "", "Расценка, руб": "",
            "Сумма, руб": round(works_total, 2),
        })
        pd.DataFrame(works_rows).to_excel(writer, sheet_name="Работы", index=False)

        summary_rows = [
            {"Статья": "МАТЕРИАЛЫ", "Сумма, руб": ""},
            {"Статья": "Материалы (без наценки)", "Сумма, руб": round(materials_total, 2)},
            {"Статья": "Наценка на материалы (20%)", "Сумма, руб": round(materials_markup, 2)},
            {"Статья": "Итого материалы", "Сумма, руб": round(materials_with_markup, 2)},
            {"Статья": "", "Сумма, руб": ""},
            {"Статья": "РАБОТЫ", "Сумма, руб": ""},
            {"Статья": "Работы (база)", "Сумма, руб": round(works_base, 2)},
            {"Статья": f"Коэффициенты условий (×{COEF_TOTAL:.3f})", "Сумма, руб": round(works_with_coef, 2)},
            {"Статья": f"Повороты (+{int(COEF_TURNS*100)}%)", "Сумма, руб": round(works_with_turns, 2)},
            {"Статья": "Оконечка кабелей (укрупнённо)", "Сумма, руб": round(FEE_CABLE_TERMINATION, 2)},
            {"Статья": "Итого работы (до наценки)", "Сумма, руб": round(works_with_termination, 2)},
            {"Статья": "Наценка на работы (15%)", "Сумма, руб": round(works_markup, 2)},
            {"Статья": "Итого работы", "Сумма, руб": round(works_total, 2)},
            {"Статья": "", "Сумма, руб": ""},
            {"Статья": "ИТОГО ПО СМЕТЕ", "Сумма, руб": ""},
            {"Статья": "Материалы + Работы (подытог)", "Сумма, руб": round(subtotal, 2)},
            {"Статья": "НДС 20%", "Сумма, руб": round(vat_amount, 2)},
            {"Статья": "=== ВСЕГО С НДС ===", "Сумма, руб": round(grand_total, 2)},
            {"Статья": "", "Сумма, руб": ""},
            {"Статья": "ПРИМЕЧАНИЕ", "Сумма, руб": ""},
            {"Статья": "Работы рассчитаны по базовым расценкам БЕЗ учёта высотных работ (от 3 м) и ночного времени.", "Сумма, руб": ""},
            {"Статья": "При необходимости применяются коэффициенты: высота 3-5 м — ×1.3; высота 5+ м — ×2.0; ночь — ×1.5.", "Сумма, руб": ""},
            {"Статья": "Регион расчёта: Москва (msk).", "Сумма, руб": ""},
            {"Статья": "Цены действительны на дату расчёта. Заказные щиты (ГРЩ, ШШР) требуют проработки завода-изготовителя.", "Сумма, руб": ""},
        ]
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Сводка", index=False)

    log.info("Сохранено: %s", OUT_XLSX.resolve())


if __name__ == "__main__":
    main()