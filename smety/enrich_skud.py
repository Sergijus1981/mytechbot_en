"""
enrich_skud.py
Обогащает products/prices позициями из СКУД (id=23).
"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB = Path("smety.db")


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM products")
    prod_before = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM prices")
    price_before = cur.fetchone()[0]

    print(f"До: products={prod_before}, prices={price_before}")

    cur.execute("""
        SELECT id, name, price, sum, note, source
        FROM estimate_items WHERE estimate_id = 23
    """)
    items = cur.fetchall()
    print(f"Позиций: {len(items)}")

    added_prod = 0
    added_price = 0
    linked = 0
    now = datetime.now().isoformat()

    for item in items:
        item_id, name, price, summ, note, source = item

        if not name or name.strip() == "":
            continue

        name = name.strip()

        cur.execute("SELECT id FROM products WHERE LOWER(name) = LOWER(?)", (name,))
        row = cur.fetchone()

        if row:
            prod_id = row[0]
        else:
            unit = ""
            if note:
                for u in ["шт.", "м.", "м²", "компл", "уп.", "кг"]:
                    if u in note:
                        unit = u
                        break

            cur.execute("""
                INSERT INTO products (name, unit, category, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (name, unit, "", now, now))
            prod_id = cur.lastrowid
            added_prod += 1

        cur.execute("UPDATE estimate_items SET product_id = ? WHERE id = ?", (prod_id, item_id))
        linked += 1

        if price and float(price) > 0:
            cur.execute("SELECT id FROM prices WHERE product_id = ? AND price = ?",
                        (prod_id, float(price)))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO prices (product_id, price, source, region, parsed_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (prod_id, float(price), source or "Ручная", "msk", now))
                added_price += 1

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM products")
    prod_after = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM prices")
    price_after = cur.fetchone()[0]

    print(f"\n=== ИТОГО ===")
    print(f"products: {prod_before} → {prod_after} (+{added_prod})")
    print(f"prices:   {price_before} → {price_after} (+{added_price})")
    print(f"Связано: {linked}")

    conn.close()


if __name__ == "__main__":
    main()