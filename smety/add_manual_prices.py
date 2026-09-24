"""
add_manual_prices.py
Ручная заливка цен в prices_works.db.
Использование:
  python add_manual_prices.py <файл.txt> <source> <region>
  
Или:
  python add_manual_prices.py prices_input.txt dom_electric msk
"""
import sys
import re
import sqlite3
import io
from pathlib import Path

DB_PATH = Path("prices_works.db")


def normalize_key(name):
    n = str(name).lower()
    n = re.sub(r"[\s\-_\.\(\)\"']", "", n)
    n = re.sub(r"[,;:]", "", n)
    return n


def extract_price(text):
    if not text:
        return None
    m = re.search(r"(\d[\d\s\xa0]*)(?:[,.](\d{1,2}))?", text)
    if not m:
        return None
    int_part = m.group(1).replace(" ", "").replace("\xa0", "")
    dec_part = m.group(2) or "0"
    try:
        p = float(int_part + "." + dec_part)
        if 0 < p < 10_000_000:
            return p
    except ValueError:
        pass
    return None


def extract_unit(name):
    n = name.lower()
    if any(w in n for w in ["/м", "м.п", "пог.м", "метр"]):
        return "м"
    if any(w in n for w in ["м2", "м²", "кв.м"]):
        return "м²"
    if any(w in n for w in ["м3", "м³"]):
        return "м³"
    if any(w in n for w in ["/компл", "компл"]):
        return "компл"
    return "шт"


def parse_text(text):
    """
    Парсит текст прайса. Возвращает [(название, цена, ед.)].
    Поддерживает форматы:
      Название 300 руб.
      Название — 300 ₽
      Название | 300 | шт
      Название 300
    """
    results = []
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line or len(line) < 5:
            continue
        # Пропускаем заголовки
        if any(w in line.lower() for w in ["наименование", "цена", "стоимость", "ед. изм"]):
            continue

        # Формат с разделителем "|"
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                name = parts[0]
                price = extract_price(parts[1])
                unit = parts[2] if len(parts) >= 3 else extract_unit(name)
                if name and price:
                    results.append((name, price, unit))
                continue

        # Ищем число в конце строки (перед руб/₽ или без)
        # Убираем "руб.", "₽", "р."
        clean = re.sub(r"(руб\.?|₽|р\.)", "", line, flags=re.IGNORECASE).strip()
        # Ищем последнее число
        m = re.search(r"^(.*?)[\s\-—–:]*(\d[\d\s\xa0]*(?:[,.]\d{1,2})?)\s*(?:шт|м|компл|м2)?\s*$", clean)
        if not m:
            continue
        name = m.group(1).strip(" -—–:")
        price_text = m.group(2)
        price = extract_price(price_text)
        if name and price and len(name) > 3:
            unit = extract_unit(name)
            results.append((name, price, unit))

    return results


def save_prices(source, region, prices):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Удаляем старые записи этого источника
    cur.execute("DELETE FROM prices WHERE source = ? AND region = ?", (source, region))
    saved = 0
    for name, price, unit in prices:
        if not name or not price:
            continue
        key = normalize_key(name)
        cur.execute("""
            INSERT INTO prices (source, region, work_name, work_key, price, unit)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (source, region, name, key, price, unit))
        saved += 1
    conn.commit()
    conn.close()
    return saved


def main():
    if len(sys.argv) < 4:
        print("Использование: python add_manual_prices.py <файл.txt> <source> <region>")
        print("Пример: python add_manual_prices.py dom_electric.txt dom_electric msk")
        return

    file_path = sys.argv[1]
    source = sys.argv[2]
    region = sys.argv[3]

    if not Path(file_path).exists():
        print(f"Файл не найден: {file_path}")
        return

    text = io.open(file_path, encoding="utf-8").read()
    prices = parse_text(text)
    print(f"Распарсено: {len(prices)} цен")

    if not prices:
        print("Ничего не найдено. Проверь формат.")
        return

    saved = save_prices(source, region, prices)
    print(f"Сохранено: {saved} цен ({source}, {region})")

    # Показываем первые 5
    print("\nПервые 5:")
    for name, price, unit in prices[:5]:
        print(f"  {name} — {price} ₽/{unit}")


if __name__ == "__main__":
    main()