"""
sources/volt220.py v1
Парсер 220-volt.ru через JSON-LD + Schema.org.
Аура, 2026-09-24.
"""
import os
import re
import json
import time
import logging
from urllib.parse import quote_plus

from curl_cffi import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# Регион → поддомен 220-volt
VOLT_CITY = {
    "msk": "www",
    "spb": "spb",
    "nsk": "nsk",
    "vvo": "vlad",
    "ekb": "ekb",
    "kzn": "kzn",
    "krd": "krd",
    "nn": "nn",
    "sam": "sam",
    "chel": "chel",
    "perm": "perm",
    "ufa": "ufa",
    "vor": "vor",
    "kras": "kras",
}

HEADERS = {"Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"}
PAUSE = 0.5

PROXY_URL = os.getenv("ETM_PROXY_URL", "").strip()
PROXY_SECRET = os.getenv("ETM_PROXY_SECRET", "").strip()


def _base(region="msk"):
    sub = VOLT_CITY.get(region, "www")
    return f"https://{sub}.220-volt.ru"


def _get(url):
    """GET через прокси или напрямую."""
    if PROXY_URL and PROXY_SECRET:
        try:
            r = requests.post(
                PROXY_URL.rstrip("/") + "/fetch",
                json={"url": url, "secret": PROXY_SECRET},
                timeout=35,
            )
            if r.status_code == 200:
                data = r.json()

                class _MockResp:
                    def __init__(self, code, text, url):
                        self.status_code = code
                        self.text = text
                        self.url = url

                return _MockResp(
                    data.get("status", 500),
                    data.get("html", ""),
                    data.get("url", url),
                )
            else:
                log.warning("Proxy http %s", r.status_code)
                return None
        except Exception as e:
            log.warning("Proxy error: %s", e)
            return None
    else:
        try:
            return requests.get(url, impersonate="chrome124", timeout=25, headers=HEADERS)
        except Exception as e:
            log.warning("GET error: %s", e)
            return None


def _extract_json_ld(soup, expected_type):
    """Извлекает JSON-LD нужного типа."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
        except Exception:
            continue
        if data.get("@type") == expected_type:
            return data
        if isinstance(data, list):
            for item in data:
                if item.get("@type") == expected_type:
                    return item
    return None


def search(query, limit=8, region="msk"):
    """Поиск на 220-volt."""
    base = _base(region)
    url = f"{base}/catalog/?q={quote_plus(query)}"
    r = _get(url)
    if not r or r.status_code != 200:
        log.warning("220V search http %s", r.status_code if r else 0)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    results = []

    # Ищем ссылки на товары
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/catalog/" in href and href.endswith(".html"):
            full_url = href if href.startswith("http") else base + href
            if full_url not in [x["url"] for x in results]:
                results.append({
                    "name": a.get_text(strip=True)[:200],
                    "url": full_url,
                })
        if len(results) >= limit:
            break

    return results


def get_product(url):
    """Парсит цену товара."""
    r = _get(url)
    if not r or r.status_code != 200:
        return {"error": f"http {r.status_code if r else 0}"}

    soup = BeautifulSoup(r.text, "html.parser")
    product = _extract_json_ld(soup, "Product")

    name = ""
    sku = mpn = brand = None
    price = None

    if product:
        name = product.get("name", "")
        sku = product.get("sku")
        mpn = product.get("mpn")
        b = product.get("brand")
        brand = b.get("name") if isinstance(b, dict) else None

        offers = product.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        p = offers.get("price")
        if p:
            try:
                price = float(p)
            except (ValueError, TypeError):
                price = None

    return {
        "name": name,
        "sku": sku,
        "mpn": mpn,
        "brand": brand,
        "price": price,
        "url": url,
    }


def _key_in_name(key, text):
    """Проверяет, что ключ входит в текст."""
    if not key or not text:
        return False

    def norm(s):
        return re.sub(r"[\s,\.\(\)\-\_]", "", s.lower().replace("x", "х"))

    kn, nn = norm(key), norm(text)
    if len(kn) < 3:
        return False
    return kn in nn


def _key_matches_product(key, product):
    if not key:
        return False
    for f in (product.get("name"), product.get("mpn"),
              product.get("sku"), product.get("brand")):
        if f and _key_in_name(key, str(f)):
            return True
    return False


def find_best(query, keywords=None, expected_brand=None, min_price=100, region="msk"):
    """
    Ищет лучший результат:
    - 1 кандидат → он
    - 2 → дороже
    - 3+ → медиана
    """
    queries_to_try = []
    if query and len(query.strip()) >= 8:
        queries_to_try.append(query)
    if keywords:
        sorted_kw = sorted([k for k in keywords if k and len(k) >= 4],
                           key=lambda x: (not x[0].isupper(), -len(x)))
        for k in sorted_kw:
            if k not in queries_to_try:
                queries_to_try.append(k)
    if not queries_to_try and query:
        queries_to_try.append(query)

    if not queries_to_try:
        return {"found": False, "reason": "no queries"}

    log.info("220V: region=%s, brand=%r, min_price=%s, queries=%s",
             region, expected_brand, min_price, queries_to_try[:2])

    for q in queries_to_try:
        results = search(q, limit=8, region=region)
        if not results:
            continue

        candidates = []
        for r in results:
            time.sleep(PAUSE)
            product = get_product(r["url"])
            if not product.get("price"):
                continue
            if keywords:
                if not any(_key_matches_product(k, product) for k in keywords):
                    continue
            candidates.append(product)

        if not candidates:
            continue

        filtered = [c for c in candidates if c["price"] >= min_price]
        if filtered:
            candidates = filtered

        candidates.sort(key=lambda x: x["price"])

        if len(candidates) == 1:
            chosen = candidates[0]
        elif len(candidates) == 2:
            chosen = candidates[-1]
        else:
            chosen = candidates[len(candidates) // 2]

        chosen["found"] = True
        chosen["source"] = "220V"
        chosen["region_used"] = region
        chosen["coef"] = 1.00
        chosen["note"] = "220-volt"
        chosen["candidates_count"] = len(candidates)
        log.info("220V: выбрано: %s | %s ₽ | кандидатов: %d",
                 chosen.get("name", "")[:50], chosen["price"], len(candidates))
        return chosen

    return {"found": False, "reason": "no match"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    print("Тест: ППГнг 1х120")
    r = find_best("ППГнг(А)-HF 1х120(ок)", keywords=["ППГнг(А)-HF 1х120"], region="msk")
    print(r)