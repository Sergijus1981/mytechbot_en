"""
make_smeta_works.py v9
Расчёт работ по спецификации.
- Захардкоженные цены (кабели, лотки, щиты, муфты) — для ЭОМ 2.3
- НОВОЕ: WORKS_PRICES — расценки по ключевым словам для любых позиций
- Монтаж розеток, выключателей, светильников, извещателей, оповещателей
"""
import re
import logging
from pathlib import Path

import pandas as pd

IN_XLSX = Path("smeta_eom_materials.xlsx")
OUT_XLSX = Path("smeta_eom_full.xlsx")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("make_smeta_works")


MARKUP_MATERIALS = 0.20
MARKUP_WORKS = 0.15

COEF_HEIGHT = 1.30
COEF_ACTIVE = 1.15
COEF_NIGHT = 1.40
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
WORKS_PRICES = [
    # (ключ в наименовании, расценка, название работы)
    ("розетк", 400, "Монтаж розетки"),
    ("выключател", 400, "Монтаж выключателя"),
    ("переключател", 400, "Монтаж переключателя"),
    ("светильник", 600, "Монтаж светильника"),
    ("люстра", 800, "Монтаж люстры"),
    ("лючок", 1500, "Монтаж лючка напольного"),
    ("лента светодиод", 300, "Монтаж светодиодной ленты"),
    ("блок питания", 500, "Монтаж блока питания"),

    # Слаботочка
    ("извещател", 300, "Монтаж извещателя"),
    ("оповещател", 400, "Монтаж оповещателя"),
    ("табло", 400, "Монтаж табло"),
    ("сирена", 400, "Монтаж сирены"),
    ("орфей", 500, "Монтаж речевого оповещателя"),
    ("прибор приемно", 3000, "Монтаж прибора приемно-контрольного"),
    ("панель-", 3000, "Монтаж панели"),
    ("контроллер", 1500, "Монтаж контроллера"),
    ("программатор", 1000, "Монтаж программатора"),
    ("блок индикации", 1000, "Монтаж блока индикации"),
    ("блок исполнительн", 800, "Монтаж исполнительного блока"),
    ("аккумулятор", 300, "Монтаж АКБ"),
    ("скоба", 200, "Монтаж скобы"),

    # Кабели, трубы, лотки
    ("кабель", 100, "Прокладка кабеля"),
    ("провод", 80, "Прокладка провода"),
    ("труба", 50, "Прокладка трубы"),
    ("лоток", 200, "Монтаж лотка"),
    ("короб", 150, "Монтаж короба"),
    ("мини-канал", 100, "Монтаж мини-канала"),
    ("гофр", 50, "Прокладка гофры"),
    ("держател", 100, "Монтаж держателя"),
    ("дюбель", 30, "Монтаж дюбеля"),
    ("саморез", 10, "Монтаж самореза"),

    # Автоматы, щиты
    ("автомат", 300, "Монтаж автомата"),
    ("дифавтомат", 500, "Монтаж дифавтомата"),
    ("узо", 500, "Монтаж УЗО"),
    ("счетчик", 1500, "Монтаж счетчика"),
    ("трансформатор", 800, "Монтаж трансформатора"),
    ("рубильник", 500, "Монтаж рубильника"),
    ("ограничитель", 500, "Монтаж ОПН"),
    ("щит", 5000, "Монтаж щита"),
    ("шкаф", 5000, "Монтаж шкафа"),
    ("щит питания", 5000, "Монтаж щита питания"),
    ("наконечник", 50, "Монтаж наконечника"),
    ("болт", 30, "Монтаж болта"),
    ("гайка", 20, "Монтаж гайки"),
    ("шайба", 10, "Монтаж шайбы"),
    ("шпильк", 50, "Монтаж шпильки"),
    ("полоса", 150, "Монтаж полосы"),
    ("уголок", 150, "Монтаж уголка"),
    ("коробка", 200, "Монтаж коробки"),
    ("пена", 500, "Огнестойкая пена"),
    ("кожух", 300, "Монтаж кожуха"),
]


def find_work_price(name):
    """Ищет расценку по ключевому слову в наименовании."""
    if not name:
        return None, None
    n = name.lower()
    for key, price, work_name in WORKS_PRICES:
        if key in n:
            return price, work_name
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
        ]
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Сводка", index=False)

    log.info("Сохранено: %s", OUT_XLSX.resolve())


if __name__ == "__main__":
    main()