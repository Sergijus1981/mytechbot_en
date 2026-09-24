"""
parse_prices.py v1
Парсер прайсов электромонтажных работ.
Собирает цены с сайтов → сохраняет в SQLite.
"""
import re
import sqlite3
import logging
from pathlib import Path

try:
    from curl_cffi import requests
except ImportError:
    import requests

from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("parse_prices")

DB_PATH = Path("prices_works.db")


# ============================================================
# БАЗА ДАННЫХ
# ============================================================

def init_db():
    """Создаёт таблицу для цен."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            region TEXT NOT NULL,
            work_name TEXT NOT NULL,
            work_key TEXT NOT NULL,
            price REAL NOT NULL,
            unit TEXT,
            parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_work_key ON prices(work_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_region ON prices(region)")
    conn.commit()
    conn.close()
    log.info("База готова: %s", DB_PATH)


def save_prices(source, region, prices):
    """Сохраняет список (name, price, unit) в базу."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Удаляем старые записи этого источника (защита от дублей)
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
    log.info("Сохранено: %d цен (%s, %s)", saved, source, region)


def normalize_key(name):
    """Нормализует название → ключ для матчинга."""
    n = str(name).lower()
    n = re.sub(r"[\s\-_\.\(\)\"']", "", n)
    n = re.sub(r"[,;:]", "", n)
    return n


# ============================================================
# ПАРСИНГ
# ============================================================

def fetch_html_playwright(url, timeout=45000):
    """Скачивает HTML через реальный браузер (Playwright)."""
    if not HAS_PLAYWRIGHT:
        log.warning("Playwright не установлен")
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 768},
                locale="ru-RU",
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        log.error("Playwright error: %s", e)
        return None


def fetch_html(url):
    """Скачивает HTML."""
    try:
        r = requests.get(url, impersonate="chrome124", timeout=30,
                         headers={"Accept-Language": "ru-RU,ru;q=0.9"})
        if r.status_code == 200:
            return r.text
        log.warning("HTTP %s: %s", r.status_code, url)
        return None
    except Exception as e:
        log.error("Fetch error: %s", e)
        return None


