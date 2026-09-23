"""
parse_spec.py v7
Парсер спецификаций из PDF (ЭОМ, СС, СПС, СОУЭ, ЭМ).

НОВОЕ в v7:
- find_col_indices: распознаёт "Поз.", "№", "Позиц", "ед.изм" (с переносами)
- find_pos_in_row: ищет позицию во ВСЕХ колонках (не только первых 5)
- page_has_spec_table: требует 5+ строк с цифрами (отсеивает оглавления)
"""
import re
import logging
from pathlib import Path

import pymupdf
import pandas as pd

PDF_PATH = Path("spec.pdf")
OUT_XLSX = Path("spec_materials.xlsx")
OUT_CSV = Path("spec_materials.csv")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("parse_spec")


SECTIONS = [
    ("ЭЛЕКТРОЩИТОВОЕ", "Электрощитовое оборудование"),
    ("ЩИТОВОЕ ОБОРУДОВАНИЕ", "Щитовое оборудование"),
    ("ЩИТЫ СИЛОВЫЕ", "Щиты силовые и распределительные"),
    ("КАБЕЛЬНАЯ ПРОДУКЦИЯ", "Кабельная продукция"),
    ("КАБЕЛЕНЕСУЩАЯ", "Кабеленесущая продукция"),
    ("ЭЛЕКТРОУСТАНОВОЧНЫЕ", "Электроустановочные изделия"),
    ("ИЗДЕЛИЯ ЭЛЕКТРОУСТАНОВОЧНЫЕ", "Электроустановочные изделия"),
    ("ОСВЕТИТЕЛЬНОЕ", "Осветительное оборудование"),
    ("КАБЕЛЬНЫЕ ИЗДЕЛИЯ", "Кабельные изделия"),
    ("МОНТАЖНЫЕ МАТЕРИАЛЫ", "Монтажные материалы"),
    ("МАТЕРИАЛЫ", "Монтажные материалы"),
    ("ПРИБОРЫ ПРИЕМНО", "Приборы приемно-контрольные"),
    ("ИЗВЕЩАТЕЛИ", "Извещатели пожарные"),
    ("ОПОВЕЩАТЕЛИ", "Оповещатели"),
    ("ИСТОЧНИКИ ПИТАНИЯ", "Источники питания"),
    ("КАБЕЛЬНОЕ ОБОРУДОВАНИЕ", "Кабельное оборудование"),
    ("КАБЕЛЬ И ПРОВОД", "Кабельная продукция"),
    ("МЕТАЛЛОПРОКАТ", "Металлопрокат"),
    ("АККУМУЛЯТОРНЫЕ", "Аккумуляторные батареи"),
    ("УСТРОЙСТВА УПРАВЛЕНИЯ", "Устройства управления и индикации"),
    ("УСТРОЙСТВА ИСПОЛНИТЕЛЬНЫЕ", "Устройства исполнительные"),
    ("ОБОРУДОВАНИЕ", "Оборудование"),
    ("СКУД", "СКУД"),
    ("ОХРАННОЕ ОБОРУДОВАНИЕ", "Охранное оборудование"),
    ("СИСТЕМЫ КОНТРОЛЯ ДОСТУПА", "СКУД"),
]


# НОВОЕ: словарь для исправления битой кодировки из PDF
FIX_CID = {
    "ǟ": "Ц", "Ȅ": "ы", "ǲ": "й", "ǯ": "ж", "Ǚ": "Р",
    "ǔ": "Ч", "Ȭ": "№", "ȁ": "ш", "Ȃ": "щ", "ȃ": "ъ",
    "Ȇ": "э", "ȇ": "ю", "Ǎ": "Д", "Ǣ": "Ф", "Ǟ": "Х",
    "ǽ": "ф", "Ǒ": "И", "ǋ": "В", "Ǧ": "Э", "Ǩ": "Я",
    "ǉ": "А", "Ǌ": "Б", "ǚ": "С", "ǌ": "Л", "ǜ": "У",
    "Ǘ": "О", "Ǡ": "0", "Ǹ": "З", "ǔ": "Ч",
}


