import pdfplumber
import json
import sys
import re

def extract_tables_from_pdf(pdf_path, start_page=1, end_page=None):
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        if end_page is None or end_page > total:
            end_page = total
        
        print(f"📄 Всего страниц: {total}")
        print(f"📄 Обрабатываю: {start_page}-{end_page}\n")
        
        for page_num in range(start_page, end_page + 1):
            page = pdf.pages[page_num - 1]
            print(f"📄 Страница {page_num}...")
            try:
                page_tables = page.extract_tables()
                if page_tables:
                    print(f"   ✅ Таблиц: {len(page_tables)}")
                for table in page_tables:
                    if table and len(table) > 1:
                        tables.append({"page": page_num, "data": table})
            except Exception as e:
                print(f"   ⚠️ Ошибка: {e}")
    return tables

def is_specification_table(table_data):
    if not table_data or len(table_data) < 2:
        return False
    header = " ".join([str(cell).lower() for cell in table_data[0] if cell])
    keywords = ["наименование", "кол", "ед", "изм", "тип", "марка", "поставщик", "код"]
    return sum(1 for kw in keywords if kw in header) >= 2

def is_valid_item(name, qty, unit):
    """Проверяет, что это реальная позиция, а не шум"""
    if not name or len(name.strip()) < 5:
        return False
    if not qty or not unit:
        return False
    # Убираем заголовки разделов
    noise = [
        "оборудование", "провода и кабели", "сталь", "трубы", "изделия",
        "электроустановочные", "устанавливаются", "состав", "примечания",
        "сведения", "ведомость"
    ]
    name_lower = name.lower()
    for n in noise:
        if name_lower.startswith(n):
            return False
    # Убираем обрывки
    if len(name.strip()) < 5:
        return False
    if re.match(r'^\d+\s*(вт|мм|в|а)$', name_lower):
        return False
    if name_lower in ["т-ры", "36вт", "аккумклятора"]:
        return False
    return True

def parse_specification(table_data):
    items = []
    header = table_data[0]
    
    col_name = 0
    col_type = None
    col_unit = None
    col_qty = None
    
    for i, cell in enumerate(header):
        if not cell:
            continue
        cell_lower = str(cell).lower()
        if "наименование" in cell_lower:
            col_name = i
        elif "тип" in cell_lower or "марка" in cell_lower:
            col_type = i
        elif "ед" in cell_lower and "изм" in cell_lower:
            col_unit = i
        elif "кол" in cell_lower:
            col_qty = i
    
    if col_qty is None:
        col_qty = len(header) - 2
    if col_unit is None:
        col_unit = len(header) - 3
    
    for row in table_data[1:]:
        if not row or not row[col_name]:
            continue
        
        name = str(row[col_name]).strip().replace("\n", " ")
        qty = str(row[col_qty]).strip() if col_qty < len(row) and row[col_qty] else ""
        unit = str(row[col_unit]).strip() if col_unit < len(row) and row[col_unit] else ""
        
        if not is_valid_item(name, qty, unit):
            continue
        
        item = {
            "name": name,
            "type": str(row[col_type]).strip() if col_type is not None and col_type < len(row) and row[col_type] else "",
            "unit": unit,
            "qty": qty,
        }
        items.append(item)
    
    return items

def process_pdf(pdf_path, start_page=1, end_page=None):
    print(f"📄 Открываю: {pdf_path}\n")
    tables = extract_tables_from_pdf(pdf_path, start_page, end_page)
    print(f"\n📊 Всего таблиц: {len(tables)}")
    
    all_items = []
    for t in tables:
        if is_specification_table(t["data"]):
            items = parse_specification(t["data"])
            all_items.extend(items)
    
    print(f"\n📦 Чистых позиций: {len(all_items)}")
    
    with open("specification.json", "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    print("💾 Сохранено в specification.json")
    
    print("\n🔍 Позиции:")
    for i, item in enumerate(all_items, 1):
        print(f"{i}. {item['name'][:70]} | {item['qty']} {item['unit']}")
    
    return all_items

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parser_pdf.py <pdf> [start] [end]")
        sys.exit(1)
    pdf_path = sys.argv[1]
    start_page = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    end_page = int(sys.argv[3]) if len(sys.argv) > 3 else None
    process_pdf(pdf_path, start_page, end_page)
