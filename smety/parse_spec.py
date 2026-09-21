"""
parse_spec.py v4
Парсер спецификации оборудования из PDF ЭОМ (формат 2004-ЭОМ2.3.СО).
- Позиции хранятся строками (не преобразуются в числа).
- Заголовки разделов ищутся и в таблицах, и в тексте страницы.
"""
import re
import logging
from pathlib import Path

import pdfplumber
import pandas as pd

PDF_PATH = Path("spec.pdf")
OUT_XLSX = Path("spec_materials.xlsx")
OUT_CSV  = Path("spec_materials.csv")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("parse_spec")


SECTIONS = [
    ("ЭЛЕКТРОЩИТОВОЕ ОБОРУДОВАНИЕ", "Электрощитовое оборудование"),
    ("КАБЕЛЬНАЯ ПРОДУКЦИЯ", "Кабельная продукция"),
    ("КАБЕЛЕНЕСУЩАЯ ПРОДУКЦИЯ", "Кабеленесущая продукция"),
]


def detect_section(text):
    if not text:
        return None
    t = text.upper()
    # нормализуем возможные переносы
    t = re.sub(r"\s+", " ", t)
    for key, label in SECTIONS:
        if key in t:
            return label
    return None


def clean(s):
    if s is None:
        return ""
    s = str(s).replace("\xa0", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse_qty(s):
    if not s:
        return None
    s = clean(s).replace(" ", "").replace(",", ".")
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def find_col_indices(header_row):
    """Находит индексы колонок по тексту в заголовке."""
    cols = {}
    for i, cell in enumerate(header_row):
        c = clean(cell).lower()
        if not c:
            continue
        if "позиция" in c and "col_pos" not in cols:
            cols["col_pos"] = i
        elif "наименование" in c and "col_name" not in cols:
            cols["col_name"] = i
        elif "тип" in c and "марка" in c and "col_type" not in cols:
            cols["col_type"] = i
        elif "код" in c and "col_code" not in cols:
            cols["col_code"] = i
        elif "завод" in c and "col_vendor" not in cols:
            cols["col_vendor"] = i
        elif ("единица" in c or "ед." in c) and "col_unit" not in cols:
            cols["col_unit"] = i
        elif ("колич" in c or "кол-" in c or c.startswith("кол")) and "col_qty" not in cols:
            cols["col_qty"] = i
        elif "масса" in c and "col_mass" not in cols:
            cols["col_mass"] = i
        elif "примечание" in c and "col_note" not in cols:
            cols["col_note"] = i
    return cols


def get_cell(row, idx):
    if idx is None or idx >= len(row):
        return ""
    return clean(row[idx])


def extract_spec(pdf_path):
    items = []
    current_section = ""

    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            # 1) сначала ищем разделы в тексте всей страницы (вне таблицы)
            page_text = (page.extract_text() or "").upper()
            page_sections = []
            for key, label in SECTIONS:
                if key in page_text:
                    page_sections.append(label)

            tables = page.extract_tables() or []
            log.info("Страница %d: таблиц %d, разделов в тексте: %s",
                     pno, len(tables), page_sections)

            for table in tables:
                if not table:
                    continue

                header_idx = None
                cols = {}
                for i, row in enumerate(table[:3]):
                    row_text = " ".join(clean(c) for c in row).lower()
                    if "позиция" in row_text and "наименование" in row_text:
                        header_idx = i
                        cols = find_col_indices(row)
                        break
                if header_idx is None or "col_pos" not in cols:
                    continue

                log.info("  Заголовок на строке %d, колонки: %s", header_idx, cols)

                for row in table[header_idx + 1:]:
                    if not row:
                        continue

                    joined = " ".join(clean(c) for c in row)
                    sec = detect_section(joined)
                    if sec:
                        current_section = sec
                        log.info("  Раздел (из ячейки): %s", sec)
                        continue

                    pos = get_cell(row, cols.get("col_pos"))
                    if not pos or not re.match(r"^\d+(?:\.\d+)*$", pos):
                        continue

                    name = get_cell(row, cols.get("col_name"))
                    if not name or len(name) < 3:
                        continue

                    # если раздел ещё не установлен — берём первый из текста страницы
                    section_for_row = current_section
                    if not section_for_row and page_sections:
                        section_for_row = page_sections[0]

                    # эвристика: позиции 14.x — кабели, 15.x — кабеленесущие
                    if pos.startswith("14.") or pos == "14":
                        section_for_row = "Кабельная продукция"
                    elif pos.startswith("15.") or pos == "15":
                        section_for_row = "Кабеленесущая продукция"
                    elif re.match(r"^\d+(?:\.\d+)?$", pos) and float(pos) <= 13:
                        section_for_row = "Электрощитовое оборудование"

                    item = {
                        "Позиция": pos,  # строка!
                        "Раздел": section_for_row,
                        "Наименование": name,
                        "Тип/марка": get_cell(row, cols.get("col_type")),
                        "Код": get_cell(row, cols.get("col_code")),
                        "Завод": get_cell(row, cols.get("col_vendor")),
                        "Ед.": get_cell(row, cols.get("col_unit")),
                        "Кол-во": parse_qty(get_cell(row, cols.get("col_qty"))),
                        "Масса, кг": parse_qty(get_cell(row, cols.get("col_mass"))),
                        "Примечание": get_cell(row, cols.get("col_note")),
                    }
                    items.append(item)

    return items


def main():
    if not PDF_PATH.exists():
        log.error("Нет файла: %s", PDF_PATH)
        return

    log.info("Читаю: %s", PDF_PATH)
    items = extract_spec(PDF_PATH)
    log.info("Найдено позиций: %d", len(items))

    if not items:
        log.warning("Ничего не найдено. Проверь формат PDF.")
        return

    df = pd.DataFrame(items)

    # ВАЖНО: пишем позицию как строку, чтобы Excel не превратил "1.1" в "1.10"
    df["Позиция"] = df["Позиция"].astype(str)

    df.to_excel(OUT_XLSX, index=False)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    log.info("Сохранено: %s", OUT_XLSX.resolve())
    log.info("Сохранено: %s", OUT_CSV.resolve())

    log.info("--- Сводка по разделам ---")
    for sec, cnt in df["Раздел"].value_counts().items():
        log.info("  %-30s %d поз.", sec or "(без раздела)", cnt)

    log.info("--- Первые 8 позиций ---")
    for _, r in df.head(8).iterrows():
        log.info("  %s | %s | %s | %s %s",
                 r["Позиция"], r["Наименование"][:50],
                 r["Тип/марка"][:20], r["Кол-во"], r["Ед."])


if __name__ == "__main__":
    main()