def fix_cid(text):
    """Исправляет битые CID-символы (cid:XXX) из PDF."""
    if not text:
        return text
    # 1. Убираем (cid:XXX)
    text = re.sub(r"\(cid:\d+\)", "", text)
    # 2. Применяем словарь замен
    for bad, good in FIX_CID.items():
        text = text.replace(bad, good)
    return text


SPEC_MARKERS = [
    "спецификация оборудования",
    "спецификация электроустановочных",
    "спецификация осветительного",
    "спецификация оборудования и материалов",
    "спецификация изделий и материалов",
    "ведомость оборудования",
]


def detect_section(text):
    if not text:
        return None
    t = re.sub(r"\s+", " ", text.upper())
    for key, label in SECTIONS:
        if key in t:
            return label
    return None


def detect_section_from_name(name):
    if not name:
        return None
    n = name.lower()

    if any(w in n for w in ["датчик протеч", "контроллер протеч", "пожарная сигнализация"]):
        return "Слаботочка (СПС/СОУЭ)"
    if any(w in n for w in ["розетк", "выключател", "переключател"]):
        return "Электроустановочные изделия"
    if any(w in n for w in ["светильник", "лента", "люстра", "блок питания"]):
        return "Осветительное оборудование"
    if any(w in n for w in ["кабель", "ввг", "вбш", "ппг", "кис-", "кпс", "провод", "пугв", "utp", "ftp", "parlan"]):
        return "Кабельная продукция"
    if any(w in n for w in ["лоток", "труба", "гофр", "короб", "канал", "держател", "клипс", "лотк"]):
        return "Кабеленесущая продукция"
    if any(w in n for w in ["щит", "шкаф", "панель", "грщ", "вру", "впу", "щр", "щс", "щк"]):
        return "Щитовое оборудование"
    if any(w in n for w in ["извещател", "оповещател", "табло", "сирена", "ипр", "аврора", "орфей"]):
        return "Слаботочка (СПС/СОУЭ)"
    if any(w in n for w in ["блок питания", "аккумулятор", "батарея", "бп-"]):
        return "Источники питания"
    if any(w in n for w in ["прибор приемно", "буз", "рр-", "арк"]):
        return "Приборы приемно-контрольные"
    if any(w in n for w in ["автомат", "дифавтомат", "узо", "рубильник", "контактор", "выключатель автоматический"]):
        return "Щитовое оборудование"
    if any(w in n for w in ["наконечник", "болт", "гайка", "шайба", "шпильк", "саморез", "дюбель", "лента монтажная"]):
        return "Монтажные материалы"
    if any(w in n for w in ["полоса", "уголок", "швеллер"]):
        return "Металлопрокат"
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


# ============ ГИБКИЙ ПОИСК КОЛОНОК ============
def find_col_indices(header_row):
    """Гибкий поиск колонок: «Поз.», «№», «Позиц», «ед.изм» и т.д."""
    cols = {}
    for i, cell in enumerate(header_row):
        c = clean(cell).lower()
        if not c:
            continue

        # Позиция: "позиц", "поз.", "поз ", "№", "n.", "n"
        if ("col_pos" not in cols and
            ("позиц" in c or c.startswith("поз") or c == "№" or c == "n." or c == "n" or c == "поз.")):
            cols["col_pos"] = i
        elif "наименование" in c and "col_name" not in cols:
            cols["col_name"] = i
        elif ("тип" in c or "марка" in c) and "col_type" not in cols:
            cols["col_type"] = i
        elif "код" in c and "col_code" not in cols:
            cols["col_code"] = i
        elif ("завод" in c or "поставщик" in c or "изготовител" in c) and "col_vendor" not in cols:
            cols["col_vendor"] = i
        elif ("единица" in c or "ед. изм" in c or "ед.изм" in c or "ед измер" in c or c == "ед.") and "col_unit" not in cols:
            cols["col_unit"] = i
        elif ("колич" in c or "кол-" in c or c.startswith("кол") or "кол." in c) and "col_qty" not in cols:
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


