"""Загрузка сметы из Excel в базу."""
import sqlite3
import datetime as dt
from pathlib import Path
import openpyxl

DB_PATH = Path("/data/smety.db") if Path("/data").exists() else Path("smety.db")


def get_or_create_product(conn, name, unit, category, model="", brand="", code="", vendor=""):
    c = conn.cursor()
    r = c.execute(
        "SELECT id FROM products WHERE name = ? AND model = ?",
        (name, model)
    ).fetchone()
    if r:
        return r[0]
    now = dt.datetime.now().isoformat()
    c.execute(
        "INSERT INTO products (name, brand, model, code, vendor, unit, category, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, brand, model, code, vendor, unit, category, now, now)
    )
    return c.lastrowid


def add_price(conn, product_id, price, source, vendor="", region="msk"):
    if price is None or price <= 0:
        return
    conn.execute(
        "INSERT INTO prices (product_id, price, source, vendor, date, region, parsed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (product_id, price, source, vendor, dt.datetime.now().isoformat(), region, dt.datetime.now().isoformat())
    )


def load_estimate_from_xlsx(xlsx_path, estimate_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = dt.datetime.now().isoformat()

    # Создаём смету
    c.execute(
        "INSERT INTO estimates (name, created_at) VALUES (?, ?)",
        (estimate_name, now)
    )
    estimate_id = c.lastrowid

    # Читаем лист "Материалы"
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    if "Материалы" in wb.sheetnames:
        ws = wb["Материалы"]
        total_materials = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            r = list(row) + [None]*16
            pos = r[0]; section = r[1]; name = r[2]
            model = r[3] or ""; code = r[4] or ""; vendor = r[5] or ""
            unit = r[6] or ""; qty = r[7]
            price = r[8]; summ = r[9]
            source = r[10] or ""; region = r[13] or "msk"; coef = r[14]; note = r[15] or ""
            if not name or not pos:
                continue
            if str(name).upper().startswith("ИТОГО") or "Наценка" in str(name):
                continue
            product_id = get_or_create_product(conn, str(name), unit, section, model=str(model), code=str(code), vendor=str(vendor))
            # проверяем, что price - число
            _price_num = None
            try:
                if price is not None and str(price).strip() not in ("", "nan", "None", "заказная сборка"):
                    _price_num = float(price)
            except (ValueError, TypeError):
                _price_num = None
            if _price_num:
                add_price(conn, product_id, _price_num, source, str(vendor), region=str(region))
            c.execute(
                "INSERT INTO estimate_items (estimate_id, product_id, position, section, name, qty, price, sum, status, region, coef, note, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (estimate_id, product_id, str(pos), section or "", str(name), qty or 0, _price_num or 0, summ or 0, "ok" if _price_num else "заказная сборка", str(region), coef, str(note), source)
            )
            if summ:
                total_materials += float(summ)

    # Читаем лист "Работы" — итог в колонке B, название в колонке A
    total_works = 0
    if "Работы" in wb.sheetnames:
        ws = wb["Работы"]
        for row in ws.iter_rows(min_row=2, values_only=True):
            vals = list(row) + [None]*6
            key = str(vals[1] or "") or str(vals[0] or "")
            if "ИТОГО работы с наценкой" in key and vals[5]:
                total_works = float(vals[5])
                break

    # Читаем лист "Сводка"
    total_nds = 0
    total_all = 0
    if "Сводка" in wb.sheetnames:
        ws = wb["Сводка"]
        for row in ws.iter_rows(min_row=2, values_only=True):
            vals = list(row) + [None]*2
            key = str(vals[0] or "")
            if "НДС 20%" in key and vals[1]:
                total_nds = float(vals[1])
            if not key and vals[1] and total_all == 0 and total_nds > 0:
                # Пустая колонка A + число = ВСЕГО С НДС
                total_all = float(vals[1])

    # Обновляем итоги
    c.execute(
        "UPDATE estimates SET total_materials = ?, total_works = ?, total_nds = ?, total_all = ? WHERE id = ?",
        (total_materials, total_works, total_nds, total_all, estimate_id)
    )
    conn.commit()
    conn.close()
    print(f"✅ Загружено: {estimate_name} | материалы: {total_materials:,.2f} ₽ | работы: {total_works:,.2f} ₽ | НДС: {total_nds:,.2f} ₽ | ВСЕГО: {total_all:,.2f} ₽")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python db_loader.py <xlsx_path> <estimate_name>")
        sys.exit(1)
    load_estimate_from_xlsx(sys.argv[1], sys.argv[2])