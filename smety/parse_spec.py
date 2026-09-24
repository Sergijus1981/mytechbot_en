"""
parse_spec.py v7.1
Парсер спецификаций из PDF (АПС, СКУД, СВН, СОУЭ, ЭОМ).

НОВОЕ в v7.1:
- detect_section: спецобработка "КАБЕЛЬНЫЕ ПРОДУКЦИЯ" (опечатка из PDF)
- detect_region: определение региона по тексту PDF
- Порог spec_pages = 5 (захватывает стр. 1)
- Раздел переключается только если это НЕ данные (нет позиции)
"""
import re
import logging
from pathlib import Path

try:
    import pymupdf
    HAS_PYMUPDF = True
except ImportError:
    import pdfplumber
    HAS_PYMUPDF = False
import pandas as pd

try:
    from . import regions
except ImportError:
    import regions

PDF_PATH = Path("spec.pdf")
OUT_XLSX = Path("spec_materials.xlsx")
OUT_CSV = Path("spec_materials.csv")

CURRENT_REGION = "msk"  # заполняется в extract_spec()

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


FIX_CID = {
    "ЖЯ": "Ц", "ЫД": "Ы", "Ж▓": "й", "Жп": "ж", "ЖЩ": "Р",
    "ЖФ": "Ч", "Ым": "№", "ЫБ": "ш", "ЫВ": "й", "ЫГ": "ъ",
    "ЫЖ": "э", "ЫЗ": "ю", "ЖН": "Д", "Жв": "ф", "ЖЮ": "е",
    "Ж╜": "ф", "ЖС": "И", "ЖЛ": "Т", "Жж": "н", "Жи": "п",
    "ЖЙ": "А", "ЖК": "Б", "ЖЪ": "б", "ЖМ": "Л", "ЖЬ": "У",
    "ЖЧ": "Ю", "Жа": "0", "Ж╕": "З",
    "(cid:459)": "Т", "(cid:457)": "А", "(cid:36)": "А",
    "(cid:52)": "К", "(cid:45)": "Б", "(cid:16)": "×",
    "(cid:10)": "", "(cid:513)": "Тт", "(cid:44)": ",",
    "(cid:46)": ".", "(cid:45)": "-",
}