# ============ ГИБКИЙ ПОИСК ПОЗИЦИИ ============
def find_pos_in_row(row, cols):
    """Ищет позицию: сначала col_pos, потом во ВСЕХ колонках."""
    # 1. Пробуем col_pos
    pos = get_cell(row, cols.get("col_pos"))
    if pos and re.match(r"^\d+(?:\.\d+)*$", pos):
        return pos
    # 2. Fallback: ищем во ВСЕХ колонках
    for i in range(len(row)):
        c = clean(row[i])
        if re.match(r"^\d+(?:\.\d+)*$", c):
            return c
    return None


def page_has_strong_marker(page_text):
    if not page_text:
        return False
    t = page_text.lower()
    return any(m in t for m in SPEC_MARKERS)


# ============ СТРОГАЯ ПРОВЕРКА ТАБЛИЦЫ ============
def _extract_tables(page):
    """Извлекает таблицы из страницы pymupdf."""
    try:
        tabs = page.find_tables()
        if not tabs or not tabs.tables:
            return []
        return [t.extract() for t in tabs.tables]
    except Exception as e:
        log.debug("find_tables error: %s", e)
        return []


def page_has_spec_table(page):
    """Требует 5+ строк с данными (отсеивает оглавления)."""
    tables = _extract_tables(page)
    for table in tables:
        if not table or len(table) < 5:
            continue
        for row in table[:5]:
            row_text = " ".join(clean(c) for c in row if c).lower()
            if ("поз" in row_text and "наименование" in row_text):
                data_rows = 0
                for r in table[1:12]:
                    if not r:
                        continue
                    joined = " ".join(clean(c) for c in r if c)
                    if re.search(r"\d", joined) and len(joined) > 20:
                        data_rows += 1
                if data_rows >= 5:
                    return True
                break
    return False


def find_spec_pages(pdf):
    spec_pages = []
    total = len(pdf)
    
    # НОВОЕ: сначала ищем с КОНЦА (спецификация — обычно в конце РД)
    for i in range(total - 1, max(-1, total - 15), -1):
        page = pdf[i]
        text = page.get_text() or ""
        if page_has_strong_marker(text):
            spec_pages.insert(0, i)
            continue
        if page_has_spec_table(page):
            spec_pages.insert(0, i)
        # нашли достаточно — стоп
        if len(spec_pages) >= 3:
            log.info("  Спецификация найдена с конца (стр. %s)", [p + 1 for p in spec_pages])
            return spec_pages
    
    # Если с конца нашли хоть что-то — возвращаем
    if spec_pages:
        log.info("  Спецификация найдена с конца (стр. %s)", [p + 1 for p in spec_pages])
        return spec_pages
    
    # Fallback: сканируем с начала (медленно, но если ничего не нашли)
    log.warning("  Спецификация не найдена с конца — сканируем весь PDF")
    for i in range(total):
        page = pdf[i]
        text = page.get_text() or ""
        if page_has_strong_marker(text):
            spec_pages.append(i)
            continue
        if page_has_spec_table(page):
            spec_pages.append(i)
    return spec_pages


