"""
load_svn.py
Загружает СВН (id=22) в smety.db.
"""
import sqlite3
import pandas as pd
from pathlib import Path

DB = Path("smety.db")
XLSX = Path("smeta_svn_full.xlsx")


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("SELECT id FROM estimates WHERE id = 22")
    if cur.fetchone():
        print("Смета id=22 уже есть — удаляю")
        cur.execute("DELETE FROM estimate_items WHERE estimate_id = 22")
        cur.execute("DELETE FROM estimates WHERE id = 22")

    df_mat = pd.read_excel(XLSX, sheet_name="Материалы")
    df_work = pd.read_excel(XLSX, sheet_name="Работы")
    df_sum = pd.read_excel(XLSX, sheet_name="Сводка")

    def get_val(df, key):
        for _, r in df.iterrows():
            if str(r.iloc[0]).strip().lower() == key.lower():
                v = r.iloc[1]
                return float(v) if pd.notna(v) else 0.0
        return 0.0

    total_mat = get_val(df_sum, "Материалы (без наценки)")
    total_work = get_val(df_sum, "Итого работы")
    total_nds = get_val(df_sum, "НДС 20%")
    total_all = get_val(df_sum, "=== ВСЕГО С НДС ===")

    cur.execute("""
        INSERT INTO estimates (id, name, description, total_materials, total_works, total_nds, total_all)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (22, "МК3-ZAR-РД-СВН",
          "Система видеонаблюдения. Москва, Заречная ул., вл. 2/1",
          total_mat, total_work, total_nds, total_all))
    print(f"Смета создана: id=22, всего={total_all}")

    n_items = 0
    for _, r in df_mat.iterrows():
        pos = str(r.get("Позиция", "")).strip()
        section = str(r.get("Раздел", "")).strip()
        name_item = str(r.get("Наименование", "")).strip()
        unit = str(r.get("Ед.", "")).strip() if pd.notna(r.get("Ед.")) else ""
        qty = r.get("Кол-во")
        price = r.get("Цена ед., руб")
        summ = r.get("Сумма, руб")
        note = str(r.get("Примечание", "")).strip() if pd.notna(r.get("Примечание")) else ""
        source = str(r.get("Источник", "")).strip() if pd.notna(r.get("Источник")) else ""

        if section == "ИТОГО" or pos == "":
            continue
        if pd.isna(qty) or not unit:
            continue

        full_note = (note + " | " + unit) if (note and unit) else (unit or note)

        cur.execute("""
            INSERT INTO estimate_items 
            (estimate_id, position, section, name, qty, price, sum, note, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (22, pos, section, name_item, float(qty),
              float(price) if pd.notna(price) else None,
              float(summ) if pd.notna(summ) else None,
              full_note, source))
        n_items += 1

    for _, r in df_work.iterrows():
        pos = str(r.get("Позиция", "")).strip()
        work = str(r.get("Работа", "")).strip()
        unit = str(r.get("Ед.", "")).strip() if pd.notna(r.get("Ед.")) else ""
        qty = r.get("Объём")
        price = r.get("Расценка, руб")
        summ = r.get("Сумма, руб")

        if not pos or not unit:
            continue
        row_text = " ".join(str(v) for v in r.values if pd.notna(v))
        if "ИТОГО" in row_text.upper():
            continue

        cur.execute("""
            INSERT INTO estimate_items 
            (estimate_id, position, section, name, qty, price, sum, note, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (22, pos, "Работы", work,
              float(qty) if pd.notna(qty) else None,
              float(price) if pd.notna(price) else None,
              float(summ) if pd.notna(summ) else None, unit, "WORKS_PRICES"))
        n_items += 1

    conn.commit()
    print(f"Загружено позиций: {n_items}")


if __name__ == "__main__":
    main()