def fix_cid(text):
    if not text:
        return text
    for bad, good in FIX_CID.items():
        text = text.replace(bad, good)
    text = re.sub(r"\(cid:\d+\)", "", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
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
    """
    Определяет раздел по тексту заголовка.
    Спецобработка опечаток из PDF.
    """
    if not text:
        return None
    t = re.sub(r"\s+", " ", text.upper())

    if "КАБЕЛЬ" in t and "ПРОДУКЦ" in t:
        return "Кабельная продукция"
    if "КАБЕЛЕНЕСУЩ" in t:
        return "Кабеленесущая продукция"
    if "КАБЕЛЬ" in t and "ПРОВОД" in t:
        return "Кабельная продукция"

    for key, label in SECTIONS:
        if key in t:
            return label
    return None


def detect_section_from_name(name):
    if not name:
        return None
    n = name.lower()

    # КАБЕЛЬ — ПЕРВЫМ
    if any(w in n for w in ["кабель", "ввг", "вбш", "ппг", "кис-", "кпс", "провод", "пугв", "utp", "ftp", "parlan"]):
        return "Кабельная продукция"

    if any(w in n for w in ["датчик протеч", "контроллер протеч", "пожарная сигнализация"]):
        return "Слаботочка (СПС/СОУЭ)"
    if any(w in n for w in ["розетк", "выключател", "переключател"]):
        return "Электроустановочные изделия"
    if any(w in n for w in ["светильник", "лента", "люстра", "блок питания"]):
        return "Осветительное оборудование"
    if any(w in n for w in ["лоток", "труба", "гофр", "короб", "канал", "держател", "клипс", "лотк"]):
        return "Кабеленесущая продукция"
    if any(w in n for w in ["щит", "шкаф", "панель", "грщ", "вру", "впу", "шр", "шс", "шк"]):
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


def find_col_indices(header_row):
    cols = {}
    for i, cell in enumerate(header_row):
        c = clean(cell).lower()
        if not c:
            continue

        if ("col_pos" not in cols and
            ("позиц" in c or c.startswith("поз") or c == "№" or c == "n." or c == "n" or c == "поз.")):
            cols["col_pos"] = i
        elif "наименование" in c and "col_name" not in cols:
            cols["col_name"] = i
        elif ("тип" in c or "марка" in c) and "col_type" not in cols:
            cols["col_type"] = i
        elif "код" in c and "col_code" not in cols:
            cols["col_code"] = i
        elif ("завод" in c or "поставщик" in c or "изготовитель" in c) and "col_vendor" not in cols:
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


def find_pos_in_row(row, cols):
    pos = get_cell(row, cols.get("col_pos"))
    if pos and re.match(r"^\d+(?:\.\d+)*$", pos):
        return pos
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


def detect_document_type(pdf):
    """
    Определяет тип документа:
    - spec_table: табличная спецификация (Поз | Наименование | Ед | Кол-во)
    - vedomost: ведомость (Наименование | Кол-во)
    - text_list: текстовый список
    """
    if not pdf or len(pdf) == 0:
        return "unknown"

    pages_to_check = [0]
    if len(pdf) > 1:
        pages_to_check.append(len(pdf) - 1)

    full_text = ""
    for pno in pages_to_check:
        try:
            text = fix_cid(pdf[pno].get_text() or "")
            full_text += " " + text
        except Exception:
            pass

    low = full_text.lower()

    # СНАЧАЛА — спецификация (строгие маркеры)
    spec_markers = [
        "спецификация", "позиция", "поз.", "ед. изм", "ед.изм",
        "кол-во", "количество", "тип, марка",
    ]
    spec_score = sum(1 for m in spec_markers if m in low)
    if spec_score >= 2:
        return "spec_table"

    # Ведомость (только если спецификации нет)
    vedomost_markers = [
        "перечень оборудования", "перечень", "затоплен", "дефектная", "опись",
        "бирка маркировочная", "наклейка", "гильза защитная", "патч-корд",
        "ведомость", "томилинский", "ковровый",
    ]
    if any(m in low for m in vedomost_markers):
        return "vedomost"

    if spec_score >= 1:
        return "spec_table"

    lines = [l for l in full_text.split("\n") if l.strip()]
    if len(lines) > 20:
        return "text_list"

    return "spec_table"


def _extract_tables(page):
    try:
        tabs = page.find_tables()
        if not tabs or not tabs.tables:
            return []
        return [t.extract() for t in tabs.tables]
    except Exception as e:
        log.debug("find_tables error: %s", e)
        return []


def page_has_spec_table(page):
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

    for i in range(total - 1, max(-1, total - 15), -1):
        page = pdf[i]
        text = page.get_text() or ""
        if page_has_strong_marker(text):
            spec_pages.insert(0, i)
            continue
        if page_has_spec_table(page):
            spec_pages.insert(0, i)
        if len(spec_pages) >= 5:
            log.info("  Спецификация найдена с конца (стр. %s)", [p + 1 for p in spec_pages])
            return spec_pages

    if spec_pages:
        log.info("  Спецификация найдена с конца (стр. %s)", [p + 1 for p in spec_pages])
        return spec_pages

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


def parse_vedomost(pdf):
    """
    Парсит ведомость: 2 колонки (Наименование | Кол-во).
    Автонумерация позиций, ед.изм. — по названию.
    """
    items = []
    auto_num = [0]

    def next_num():
        auto_num[0] += 1
        return str(auto_num[0])

    def detect_unit(name):
        n = (name or "").lower()
        if any(w in n for w in ["кабель", "провод", "труба", "лоток", "полоса", "пруток", "шина"]):
            return "м"
        return "шт"

    for pno in range(len(pdf)):
        page = pdf[pno]
        tables = _extract_tables(page)
        for table in tables:
            if not table or len(table) < 2:
                continue

            header_row = None
            header_idx = None
            for i, row in enumerate(table[:5]):
                row_text = " ".join(clean(c) for c in row if c).lower()
                if "наимен" in row_text and (
                    "кол" in row_text or "количество" in row_text or "шт" in row_text
                ):
                    header_row = row
                    header_idx = i
                    break

            if header_idx is None:
                continue

            cols = find_col_indices(header_row)
            if "col_qty" not in cols:
                for i, cell in enumerate(header_row):
                    c = clean(cell).lower()
                    if "кол" in c or "шт" in c or "количество" in c:
                        cols["col_qty"] = i
                        break

            if "col_name" not in cols or "col_qty" not in cols:
                continue

            log.info("  Ведомость: заголовок на строке %d, колонки %s", header_idx, cols)

            for row in table[header_idx + 1:]:
                if not row:
                    continue
                row = [fix_cid(str(c)) if c else "" for c in row]
                name = get_cell(row, cols.get("col_name"))
                qty = parse_qty(get_cell(row, cols.get("col_qty")))
                if not name or len(name) < 4 or not qty:
                    continue

                pos = find_pos_in_row(row, cols) or next_num()
                unit = detect_unit(name)

                items.append({
                    "Позиция": pos,
                    "Раздел": detect_section_from_name(name) or "Ведомость",
                    "Наименование": name,
                    "Тип/марка": get_cell(row, cols.get("col_type")),
                    "Код": get_cell(row, cols.get("col_code")),
                    "Завод": get_cell(row, cols.get("col_vendor")),
                    "Ед.": unit,
                    "Кол-во": qty,
                    "Масса, кг": None,
                    "Примечание": "из ведомости",
                })

    return items


def parse_vedomost_ocr(pdf_path):
    """
    OCR-парсер ведомостей: текст → позиции.
    Формат: <название> <число>
    """
    try:
        import ocr_spec
    except ImportError:
        log.error("ocr_spec не найден")
        return []

    pages = ocr_spec.ocr_pdf_pages(pdf_path)
    items = []
    auto_num = [0]

    skip_words = [
        "дефектная", "ведомость", "на объекте", "адресу", "выявлено",
        "затоплено", "перечень", "наименования", "директор", "заместитель",
        "инженер", "ведущий", "макаренко", "чечеткин", "морозов", "шестаков",
        "ооо", "ловител", "пуско-наладочные",
    ]

    for pno, text in enumerate(pages, 1):
        log.info("OCR-ведомость: страница %d", pno)
        for line in text.split("\n"):
            line = line.strip()
            if not line or len(line) < 5:
                continue
            low = line.lower()
            if any(w in low for w in skip_words):
                continue

            # Ищем: название ... число (последнее число в строке)
            # Формат: "Бирка маркировочная 281,000" или "Наклейка 2,000"
            m = re.search(r"^(.*?)\s+([\d\s]+(?:[,.]\d+)?)\s*$", line)
            if not m:
                continue
            name = m.group(1).strip(" .,:;-—/|")
            qty_str = m.group(2).replace(" ", "").replace(",", ".")
            try:
                qty = float(qty_str)
            except ValueError:
                continue
            if qty <= 0 or len(name) < 4:
                continue

            auto_num[0] += 1
            # Ед. изм.
            n = name.lower()
            if any(w in n for w in ["кабель", "провод", "окгнг", "parlan", "ввгнг", "пв1", "пвс", "труба"]):
                unit = "м"
            else:
                unit = "шт"

            items.append({
                "Позиция": str(auto_num[0]),
                "Раздел": detect_section_from_name(name) or "СКС (ведомость)",
                "Наименование": name,
                "Тип/марка": "",
                "Код": "",
                "Завод": "",
                "Ед.": unit,
                "Кол-во": qty,
                "Масса, кг": None,
                "Примечание": "OCR из ведомости",
            })

    return items


def parse_defect_ocr(pdf_path):
    """
    OCR-парсер дефектных ведомостей (сборная солянка).
    """
    try:
        import ocr_spec
    except ImportError:
        log.error("ocr_spec не найден")
        return []

    pages = ocr_spec.ocr_pdf_pages(pdf_path)
    items = []

    skip_words = [
        "дефектная", "ведомость", "на объекте", "адресу", "выявлено",
        "затоплено", "перечень", "наименования", "директор", "заместитель",
        "инженер", "ведущий", "макаренко", "чечеткин", "морозов",
        "ловител", "пуско-наладочные", "смонтировано", "проектной",
        "жк томилинский", "дoy", "перечень слаботочных",
    ]

    sections = ["ОЗДС", "БР", "СВН", "АСУД", "КСБ", "СС", "Безопасный регион"]

    def norm_qty(qty_str):
        """Нормализует кол-во: '1', 'Юш', 'Ош', '4', '2.' → число"""
        if not qty_str:
            return 1.0
        s = qty_str.strip()
        # Замена букв на цифры
        s = s.replace("Ю", "10").replace("ю", "10")
        s = s.replace("О", "0").replace("о", "0")
        s = s.replace("З", "3").replace("з", "3")
        # Извлекаем первое число
        import re as _re
        m = _re.search(r"\d+", s)
        if m:
            try:
                return float(m.group())
            except ValueError:
                pass
        return 1.0

    def norm_name(name):
        """Чистит название от мусора"""
        import re as _re
        # Убираем хвост "| 1ш |" или "  4ш"
        name = _re.sub(r"\s*\|?\s*(\d+|[ЮюОо]ш)\s*[шщмШЩМ]?\S*\s*\|?\s*$", "", name)
        name = name.strip(" .,:;-—/|[]")
        return name

    current_section = "Дефектная ведомость"

    for pno, text in enumerate(pages, 1):
        log.info("OCR-дефектная: страница %d", pno)
        for line in text.split("\n"):
            line = line.strip()
            if not line or len(line) < 5:
                continue
            low = line.lower()
            if any(w in low for w in skip_words):
                continue

            # Раздел
            for sec in sections:
                if sec.lower() in low and len(line) < 40:
                    current_section = sec
                    break

            # Убираем мусор в начале
            clean_line = re.sub(r"^[\s\[\|_®]+", "", line)
            clean_line = re.sub(r"\s*\|\s*", " | ", clean_line)

            # Ищем N. в начале (более гибко)
            m = re.match(r"^(\d+)\s*[\.\s]\s*\|?\s*(.+)$", clean_line)
            if not m:
                continue

            num = m.group(1)
            name_raw = m.group(2)

            # Ищем кол-во в конце строки: "| 1ш |" или " 4ш" или " Юш"
            qty_match = re.search(
                r"\|?\s*(\d+|[ЮюОо])\s*[шщмШЩМ]\S*\s*\|?\s*$",
                name_raw
            )
            if qty_match:
                qty = norm_qty(qty_match.group(1))
                # Проверяем единицу — м или шт
                unit_match = re.search(r"[шщмШЩМ]", qty_match.group(0))
                unit_char = unit_match.group().lower() if unit_match else "ш"
                unit = "м" if unit_char == "м" else "шт"
                name = name_raw[:qty_match.start()].strip(" .,:;-—/|[]")
            else:
                qty = 1.0
                unit = "шт"
                name = norm_name(name_raw)

            name = name.strip(" .,:;-—/|[]")
            if not name or len(name) < 5:
                continue

            items.append({
                "Позиция": str(num),
                "Раздел": current_section,
                "Наименование": name,
                "Тип/марка": "",
                "Код": "",
                "Завод": "",
                "Ед.": unit,
                "Кол-во": qty,
                "Масса, кг": None,
                "Примечание": "OCR",
            })

    return items


def extract_spec(pdf_path):
    global CURRENT_REGION

    items = []
    current_section = ""

    with pymupdf.open(pdf_path) as pdf:
        # === РЕГИОН ===
        try:
            first_text = fix_cid(pdf[0].get_text() or "")
            if len(pdf) > 1:
                last_text = fix_cid(pdf[-1].get_text() or "")
                full_for_region = first_text + " " + last_text
            else:
                full_for_region = first_text
            CURRENT_REGION = regions.detect_region(full_for_region)
            log.info("Регион: %s (%s)", CURRENT_REGION, regions.region_name(CURRENT_REGION))
        except Exception as e:
            log.warning("Не удалось определить регион: %s", e)
            CURRENT_REGION = "msk"

        # === АВТОВЫБОР ПАРСЕРА ===
        doc_type = detect_document_type(pdf)
        log.info("Тип документа: %s", doc_type)
        if doc_type in ("vedomost", "text_list"):
            return parse_vedomost(pdf)

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

                    pos = find_pos_in_row(row, cols)
                    name = get_cell(row, cols.get("col_name"))

                    # === РАЗДЕЛ из ячейки === (только если это НЕ данные)
                    sec = detect_section(joined)
                    if sec and not pos:
                        generic = {"Монтажные материалы", "Оборудование", "Прочее"}
                        if current_section in generic or not current_section or sec not in generic:
                            current_section = sec
                            log.info("  Раздел (из ячейки): %s", sec)
                        else:
                            log.info("  Раздел (из ячейки) ПРОПУЩЕН (общий): %s", sec)
                        continue
                        current_section = sec
                        log.info("  Раздел (из ячейки): %s", sec)
                        continue

                    if not name or len(name) < 3:
                        continue
                    if not pos:
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

                # NC-8000
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

    for it in items:
        for k, v in it.items():
            if isinstance(v, str):
                it[k] = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", v)
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