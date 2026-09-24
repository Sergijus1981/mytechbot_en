"""OCR-парсер спецификаций для кривых PDF (АПС)."""
import logging
import re
from pathlib import Path

import pytesseract
from pdf2image import convert_from_path

log = logging.getLogger(__name__)


def ocr_page_text(image, lang="rus"):
    """Распознаёт текст со страницы (картинки)."""
    return pytesseract.image_to_string(image, lang=lang, config="--psm 6")


def ocr_pdf_pages(pdf_path, dpi=300):
    """Рендерит PDF в картинки через pymupdf (без Poppler) и распознаёт текст."""
    import pymupdf
    from PIL import Image
    import io as _io

    log.info("OCR: рендер PDF через pymupdf (dpi=%d)", dpi)
    doc = pymupdf.open(pdf_path)
    pages_text = []

    zoom = dpi / 72.0
    mat = pymupdf.Matrix(zoom, zoom)

    for i, page in enumerate(doc, 1):
        log.info("OCR: страница %d", i)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        img = Image.open(_io.BytesIO(img_data))
        text = ocr_page_text(img)
        pages_text.append(text)

    doc.close()
    return pages_text


def parse_ocr_spec(pdf_path):
    """Парсит спецификацию через OCR. Возвращает список позиций."""
    pages_text = ocr_pdf_pages(pdf_path)

    items = []
    current_section = "Оборудование"

    for pno, text in enumerate(pages_text, 1):
        log.info("OCR: разбор страницы %d", pno)
        lines = text.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Раздел
            if "кабельные изделия" in line.lower():
                current_section = "Кабельные изделия"
                continue
            if "монтажные материалы" in line.lower():
                current_section = "Монтажные материалы"
                continue

            # Позиция: 1.1, 2.15 и т.п.
            m = re.match(r"^(\d+\.\d+)\s+(.+)$", line)
            if not m:
                continue

            pos = m.group(1)
            rest = m.group(2)

            # Кол-во в конце (последнее число)
            qty_match = re.search(r"(\d+)\s*$", rest)
            qty = int(qty_match.group(1)) if qty_match else None
            name = rest[: qty_match.start()].strip() if qty_match else rest

            items.append({
                "Позиция": pos,
                "Раздел": current_section,
                "Наименование": name,
                "Ед.": "шт.",
                "Кол-во": qty,
                "Тип/марка": "",
                "Код": "",
                "Завод": "",
                "Масса, кг": None,
                "Примечание": "OCR",
            })

    log.info("OCR: всего позиций %d", len(items))
    return items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "test_aps.pdf"
    result = parse_ocr_spec(path)
    for it in result[:20]:
        print(it)