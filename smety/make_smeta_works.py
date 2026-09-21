"""
make_smeta_works.py v3 (ФИНАЛ)
Считает электромонтажные работы по спецификации ЭОМ.
Учитывает: коэффициенты условий, повороты, оконечку, НДС.

Вход:  smeta_eom_materials.xlsx (из make_smeta_eom.py)
Выход: smeta_eom_full.xlsx (материалы + работы + итого)
"""
import re
import logging
from pathlib import Path

import pandas as pd

IN_XLSX = Path("smeta_eom_materials.xlsx")
OUT_XLSX = Path("smeta_eom_full.xlsx")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("make_smeta_works")


# ===== НАЦЕНКИ =====
MARKUP_MATERIALS = 0.20   # +20% на материалы
MARKUP_WORKS = 0.15       # +15% на работы

# ===== КОЭФФИЦИЕНТЫ УСЛОВИЙ РАБОТ =====
COEF_HEIGHT = 1.30        # высота 9 м
COEF_ACTIVE = 1.15        # действующий объект
COEF_NIGHT = 1.40         # ночные работы
COEF_TOTAL = COEF_HEIGHT * COEF_ACTIVE * COEF_NIGHT   # = 2.093

# ===== НДС =====
VAT = 0.20

# ===== ДОПОЛНИТЕЛЬНЫЕ РАБОТЫ =====
COEF_TURNS = 0.07         # +7% на повороты
FEE_CABLE_TERMINATION = 150_000   # оконечка кабелей, укрупнённо


# ===== РАСЦЕНКИ НА РАБОТЫ =====
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

    for _, r in df.iterrows():
        pos = str(r["Позиция"])
        name = str(r["Наименование"])
        model = str(r["Тип/марка"]) if pd.notna(r["Тип/марка"]) else ""
        qty = r["Кол-во"] if pd.notna(r["Кол-во"]) else None
        section = r["Раздел"] if pd.notna(r["Раздел"]) else ""

        if qty is None:
            continue

        if section == "Кабельная продукция" and name.startswith("ППГнг"):
            sec = parse_cable_section(name)
            if sec and sec in CABLE_PRICES:
                rate = CABLE_PRICES[sec]
                works.append({
                    "Позиция": pos,
                    "Работа": f"Прокладка кабеля {sec}",
                    "Ед.": "м", "Объём": qty,
                    "Расценка, руб": rate,
                    "Сумма, руб": round(rate * qty, 2),
                })

        elif section == "Кабеленесущая продукция" and "лоток" in name.lower():
            sec = parse_tray_section(name)
            if sec and sec in TRAY_PRICES:
                rate = TRAY_PRICES[sec]
                works.append({
                    "Позиция": pos,
                    "Работа": f"Монтаж лотка {sec}",
                    "Ед.": "м", "Объём": qty,
                    "Расценка, руб": rate,
                    "Сумма, руб": round(rate * qty, 2),
                })

        elif section == "Электрощитовое оборудование":
            m = model.strip()
            if m in PANEL_PRICES:
                rate = PANEL_PRICES[m]
                works.append({
                    "Позиция": pos,
                    "Работа": f"Монтаж щита {m}",
                    "Ед.": "шт", "Объём": qty,
                    "Расценка, руб": rate,
                    "Сумма, руб": round(rate * qty, 2),
                })

        elif "муфта кабельная" in name.lower():
            for key, rate in COUPLING_PRICES.items():
                if key in name:
                    works.append({
                        "Позиция": pos,
                        "Работа": f"Монтаж муфты {key}",
                        "Ед.": "шт", "Объём": qty,
                        "Расценка, руб": rate,
                        "Сумма, руб": round(rate * qty, 2),
                    })
                    break

        elif "труба гофрированная" in name.lower() and r["Ед."] == "м":
            works.append({
                "Позиция": pos,
                "Работа": "Затяжка кабеля в гофротрубу",
                "Ед.": "м", "Объём": qty,
                "Расценка, руб": PULL_PRICE,
                "Сумма, руб": round(PULL_PRICE * qty, 2),
            })

    return works


