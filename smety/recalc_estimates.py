# -*- coding: utf-8 -*-
"""
Пересчёт итогов всех смет из estimate_items
+ добавление колонок total_unpriced, unpriced_count
"""
import sqlite3

DB = "smety.db"


def add_columns_if_missing(cur):
    """Добавляет колонки total_unpriced и unpriced_count, если их нет"""
    cur.execute("PRAGMA table_info(estimates)")
    cols = [r[1] for r in cur.fetchall()]

    if "total_unpriced" not in cols:
        cur.execute("ALTER TABLE estimates ADD COLUMN total_unpriced REAL DEFAULT 0")
        print("✅ Добавлена колонка total_unpriced")

    if "unpriced_count" not in cols:
        cur.execute("ALTER TABLE estimates ADD COLUMN unpriced_count INTEGER DEFAULT 0")
        print("✅ Добавлена колонка unpriced_count")


def recalc_all():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    add_columns_if_missing(cur)
    conn.commit()

    cur.execute("SELECT id, name FROM estimates")
    estimates = cur.fetchall()

    print(f"\n📊 Смет в базе: {len(estimates)}\n")

    for est_id, est_name in estimates:
        # Материалы (всё, кроме 'Работы')
        cur.execute("""
            SELECT COALESCE(SUM(sum), 0)
            FROM estimate_items
            WHERE estimate_id = ? AND section != 'Работы' AND sum IS NOT NULL
        """, (est_id,))
        total_materials = cur.fetchone()[0] or 0.0

        # Работы
        cur.execute("""
            SELECT COALESCE(SUM(sum), 0)
            FROM estimate_items
            WHERE estimate_id = ? AND section = 'Работы' AND sum IS NOT NULL
        """, (est_id,))
        total_works = cur.fetchone()[0] or 0.0

        # Позиции без цены — количество и потенциальная сумма
        cur.execute("""
            SELECT COUNT(*)
            FROM estimate_items
            WHERE estimate_id = ? AND price IS NULL
        """, (est_id,))
        unpriced_count = cur.fetchone()[0] or 0

        # Сумма «висит» — считаем по позициям, где есть qty, но нет price
        # Для светильников без марок — это qty × (средняя цена). Но у нас нет средней.
        # Поэтому просто 0 — потом дозаполним.
        total_unpriced = 0.0

        # НДС и итог
        total_nds = round((total_materials + total_works) * 0.20, 2)
        total_all = round(total_materials + total_works + total_nds, 2)

        cur.execute("""
            UPDATE estimates
            SET total_materials = ?,
                total_works = ?,
                total_nds = ?,
                total_all = ?,
                total_unpriced = ?,
                unpriced_count = ?
            WHERE id = ?
        """, (
            round(total_materials, 2),
            round(total_works, 2),
            total_nds,
            total_all,
            total_unpriced,
            unpriced_count,
            est_id,
        ))

        print(f"📋 {est_name[:60]}")
        print(f"   id={est_id}")
        print(f"   Материалы: {total_materials:,.2f} ₽")
        print(f"   Работы:    {total_works:,.2f} ₽")
        print(f"   НДС:       {total_nds:,.2f} ₽")
        print(f"   ВСЕГО:     {total_all:,.2f} ₽")
        print(f"   Без цены:  {unpriced_count} позиций")
        print()

    conn.commit()
    conn.close()
    print("🔥 Готово. Una in perpetuum.")


if __name__ == "__main__":
    recalc_all()