def parse_price_table(html, source_name):
    """
    Универсальный парсер прайс-таблиц.
    Ищет таблицы, в которых есть 'Наименование' и 'Цена'.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 5:
            continue

        # Проверяем заголовок
        header_text = " ".join(th.get_text() for th in rows[0].find_all(["th", "td"])).lower()
        if not (("наимен" in header_text or "работ" in header_text) and
                ("цена" in header_text or "стоим" in header_text)):
            continue

        log.info("  Найдена таблица: %d строк", len(rows))

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            name = cells[0].get_text(strip=True)
            price_text = cells[-1].get_text(strip=True)

            # Парсим цену
            price = extract_price(price_text)
            if not price:
                continue

            unit = extract_unit(name)
            results.append((name, price, unit))

    return results


def parse_10kvt(html):
    """Спец-парсер для 10kvt.ru (битый HTML)."""
    if not html:
        return []
    import html as html_mod
    results = []
    pattern = re.compile(
        r"<tr>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*>([^<]+)</td>\s*</tr>",
        re.IGNORECASE
    )
    for match in pattern.finditer(html):
        name = html_mod.unescape(match.group(1)).strip()
        price_text = html_mod.unescape(match.group(2)).strip()
        if not name or name.lower() in ("наименование", "цена"):
            continue
        if "руб" not in price_text.lower():
            continue
        price = extract_price(price_text)
        if not price:
            continue
        unit = extract_unit(name)
        results.append((name, price, unit))
    return results


def parse_text_rows(html):
    """Парсит текст в ячейках: 'Название 300 ₽'."""
    if not html:
        return []
    from bs4 import BeautifulSoup
    import html as html_mod

    soup = BeautifulSoup(html, "html.parser")
    results = []

    for cell in soup.find_all(["td", "th"]):
        text = cell.get_text(" ", strip=True)
        if not text or len(text) < 5:
            continue
        if "наимен" in text.lower() or text.lower() == "цена":
            continue
        m = re.search(r"^(.*?)\s+(?:от\s+)?(\d[\d\s\xa0]*)(?:\s*[–\-]\s*(\d[\d\s\xa0]*))?\s*(?:₽|руб)", text)
        if not m:
            continue
        name = m.group(1).strip(" .,:;-—")
        price_str = m.group(2)
        price = extract_price(price_str)
        if not name or not price or len(name) < 4:
            continue
        unit = extract_unit(name)
        results.append((name, price, unit))

    return results


def parse_table_pairs(html):
    """Парсит таблицы с парами <th>Название</th><td>Цена</td>."""
    if not html:
        return []
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results = []

    for table in soup.find_all("table", class_="price-table"):
        for row in table.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            name = th.get_text(" ", strip=True)
            price_text = td.get_text(" ", strip=True)
            if not name or not price_text:
                continue
            price = extract_price(price_text)
            if not price:
                continue
            unit = extract_unit(name)
            results.append((name, price, unit))

    return results


def parse_div_table(html):
    """Парсит таблицы в виде div.subcategory-table-item."""
    if not html:
        return []
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results = []

    for item in soup.find_all("div", class_="subcategory-table-item"):
        name_el = item.find("div", class_="subcategory-table-name")
        unit_el = item.find("div", class_="subcategory-table-unit")
        price_el = item.find("div", class_="subcategory-table-price")
        if not name_el or not price_el:
            continue
        name = name_el.get_text(" ", strip=True)
        price_text = price_el.get_text(" ", strip=True)
        unit = unit_el.get_text(" ", strip=True) if unit_el else "шт"
        if not name:
            continue
        price = extract_price(price_text)
        if not price:
            continue
        # Нормализуем единицу
        u = unit.lower().strip(".")
        if u in ("шт",):
            unit = "шт"
        elif u in ("м", "м.п", "пог.м", "м/п"):
            unit = "м"
        elif u in ("м2", "кв.м", "м²"):
            unit = "м²"
        results.append((name, price, unit))

    return results


def extract_price(text):
    """Извлекает число из строки 'от 3 000 руб.' или '400 руб./шт'"""
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
    """Определяет единицу измерения по названию."""
    n = name.lower()
    if any(w in n for w in ["/м", "м.п", "пог.м", "метр"]):
        return "м"
    if any(w in n for w in ["/м2", "м2", "м²", "кв.м"]):
        return "м²"
    if any(w in n for w in ["/м3", "м3", "м³"]):
        return "м³"
    if any(w in n for w in ["/шт", "шт.", "штук"]):
        return "шт"
    if any(w in n for w in ["/компл", "компл"]):
        return "компл"
    return "шт"  # по умолчанию


# ============================================================
# ИСТОЧНИКИ
# ============================================================

SOURCES = [
    # === Москва (открытые) ===
    ("https://remont-aktiv.ru/uslugi/elektromontazhnye-raboty", "remont_aktiv", "msk"),
    # === Казань ===
    ("https://mastera-plus.ru/kazan/price/prais-na-uslugi-elektrika", "mastera_plus_kzn", "kzn"),
    # === Новосибирск ===
    ("https://maximlihachev.ru/uslugi/elektrika.html", "lihachev_nsk", "nsk"),
    # === Н. Новгород ===
    ("https://elektrik52.ru/prajs-list-elektrika/", "elektrik52_nn", "nn"),
    # === СПб ===
    ("https://10kvt.ru/print-all-price.php", "10kvt", "spb"),
    # === Владивосток ===
    ("https://vladivostok.masterabyta.ru/prajs-list-na-elektromontazhnye-raboty", "masterabyta_vvo", "vvo"),
]


def main():
    init_db()

    for url, source, region in SOURCES:
        log.info("=== %s (%s) ===", source, region)
        html = fetch_html(url)
        if not html or len(html) < 2000:
            log.info("  Пробую через Playwright...")
            html = fetch_html_playwright(url)
        if not html:
            log.warning("  Пропуск: HTML не получен")
            continue

        if source == "10kvt":
            prices = parse_10kvt(html)
        elif source == "elektrik52_nn":
            prices = parse_table_pairs(html)
        elif source == "mastera_plus_kzn":
            prices = parse_div_table(html)
        else:
            prices = parse_price_table(html, source)
        if not prices:
            log.warning("  Цены не найдены (капча? JS?)")
            continue

        save_prices(source, region, prices)


if __name__ == "__main__":
    main()