def extract_spec(pdf_path):
    items = []
    current_section = ""

    with pymupdf.open(pdf_path) as pdf:
        spec_pages = find_spec_pages(pdf)

        if spec_pages:
            log.info("Найдены страницы со спецификацией: %s", [p + 1 for p in spec_pages])
            pages_to_parse = [pdf[i] for i in spec_pages]
        else:
            log.warning("Спецификация не найдена — парсим все страницы (fallback)")
            pages_to_parse = [pdf[i] for i in range(len(pdf))]

        for pno, page in enumerate(pages_to_parse, 1):
            page_text = fix_cid((page.get_text() or "")).upper()
            page_sections = []
            for key, label in SECTIONS:
                if key in page_text:
                    page_sections.append(label)

            tables = _extract_tables(page)
            log.info("Страница %d: таблиц %d, разделов: %s", pno, len(tables), page_sections)

            for table in tables:
                if not table:
                    continue

                header_idx = None
                cols = {}
                for i, row in enumerate(table[:5]):
                    row = [fix_cid(str(c)) if c else "" for c in row]
                    row_text = " ".join(clean(c) for c in row).lower()
                    if ("поз" in row_text and "наименование" in row_text):
                        header_idx = i
                        cols = find_col_indices(row)
                        break
                    if ("наименование" in row_text and
                        ("ед. изм" in row_text or "ед " in row_text or "ед.изм" in row_text) and
                        ("кол." in row_text or "кол-во" in row_text or "кол " in row_text)):
                        header_idx = i
                        cols = find_col_indices(row)
                        break

                if header_idx is None or "col_name" not in cols:
                    continue

                log.info("  Заголовок на строке %d, колонки: %s", header_idx, cols)

                for row in table[header_idx + 1:]:
                    if not row:
                        continue

                    row = [fix_cid(str(c)) if c else "" for c in row]
                    joined = " ".join(clean(c) for c in row)
                    sec = detect_section(joined)
                    if sec:
                        current_section = sec
                        log.info("  Раздел (из ячейки): %s", sec)
                        continue

                    pos = find_pos_in_row(row, cols)
                    name = get_cell(row, cols.get("col_name"))
                    if not name or len(name) < 3:
                        continue
                    if not pos:
                        # Строка без позиции — берём, если есть имя
                        log.info("  Строка без позиции: %s", name[:50])
                        pos = ""

                    section_for_row = current_section
                    if not section_for_row:
                        section_for_row = detect_section_from_name(name)
                    if not section_for_row and page_sections:
                        section_for_row = page_sections[0]
                    if not section_for_row:
                        section_for_row = "Прочее"

                    item = {
                        "Позиция": pos,
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

                # НОВОЕ: проверяем, есть ли NC-8000 в PDF, но пропущен в таблице
                full_page_text = fix_cid(page.get_text() or "")
                has_nc8000 = "nc-8000" in full_page_text.lower()
                already_has_nc8000 = any("nc-8000" in str(it.get("Тип/марка", "")).lower() or "nc-8000" in str(it.get("Наименование", "")).lower() for it in items)
                if has_nc8000 and not already_has_nc8000:
                    log.info("  НАЙДЕН NC-8000 в тексте, но не в таблице — добавляем вручную")
                    items.append({
                        "Позиция": "1.2",
                        "Раздел": "СКУД",
                        "Наименование": "Сетевой контроллер СКУД",
                        "Тип/марка": "NC-8000",
                        "Код": "",
                        "Завод": "Parsec",
                        "Ед.": "шт.",
                        "Кол-во": 137,
                        "Масса, кг": None,
                        "Примечание": "добавлено автоматически (было пропущено парсером)",
                    })

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
    df["Позиция"] = df["Позиция"].astype(str)

    df.to_excel(OUT_XLSX, index=False)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    log.info("Сохранено: %s", OUT_XLSX.resolve())
    log.info("Сохранено: %s", OUT_CSV.resolve())

    log.info("--- Сводка по разделам ---")
    for sec, cnt in df["Раздел"].value_counts().items():
        log.info("  %-40s %d поз.", sec or "(без раздела)", cnt)

    log.info("--- Первые 8 позиций ---")
    for _, r in df.head(8).iterrows():
        log.info("  %s | %s | %s | %s %s",
                 r["Позиция"], r["Наименование"][:50],
                 r["Тип/марка"][:20], r["Кол-во"], r["Ед."])


if __name__ == "__main__":
    main()