def main():
    if not IN_XLSX.exists():
        log.error("Нет файла: %s", IN_XLSX)
        return

    log.info("Читаю: %s", IN_XLSX)
    df = pd.read_excel(IN_XLSX, dtype={"Позиция": str, "Код": str})
    log.info("Позиций: %d", len(df))

    # материалы — без строки ИТОГО
    df_no_total = df[df["Раздел"] != "ИТОГО"]
    if "Сумма, руб" in df_no_total.columns:
        m = pd.to_numeric(df_no_total["Сумма, руб"], errors="coerce").fillna(0)
        materials_total = float(m.sum())
    else:
        materials_total = 0.0

    log.info("Материалы (без наценки): %.2f руб", materials_total)

    # работы — базовые
    works = calc_works(df_no_total)
    log.info("Найдено работ (позиций): %d", len(works))
    works_base = sum(w["Сумма, руб"] for w in works)
    log.info("Работы (база): %.2f руб", works_base)

    # применяем коэффициенты и повороты
    works_with_coef = works_base * COEF_TOTAL
    log.info("× Коэффициенты (высота×активный×ночь = %.3f): %.2f руб",
             COEF_TOTAL, works_with_coef)

    turns_amount = works_with_coef * COEF_TURNS
    works_with_turns = works_with_coef + turns_amount
    log.info("+ Повороты (%.0f%%): %.2f руб", COEF_TURNS * 100, works_with_turns)

    works_with_termination = works_with_turns + FEE_CABLE_TERMINATION
    log.info("+ Оконечка кабелей: %.2f руб", works_with_termination)

    works_markup = works_with_termination * MARKUP_WORKS
    works_total = works_with_termination + works_markup
    log.info("+15%% наценка на работы: %.2f руб", works_markup)
    log.info("Итого работы: %.2f руб", works_total)

    # материалы с наценкой
    materials_markup = materials_total * MARKUP_MATERIALS
    materials_with_markup = materials_total + materials_markup
    log.info("Материалы +20%% наценка: %.2f руб", materials_with_markup)

    # подытог
    subtotal = materials_with_markup + works_total
    log.info("Подытог (материалы+работы): %.2f руб", subtotal)

    # НДС
    vat_amount = subtotal * VAT
    grand_total = subtotal + vat_amount
    log.info("НДС 20%%: %.2f руб", vat_amount)

    log.info("=====================================")
    log.info("=== ИТОГО С НДС: %.2f руб ===", grand_total)
    log.info("=====================================")

    # ===== Сохранение в Excel с листами =====
    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        # --- Лист 1: Материалы ---
        materials_rows = []
        for _, r in df.iterrows():
            materials_rows.append({
                "Позиция": r["Позиция"], "Раздел": r["Раздел"],
                "Наименование": r["Наименование"], "Ед.": r["Ед."],
                "Кол-во": r["Кол-во"],
                "Цена ед., руб": r["Цена ед., руб"],
                "Сумма, руб": r["Сумма, руб"],
                "Источник": r["Источник"], "Статус": r["Статус"],
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

        # --- Лист 2: Работы ---
        works_rows = list(works)

        # добавляем строки коэффициентов и доп. работ
        works_rows.append({
            "Позиция": "", "Работа": "ИТОГО работы (база)",
            "Ед.": "", "Объём": "", "Расценка, руб": "",
            "Сумма, руб": round(works_base, 2),
        })
        works_rows.append({
            "Позиция": "", "Работа": f"× Коэффициент условий (высота×активный×ночь = {COEF_TOTAL:.3f})",
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

        # --- Лист 3: Сводка ---
        summary_rows = [
            {"Статья": "МАТЕРИАЛЫ", "Сумма, руб": ""},
            {"Статья": "Материалы (без наценки)", "Сумма, руб": round(materials_total, 2)},
            {"Статья": "Наценка на материалы (20%)", "Сумма, руб": round(materials_markup, 2)},
            {"Статья": "Итого материалы", "Сумма, руб": round(materials_with_markup, 2)},
            {"Статья": "", "Сумма, руб": ""},

            {"Статья": "РАБОТЫ", "Сумма, руб": ""},
            {"Статья": "Работы (база)", "Сумма, руб": round(works_base, 2)},
            {"Статья": f"Коэффициенты условий (×{COEF_TOTAL:.3f})",
             "Сумма, руб": round(works_with_coef, 2)},
            {"Статья": f"Повороты (+{int(COEF_TURNS*100)}%)",
             "Сумма, руб": round(works_with_turns, 2)},
            {"Статья": "Оконечка кабелей (укрупнённо)",
             "Сумма, руб": round(FEE_CABLE_TERMINATION, 2)},
            {"Статья": "Итого работы (до наценки)",
             "Сумма, руб": round(works_with_termination, 2)},
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