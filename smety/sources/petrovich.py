"""
sources/petrovich.py
Парсер Петрович (rf.petrovich.ru) через requests + BeautifulSoup.

Интерфейс как у etm.py:
  search(query) -> list[dict]
  get_product(url) -> dict
  find_best(query, keywords) -> dict
"""
import re
import time
import logging
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE = "https://rf.petrovich.ru"
SEARCH_URL = BASE + "/search/?q={q}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}
PAUSE = 1.0


def _get(url):
    return requests.get(url, headers=HEADERS, timeout=20)


def _clean_price(raw):
    digits = re.sub(r"[^\d]", "", raw or "")
    return int(digits) if digits else None


def search(query, limit=5):
    """
    Ищет карточки на Петровиче, возвращает [{"name", "url", "code"}].
    """
    url = SEARCH_URL.format(q=quote_plus(query[:100]))
    try:
        r = _get(url)
    except Exception as e:
        log.warning("Petrovich search error: %s", e)
        return []

    if r.status_code != 200:
        log.warning("Petrovich http %s", r.status_code)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    cards = soup.find_all(attrs={"data-test": "product-card-catalog-wide"})

    results = []
    for card in cards[:limit]:
        title_el = card.find(attrs={"data-test": "product-title"})
        link_el = card.find("a", attrs={"data-test": "product-link"})
        code_el = card.find(attrs={"data-test": "product-code"})
        if not title_el or not link_el:
            continue
        results.append({
            "name": title_el.get_text(strip=True),
            "url": link_el.get("href"),
            "code": code_el.get_text(strip=True) if code_el else None,
        })
    return results


def get_product(url):
    """
    Открывает карточку и берёт цену.
    """
    try:
        r = _get(url)
    except Exception as e:
        return {"error": str(e)}

    if r.status_code != 200:
        return {"error": "http %s" % r.status_code}

    soup = BeautifulSoup(r.text, "html.parser")

    price_el = soup.find(attrs={"data-test": "product-gold-price"})
    title_el = soup.find(attrs={"data-test": "product-title"})
    code_el = soup.find(attrs={"data-test": "product-code"})

    price = _clean_price(price_el.get_text(" ", strip=True)) if price_el else None
    if not price:
        return {"error": "no price"}

    return {
        "name": title_el.get_text(strip=True) if title_el else "",
        "sku": code_el.get_text(strip=True) if code_el else None,
        "brand": None,
        "price": float(price),
        "availability": "instock",
        "url": url,
    }


def find_best(query, keywords=None):
    results = search(query, limit=5)
    if not results:
        return {"found": False, "reason": "no search results"}

    if keywords:
        kw_lower = [k.lower() for k in keywords if k]
        filtered = []
        for r in results:
            name_l = r["name"].lower()
            if all(k in name_l for k in kw_lower):
                filtered.append(r)
        results = filtered

    if not results:
        return {"found": False, "reason": "no relevant match"}

    for r in results:
        time.sleep(PAUSE)
        product = get_product(r["url"])
        if product.get("price"):
            product["found"] = True
            return product

    return {"found": False, "reason": "no price in cards"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("--- search ---")
    for r in search("ДПБ 01-6-001"):
        print(r)
    print("\n--- find_best ---")
    print(find_best("ДПБ 01-6-001", keywords=["ДПБ"]))