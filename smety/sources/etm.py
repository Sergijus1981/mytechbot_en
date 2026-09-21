"""
sources/etm.py
Парсер ЭТМ (etm.ru) через curl_cffi + Schema.org.
Цена берётся из HTML — ГЛАВНАЯ цена товара.
Поддержка прокси через Cloudflare Tunnel.
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

BASE = "https://www.etm.ru"
SEARCH_URL = BASE + "/catalog?searchValue={q}"

HEADERS = {"Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"}
PAUSE = 0.3

PROXY_URL = os.getenv("ETM_PROXY_URL", "").strip()
PROXY_SECRET = os.getenv("ETM_PROXY_SECRET", "").strip()


def _get(url):
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
        return requests.get(url, impersonate="chrome124", timeout=25, headers=HEADERS)


def _extract_json_ld(soup, expected_type):
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


def _extract_price_per_unit(html):
    if not html:
        return None, None

    pattern = re.compile(
        r'data-testid="catalog-list-item-price-details-\d+-\d+-\d+"[^>]*>'
        r'\s*([\d\s]+[,.]\d+)\s*'
        r'.{0,400}?'
        r'data-testid="catalog-list-item-price-details-\d+-\d+-\d+-unit"[^>]*>'
        r'\s*₽\s*/\s*(\w+)',
        re.DOTALL
    )
    m = pattern.search(html)
    if m:
        raw = m.group(1).replace(" ", "").replace("\xa0", "").replace(",", ".")
        try:
            price = float(raw)
            if 0 < price < 100_000_000:
                return price, m.group(2).lower()
        except ValueError:
            pass

    pattern2 = re.compile(
        r'class="[^"]*priceItem-priceColor[^"]*"[^>]*>\s*([\d\s]+[,.]\d+)\s*'
        r'.{0,300}?₽\s*/\s*(\w+)',
        re.DOTALL
    )
    m2 = pattern2.search(html)
    if m2:
        raw = m2.group(1).replace(" ", "").replace("\xa0", "").replace(",", ".")
        try:
            price = float(raw)
            if 0 < price < 100_000_000:
                return price, m2.group(2).lower()
        except ValueError:
            pass

    pattern3 = re.compile(
        r"(\d[\d\s]*[,.]\d{1,2}|\d+)\s*₽\s*/\s*(м|шт|уп|кг|м2|м²|компл|м\.п\.)",
        re.IGNORECASE
    )
    candidates = []
    for raw, unit in pattern3.findall(html):
        raw_c = raw.replace(" ", "").replace("\xa0", "").replace(",", ".")
        try:
            p = float(raw_c)
        except ValueError:
            continue
        if 0 < p < 100_000_000:
            candidates.append((p, unit.lower()))
    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0]

    return None, None


def search(query, limit=8):
    url = SEARCH_URL.format(q=quote_plus(query))
    try:
        r = _get(url)
    except Exception as e:
        log.warning("ETM search error: %s", e)
        return []
    if not r or r.status_code != 200:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    itemlist = _extract_json_ld(soup, "ItemList")
    if not itemlist:
        return []

    results = []
    for item in itemlist.get("itemListElement", [])[:limit]:
        url_item = item.get("url") or ""
        code_match = re.search(r"/cat/nn/(\d+)", url_item)
        results.append({
            "name": item.get("name", ""),
            "url": url_item,
            "code": code_match.group(1) if code_match else None,
        })
    return results


def get_product(url):
    try:
        r = _get(url)
    except Exception as e:
        return {"error": str(e)}
    if not r or r.status_code != 200:
        return {"error": "http %s" % (r.status_code if r else 0)}

    html = r.text
    soup = BeautifulSoup(html, "html.parser")
    product = _extract_json_ld(soup, "Product")

    name = ""
    sku = mpn = brand = None
    if product:
        name = product.get("name", "")
        sku = product.get("sku")
        mpn = product.get("mpn")
        b = product.get("brand")
        brand = b.get("name") if isinstance(b, dict) else None

    if "товар не поставляется" in html.lower():
        return {"error": "not available"}

    price, unit = _extract_price_per_unit(html)
    if price is None and product:
        offers = product.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        p = offers.get("price")
        if p:
            price = float(p)
            unit = None

    return {
        "name": name, "sku": sku, "mpn": mpn, "brand": brand,
        "price": price, "price_unit": unit, "url": url,
    }


def _key_in_name(key, text):
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


_BRAND_CANON = {"дкс": "dkc", "иэк": "iek", "екф": "ekf", "квт": "kvt"}


def _brand_matches(expected_brand, product_brand):
    if not expected_brand or not product_brand:
        return True

    def norm(s):
        return re.sub(r"[\s\-_\.\(\)\"']", "", str(s).lower())

    e = norm(expected_brand)
    p = norm(product_brand)
    e = _BRAND_CANON.get(e, e)
    p = _BRAND_CANON.get(p, p)
    return e in p or p in e


def find_best(query, keywords=None, expected_brand=None):
    queries_to_try = []
    if keywords:
        sorted_kw = sorted([k for k in keywords if k and len(k) >= 3],
                           key=len, reverse=True)
        queries_to_try.extend(sorted_kw)
    if query and query not in queries_to_try:
        queries_to_try.append(query)

    if not queries_to_try:
        return {"found": False, "reason": "no queries"}

    log.info("ETM: brand=%r, queries=%s", expected_brand, queries_to_try[:2])
    if PROXY_URL:
        log.info("ETM: using proxy %s", PROXY_URL)

    for q in queries_to_try:
        results = search(q, limit=8)
        if not results:
            continue

        if keywords:
            kw_lower = [k.lower() for k in keywords if k and len(k) >= 3]
            filtered = [r for r in results
                        if any(k in r["name"].lower() for k in kw_lower)]
            if filtered:
                results = filtered

        for r in results:
            time.sleep(PAUSE)
            product = get_product(r["url"])
            if not product.get("price"):
                continue

            if expected_brand and not _brand_matches(expected_brand, product.get("brand")):
                continue

            if keywords:
                if not any(_key_matches_product(k, product) for k in keywords):
                    continue

            product["found"] = True
            product["search_query"] = q
            return product

    return {"found": False, "reason": "no match"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("--- Тест 1: держатель (ДКС) ---")
    print(find_best("держатель оцинкованный 25мм", keywords=["53334"], expected_brand="ДКС"))

    print("\n--- Тест 2: хомут 27616 (ДКС) ---")
    print(find_best("хомут нерж 8х600", keywords=["27616"], expected_brand="ДКС"))

    print("\n--- Тест 3: кабель 1х120 ---")
    print(find_best("ППГнг(А)-HF 1х120", keywords=["ППГнг(А)-HF 1х120"]))